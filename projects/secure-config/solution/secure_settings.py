"""Typed, validated settings from environment variables, with secrets that never reach the logs.

* ``AppSettings`` (pydantic-settings) reads ``APP_*`` variables, converts and validates them.
* ``load_settings()`` fails fast at startup with a message that names every bad variable but never
  repeats a value.
* ``describe()`` gives a masked view of the configuration that is safe to log or print.
* ``RedactingFilter`` / ``configure_logging()`` scrub secret values and ``password=...``-style pairs
  from every log record, including tracebacks.

Check your configuration from the command line::

    python solution/secure_settings.py        # prints the masked settings, or the problems (exit 2)
"""

import json
import logging
import os
import re
import sys
from collections.abc import Iterable, Mapping
from enum import Enum, StrEnum
from pathlib import Path
from typing import Self, TextIO
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    Field,
    HttpUrl,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

ENV_PREFIX = "APP_"
DEFAULT_ENV_FILE = ".env"
MASK = "**********"
PLACEHOLDER_MARKER = "change-me"
DATABASE_SCHEMES = ("postgresql", "postgresql+psycopg", "sqlite")
SECRET_MIN_LENGTHS = {"api_key": 16, "secret_key": 32}


class Environment(StrEnum):
    """Where the app runs. Production turns on extra safety rules."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Standard ``logging`` level names."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def env_var_name(field_name: str) -> str:
    """The environment variable for a settings field: ``api_key`` -> ``APP_API_KEY``."""
    return f"{ENV_PREFIX}{field_name.upper()}"


# ---------------------------------------------------------------------------
# Milestone 1: typed settings with validation
# ---------------------------------------------------------------------------


class AppSettings(BaseSettings):
    """All configuration for the app. Field ``x`` is read from the variable ``APP_X``."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = LogLevel.INFO
    public_base_url: HttpUrl = Field(default=HttpUrl("http://localhost:8000"))
    request_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    # Required secrets: no defaults, so a missing value stops the app at startup.
    database_url: SecretStr
    api_key: SecretStr
    secret_key: SecretStr

    @field_validator("environment", mode="before")
    @classmethod
    def _lowercase_environment(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase_log_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: SecretStr) -> SecretStr:
        """Accept only known schemes; never include the value in the error message."""
        parts = urlsplit(value.get_secret_value())
        if parts.scheme not in DATABASE_SCHEMES:
            raise ValueError(f"must start with one of: {', '.join(s + '://' for s in DATABASE_SCHEMES)}")
        if parts.scheme != "sqlite" and not parts.hostname:
            raise ValueError("must include a host name")
        return value

    @field_validator("api_key", "secret_key")
    @classmethod
    def _check_secret_length(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        minimum = SECRET_MIN_LENGTHS[str(info.field_name)]
        if len(value.get_secret_value()) < minimum:
            raise ValueError(f"must be at least {minimum} characters")
        return value

    @model_validator(mode="after")
    def _production_rules(self) -> Self:
        """Rules that only apply in production: they catch "it worked on my laptop" configurations."""
        if self.environment is not Environment.PRODUCTION:
            return self
        problems = []
        if self.debug:
            problems.append(f"{env_var_name('debug')} must be false in production")
        if self.public_base_url.scheme != "https":
            problems.append(f"{env_var_name('public_base_url')} must use https in production")
        for name in secret_field_names():
            if PLACEHOLDER_MARKER in getattr(self, name).get_secret_value():
                problems.append(f"{env_var_name(name)} still has the placeholder value from .env.example")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def secret_field_names() -> list[str]:
    """Names of every ``SecretStr`` field of ``AppSettings``."""
    return [name for name, info in AppSettings.model_fields.items() if info.annotation is SecretStr]


# ---------------------------------------------------------------------------
# Milestone 2: fail fast, with safe error messages
# ---------------------------------------------------------------------------


class ConfigError(RuntimeError):
    """The configuration is invalid. The message lists problems by variable name and never contains values."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = list(problems)
        super().__init__("invalid configuration:\n" + "\n".join(f"  - {p}" for p in self.problems))


def describe_validation_error(exc: ValidationError) -> list[str]:
    """Turn pydantic's errors into one line per problem, using env var names and no input values."""
    problems = []
    for error in exc.errors(include_input=False, include_url=False, include_context=False):
        message = error["msg"].removeprefix("Value error, ")
        if not error["loc"]:
            problems.append(message)
        elif error["type"] == "missing":
            problems.append(f"{env_var_name(str(error['loc'][0]))} is required but not set")
        else:
            problems.append(f"{env_var_name(str(error['loc'][0]))}: {message}")
    return problems


def unknown_app_variables(environ: Mapping[str, str] | None = None) -> list[str]:
    """``APP_*`` variables that match no setting -- usually typos such as ``APP_PROT``."""
    env = os.environ if environ is None else environ
    known = {env_var_name(name) for name in AppSettings.model_fields}
    return sorted(k for k in env if k.upper().startswith(ENV_PREFIX) and k.upper() not in known)


def load_settings(env_file: str | Path | None = DEFAULT_ENV_FILE) -> AppSettings:
    """Load and validate settings from the environment (and ``env_file`` if it exists; None = no file).

    Real environment variables win over the file. Raises ``ConfigError`` listing every problem.
    """
    for name in unknown_app_variables():
        logger.warning("ignoring unknown setting %s (typo?)", name)
    try:
        return AppSettings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = describe_validation_error(exc)
    # Raised outside the except block on purpose: no __context__ chain back to pydantic's error,
    # whose text can include the raw input values.
    raise ConfigError(problems)


# ---------------------------------------------------------------------------
# Milestone 3: a masked description that is safe to print
# ---------------------------------------------------------------------------


def mask_url(url: str) -> str:
    """Hide the password in a URL: ``postgresql://app:pw@db/app`` -> ``postgresql://app:**********@db/app``."""
    parts = urlsplit(url)
    userinfo, at, hostport = parts.netloc.rpartition("@")
    if not at or ":" not in userinfo:
        return url
    username = userinfo.split(":", 1)[0]
    return urlunsplit(parts._replace(netloc=f"{username}:{MASK}@{hostport}"))


def describe(settings: AppSettings) -> dict[str, str | int | float | bool]:
    """Every setting as JSON-safe values with secrets masked. Safe to log at startup."""
    result: dict[str, str | int | float | bool] = {}
    for name in type(settings).model_fields:
        value = getattr(settings, name)
        if name == "database_url":
            result[name] = mask_url(value.get_secret_value())
        elif isinstance(value, SecretStr):
            result[name] = MASK
        elif isinstance(value, Enum):
            result[name] = value.value
        elif isinstance(value, bool | int | float | str):
            result[name] = value
        else:
            result[name] = str(value)
    return result


# ---------------------------------------------------------------------------
# Milestone 4: log redaction
# ---------------------------------------------------------------------------

MIN_SECRET_LENGTH = 8
_SENSITIVE_KEY = r"[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key)[\w.-]*"
_KEY_VALUE = re.compile(rf"(?i)\b({_SENSITIVE_KEY})([\"']?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&\"']+)")
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^:/@\s]+:)([^@/\s]+)(@)")
_BEARER = re.compile(r"(?i)\b(bearer\s+)([\w.~+/=-]+)")


def secret_values(settings: AppSettings) -> list[str]:
    """Raw values of every secret in ``settings`` (plus the database password), for the log filter."""
    values = [getattr(settings, name).get_secret_value() for name in secret_field_names()]
    password = urlsplit(settings.database_url.get_secret_value()).password
    if password:
        values.append(password)
    return [v for v in values if v]


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Replace known secret values, URL passwords, bearer tokens and ``key=value`` secrets with ``MASK``.

    Values shorter than ``MIN_SECRET_LENGTH`` are not replaced literally: masking every "a" in a log line
    would destroy it without protecting anything.
    """
    for value in sorted({s for s in secrets if len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True):
        text = text.replace(value, MASK)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{MASK}{m.group(3)}", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)}{MASK}", text)
    return _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


class RedactingFilter(logging.Filter):
    """A logging filter that redacts the message, its arguments and any traceback text."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        clean = redact(message, self._secrets)
        if clean != message:
            record.msg, record.args = clean, ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self._secrets)
        if record.stack_info:
            record.stack_info = redact(record.stack_info, self._secrets)
        return True


def configure_logging(
    settings: AppSettings,
    target: logging.Logger | None = None,
    stream: TextIO | None = None,
) -> logging.Handler:
    """Attach a redacting stream handler to ``target`` (default: the root logger) at the configured level.

    The filter sits on the *handler*, so it also sees records propagated from child loggers.
    """
    logger_ = target if target is not None else logging.getLogger()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter(secret_values(settings)))
    logger_.addHandler(handler)
    logger_.setLevel(settings.log_level.value)
    return handler


def main() -> int:
    """Validate the configuration and print it masked. Exit code 2 if it is invalid."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(json.dumps(describe(settings), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
