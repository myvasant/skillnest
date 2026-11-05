"""Auth demo: salted password hashing, HMAC-signed access tokens and role-based access in FastAPI.

Everything security-relevant uses the standard library only:

* passwords are hashed with ``hashlib.scrypt`` and a random per-user salt,
* hashes and signatures are compared with ``hmac.compare_digest`` (constant time),
* access tokens are ``<payload>.<signature>`` where the signature is HMAC-SHA256 over the payload.

Run it locally (the secret key comes from the environment, never from the code)::

    # PowerShell
    $env:AUTH_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
    python -m uvicorn --factory auth_service:app_from_env --app-dir solution --reload

    # macOS / Linux
    export AUTH_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
    python -m uvicorn --factory auth_service:app_from_env --app-dir solution --reload
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

Clock = Callable[[], float]
"""Returns the current time in seconds since the epoch. Injected so tests can control time."""

Role = Literal["user", "admin"]
ROLES: tuple[Role, ...] = ("user", "admin")


# ---------------------------------------------------------------------------
# Shared helpers: URL-safe base64 without padding (as used by JWTs)
# ---------------------------------------------------------------------------


def b64url_encode(data: bytes) -> str:
    """Encode bytes as URL-safe base64 text without ``=`` padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Decode URL-safe base64 text (padding optional). Raises ``binascii.Error`` on bad input."""
    padded = text + "=" * (-len(text) % 4)
    return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)


# ---------------------------------------------------------------------------
# Milestone 1: password hashing with scrypt
# ---------------------------------------------------------------------------

SCHEME = "scrypt"
SALT_BYTES = 16
HASH_BYTES = 32


@dataclass(frozen=True)
class ScryptParams:
    """scrypt cost parameters. They are stored inside every hash, so they can be raised later.

    Memory use is roughly ``128 * n * r`` bytes: the defaults use 16 MiB per hash.
    """

    n: int = 2**14
    r: int = 8
    p: int = 1

    @property
    def maxmem(self) -> int:
        """A memory limit comfortably above what OpenSSL needs for these parameters."""
        return 2 * 128 * self.r * (self.n + self.p + 2)


DEFAULT_SCRYPT = ScryptParams()


def _scrypt(password: str, salt: bytes, params: ScryptParams, length: int = HASH_BYTES) -> bytes:
    """Derive ``length`` bytes from ``password`` and ``salt`` with scrypt."""
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=params.n,
        r=params.r,
        p=params.p,
        maxmem=params.maxmem,
        dklen=length,
    )


def hash_password(password: str, params: ScryptParams = DEFAULT_SCRYPT) -> str:
    """Hash ``password`` with a fresh random salt.

    Returns a self-describing string ``scrypt$<n>$<r>$<p>$<salt>$<hash>`` (base64url parts), so
    a stored hash carries everything needed to verify it, even after the defaults change.
    """
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, params)
    fields = [SCHEME, str(params.n), str(params.r), str(params.p), b64url_encode(salt), b64url_encode(digest)]
    return "$".join(fields)


def parse_password_hash(encoded: str) -> tuple[ScryptParams, bytes, bytes]:
    """Split a stored hash into ``(params, salt, digest)``. Raises ``ValueError`` if malformed."""
    parts = encoded.split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        raise ValueError("unrecognised password hash format")
    try:
        params = ScryptParams(n=int(parts[1]), r=int(parts[2]), p=int(parts[3]))
        salt = b64url_decode(parts[4])
        digest = b64url_decode(parts[5])
    except (ValueError, binascii.Error) as exc:
        raise ValueError("unrecognised password hash format") from exc
    if not salt or not digest:
        raise ValueError("unrecognised password hash format")
    return params, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    """Return True if ``password`` matches the stored hash ``encoded``.

    The comparison uses ``hmac.compare_digest`` so its duration does not depend on how many leading
    bytes match.
    """
    params, salt, expected = parse_password_hash(encoded)
    candidate = _scrypt(password, salt, params, length=len(expected))
    return hmac.compare_digest(candidate, expected)


def needs_rehash(encoded: str, params: ScryptParams = DEFAULT_SCRYPT) -> bool:
    """Return True if ``encoded`` was made with parameters other than ``params`` (rehash at next login)."""
    current, _salt, _digest = parse_password_hash(encoded)
    return current != params


# ---------------------------------------------------------------------------
# Milestone 2: short-lived HMAC-signed tokens
# ---------------------------------------------------------------------------

MIN_KEY_BYTES = 32


class TokenError(Exception):
    """The token must not be trusted. Subclasses say why."""


class InvalidTokenError(TokenError):
    """The token is malformed or its signature does not match (tampered, or signed with another key)."""


class ExpiredTokenError(TokenError):
    """The signature is valid but the token is past its expiry time."""


@dataclass(frozen=True)
class TokenClaims:
    """The verified contents of an access token."""

    sub: str
    role: Role
    iat: int
    exp: int


def _split_token(token: str) -> tuple[str, str]:
    """Split ``payload.signature``; reject anything else before doing any crypto."""
    if not token.isascii():
        raise InvalidTokenError("malformed token")
    parts = token.split(".")
    if len(parts) != 2 or not all(parts):
        raise InvalidTokenError("malformed token")
    return parts[0], parts[1]


def _claims_from_payload(payload: object) -> TokenClaims:
    """Check the decoded payload has exactly the expected claim types."""
    if not isinstance(payload, dict):
        raise InvalidTokenError("malformed token payload")
    sub, role, iat, exp = (payload.get(k) for k in ("sub", "role", "iat", "exp"))
    if not isinstance(sub, str) or role not in ROLES:
        raise InvalidTokenError("malformed token payload")
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (iat, exp)):
        raise InvalidTokenError("malformed token payload")
    return TokenClaims(sub=sub, role=role, iat=iat, exp=exp)  # type: ignore[arg-type]


class TokenSigner:
    """Issues and verifies ``<payload>.<signature>`` access tokens signed with HMAC-SHA256."""

    def __init__(self, secret_key: bytes, *, ttl_seconds: int = 900, clock: Clock = time.time) -> None:
        if len(secret_key) < MIN_KEY_BYTES:
            raise ValueError(f"secret key must be at least {MIN_KEY_BYTES} bytes, got {len(secret_key)}")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._key = secret_key
        self._clock = clock
        self.ttl_seconds = ttl_seconds

    def __repr__(self) -> str:
        return f"TokenSigner(ttl_seconds={self.ttl_seconds}, secret_key=<redacted>)"

    def _sign(self, body: str) -> str:
        """Return the base64url HMAC-SHA256 signature of the encoded payload."""
        return b64url_encode(hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest())

    def issue(self, subject: str, role: Role) -> str:
        """Return a signed token for ``subject`` that expires ``ttl_seconds`` from now."""
        now = int(self._clock())
        claims = {"sub": subject, "role": role, "iat": now, "exp": now + self.ttl_seconds}
        body = b64url_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str) -> TokenClaims:
        """Return the claims of a valid token.

        Raises ``InvalidTokenError`` for malformed or tampered tokens and ``ExpiredTokenError`` when
        the signature is valid but the token has expired. The signature is checked *before* the payload
        is parsed, so attacker-controlled JSON is never trusted.
        """
        body, signature = _split_token(token)
        if not hmac.compare_digest(self._sign(body).encode("ascii"), signature.encode("ascii")):
            raise InvalidTokenError("bad signature")
        try:
            payload = json.loads(b64url_decode(body))
        except (ValueError, binascii.Error):
            raise InvalidTokenError("malformed token payload") from None
        claims = _claims_from_payload(payload)
        if self._clock() >= claims.exp:
            raise ExpiredTokenError("token expired")
        return claims


# ---------------------------------------------------------------------------
# Milestone 3: users, registration and login
# ---------------------------------------------------------------------------

USERNAME_PATTERN = r"^[a-z0-9_]{3,32}$"
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


@dataclass(frozen=True)
class User:
    """A stored user. Only the password *hash* is kept."""

    username: str
    password_hash: str
    role: Role = "user"


class DuplicateUserError(Exception):
    """Raised when registering a username that already exists."""


class UserStore:
    """In-memory user repository, one per app instance (swap for a database table in production)."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._lock = threading.Lock()

    def add(self, user: User) -> None:
        """Store ``user``; raise ``DuplicateUserError`` if the username is taken."""
        with self._lock:
            if user.username in self._users:
                raise DuplicateUserError(user.username)
            self._users[user.username] = user

    def get(self, username: str) -> User | None:
        """Return the user called ``username``, or None."""
        return self._users.get(username)

    def all_users(self) -> list[User]:
        """Return every user, sorted by username."""
        return sorted(self._users.values(), key=lambda u: u.username)

    @cached_property
    def dummy_hash(self) -> str:
        """A hash of a random password, used to spend equal time on logins for unknown usernames."""
        return hash_password(secrets.token_urlsafe(16))


def create_user(store: UserStore, username: str, password: str, role: Role = "user") -> User:
    """Hash ``password`` and add a new user to ``store``. Raises ``DuplicateUserError``."""
    user = User(username=username, password_hash=hash_password(password), role=role)
    store.add(user)
    return user


def authenticate(store: UserStore, username: str, password: str) -> User | None:
    """Return the user if the credentials are correct, otherwise None.

    For unknown usernames a dummy hash is still verified, so response time does not reveal which
    usernames exist.
    """
    user = store.get(username)
    if user is None:
        verify_password(password, store.dummy_hash)
        return None
    return user if verify_password(password, user.password_hash) else None


class RegisterRequest(BaseModel):
    """Body of ``POST /register``. Unknown fields (such as ``role``) are rejected."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(pattern=USERNAME_PATTERN, description="3-32 lowercase letters, digits or _")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @model_validator(mode="after")
    def password_must_not_contain_username(self) -> "RegisterRequest":
        """Reject the most guessable passwords: ones containing the username."""
        if self.username in self.password.lower():
            raise ValueError("password must not contain the username")
        return self


class LoginRequest(BaseModel):
    """Body of ``POST /login``."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(max_length=64)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class TokenResponse(BaseModel):
    """A bearer token as returned by ``POST /login`` (shape follows OAuth 2.0, RFC 6749 section 5.1)."""

    access_token: str
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: int


class UserOut(BaseModel):
    """Public view of a user: never includes the password hash."""

    username: str
    role: Role


# ---------------------------------------------------------------------------
# Milestone 4: authentication and role-based authorisation dependencies
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False, description="Access token from POST /login")


def get_store(request: Request) -> UserStore:
    """Dependency: the app's user store."""
    return request.app.state.store


def get_signer(request: Request) -> TokenSigner:
    """Dependency: the app's token signer."""
    return request.app.state.signer


def unauthorized(detail: str, *, invalid_token: bool = False) -> HTTPException:
    """A 401 with the ``WWW-Authenticate`` header that RFC 6750 requires for bearer tokens."""
    challenge = 'Bearer error="invalid_token"' if invalid_token else "Bearer"
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": challenge})


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    signer: Annotated[TokenSigner, Depends(get_signer)],
) -> TokenClaims:
    """Dependency: the verified claims of the caller, or 401 (missing, malformed, tampered or expired)."""
    if credentials is None:
        raise unauthorized("missing bearer token")
    try:
        return signer.verify(credentials.credentials)
    except ExpiredTokenError:
        raise unauthorized("token expired", invalid_token=True) from None
    except TokenError:
        raise unauthorized("invalid token", invalid_token=True) from None


CurrentUser = Annotated[TokenClaims, Depends(get_current_user)]


def require_role(*allowed: Role) -> Callable[[TokenClaims], TokenClaims]:
    """Build a dependency that allows only callers whose role is in ``allowed``.

    Not authenticated -> 401 (from ``get_current_user``); authenticated but wrong role -> 403.
    """

    def check_role(user: CurrentUser) -> TokenClaims:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient permissions")
        return user

    return check_role


async def validation_error_without_input(request: Request, exc: Exception) -> JSONResponse:
    """422 handler like FastAPI's default, minus the echoed ``input`` (it may contain a password)."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    # "input" (the submitted value) and "ctx" are deliberately left out.
    detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in errors]
    return JSONResponse(status_code=422, content={"detail": detail})


def create_app(
    secret_key: bytes,
    *,
    store: UserStore | None = None,
    clock: Clock = time.time,
    token_ttl_seconds: int = 900,
) -> FastAPI:
    """Build the API. Everything stateful (users, key, clock) is injected, so tests get a fresh app."""
    app = FastAPI(title="Auth demo", version="1.0.0")
    app.state.store = store if store is not None else UserStore()
    app.state.signer = TokenSigner(secret_key, ttl_seconds=token_ttl_seconds, clock=clock)
    app.add_exception_handler(RequestValidationError, validation_error_without_input)

    Store = Annotated[UserStore, Depends(get_store)]
    Signer = Annotated[TokenSigner, Depends(get_signer)]

    @app.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
    def register(body: RegisterRequest, store: Store) -> UserOut:
        """Create a user with role ``user``. 409 if the username is taken."""
        try:
            user = create_user(store, body.username, body.password)
        except DuplicateUserError:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="username already taken") from None
        return UserOut(username=user.username, role=user.role)

    @app.post("/login", response_model=TokenResponse)
    def login(body: LoginRequest, store: Store, signer: Signer) -> TokenResponse:
        """Exchange a username and password for a short-lived bearer token."""
        user = authenticate(store, body.username, body.password)
        if user is None:
            raise unauthorized("invalid username or password")
        token = signer.issue(user.username, user.role)
        return TokenResponse(access_token=token, expires_in=signer.ttl_seconds)

    @app.get("/me", response_model=UserOut)
    def me(user: CurrentUser) -> UserOut:
        """Who am I? Requires any valid token."""
        return UserOut(username=user.sub, role=user.role)

    AdminUser = Annotated[TokenClaims, Depends(require_role("admin"))]

    @app.get("/admin/users", response_model=list[UserOut])
    def list_users(_admin: AdminUser, store: Store) -> list[UserOut]:
        """List every user. Requires the ``admin`` role."""
        return [UserOut(username=u.username, role=u.role) for u in store.all_users()]

    return app


KEY_ENV_VAR = "AUTH_SECRET_KEY"


def load_secret_key(environ: Mapping[str, str] | None = None) -> bytes:
    """Read the hex-encoded signing key from ``AUTH_SECRET_KEY``; fail fast with a helpful message."""
    env = os.environ if environ is None else environ
    raw = env.get(KEY_ENV_VAR, "").strip()
    hint = 'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    if not raw:
        raise RuntimeError(f"{KEY_ENV_VAR} is not set; {hint}")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise RuntimeError(f"{KEY_ENV_VAR} must be hex-encoded; {hint}") from None
    if len(key) < MIN_KEY_BYTES:
        raise RuntimeError(f"{KEY_ENV_VAR} must decode to at least {MIN_KEY_BYTES} bytes; {hint}")
    return key


def app_from_env() -> FastAPI:
    """Factory for uvicorn: ``uvicorn --factory auth_service:app_from_env``."""
    return create_app(load_secret_key())
