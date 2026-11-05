"""Auth demo: salted password hashing, HMAC-signed access tokens and role-based access in FastAPI.

Your job is to fill in every function that raises ``NotImplementedError``, milestone by milestone.
Run the tests for one milestone with ``python -m pytest -k Milestone1`` (then 2, 3, 4).

Everything security-relevant uses the standard library only:

* passwords are hashed with ``hashlib.scrypt`` and a random per-user salt,
* hashes and signatures are compared with ``hmac.compare_digest`` (constant time),
* access tokens are ``<payload>.<signature>`` where the signature is HMAC-SHA256 over the payload.

Run it locally once milestone 4 passes (the secret key comes from the environment)::

    # PowerShell
    $env:AUTH_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
    python -m uvicorn --factory auth_service:app_from_env --app-dir starter --reload
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
# Shared helpers (provided): URL-safe base64 without padding (as used by JWTs)
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


def hash_password(password: str, params: ScryptParams = DEFAULT_SCRYPT) -> str:
    """Hash ``password`` with a fresh random salt.

    Returns a self-describing string ``scrypt$<n>$<r>$<p>$<salt>$<hash>`` (base64url parts), so
    a stored hash carries everything needed to verify it, even after the defaults change.
    """
    # TODO(milestone 1):
    #   1. salt = secrets.token_bytes(SALT_BYTES)   (never random.random: it is predictable)
    #   2. digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params.n, r=params.r,
    #                              p=params.p, maxmem=params.maxmem, dklen=HASH_BYTES)
    #   3. join SCHEME, n, r, p, b64url_encode(salt), b64url_encode(digest) with "$"
    raise NotImplementedError("TODO(milestone 1): hash_password")


def parse_password_hash(encoded: str) -> tuple[ScryptParams, bytes, bytes]:
    """Split a stored hash into ``(params, salt, digest)``. Raises ``ValueError`` if malformed."""
    # TODO(milestone 1): split on "$"; expect exactly 6 parts starting with SCHEME. Convert n/r/p with
    # int() and decode salt/digest with b64url_decode. Turn *any* parsing problem (including empty parts)
    # into ValueError("unrecognised password hash format").
    raise NotImplementedError("TODO(milestone 1): parse_password_hash")


def verify_password(password: str, encoded: str) -> bool:
    """Return True if ``password`` matches the stored hash ``encoded``.

    The comparison must use ``hmac.compare_digest`` so its duration does not depend on how many
    leading bytes match.
    """
    # TODO(milestone 1): parse the hash, recompute scrypt with the *stored* salt and parameters, and
    # compare with hmac.compare_digest(candidate, expected) -- never with ==.
    raise NotImplementedError("TODO(milestone 1): verify_password")


def needs_rehash(encoded: str, params: ScryptParams = DEFAULT_SCRYPT) -> bool:
    """Return True if ``encoded`` was made with parameters other than ``params`` (rehash at next login)."""
    raise NotImplementedError("TODO(milestone 1): needs_rehash")


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
        # TODO(milestone 2): return something useful that does NOT include self._key.
        raise NotImplementedError("TODO(milestone 2): TokenSigner.__repr__")

    def issue(self, subject: str, role: Role) -> str:
        """Return a signed token for ``subject`` that expires ``ttl_seconds`` from now."""
        # TODO(milestone 2):
        #   now = int(self._clock())
        #   claims = {"sub": ..., "role": ..., "iat": now, "exp": now + self.ttl_seconds}
        #   body = b64url_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
        #   signature = b64url_encode(hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest())
        #   return f"{body}.{signature}"
        raise NotImplementedError("TODO(milestone 2): TokenSigner.issue")

    def verify(self, token: str) -> TokenClaims:
        """Return the claims of a valid token.

        Raises ``InvalidTokenError`` for malformed or tampered tokens and ``ExpiredTokenError`` when
        the signature is valid but the token has expired. Check the signature *before* parsing the
        payload, so attacker-controlled JSON is never trusted.
        """
        # TODO(milestone 2):
        #   1. reject non-ASCII tokens and anything that is not exactly two non-empty parts
        #   2. recompute the signature of the body; compare with hmac.compare_digest (as bytes)
        #   3. decode + json.loads the body; check sub is str, role in ROLES, iat/exp are ints
        #   4. if self._clock() >= exp: raise ExpiredTokenError
        raise NotImplementedError("TODO(milestone 2): TokenSigner.verify")


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
    """In-memory user repository, one per app instance (provided -- swap for a database later)."""

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
    raise NotImplementedError("TODO(milestone 3): create_user")


def authenticate(store: UserStore, username: str, password: str) -> User | None:
    """Return the user if the credentials are correct, otherwise None.

    For unknown usernames, still verify ``store.dummy_hash`` so response time does not reveal which
    usernames exist.
    """
    raise NotImplementedError("TODO(milestone 3): authenticate")


class RegisterRequest(BaseModel):
    """Body of ``POST /register``. Unknown fields (such as ``role``) must be rejected."""

    # TODO(milestone 3): model_config = ConfigDict(extra="forbid")
    # TODO(milestone 3): constrain the fields with Field(pattern=USERNAME_PATTERN) and
    #                    Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    username: str
    password: str

    # TODO(milestone 3): add a @model_validator(mode="after") that raises ValueError when the
    #                    password contains the username.


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
    # TODO(milestone 4): credentials is None when the header is missing or not "Bearer ...".
    #   missing -> raise unauthorized("missing bearer token")
    #   ExpiredTokenError -> raise unauthorized("token expired", invalid_token=True)
    #   any other TokenError -> raise unauthorized("invalid token", invalid_token=True)
    raise NotImplementedError("TODO(milestone 4): get_current_user")


CurrentUser = Annotated[TokenClaims, Depends(get_current_user)]


def require_role(*allowed: Role) -> Callable[[TokenClaims], TokenClaims]:
    """Build a dependency that allows only callers whose role is in ``allowed``.

    Not authenticated -> 401 (from ``get_current_user``); authenticated but wrong role -> 403.
    """
    # TODO(milestone 4): define an inner function `check_role(user: CurrentUser) -> TokenClaims` that
    # raises HTTPException(403) when user.role is not allowed, and return it (do not call it).
    raise NotImplementedError("TODO(milestone 4): require_role")


async def validation_error_without_input(request: Request, exc: Exception) -> JSONResponse:
    """422 handler like FastAPI's default, minus the echoed ``input`` (it may contain a password)."""
    # TODO(milestone 3): build [{"loc": ..., "msg": ..., "type": ...}] from exc.errors(), dropping "input".
    raise NotImplementedError("TODO(milestone 3): validation_error_without_input")


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
        # TODO(milestone 3): create_user(...); turn DuplicateUserError into HTTPException(409).
        raise NotImplementedError("TODO(milestone 3): POST /register")

    @app.post("/login", response_model=TokenResponse)
    def login(body: LoginRequest, store: Store, signer: Signer) -> TokenResponse:
        """Exchange a username and password for a short-lived bearer token."""
        # TODO(milestone 3): authenticate(...); None -> raise unauthorized("invalid username or password")
        # (the SAME message for unknown users and wrong passwords); else return a TokenResponse.
        raise NotImplementedError("TODO(milestone 3): POST /login")

    @app.get("/me", response_model=UserOut)
    def me(user: CurrentUser) -> UserOut:
        """Who am I? Requires any valid token."""
        return UserOut(username=user.sub, role=user.role)

    # TODO(milestone 4): add GET /admin/users -> list[UserOut], protected by
    #   Annotated[TokenClaims, Depends(require_role("admin"))]

    return app


KEY_ENV_VAR = "AUTH_SECRET_KEY"


def load_secret_key(environ: Mapping[str, str] | None = None) -> bytes:
    """Read the hex-encoded signing key from ``AUTH_SECRET_KEY``; fail fast with a helpful message."""
    # TODO(milestone 4): read os.environ (or `environ`), raise RuntimeError naming KEY_ENV_VAR when it
    # is missing, not hex (bytes.fromhex), or shorter than MIN_KEY_BYTES. Never print the value.
    raise NotImplementedError("TODO(milestone 4): load_secret_key")


def app_from_env() -> FastAPI:
    """Factory for uvicorn: ``uvicorn --factory auth_service:app_from_env``."""
    return create_app(load_secret_key())
