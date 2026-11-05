"""Typed, validated settings from environment variables, with secrets that never reach the logs.

* ``AppSettings`` (pydantic-settings) reads ``APP_*`` variables, converts and validates them.
* ``load_settings()`` fails fast at startup with a message that names every bad variable but never
  repeats a value.
* ``describe()`` gives a masked view of the configuration that is safe to log or print.
* ``RedactingFilter`` / ``configure_logging()`` scrub secret values and ``password=...``-style pairs
  from every log record, including tracebacks.

Work through the TODOs milestone by milestone (``python -m pytest -k Milestone1`` ...).
Check your configuration from the command line::

    python starter/secure_settings.py        # prints the masked settings, or the problems (exit 2)
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
        # TODO(milestone 1): make instances immutable (frozen=True): settings should not change at runtime.
    )

    environment: Environment = Environment.DEVELOPMENT

    # TODO(milestone 1): declare the remaining fields with types, defaults and constraints:
    #   debug: bool = False
    #   port: int = Field(default=8000, ge=1, le=65535)
    #   log_level: LogLevel = LogLevel.INFO
    #   public_base_url: HttpUrl = Field(default=HttpUrl("http://localhost:8000"))
    #   request_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    #   database_url, api_key, secret_key: SecretStr with NO default (required -> fail fast)
    #
    # TODO(milestone 1): validators (raise ValueError with a message that never includes the value):
    #   - environment and log_level: accept any case ("Staging", "debug") with mode="before" validators
    #   - database_url: scheme must be one of DATABASE_SCHEMES; non-sqlite URLs need a host name
    #     (hint: urlsplit(value.get_secret_value()))
    #   - api_key / secret_key: at least SECRET_MIN_LENGTHS[info.field_name] characters
    #   - @model_validator(mode="after"): in production, APP_DEBUG must be false, APP_PUBLIC_BASE_URL must
    #     use https, and no secret may contain PLACEHOLDER_MARKER. Collect all problems, then raise once.


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
    # TODO(milestone 2): loop over exc.errors(include_input=False, include_url=False, include_context=False)
    #   - error["type"] == "missing"  -> "APP_X is required but not set"
    #   - errors with a loc            -> "APP_X: <msg without the 'Value error, ' prefix>"
    #   - model-level errors (empty loc) -> just the message
    raise NotImplementedError("TODO(milestone 2): describe_validation_error")


def unknown_app_variables(environ: Mapping[str, str] | None = None) -> list[str]:
    """``APP_*`` variables that match no setting -- usually typos such as ``APP_PROT``. Sorted."""
    raise NotImplementedError("TODO(milestone 2): unknown_app_variables")


def load_settings(env_file: str | Path | None = DEFAULT_ENV_FILE) -> AppSettings:
    """Load and validate settings from the environment (and ``env_file`` if it exists; None = no file).

    Real environment variables win over the file. Raises ``ConfigError`` listing every problem.
    """
    # TODO(milestone 2):
    #   1. log a WARNING naming (never showing the value of) each unknown APP_* variable
    #   2. return AppSettings(_env_file=env_file)
    #   3. on ValidationError, build the problem list, and raise ConfigError(problems) OUTSIDE the
    #      except block, so the new exception has no __context__ pointing at pydantic's error (whose
    #      text can contain raw input values).
    raise NotImplementedError("TODO(milestone 2): load_settings")


# ---------------------------------------------------------------------------
# Milestone 3: a masked description that is safe to print
# ---------------------------------------------------------------------------


def mask_url(url: str) -> str:
    """Hide the password in a URL: ``postgresql://app:pw@db/app`` -> ``postgresql://app:**********@db/app``."""
    # TODO(milestone 3): urlsplit, rpartition the netloc on "@", keep the username, replace the password
    # with MASK, urlunsplit. URLs without a password come back unchanged.
    raise NotImplementedError("TODO(milestone 3): mask_url")


def describe(settings: AppSettings) -> dict[str, str | int | float | bool]:
    """Every setting as JSON-safe values with secrets masked. Safe to log at startup."""
    # TODO(milestone 3): database_url -> mask_url(...); other SecretStr -> MASK; Enum -> .value;
    # bool/int/float/str unchanged; anything else (HttpUrl) -> str(value).
    raise NotImplementedError("TODO(milestone 3): describe")


# ---------------------------------------------------------------------------
# Milestone 4: log redaction
# ---------------------------------------------------------------------------

MIN_SECRET_LENGTH = 8
# Provided patterns: a key that looks sensitive, followed by = or :, followed by a (quoted) value.
_SENSITIVE_KEY = r"[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key)[\w.-]*"
_KEY_VALUE = re.compile(rf"(?i)\b({_SENSITIVE_KEY})([\"']?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&\"']+)")
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^:/@\s]+:)([^@/\s]+)(@)")
_BEARER = re.compile(r"(?i)\b(bearer\s+)([\w.~+/=-]+)")


def secret_values(settings: AppSettings) -> list[str]:
    """Raw values of every secret in ``settings`` (plus the database password), for the log filter."""
    raise NotImplementedError("TODO(milestone 4): secret_values")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Replace known secret values, URL passwords, bearer tokens and ``key=value`` secrets with ``MASK``.

    Values shorter than ``MIN_SECRET_LENGTH`` are not replaced literally: masking every "a" in a log line
    would destroy it without protecting anything.
    """
    # TODO(milestone 4): replace the longest secrets first, then apply _URL_CREDENTIALS, _BEARER and
    # _KEY_VALUE with .sub(...), keeping the key/separator groups and replacing only the value.
    raise NotImplementedError("TODO(milestone 4): redact")


class RedactingFilter(logging.Filter):
    """A logging filter that redacts the message, its arguments and any traceback text."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        # TODO(milestone 4):
        #   - message = record.getMessage() merges msg % args; if redacting changes it, store the clean text
        #     in record.msg and set record.args = () so it is not formatted again
        #   - tracebacks: if record.exc_info and no record.exc_text yet, render it with
        #     logging.Formatter().formatException(record.exc_info); then redact record.exc_text
        #   - return True (we clean records, we never drop them)
        raise NotImplementedError("TODO(milestone 4): RedactingFilter.filter")


def configure_logging(
    settings: AppSettings,
    target: logging.Logger | None = None,
    stream: TextIO | None = None,
) -> logging.Handler:
    """Attach a redacting stream handler to ``target`` (default: the root logger) at the configured level.

    Put the filter on the *handler*, so it also sees records propagated from child loggers.
    """
    raise NotImplementedError("TODO(milestone 4): configure_logging")


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
