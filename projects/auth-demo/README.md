# Auth demo: passwords, signed tokens and roles

Build the security core of a small API yourself, using only the Python standard library for the
cryptography:

* **Registration and login** with passwords hashed by `hashlib.scrypt` and a random salt per user.
* **Short-lived access tokens** signed with HMAC-SHA256 (`hmac`), carrying the user's name, role
  and expiry time.
* **Authentication vs authorisation** in FastAPI: a dependency that answers *who are you?*
  (401 if it cannot tell) and another that answers *are you allowed?* (403 if not).

```text
POST /register {"username": "ada", "password": "correct horse battery staple"}  -> 201 {"username": "ada", "role": "user"}
POST /login    {"username": "ada", "password": "correct horse battery staple"}  -> 200 {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 900}
GET  /me           Authorization: Bearer eyJ...    -> 200 {"username": "ada", "role": "user"}
GET  /me           (no header, expired or tampered) -> 401 + WWW-Authenticate: Bearer
GET  /admin/users  Authorization: Bearer <ada>     -> 403 (authenticated, but not an admin)
```

> This is a learning project. In production, prefer a maintained library and identity provider
> (for example PyJWT or Authlib for tokens, an OAuth 2.0 / OpenID Connect provider for login). Building
> it once yourself is how you learn what those libraries protect you from.

## Setup

Windows PowerShell:

```powershell
cd projects\auth-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/auth-demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                 # all milestones, against starter/ (your code)
python -m pytest -k Milestone1   # one milestone at a time
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

## Running the API

The signing key is read from the `AUTH_SECRET_KEY` environment variable (64 hex characters = 32 bytes).
It is never written in the code, and the app refuses to start without it.

```powershell
$env:AUTH_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python -m uvicorn --factory auth_service:app_from_env --app-dir starter --reload
```

```bash
export AUTH_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m uvicorn --factory auth_service:app_from_env --app-dir starter --reload
```

Open <http://127.0.0.1:8000/docs>, register, log in, then click **Authorize** and paste the token.
Users live in memory, so they disappear when the server restarts. To try the admin route, create an
admin in a Python shell with `create_user(store, "root", "...", role="admin")` and pass that `store` to
`create_app` (registration always creates plain users).

## Milestones

| # | Tests | What you build |
|---|-------|----------------|
| 1 | `TestMilestone1PasswordHashing` | `hash_password`, `parse_password_hash`, `verify_password`, `needs_rehash` |
| 2 | `TestMilestone2SignedTokens` | `TokenSigner.issue` / `verify` / `__repr__`: HMAC signature, expiry, tamper detection |
| 3 | `TestMilestone3RegisterAndLogin` | `create_user`, `authenticate`, `RegisterRequest` validation, `/register`, `/login`, a 422 handler that does not echo passwords |
| 4 | `TestMilestone4Authorisation` | `get_current_user` (401), `require_role` (403), `/admin/users`, `load_secret_key` |

## Layout

```text
auth-demo/
  README.md
  requirements.txt
  conftest.py              # GW_TARGET=solution switches the tests to the reference solution
  starter/auth_service.py  # your code: functions raise NotImplementedError until you implement them
  solution/auth_service.py # reference solution
  tests/test_auth_service.py
```

## Optional extras

* **PyJWT** (`python -m pip install pyjwt`): replace `TokenSigner` with `jwt.encode` / `jwt.decode`
  (always pass `algorithms=["HS256"]` when decoding). Not needed for the tests.
* **argon2-cffi**: Argon2id is the current first choice for password hashing (OWASP); scrypt is used here
  because it ships with Python.
