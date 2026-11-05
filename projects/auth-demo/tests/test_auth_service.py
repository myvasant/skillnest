"""Behaviour tests for the auth demo, grouped by milestone.

Run one milestone with:  python -m pytest -k Milestone1
"""

import hmac
import json
import secrets

import auth_service as auth
import pytest
from fastapi.testclient import TestClient

# Test-only credentials and key. They are fixtures, not real secrets.
LEARNER_PW = "correct horse battery staple"  # noqa: S105 - test fixture value
OTHER_PW = "a completely different phrase"  # noqa: S105 - test fixture value
TEST_KEY = bytes(range(32))
FAST = auth.ScryptParams(n=2**10, r=8, p=1)  # cheaper parameters for tests that only inspect format


class FakeClock:
    """A controllable clock: tests move time forward instead of sleeping."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> auth.UserStore:
    return auth.UserStore()


@pytest.fixture
def client(store: auth.UserStore, clock: FakeClock) -> TestClient:
    return TestClient(auth.create_app(TEST_KEY, store=store, clock=clock, token_ttl_seconds=900))


def register(client: TestClient, username: str, password: str = LEARNER_PW):
    return client.post("/register", json={"username": username, "password": password})


def login(client: TestClient, username: str, password: str = LEARNER_PW):
    return client.post("/login", json={"username": username, "password": password})


def token_for(client: TestClient, username: str) -> str:
    """Register (if needed) and log in; return the access token."""
    register(client, username)
    response = login(client, username)
    assert response.status_code == 200, f"login should succeed for a fresh user, got {response.status_code}"
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def tamper_role(token: str, role: str) -> str:
    """Rewrite the payload's role but keep the original signature (what an attacker would try)."""
    body, signature = token.split(".")
    claims = json.loads(auth.b64url_decode(body))
    claims["role"] = role
    forged = auth.b64url_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    return f"{forged}.{signature}"


@pytest.fixture
def compare_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, object]]:
    """Record calls to hmac.compare_digest (and its alias secrets.compare_digest)."""
    calls: list[tuple[object, object]] = []
    real = hmac.compare_digest

    def spy(a, b):  # type: ignore[no-untyped-def]
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    monkeypatch.setattr(secrets, "compare_digest", spy)
    return calls


# ---------------------------------------------------------------------------
# Milestone 1: password hashing
# ---------------------------------------------------------------------------


class TestMilestone1PasswordHashing:
    def test_hash_is_self_describing_and_not_plaintext(self) -> None:
        encoded = auth.hash_password(LEARNER_PW, FAST)
        assert isinstance(encoded, str), "hash_password should return a str"
        assert LEARNER_PW not in encoded, "the stored hash must never contain the password itself"
        parts = encoded.split("$")
        assert len(parts) == 6 and parts[0] == "scrypt", f"expected 'scrypt$n$r$p$salt$hash', got {encoded!r}"
        assert parts[1:4] == ["1024", "8", "1"], "the cost parameters must be stored in the hash"

    def test_verify_accepts_the_right_password(self) -> None:
        encoded = auth.hash_password(LEARNER_PW, FAST)
        assert auth.verify_password(LEARNER_PW, encoded) is True

    def test_verify_rejects_a_wrong_password(self) -> None:
        encoded = auth.hash_password(LEARNER_PW, FAST)
        assert auth.verify_password(OTHER_PW, encoded) is False
        assert auth.verify_password(LEARNER_PW.upper(), encoded) is False, "passwords are case-sensitive"

    def test_same_password_gets_a_different_salt_each_time(self) -> None:
        first = auth.hash_password(LEARNER_PW, FAST)
        second = auth.hash_password(LEARNER_PW, FAST)
        assert first != second, "two hashes of the same password must differ (random salt)"
        assert first.split("$")[4] != second.split("$")[4], "the salt part must differ"
        assert len(auth.b64url_decode(first.split("$")[4])) >= 16, "use at least 16 random salt bytes"

    def test_verify_reads_parameters_from_the_stored_hash(self) -> None:
        old = auth.hash_password(LEARNER_PW, auth.ScryptParams(n=2**11, r=8, p=1))
        assert auth.verify_password(LEARNER_PW, old), "verify must use the n/r/p stored in the hash"

    def test_verify_uses_constant_time_comparison(self, compare_spy: list) -> None:
        encoded = auth.hash_password(LEARNER_PW, FAST)
        auth.verify_password(OTHER_PW, encoded)
        assert compare_spy, "compare digests with hmac.compare_digest, not ==, to avoid timing leaks"

    @pytest.mark.parametrize(
        "bad", ["", "plaintext", "md5$abc", "scrypt$x$8$1$c2FsdA$aGFzaA", "scrypt$1024$8$1$$"]
    )
    def test_malformed_hash_raises_value_error(self, bad: str) -> None:
        with pytest.raises(ValueError):
            auth.verify_password(LEARNER_PW, bad)

    def test_needs_rehash_when_parameters_change(self) -> None:
        weak = auth.hash_password(LEARNER_PW, FAST)
        assert auth.needs_rehash(weak) is True, "a hash made with weaker parameters should be upgraded"
        assert auth.needs_rehash(weak, FAST) is False


# ---------------------------------------------------------------------------
# Milestone 2: signed tokens
# ---------------------------------------------------------------------------


class TestMilestone2SignedTokens:
    def test_issue_and_verify_round_trip(self, clock: FakeClock) -> None:
        signer = auth.TokenSigner(TEST_KEY, ttl_seconds=900, clock=clock)
        token = signer.issue("ada", "user")
        assert token.count(".") == 1, "a token is '<payload>.<signature>'"
        now = int(clock.now)
        assert signer.verify(token) == auth.TokenClaims(sub="ada", role="user", iat=now, exp=now + 900)

    def test_token_is_valid_until_it_expires(self, clock: FakeClock) -> None:
        signer = auth.TokenSigner(TEST_KEY, ttl_seconds=900, clock=clock)
        token = signer.issue("ada", "user")
        clock.advance(899)
        assert signer.verify(token).sub == "ada", "the token should still be valid 1 second before expiry"
        clock.advance(1)
        with pytest.raises(auth.ExpiredTokenError):
            signer.verify(token)

    def test_expired_error_is_a_token_error(self) -> None:
        assert issubclass(auth.ExpiredTokenError, auth.TokenError)
        assert issubclass(auth.InvalidTokenError, auth.TokenError)

    def test_tampered_payload_is_rejected(self, clock: FakeClock) -> None:
        signer = auth.TokenSigner(TEST_KEY, clock=clock)
        forged = tamper_role(signer.issue("ada", "user"), "admin")
        with pytest.raises(auth.InvalidTokenError):
            signer.verify(forged)

    def test_tampered_signature_is_rejected(self, clock: FakeClock) -> None:
        signer = auth.TokenSigner(TEST_KEY, clock=clock)
        body, signature = signer.issue("ada", "user").split(".")
        flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
        with pytest.raises(auth.InvalidTokenError):
            signer.verify(f"{body}.{flipped}")

    def test_token_signed_with_another_key_is_rejected(self, clock: FakeClock) -> None:
        mine = auth.TokenSigner(TEST_KEY, clock=clock)
        theirs = auth.TokenSigner(bytes(reversed(range(32))), clock=clock)
        with pytest.raises(auth.InvalidTokenError):
            mine.verify(theirs.issue("ada", "admin"))

    @pytest.mark.parametrize("bad", ["", "abc", "a.b.c", "!!!.???", ".sig", "body.", "é.é"])
    def test_malformed_tokens_are_rejected(self, bad: str, clock: FakeClock) -> None:
        signer = auth.TokenSigner(TEST_KEY, clock=clock)
        with pytest.raises(auth.InvalidTokenError):
            signer.verify(bad)

    def test_signature_check_is_constant_time(self, clock: FakeClock, compare_spy: list) -> None:
        signer = auth.TokenSigner(TEST_KEY, clock=clock)
        signer.verify(signer.issue("ada", "user"))
        assert compare_spy, "compare signatures with hmac.compare_digest, not =="

    def test_short_secret_keys_are_refused(self) -> None:
        with pytest.raises(ValueError, match="32"):
            auth.TokenSigner(b"too short")

    def test_repr_does_not_reveal_the_key(self) -> None:
        signer = auth.TokenSigner(TEST_KEY)
        assert TEST_KEY.hex() not in repr(signer) and str(TEST_KEY) not in repr(signer)


# ---------------------------------------------------------------------------
# Milestone 3: register and log in
# ---------------------------------------------------------------------------


class TestMilestone3RegisterAndLogin:
    def test_register_returns_201_and_public_fields_only(self, client: TestClient) -> None:
        response = register(client, "ada")
        assert response.status_code == 201, f"expected 201 Created, got {response.status_code}"
        assert response.json() == {"username": "ada", "role": "user"}

    def test_register_stores_a_hash_not_the_password(self, client: TestClient, store: auth.UserStore) -> None:
        register(client, "ada")
        user = store.get("ada")
        assert user is not None, "the user should be in the store after registering"
        assert user.password_hash != LEARNER_PW and LEARNER_PW not in user.password_hash
        assert auth.verify_password(LEARNER_PW, user.password_hash)

    def test_duplicate_username_is_409(self, client: TestClient) -> None:
        register(client, "ada")
        response = register(client, "ada", OTHER_PW)
        assert response.status_code == 409, f"expected 409 Conflict, got {response.status_code}"

    @pytest.mark.parametrize(
        ("username", "password"),
        [("ada", "short"), ("Ada Lovelace", LEARNER_PW), ("ab", LEARNER_PW), ("ada", "ada-is-my-password")],
    )
    def test_invalid_registration_is_422(self, client: TestClient, username: str, password: str) -> None:
        response = register(client, username, password)
        assert response.status_code == 422, f"expected 422 for {username!r}/{password!r}"

    def test_validation_errors_do_not_echo_the_password(self, client: TestClient) -> None:
        response = register(client, "ada", "ada-secret-pw")
        assert response.status_code == 422
        assert "ada-secret-pw" not in response.text, "422 bodies must not echo the submitted password"

    def test_clients_cannot_choose_their_role(self, client: TestClient) -> None:
        response = client.post("/register", json={"username": "eve", "password": LEARNER_PW, "role": "admin"})
        assert response.status_code == 422, "unknown fields such as 'role' must be rejected (extra='forbid')"

    def test_login_returns_a_bearer_token(self, client: TestClient, clock: FakeClock) -> None:
        register(client, "ada")
        response = login(client, "ada")
        assert response.status_code == 200, f"expected 200, got {response.status_code}: {response.text}"
        body = response.json()
        assert (body["token_type"], body["expires_in"]) == ("bearer", 900)
        claims = auth.TokenSigner(TEST_KEY, clock=clock).verify(body["access_token"])
        assert (claims.sub, claims.role) == ("ada", "user")

    def test_wrong_password_and_unknown_user_look_identical(self, client: TestClient) -> None:
        register(client, "ada")
        wrong = login(client, "ada", OTHER_PW)
        unknown = login(client, "nobody", OTHER_PW)
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json(), "do not reveal whether the username exists"
        assert wrong.headers.get("www-authenticate", "").startswith("Bearer")

    def test_unknown_user_still_costs_a_hash(self, client: TestClient, compare_spy: list) -> None:
        login(client, "nobody", OTHER_PW)
        assert compare_spy, "verify a dummy hash for unknown users so timing does not reveal who exists"


# ---------------------------------------------------------------------------
# Milestone 4: authentication (401) and authorisation (403)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_token(client: TestClient, store: auth.UserStore) -> str:
    auth.create_user(store, "root", LEARNER_PW, role="admin")
    response = login(client, "root")
    assert response.status_code == 200, "an admin created with create_user should be able to log in"
    return response.json()["access_token"]


class TestMilestone4Authorisation:
    def test_me_without_a_token_is_401_with_challenge(self, client: TestClient) -> None:
        response = client.get("/me")
        assert response.status_code == 401, f"no token means 'who are you?': 401, not {response.status_code}"
        challenge = response.headers.get("www-authenticate", "")
        assert challenge.startswith("Bearer"), "send the header WWW-Authenticate: Bearer"

    def test_me_with_a_valid_token(self, client: TestClient) -> None:
        response = client.get("/me", headers=bearer(token_for(client, "ada")))
        assert response.status_code == 200
        assert response.json() == {"username": "ada", "role": "user"}

    def test_wrong_scheme_is_401(self, client: TestClient) -> None:
        response = client.get("/me", headers={"Authorization": "Basic YWRhOnB3"})
        assert response.status_code == 401

    def test_expired_token_is_401(self, client: TestClient, clock: FakeClock) -> None:
        token = token_for(client, "ada")
        clock.advance(901)
        response = client.get("/me", headers=bearer(token))
        assert response.status_code == 401, "an expired token must be refused"
        assert "invalid_token" in response.headers.get("www-authenticate", "")

    def test_tampered_token_is_401(self, client: TestClient) -> None:
        forged = tamper_role(token_for(client, "ada"), "admin")
        assert client.get("/me", headers=bearer(forged)).status_code == 401

    def test_admin_route_without_token_is_401_not_403(self, client: TestClient) -> None:
        assert client.get("/admin/users").status_code == 401, "unauthenticated is 401, even on admin routes"

    def test_admin_route_as_plain_user_is_403(self, client: TestClient) -> None:
        response = client.get("/admin/users", headers=bearer(token_for(client, "ada")))
        assert response.status_code == 403, f"known user without the role -> 403, got {response.status_code}"

    def test_forged_admin_claim_is_401_not_403(self, client: TestClient) -> None:
        forged = tamper_role(token_for(client, "ada"), "admin")
        assert client.get("/admin/users", headers=bearer(forged)).status_code == 401

    def test_admin_can_list_users(self, client: TestClient, admin_token: str) -> None:
        register(client, "ada")
        response = client.get("/admin/users", headers=bearer(admin_token))
        assert response.status_code == 200
        assert response.json() == [{"username": "ada", "role": "user"}, {"username": "root", "role": "admin"}]

    def test_require_role_is_reusable(self, clock: FakeClock) -> None:
        check = auth.require_role("admin", "user")
        claims = auth.TokenClaims(sub="ada", role="user", iat=0, exp=10)
        assert check(claims) == claims, "require_role(...) should return a dependency that allows these roles"

    def test_app_from_env_fails_fast_without_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(auth.KEY_ENV_VAR, raising=False)
        with pytest.raises(RuntimeError, match=auth.KEY_ENV_VAR):
            auth.app_from_env()
        monkeypatch.setenv(auth.KEY_ENV_VAR, "not-hex")
        with pytest.raises(RuntimeError, match="hex"):
            auth.app_from_env()
        monkeypatch.setenv(auth.KEY_ENV_VAR, TEST_KEY.hex())
        assert auth.app_from_env().title == "Auth demo"
