"""Behaviour tests for the caching demo, grouped by milestone.

Run one milestone with:  python -m pytest -k Milestone1

Nothing here sleeps or reads the real clock: a ``FakeClock`` drives TTLs and a ``RecordingSleep``
replaces ``time.sleep`` in the slow catalogue, so "the source was called" is something we count.
"""

import fnmatch
import logging
import math
import os
import sys
from collections.abc import Iterator

import cache_aside as ca
import pytest
from fastapi.testclient import TestClient

TTL = 30.0


class FakeClock:
    """A controllable monotonic clock: tests move time forward instead of sleeping."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingSleep:
    """Stands in for ``time.sleep``: records each requested delay and returns immediately."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class BrokenCache:
    """A cache whose backend is down: every operation raises, like an unreachable Redis."""

    def get(self, key: str) -> str | None:
        raise ConnectionError("cache is down")

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        raise ConnectionError("cache is down")

    def delete(self, key: str) -> None:
        raise ConnectionError("cache is down")

    def clear(self) -> None:
        raise ConnectionError("cache is down")


class RecordingCache:
    """Wraps a real cache and appends every operation to a shared event log."""

    def __init__(self, inner: ca.InMemoryCache, events: list[str]) -> None:
        self.inner = inner
        self.events = events

    def get(self, key: str) -> str | None:
        self.events.append(f"cache.get {key}")
        return self.inner.get(key)

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        self.events.append(f"cache.set {key}")
        self.inner.set(key, value, ttl_seconds)

    def delete(self, key: str) -> None:
        self.events.append(f"cache.delete {key}")
        self.inner.delete(key)

    def clear(self) -> None:
        self.inner.clear()


class RecordingCatalogue:
    """Wraps a catalogue and logs writes; optionally fails every write."""

    def __init__(self, inner: ca.SlowCatalogue, events: list[str], fail_writes: bool = False) -> None:
        self.inner = inner
        self.events = events
        self.fail_writes = fail_writes

    def get_product(self, product_id: int) -> ca.Product:
        return self.inner.get_product(product_id)

    def update_price(self, product_id: int, price_cents: int) -> ca.Product:
        self.events.append(f"source.update {product_id}")
        if self.fail_writes:
            raise TimeoutError("source write timed out")
        return self.inner.update_price(product_id, price_cents)


class FakeRedisClient:
    """The few ``redis.Redis`` methods RedisCache uses, backed by a dict. Values are stored as bytes."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ttl_ms: dict[str, int] = {}

    def get(self, name: str) -> bytes | None:
        return self.data.get(name)

    def set(self, name: str, value: bytes | str, *, px: int | None = None) -> bool:
        self.data[name] = value if isinstance(value, bytes) else value.encode("utf-8")
        if px is not None:
            self.ttl_ms[name] = px
        return True

    def delete(self, *names: bytes | str) -> int:
        removed = 0
        for raw in names:
            name = raw.decode() if isinstance(raw, bytes) else raw
            removed += int(self.data.pop(name, None) is not None)
            self.ttl_ms.pop(name, None)
        return removed

    def scan_iter(self, match: str = "*") -> Iterator[bytes]:
        for name in list(self.data):
            if fnmatch.fnmatchcase(name, match):
                yield name.encode()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sleep() -> RecordingSleep:
    return RecordingSleep()


@pytest.fixture
def catalogue(sleep: RecordingSleep) -> ca.SlowCatalogue:
    return ca.SlowCatalogue(delay_seconds=0.5, sleep=sleep)


@pytest.fixture
def cache(clock: FakeClock) -> ca.InMemoryCache:
    return ca.InMemoryCache(clock=clock)


@pytest.fixture
def cached(catalogue: ca.SlowCatalogue, cache: ca.InMemoryCache) -> ca.CachedCatalogue:
    return ca.CachedCatalogue(catalogue, cache, ttl_seconds=TTL)


@pytest.fixture
def client(catalogue: ca.SlowCatalogue, cache: ca.InMemoryCache) -> Iterator[TestClient]:
    with TestClient(ca.create_app(catalogue, cache, ttl_seconds=TTL)) as test_client:
        yield test_client


def product_json(product: ca.Product) -> str:
    return product.model_dump_json()


# ---------------------------------------------------------------------------
# Milestone 1: an in-memory TTL cache with an injectable clock
# ---------------------------------------------------------------------------


class TestMilestone1InMemoryCache:
    def test_missing_key_returns_none(self, cache: ca.InMemoryCache) -> None:
        assert cache.get("nope") is None, "get() of a key that was never set should return None"

    def test_set_then_get_returns_the_value(self, cache: ca.InMemoryCache) -> None:
        cache.set("greeting", "hello", TTL)
        assert cache.get("greeting") == "hello"

    def test_entry_is_live_just_before_its_ttl(self, cache: ca.InMemoryCache, clock: FakeClock) -> None:
        cache.set("k", "v", TTL)
        clock.advance(TTL - 0.001)
        assert cache.get("k") == "v", "an entry must still be served while clock() < written_at + ttl"

    def test_entry_expires_exactly_at_its_ttl(self, cache: ca.InMemoryCache, clock: FakeClock) -> None:
        cache.set("k", "v", TTL)
        clock.advance(TTL)
        assert cache.get("k") is None, "an entry is expired once clock() >= written_at + ttl (use >=, not >)"

    def test_overwriting_replaces_value_and_restarts_ttl(
        self, cache: ca.InMemoryCache, clock: FakeClock
    ) -> None:
        cache.set("k", "old", TTL)
        clock.advance(20)
        cache.set("k", "new", TTL)
        clock.advance(20)  # 40 s after the first write, 20 s after the second
        assert cache.get("k") == "new", "set() should store the new value with a fresh TTL"

    def test_expired_entries_are_removed_and_counted(self, cache: ca.InMemoryCache, clock: FakeClock) -> None:
        cache.set("a", "1", TTL)
        cache.set("b", "2", TTL * 2)
        clock.advance(TTL)
        assert len(cache) == 1, "len() should count only live entries"
        stats = cache.stats()
        assert (stats.size, stats.expirations) == (1, 1), f"expected size 1 and 1 expiration, got {stats}"

    def test_delete_removes_a_key_and_ignores_missing_keys(self, cache: ca.InMemoryCache) -> None:
        cache.set("k", "v", TTL)
        cache.delete("k")
        cache.delete("never-set")  # must not raise
        assert cache.get("k") is None

    def test_clear_removes_everything(self, cache: ca.InMemoryCache) -> None:
        for key in ("a", "b", "c"):
            cache.set(key, key, TTL)
        cache.clear()
        assert len(cache) == 0 and cache.get("a") is None

    @pytest.mark.parametrize("bad_ttl", [0, -1, math.nan, math.inf, True])
    def test_rejects_ttls_that_are_not_finite_positive_numbers(
        self, cache: ca.InMemoryCache, bad_ttl: float
    ) -> None:
        with pytest.raises(ValueError, match="ttl"):
            cache.set("k", "v", bad_ttl)

    def test_validate_ttl_returns_a_float(self) -> None:
        assert ca.validate_ttl(5) == 5.0 and isinstance(ca.validate_ttl(5), float)

    def test_rejects_non_string_values(self, cache: ca.InMemoryCache) -> None:
        with pytest.raises(TypeError, match="str"):
            cache.set("k", {"not": "serialised"}, TTL)  # type: ignore[arg-type]

    def test_least_recently_used_entry_is_evicted(self, clock: FakeClock) -> None:
        small = ca.InMemoryCache(clock=clock, max_entries=2)
        small.set("a", "1", TTL)
        small.set("b", "2", TTL)
        small.get("a")  # "a" is now more recently used than "b"
        small.set("c", "3", TTL)
        assert small.get("b") is None, "the least recently *used* entry (b) should have been evicted"
        assert (small.get("a"), small.get("c")) == ("1", "3")
        assert small.stats().evictions == 1

    def test_expired_entries_are_dropped_before_evicting_live_ones(self, clock: FakeClock) -> None:
        small = ca.InMemoryCache(clock=clock, max_entries=2)
        small.set("short", "1", 1)
        small.set("long", "2", TTL)
        clock.advance(2)
        small.set("new", "3", TTL)
        assert small.get("long") == "2", "make room by removing expired entries before evicting live ones"
        assert small.stats().evictions == 0

    def test_max_entries_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="max_entries"):
            ca.InMemoryCache(max_entries=0)

    def test_implements_the_cache_protocol(self, cache: ca.InMemoryCache) -> None:
        assert isinstance(cache, ca.Cache), "InMemoryCache needs get, set, delete and clear"


# ---------------------------------------------------------------------------
# Milestone 2: the cache-aside read path
# ---------------------------------------------------------------------------


class TestMilestone2CacheAsideReads:
    def test_slow_catalogue_sleeps_on_every_call(
        self, catalogue: ca.SlowCatalogue, sleep: RecordingSleep
    ) -> None:
        catalogue.get_product(1)
        catalogue.get_product(1)
        assert sleep.calls == [0.5, 0.5] and catalogue.reads == 2

    def test_miss_calls_the_loader_and_stores_the_value(self, cache: ca.InMemoryCache) -> None:
        calls: list[str] = []

        def loader() -> str:
            calls.append("load")
            return "fresh"

        result = ca.get_or_load(cache, "k", loader, TTL, serialize=str.upper, deserialize=str.lower)
        assert result == ca.Lookup(value="fresh", hit=False)
        assert calls == ["load"]
        assert cache.get("k") == "FRESH", "the serialised value should be stored in the cache"

    def test_hit_returns_the_cached_value_without_calling_the_loader(self, cache: ca.InMemoryCache) -> None:
        cache.set("k", "CACHED", TTL)

        def loader() -> str:
            raise AssertionError("the loader must not be called on a hit")

        result = ca.get_or_load(cache, "k", loader, TTL, serialize=str.upper, deserialize=str.lower)
        assert result == ca.Lookup(value="cached", hit=True)

    def test_loader_errors_propagate_and_are_not_cached(self, cache: ca.InMemoryCache) -> None:
        def loader() -> str:
            raise ca.ProductNotFoundError(9)

        with pytest.raises(ca.ProductNotFoundError):
            ca.get_or_load(cache, "k", loader, TTL, serialize=str, deserialize=str)
        assert cache.get("k") is None, "a failed load must not leave anything in the cache"

    def test_undecodable_entry_is_treated_as_a_miss(self, cache: ca.InMemoryCache) -> None:
        cache.set("product:v1:1", "{not json", TTL)
        result = ca.get_or_load(
            cache,
            "product:v1:1",
            lambda: ca.DEFAULT_PRODUCTS[0],
            TTL,
            serialize=product_json,
            deserialize=ca.Product.model_validate_json,
        )
        assert result.hit is False and result.value == ca.DEFAULT_PRODUCTS[0]
        assert cache.get("product:v1:1") == product_json(ca.DEFAULT_PRODUCTS[0]), (
            "the bad entry should be replaced"
        )

    def test_broken_cache_falls_back_to_the_source_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="cache_aside"):
            result = ca.get_or_load(
                BrokenCache(), "k", lambda: "from source", TTL, serialize=str, deserialize=str
            )
        assert result == ca.Lookup(value="from source", hit=False), "a cache outage must not break reads"
        assert caplog.records, "log a warning when the cache fails, so the outage is visible"
        assert all(record.levelno == logging.WARNING for record in caplog.records)

    def test_repeated_reads_reach_the_slow_source_once(
        self, cached: ca.CachedCatalogue, catalogue: ca.SlowCatalogue, sleep: RecordingSleep
    ) -> None:
        first = cached.get_product(1)
        second = cached.get_product(1)
        third = cached.get_product(1)
        assert first == second == third == ca.DEFAULT_PRODUCTS[0]
        assert catalogue.reads == 1, f"expected 1 read from the source, got {catalogue.reads}"
        assert sleep.calls == [0.5], "only the first read should pay the 0.5 s delay"

    def test_lookup_reports_miss_then_hit(self, cached: ca.CachedCatalogue) -> None:
        assert cached.lookup(2).hit is False
        assert cached.lookup(2).hit is True

    def test_keys_are_namespaced_and_versioned(
        self, cached: ca.CachedCatalogue, cache: ca.InMemoryCache
    ) -> None:
        assert ca.product_key(7) == "product:v1:7"
        cached.get_product(1)
        assert cache.get("product:v1:1") is not None, (
            "CachedCatalogue should store products under product_key(id)"
        )

    def test_cached_value_round_trips_exactly(self, cached: ca.CachedCatalogue) -> None:
        cached.get_product(3)
        hit = cached.lookup(3)
        assert hit.hit and hit.value == ca.DEFAULT_PRODUCTS[2] and isinstance(hit.value, ca.Product)

    def test_not_found_is_not_cached(self, cached: ca.CachedCatalogue, catalogue: ca.SlowCatalogue) -> None:
        for _ in range(2):
            with pytest.raises(ca.ProductNotFoundError):
                cached.get_product(999)
        assert catalogue.reads == 2, "errors must not be cached: each lookup of a missing id asks the source"

    def test_stats_count_hits_and_misses(self, cached: ca.CachedCatalogue) -> None:
        cached.get_product(1)
        cached.get_product(1)
        cached.get_product(1)
        stats = cached.stats()
        assert (stats.hits, stats.misses, stats.size) == (2, 1, 1)
        assert stats.hit_ratio == pytest.approx(2 / 3)

    def test_stats_without_traffic(self, cached: ca.CachedCatalogue) -> None:
        stats = cached.stats()
        assert (stats.hits, stats.misses, stats.hit_ratio) == (0, 0, 0.0), "no lookups means a 0.0 ratio"

    def test_cached_catalogue_survives_a_broken_cache(self, catalogue: ca.SlowCatalogue) -> None:
        cached = ca.CachedCatalogue(catalogue, BrokenCache(), ttl_seconds=TTL)
        assert cached.get_product(1) == ca.DEFAULT_PRODUCTS[0]
        assert cached.stats().size is None, "size is None when the cache cannot report it"

    def test_rejects_invalid_ttl(self, catalogue: ca.SlowCatalogue, cache: ca.InMemoryCache) -> None:
        with pytest.raises(ValueError):
            ca.CachedCatalogue(catalogue, cache, ttl_seconds=0)


# ---------------------------------------------------------------------------
# Milestone 3: invalidation on writes, and expiry
# ---------------------------------------------------------------------------


class TestMilestone3InvalidationAndExpiry:
    def test_update_returns_the_new_price_and_next_read_reloads(
        self, cached: ca.CachedCatalogue, catalogue: ca.SlowCatalogue
    ) -> None:
        cached.get_product(1)
        updated = cached.update_price(1, 7999)
        assert updated.price_cents == 7999
        after = cached.lookup(1)
        assert after.hit is False, "after a write the cached copy must be gone, so the next read is a miss"
        assert after.value.price_cents == 7999
        assert catalogue.reads == 2

    def test_write_goes_to_the_source_before_the_cache_is_invalidated(
        self, catalogue: ca.SlowCatalogue, cache: ca.InMemoryCache
    ) -> None:
        events: list[str] = []
        cached = ca.CachedCatalogue(RecordingCatalogue(catalogue, events), RecordingCache(cache, events), TTL)
        cached.update_price(2, 999)
        assert events == ["source.update 2", "cache.delete product:v1:2"], (
            f"write the source of truth first, then delete the key; got {events}"
        )

    def test_a_failed_write_leaves_the_cache_untouched(
        self, catalogue: ca.SlowCatalogue, cache: ca.InMemoryCache
    ) -> None:
        events: list[str] = []
        cached = ca.CachedCatalogue(RecordingCatalogue(catalogue, events, fail_writes=True), cache, TTL)
        cached.get_product(1)
        with pytest.raises(TimeoutError):
            cached.update_price(1, 1)
        assert cached.lookup(1).hit is True, (
            "if the write fails, keep serving the (still correct) cached copy"
        )

    def test_update_of_unknown_product_raises(self, cached: ca.CachedCatalogue) -> None:
        with pytest.raises(ca.ProductNotFoundError):
            cached.update_price(999, 100)

    def test_invalidation_only_affects_that_product(self, cached: ca.CachedCatalogue) -> None:
        cached.get_product(1)
        cached.get_product(2)
        cached.update_price(1, 5000)
        assert cached.lookup(2).hit is True, "updating product 1 must not evict product 2"

    def test_entry_is_served_until_the_ttl(self, cached: ca.CachedCatalogue, clock: FakeClock) -> None:
        cached.get_product(1)
        clock.advance(TTL - 0.1)
        assert cached.lookup(1).hit is True

    def test_entry_is_reloaded_after_the_ttl(
        self, cached: ca.CachedCatalogue, catalogue: ca.SlowCatalogue, clock: FakeClock
    ) -> None:
        cached.get_product(1)
        clock.advance(TTL)
        assert cached.lookup(1).hit is False, "after the TTL the entry is expired and must be reloaded"
        assert catalogue.reads == 2

    def test_ttl_bounds_staleness_after_an_out_of_band_change(
        self, cached: ca.CachedCatalogue, catalogue: ca.SlowCatalogue, clock: FakeClock
    ) -> None:
        cached.get_product(1)
        catalogue.update_price(1, 1)  # someone changed the source directly, bypassing invalidation
        assert cached.get_product(1).price_cents == ca.DEFAULT_PRODUCTS[0].price_cents, "stale until the TTL"
        clock.advance(TTL)
        assert cached.get_product(1).price_cents == 1, "after the TTL the new price must appear"

    def test_failed_invalidation_does_not_fail_the_write(
        self, catalogue: ca.SlowCatalogue, caplog: pytest.LogCaptureFixture
    ) -> None:
        cached = ca.CachedCatalogue(catalogue, BrokenCache(), TTL)
        with caplog.at_level(logging.WARNING, logger="cache_aside"):
            updated = cached.update_price(1, 4242)
        assert updated.price_cents == 4242, "the source write succeeded, so the update must succeed"
        assert caplog.records, "a failed invalidation should be logged: the entry may be stale until its TTL"


# ---------------------------------------------------------------------------
# Milestone 4: the HTTP layer
# ---------------------------------------------------------------------------


class TestMilestone4HttpLayer:
    def test_first_read_is_a_miss_and_second_is_a_hit(self, client: TestClient) -> None:
        first = client.get("/products/1")
        second = client.get("/products/1")
        assert first.status_code == 200 and second.status_code == 200
        assert first.headers.get("x-cache") == "MISS", "the first read should report X-Cache: MISS"
        assert second.headers.get("x-cache") == "HIT", "the second read should report X-Cache: HIT"
        assert first.json() == second.json() == {"id": 1, "name": "Mechanical keyboard", "price_cents": 8999}

    def test_repeated_requests_reach_the_source_once(
        self, client: TestClient, catalogue: ca.SlowCatalogue, sleep: RecordingSleep
    ) -> None:
        for _ in range(5):
            client.get("/products/2")
        assert catalogue.reads == 1 and sleep.calls == [0.5]

    def test_unknown_product_is_404_and_not_cached(
        self, client: TestClient, catalogue: ca.SlowCatalogue
    ) -> None:
        for _ in range(2):
            response = client.get("/products/999")
            assert response.status_code == 404
            assert response.json() == {"detail": "product 999 not found"}
        assert catalogue.reads == 2

    @pytest.mark.parametrize("bad_id", ["0", "-3", "abc"])
    def test_invalid_product_id_is_422(self, client: TestClient, bad_id: str) -> None:
        assert client.get(f"/products/{bad_id}").status_code == 422

    def test_put_price_updates_and_invalidates(self, client: TestClient) -> None:
        client.get("/products/1")
        response = client.put("/products/1/price", json={"price_cents": 7999})
        assert response.status_code == 200 and response.json()["price_cents"] == 7999
        after = client.get("/products/1")
        assert after.headers.get("x-cache") == "MISS", "a PUT must invalidate the cached product"
        assert after.json()["price_cents"] == 7999

    @pytest.mark.parametrize(
        "body",
        [
            {"price_cents": -1},
            {"price_cents": "12"},
            {"price_cents": 12.5},
            {},
            {"price_cents": 1, "name": "x"},
        ],
    )
    def test_put_price_validates_the_body(self, client: TestClient, body: dict[str, object]) -> None:
        assert client.put("/products/1/price", json=body).status_code == 422

    def test_put_price_for_unknown_product_is_404(self, client: TestClient) -> None:
        assert client.put("/products/999/price", json={"price_cents": 1}).status_code == 404

    def test_stats_endpoint(self, client: TestClient) -> None:
        client.get("/products/1")
        client.get("/products/1")
        client.get("/products/2")
        stats = client.get("/cache/stats")
        assert stats.status_code == 200
        body = stats.json()
        assert {k: body[k] for k in ("hits", "misses", "size")} == {"hits": 1, "misses": 2, "size": 2}
        assert body["hit_ratio"] == pytest.approx(1 / 3)

    def test_expiry_through_the_api(self, catalogue: ca.SlowCatalogue, clock: FakeClock) -> None:
        app = ca.create_app(catalogue, ca.InMemoryCache(clock=clock), ttl_seconds=10)
        with TestClient(app) as test_client:
            test_client.get("/products/3")
            clock.advance(10)
            assert test_client.get("/products/3").headers.get("x-cache") == "MISS"

    def test_default_wiring_uses_injected_clock_and_sleep(
        self, clock: FakeClock, sleep: RecordingSleep
    ) -> None:
        with TestClient(ca.create_app(clock=clock, sleep=sleep)) as test_client:
            assert test_client.get("/products/1").headers.get("x-cache") == "MISS"
            assert test_client.get("/products/1").headers.get("x-cache") == "HIT"
            clock.advance(30)
            assert test_client.get("/products/1").headers.get("x-cache") == "MISS", "default TTL is 30 s"
        assert sleep.calls == [0.5, 0.5], "create_app() should build SlowCatalogue(sleep=sleep) by default"

    def test_each_app_has_its_own_cache(self, clock: FakeClock, sleep: RecordingSleep) -> None:
        with TestClient(ca.create_app(clock=clock, sleep=sleep)) as one:
            one.get("/products/1")
        with TestClient(ca.create_app(clock=clock, sleep=sleep)) as two:
            assert two.get("/products/1").headers.get("x-cache") == "MISS", (
                "no global cache shared between apps"
            )


# ---------------------------------------------------------------------------
# Milestone 5: Redis behind the same interface (fake client; the real server is optional)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> FakeRedisClient:
    return FakeRedisClient()


@pytest.fixture
def redis_cache(fake_redis: FakeRedisClient) -> ca.RedisCache:
    return ca.RedisCache(fake_redis, namespace="caching-demo:")


class TestMilestone5RedisAdapter:
    def test_implements_the_cache_protocol(self, redis_cache: ca.RedisCache) -> None:
        assert isinstance(redis_cache, ca.Cache)

    def test_set_uses_a_namespaced_key_and_px_milliseconds(
        self, redis_cache: ca.RedisCache, fake_redis: FakeRedisClient
    ) -> None:
        redis_cache.set("product:v1:1", "hello", TTL)
        assert fake_redis.data == {"caching-demo:product:v1:1": b"hello"}, "prefix keys with the namespace"
        assert fake_redis.ttl_ms == {"caching-demo:product:v1:1": 30_000}, "pass the TTL as px=milliseconds"

    @pytest.mark.parametrize(("ttl", "expected_ms"), [(0.25, 250), (0.0001, 1), (2, 2000)])
    def test_ttl_is_converted_to_at_least_one_millisecond(
        self, redis_cache: ca.RedisCache, fake_redis: FakeRedisClient, ttl: float, expected_ms: int
    ) -> None:
        redis_cache.set("k", "v", ttl)
        assert fake_redis.ttl_ms["caching-demo:k"] == expected_ms

    def test_get_decodes_bytes_and_returns_none_when_missing(
        self, redis_cache: ca.RedisCache, fake_redis: FakeRedisClient
    ) -> None:
        fake_redis.data["caching-demo:k"] = "héllo".encode()
        assert redis_cache.get("k") == "héllo", "decode the bytes Redis returns as UTF-8"
        assert redis_cache.get("missing") is None

    def test_delete_uses_the_namespaced_key(
        self, redis_cache: ca.RedisCache, fake_redis: FakeRedisClient
    ) -> None:
        redis_cache.set("k", "v", TTL)
        redis_cache.delete("k")
        redis_cache.delete("never-set")
        assert fake_redis.data == {}

    def test_clear_deletes_only_this_namespace(
        self, redis_cache: ca.RedisCache, fake_redis: FakeRedisClient
    ) -> None:
        fake_redis.data["other-app:session"] = b"keep me"
        redis_cache.set("a", "1", TTL)
        redis_cache.set("b", "2", TTL)
        redis_cache.clear()
        assert fake_redis.data == {"other-app:session": b"keep me"}, "never delete another app's keys"

    def test_len_counts_only_this_namespace(
        self, redis_cache: ca.RedisCache, fake_redis: FakeRedisClient
    ) -> None:
        fake_redis.data["other-app:x"] = b"1"
        redis_cache.set("a", "1", TTL)
        assert len(redis_cache) == 1

    @pytest.mark.parametrize("bad_ttl", [0, -5, math.inf])
    def test_rejects_bad_ttls(self, redis_cache: ca.RedisCache, bad_ttl: float) -> None:
        with pytest.raises(ValueError):
            redis_cache.set("k", "v", bad_ttl)

    @pytest.mark.parametrize("namespace", ["", "has space:", "glob*:"])
    def test_rejects_unsafe_namespaces(self, fake_redis: FakeRedisClient, namespace: str) -> None:
        with pytest.raises(ValueError, match="namespace"):
            ca.RedisCache(fake_redis, namespace=namespace)

    def test_works_behind_cached_catalogue(
        self, redis_cache: ca.RedisCache, catalogue: ca.SlowCatalogue
    ) -> None:
        cached = ca.CachedCatalogue(catalogue, redis_cache, ttl_seconds=TTL)
        assert cached.lookup(1).hit is False
        assert cached.lookup(1).hit is True, "the same cache-aside code must work with any Cache"
        assert catalogue.reads == 1
        assert cached.stats().size == 1

    def test_from_url_without_the_package_explains_how_to_install(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "redis", None)  # makes `import redis` raise ImportError
        with pytest.raises(RuntimeError, match="pip install redis"):
            ca.RedisCache.from_url("redis://localhost:6379/0")


@pytest.mark.network
class TestOptionalRealRedis:
    """Runs only with `python -m pytest -m network`, the `redis` package, and a reachable server."""

    @pytest.fixture
    def real_cache(self) -> Iterator[ca.RedisCache]:
        redis = pytest.importorskip("redis")
        url = os.environ.get("GW_REDIS_URL", "redis://localhost:6379/0")
        cache = ca.RedisCache.from_url(url, namespace="caching-demo-test:")
        try:
            cache.clear()
        except redis.RedisError:
            pytest.skip(f"no Redis server reachable at {url}")
        yield cache
        cache.clear()

    def test_round_trip_and_delete(self, real_cache: ca.RedisCache) -> None:
        real_cache.set("k", "value", TTL)
        assert real_cache.get("k") == "value"
        real_cache.delete("k")
        assert real_cache.get("k") is None

    def test_cached_catalogue_against_real_redis(
        self, real_cache: ca.RedisCache, catalogue: ca.SlowCatalogue
    ) -> None:
        cached = ca.CachedCatalogue(catalogue, real_cache, ttl_seconds=TTL)
        assert [cached.lookup(1).hit, cached.lookup(1).hit] == [False, True]
