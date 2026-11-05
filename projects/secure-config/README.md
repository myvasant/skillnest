# Secure configuration: typed settings, fail-fast secrets, redacted logs

Every service needs configuration (ports, URLs, log level) and secrets (database passwords, API keys,
signing keys). Most production incidents with configuration are one of these:

* a typo or wrong type that is only discovered on the first request (`APP_PORT=80OO`),
* a missing secret that crashes the app at 3 a.m. instead of at deploy time,
* a secret that ends up in a log line, an error message or a `print(settings)`.

In this project you build `secure_settings.py`, a small configuration module that prevents all three:

```text
$ python solution/secure_settings.py            # nothing set
invalid configuration:
  - APP_DATABASE_URL is required but not set
  - APP_API_KEY is required but not set
  - APP_SECRET_KEY is required but not set
(exit code 2)

$ python solution/secure_settings.py            # with a valid .env
{
  "environment": "development",
  "port": 8000,
  "database_url": "postgresql://app:**********@localhost:5432/app",
  "api_key": "**********",
  ...
}
```

## Setup

Windows PowerShell:

```powershell
cd projects\secure-config
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env      # then edit .env; it is git-ignored
```

macOS / Linux:

```bash
cd projects/secure-config
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env             # then edit .env; it is git-ignored
```

`.env` is listed in this kit's `.gitignore` (and the repository's). Only `.env.example`, which holds
placeholders, is committed. Generate real values with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Running the tests

```bash
python -m pytest                 # all milestones, against starter/
python -m pytest -k Milestone1   # one milestone
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

The tests remove every `APP_*` variable from the environment and run in a temporary directory, so your
own shell variables and `.env` never affect them. They set variables with `monkeypatch.setenv`.

## Milestones

| # | Tests | What you build |
|---|-------|----------------|
| 1 | `TestMilestone1TypedSettings` | the `AppSettings` fields, constraints and validators (`SecretStr`, enums, URL checks, production rules) |
| 2 | `TestMilestone2FailFast` | `load_settings`, `describe_validation_error`, `unknown_app_variables` and the `.env.example` |
| 3 | `TestMilestone3SafeDescribe` | `mask_url`, `describe` (masked, JSON-safe view) |
| 4 | `TestMilestone4Redaction` | `secret_values`, `redact`, `RedactingFilter`, `configure_logging` |

## Settings

| Variable | Type | Default | Notes |
|---|---|---|---|
| `APP_ENVIRONMENT` | `development` / `staging` / `production` | `development` | production enables extra rules |
| `APP_DEBUG` | bool | `false` | must be false in production |
| `APP_PORT` | int 1-65535 | `8000` | |
| `APP_LOG_LEVEL` | `DEBUG` ... `CRITICAL` | `INFO` | case-insensitive |
| `APP_PUBLIC_BASE_URL` | http(s) URL | `http://localhost:8000` | must be https in production |
| `APP_REQUEST_TIMEOUT_SECONDS` | float, 0 < x <= 60 | `5` | |
| `APP_DATABASE_URL` | secret URL | **required** | `postgresql://`, `postgresql+psycopg://` or `sqlite://` |
| `APP_API_KEY` | secret, >= 16 chars | **required** | |
| `APP_SECRET_KEY` | secret, >= 32 chars | **required** | |

## Layout

```text
secure-config/
  README.md
  requirements.txt
  .env.example                # placeholders only; copy to .env
  .gitignore                  # keeps .env out of git
  conftest.py                 # GW_TARGET=solution switches the tests to the reference solution
  starter/secure_settings.py  # your code
  solution/secure_settings.py # reference solution
  tests/test_secure_settings.py
```

## Optional extras

* A secrets manager in production (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret
  Manager, Kubernetes secrets): pydantic-settings can also read one file per secret with
  `secrets_dir="/run/secrets"` (Docker / Kubernetes secrets). Not needed for the tests.
