"""Behaviour tests for typed, secret-safe configuration, grouped by milestone.

Every test starts from an environment with no APP_* variables and a temporary working directory,
so neither your shell nor a stray .env file can change the results.

Run one milestone with:  python -m pytest -k Milestone2
"""

import io
import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import secure_settings as cfg
from pydantic import SecretStr, ValidationError

KIT_DIR = Path(__file__).resolve().parents[1]

# Fake but realistic-looking test values (not real credentials).
DB_PASSWORD = "db-pass-9f3k2m7q"  # noqa: S105 - test fixture value
DB_URL = f"postgresql://app:{DB_PASSWORD}@db.internal:5432/app"
API_KEY = "test-api-key-5d8e1c0b9a"
SIGNING_KEY = "test-signing-key-6b2f9e4d1a7c3b8e5f0a2d4c"
REQUIRED = {"APP_DATABASE_URL": DB_URL, "APP_API_KEY": API_KEY, "APP_SECRET_KEY": SIGNING_KEY}
ALL_SECRETS = (DB_PASSWORD, API_KEY, SIGNING_KEY)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove every APP_* variable and run in an empty directory (no .env to pick up by accident)."""
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def settings(required_env: None) -> cfg.AppSettings:
    return cfg.AppSettings(_env_file=None)


@pytest.fixture
def test_logger() -> Iterator[logging.Logger]:
    """An isolated logger (does not propagate to the root logger); handlers are removed afterwards."""
    log = logging.getLogger("secure_settings.tests")
    log.propagate = False
    yield log
    for handler in list(log.handlers):
        log.removeHandler(handler)


def assert_no_secrets(text: str) -> None:
    for secret in ALL_SECRETS:
        assert secret not in text, f"a secret value leaked into: {text!r}"


# ---------------------------------------------------------------------------
# Milestone 1: typed settings with validation
# ---------------------------------------------------------------------------


class TestMilestone1TypedSettings:
    def test_defaults_when_only_secrets_are_set(self, settings: cfg.AppSettings) -> None:
        assert settings.environment == cfg.Environment.DEVELOPMENT
        assert settings.debug is False
        assert settings.port == 8000
        assert settings.log_level == cfg.LogLevel.INFO
        assert str(settings.public_base_url) == "http://localhost:8000/"
        assert settings.request_timeout_seconds == 5.0

    def test_strings_from_the_environment_become_typed_values(
        self, monkeypatch: pytest.MonkeyPatch, required_env: None
    ) -> None:
        monkeypatch.setenv("APP_PORT", "9000")
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("APP_LOG_LEVEL", "debug")
        monkeypatch.setenv("APP_ENVIRONMENT", "Staging")
        monkeypatch.setenv("APP_REQUEST_TIMEOUT_SECONDS", "2.5")
        s = cfg.AppSettings(_env_file=None)
        assert (s.port, s.debug, s.request_timeout_seconds) == (9000, True, 2.5), "convert to int/bool/float"
        assert s.log_level is cfg.LogLevel.DEBUG, "log level names are case-insensitive"
        assert s.environment is cfg.Environment.STAGING, "environment names are case-insensitive"

    def test_secrets_are_secretstr(self, settings: cfg.AppSettings) -> None:
        for name in ("database_url", "api_key", "secret_key"):
            assert isinstance(getattr(settings, name), SecretStr), f"{name} should be a SecretStr"
        assert settings.api_key.get_secret_value() == API_KEY

    @pytest.mark.parametrize(
        ("variable", "value"),
        [
            ("APP_PORT", "0"),
            ("APP_PORT", "70000"),
            ("APP_PORT", "eighty"),
            ("APP_LOG_LEVEL", "LOUD"),
            ("APP_ENVIRONMENT", "prod"),
            ("APP_PUBLIC_BASE_URL", "not a url"),
            ("APP_REQUEST_TIMEOUT_SECONDS", "0"),
            ("APP_DATABASE_URL", "mysql://app:pw@localhost/app"),
            ("APP_DATABASE_URL", "postgresql:///no-host"),
            ("APP_API_KEY", "too-short"),
            ("APP_SECRET_KEY", "only-twenty-chars-xx"),
        ],
    )
    def test_invalid_values_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, required_env: None, variable: str, value: str
    ) -> None:
        monkeypatch.setenv(variable, value)
        with pytest.raises(ValidationError):
            cfg.AppSettings(_env_file=None)

    def test_repr_and_str_never_show_secrets(self, settings: cfg.AppSettings) -> None:
        assert_no_secrets(repr(settings))
        assert_no_secrets(str(settings))

    def test_settings_are_immutable(self, settings: cfg.AppSettings) -> None:
        with pytest.raises(ValidationError):
            settings.port = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Milestone 2: fail fast with safe errors
# ---------------------------------------------------------------------------


class TestMilestone2FailFast:
    def test_missing_secrets_are_all_reported_by_name(self) -> None:
        with pytest.raises(cfg.ConfigError) as info:
            cfg.load_settings(env_file=None)
        message = str(info.value)
        for name in REQUIRED:
            assert f"{name} is required but not set" in message, f"the error should name {name}"
        assert len(info.value.problems) == 3, "report every problem at once, not just the first"

    def test_errors_never_repeat_values(self, monkeypatch: pytest.MonkeyPatch, required_env: None) -> None:
        monkeypatch.setenv("APP_PORT", API_KEY)  # an operator pasted the API key into the wrong variable
        monkeypatch.setenv("APP_SECRET_KEY", "short-secret-value")
        with pytest.raises(cfg.ConfigError) as info:
            cfg.load_settings(env_file=None)
        message = str(info.value)
        assert "APP_PORT" in message and "APP_SECRET_KEY" in message
        assert API_KEY not in message and "short-secret-value" not in message, "never echo values in errors"
        assert info.value.__cause__ is None and info.value.__context__ is None, (
            "do not chain pydantic's ValidationError: its text includes the raw input values"
        )

    def test_reads_an_env_file_and_the_environment_wins(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / "custom.env"
        lines = [f"{k}={v}" for k, v in REQUIRED.items()] + ["APP_PORT=9000", "APP_LOG_LEVEL=WARNING"]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setenv("APP_PORT", "9100")
        s = cfg.load_settings(env_file=env_file)
        assert s.api_key.get_secret_value() == API_KEY, "values should be read from the env file"
        assert s.log_level is cfg.LogLevel.WARNING
        assert s.port == 9100, "a real environment variable must override the .env file"

    def test_env_file_none_ignores_dotenv(self, required_env: None, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("APP_PORT=1234\n", encoding="utf-8")
        assert cfg.load_settings(env_file=None).port == 8000, "env_file=None must not read .env"
        assert cfg.load_settings().port == 1234, "the default should read .env from the working directory"

    def test_production_rules(self, monkeypatch: pytest.MonkeyPatch, required_env: None) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("APP_PUBLIC_BASE_URL", "http://example.com")
        with pytest.raises(cfg.ConfigError) as info:
            cfg.load_settings(env_file=None)
        message = str(info.value)
        assert "APP_DEBUG" in message and "APP_PUBLIC_BASE_URL" in message

    def test_valid_production_configuration_loads(
        self, monkeypatch: pytest.MonkeyPatch, required_env: None
    ) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("APP_PUBLIC_BASE_URL", "https://api.example.com")
        assert cfg.load_settings(env_file=None).environment is cfg.Environment.PRODUCTION

    def test_unknown_app_variables_are_warned_by_name_only(
        self, monkeypatch: pytest.MonkeyPatch, required_env: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("APP_PROT", "typo-value-31337")
        with caplog.at_level(logging.WARNING):
            cfg.load_settings(env_file=None)
        assert "APP_PROT" in caplog.text, "warn about APP_* variables that match no setting (typos)"
        assert "typo-value-31337" not in caplog.text, "log the name, never the value"
        assert cfg.unknown_app_variables({"APP_PORT": "1", "APP_PROT": "1", "HOME": "x"}) == ["APP_PROT"]

    def test_env_example_documents_every_setting_with_placeholders(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        example = KIT_DIR / ".env.example"
        assert example.is_file(), "ship a .env.example next to the README"
        text = example.read_text(encoding="utf-8")
        for name in cfg.AppSettings.model_fields:
            assert cfg.env_var_name(name) in text, f".env.example should document {cfg.env_var_name(name)}"
        assert cfg.load_settings(env_file=example).environment is cfg.Environment.DEVELOPMENT
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("APP_PUBLIC_BASE_URL", "https://api.example.com")
        with pytest.raises(cfg.ConfigError, match="placeholder"):
            cfg.load_settings(env_file=example)

    def test_dotenv_is_git_ignored(self) -> None:
        ignored = (KIT_DIR / ".gitignore").read_text(encoding="utf-8").split()
        assert ".env" in ignored and "!.env.example" in ignored


# ---------------------------------------------------------------------------
# Milestone 3: a masked description that is safe to print
# ---------------------------------------------------------------------------


class TestMilestone3SafeDescribe:
    def test_describe_masks_secrets_and_shows_the_rest(self, settings: cfg.AppSettings) -> None:
        described = cfg.describe(settings)
        assert_no_secrets(json.dumps(described))
        assert described["api_key"] == cfg.MASK and described["secret_key"] == cfg.MASK
        assert described["port"] == 8000 and described["environment"] == "development"
        assert described["log_level"] == "INFO" and described["debug"] is False

    def test_database_url_keeps_host_but_hides_password(self, settings: cfg.AppSettings) -> None:
        assert cfg.describe(settings)["database_url"] == f"postgresql://app:{cfg.MASK}@db.internal:5432/app"

    @pytest.mark.parametrize(
        "url", ["sqlite:///data/app.db", "postgresql://db.internal/app", "https://x.org/a"]
    )
    def test_mask_url_leaves_urls_without_passwords_alone(self, url: str) -> None:
        assert cfg.mask_url(url) == url

    def test_describe_is_json_serialisable(self, settings: cfg.AppSettings) -> None:
        json.dumps(cfg.describe(settings))
        assert set(cfg.describe(settings)) == set(cfg.AppSettings.model_fields), "describe every setting"

    def test_main_prints_masked_settings(
        self, required_env: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cfg.main() == 0
        out = capsys.readouterr().out
        assert json.loads(out)["api_key"] == cfg.MASK
        assert_no_secrets(out)

    def test_main_reports_problems_and_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cfg.main() == 2, "invalid configuration should exit with status 2"
        assert "APP_API_KEY" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Milestone 4: log redaction
# ---------------------------------------------------------------------------


class TestMilestone4Redaction:
    def test_redacts_known_secret_values(self) -> None:
        text = cfg.redact(f"calling upstream with key {API_KEY} now", [API_KEY])
        assert text == f"calling upstream with key {cfg.MASK} now"

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("password=hunter2 user=bob", f"password={cfg.MASK} user=bob"),
            ("db_password: 'p@ss w0rd'", f"db_password: {cfg.MASK}"),
            ('{"api_key": "abc123"}', f'{{"api_key": {cfg.MASK}}}'),
            ("X-Api-Key=abc123&page=2", f"X-Api-Key={cfg.MASK}&page=2"),
            ("refresh_token=abc.def", f"refresh_token={cfg.MASK}"),
            ("Authorization: Bearer eyJhbGciOi.payload.sig", f"Authorization: Bearer {cfg.MASK}"),
            ("connect postgresql://app:pw123@db/app", f"connect postgresql://app:{cfg.MASK}@db/app"),
            ("user=bob page=2", "user=bob page=2"),
        ],
    )
    def test_redacts_secret_looking_patterns(self, line: str, expected: str) -> None:
        assert cfg.redact(line) == expected

    def test_short_values_are_not_replaced_everywhere(self) -> None:
        assert cfg.redact("banana", ["a"]) == "banana", (
            "do not mask tiny values: it destroys logs and protects nothing"
        )

    def test_filter_redacts_formatted_arguments(self, test_logger: logging.Logger) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(cfg.RedactingFilter([API_KEY]))
        test_logger.addHandler(handler)
        test_logger.warning("retrying with %s (attempt %d)", API_KEY, 2)
        assert stream.getvalue().strip() == f"retrying with {cfg.MASK} (attempt 2)"

    def test_filter_redacts_tracebacks(self, test_logger: logging.Logger) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(cfg.RedactingFilter([SIGNING_KEY]))
        test_logger.addHandler(handler)
        try:
            raise ValueError(f"bad signature for key {SIGNING_KEY}")
        except ValueError:
            test_logger.exception("token check failed")
        output = stream.getvalue()
        assert "ValueError" in output and "token check failed" in output
        assert SIGNING_KEY not in output, "exception messages inside tracebacks must be redacted too"

    def test_secret_values_include_the_database_password(self, settings: cfg.AppSettings) -> None:
        values = cfg.secret_values(settings)
        for secret in ALL_SECRETS:
            assert secret in values

    def test_configure_logging_redacts_and_uses_the_level(
        self, settings: cfg.AppSettings, test_logger: logging.Logger
    ) -> None:
        stream = io.StringIO()
        handler = cfg.configure_logging(settings, test_logger, stream)
        assert isinstance(handler, logging.Handler)
        child = logging.getLogger("secure_settings.tests.child")
        child.info("config loaded: %s", settings.database_url.get_secret_value())
        test_logger.info("api key is %s and secret is %s", API_KEY, SIGNING_KEY)
        test_logger.debug("this is below INFO and must not appear")
        output = stream.getvalue()
        assert "config loaded" in output, "records from child loggers should reach the handler"
        assert_no_secrets(output)
        assert "below INFO" not in output, "the logger level should come from settings.log_level"
