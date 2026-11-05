"""Caching demo: a cache-aside layer with TTL and invalidation in front of a deliberately slow source.

The pieces, from the bottom up:

* ``SlowCatalogue`` stands in for a slow upstream (a remote API, a heavy SQL query). Every call
  costs ``delay_seconds`` through an injected ``sleep`` function, so tests can count calls instead
  of waiting.
* ``Cache`` is the interface every cache implements: string values, a TTL on every ``set``.
  ``InMemoryCache`` (TTL + LRU, injectable clock) and ``RedisCache`` (optional) implement it.
* ``get_or_load`` is the cache-aside read path; ``CachedCatalogue`` uses it for reads and
  invalidates (deletes) entries after writes.
* ``create_app`` exposes it over HTTP with an ``X-Cache: HIT|MISS`` header.

Run it locally::

    python -m uvicorn --factory cache_aside:create_app --app-dir solution --reload

then request ``/products/1`` twice: the first answer takes about half a second (``MISS``), the
second is immediate (``HIT``).
"""

import logging
import math
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Generic, Protocol, TypeVar, runtime_checkable

from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("cache_aside")

Clock = Callable[[], float]
"""Returns monotonic seconds (``time.monotonic``). Injected so tests can move time forward."""

Sleep = Callable[[float], None]
"""Blocks for a number of seconds (``time.sleep``). Injected so tests never really wait."""

T = TypeVar("T")


# ---------------------------------------------------------------------------
# The slow source of truth (provided)
# ---------------------------------------------------------------------------


class Product(BaseModel):
    """A catalogue entry. Prices are integer cents, so JSON round-trips are exact."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    price_cents: int = Field(ge=0)


class PriceUpdate(BaseModel):
    """Body of ``PUT /products/{id}/price``."""

    model_config = ConfigDict(extra="forbid")

    price_cents: int = Field(ge=0, le=100_000_000, strict=True, examples=[1299])


class ProductNotFoundError(LookupError):
    """The source has no product with this id."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"product {product_id} not found")
        self.product_id = product_id


@runtime_checkable
class Catalogue(Protocol):
    """Anything that can read and update products: the slow source, or a cached wrapper around it."""

    def get_product(self, product_id: int) -> Product:
        """Return the product or raise ``ProductNotFoundError``."""
        ...

    def update_price(self, product_id: int, price_cents: int) -> Product:
        """Change the price and return the updated product, or raise ``ProductNotFoundError``."""
        ...


DEFAULT_PRODUCTS: tuple[Product, ...] = (
    Product(id=1, name="Mechanical keyboard", price_cents=8999),
    Product(id=2, name="USB-C cable", price_cents=1299),
    Product(id=3, name="27-inch monitor", price_cents=24900),
)


class SlowCatalogue:
    """An in-memory catalogue that pretends to be slow: every call sleeps ``delay_seconds`` first.

    ``reads`` and ``writes`` count the calls that reached the source, which is what caching saves.
    """

    def __init__(
        self,
        products: Iterable[Product] = DEFAULT_PRODUCTS,
        *,
        delay_seconds: float = 0.5,
        sleep: Sleep = time.sleep,
    ) -> None:
        self._products = {product.id: product for product in products}
        self._delay_seconds = delay_seconds
        self._sleep = sleep
        self._lock = threading.Lock()
        self.reads = 0
        self.writes = 0

    def get_product(self, product_id: int) -> Product:
        """Return the product after the simulated delay."""
        with self._lock:
            self.reads += 1
        self._sleep(self._delay_seconds)
        with self._lock:
            product = self._products.get(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    def update_price(self, product_id: int, price_cents: int) -> Product:
        """Store a new price after the simulated delay and return the updated product."""
        with self._lock:
            self.writes += 1
        self._sleep(self._delay_seconds)
        with self._lock:
            current = self._products.get(product_id)
            if current is None:
                raise ProductNotFoundError(product_id)
            updated = current.model_copy(update={"price_cents": price_cents})
            self._products[product_id] = updated
        return updated


# ---------------------------------------------------------------------------
# Milestone 1: the cache interface and an in-memory TTL + LRU cache
# ---------------------------------------------------------------------------


@runtime_checkable
class Cache(Protocol):
    """A key-value cache of strings. Every entry has a time to live (TTL)."""

    def get(self, key: str) -> str | None:
        """Return the value, or ``None`` if the key is missing or expired."""
        ...

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        """Store ``value`` for ``ttl_seconds`` (must be > 0), replacing any previous value."""
        ...

    def delete(self, key: str) -> None:
        """Remove the key if present (deleting a missing key is not an error)."""
        ...

    def clear(self) -> None:
        """Remove every entry this cache owns."""
        ...


def validate_ttl(ttl_seconds: float) -> float:
    """Return ``ttl_seconds`` if it is a finite number greater than zero, else raise ``ValueError``."""
    is_number = isinstance(ttl_seconds, int | float) and not isinstance(ttl_seconds, bool)
    if not (is_number and math.isfinite(ttl_seconds) and ttl_seconds > 0):
        raise ValueError(f"ttl_seconds must be a finite number greater than 0, got {ttl_seconds!r}")
    return float(ttl_seconds)


@dataclass(frozen=True)
class MemoryCacheStats:
    """Housekeeping counters for ``InMemoryCache``."""

    size: int
    evictions: int
    expirations: int


class InMemoryCache:
    """A thread-safe in-process cache with per-entry TTL and least-recently-used eviction.

    An entry written at time ``t`` with TTL ``ttl`` is live while ``clock() < t + ttl`` and expired
    from ``t + ttl`` on. Expired entries are removed lazily, when they are next touched (or when
    space is needed), so no background thread is required.
    """

    def __init__(self, clock: Clock = time.monotonic, max_entries: int = 1024) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be at least 1, got {max_entries}")
        self._clock = clock
        self._max_entries = max_entries
        self._entries: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._evictions = 0
        self._expirations = 0

    def get(self, key: str) -> str | None:
        """Return the live value for ``key`` and mark it as recently used, else ``None``."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._clock() >= expires_at:
                del self._entries[key]
                self._expirations += 1
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        """Store ``value`` until ``clock() + ttl_seconds``; evict if the cache is over capacity."""
        ttl = validate_ttl(ttl_seconds)
        if not isinstance(value, str):
            raise TypeError(f"cache values must be str (serialise first), got {type(value).__name__}")
        with self._lock:
            self._entries[key] = (value, self._clock() + ttl)
            self._entries.move_to_end(key)
            if len(self._entries) > self._max_entries:
                self._purge_expired()
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
                self._evictions += 1

    def delete(self, key: str) -> None:
        """Remove ``key`` if present."""
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """Remove every entry."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """Number of live (unexpired) entries."""
        with self._lock:
            self._purge_expired()
            return len(self._entries)

    def stats(self) -> MemoryCacheStats:
        """Current size and how many entries were evicted (LRU) or expired so far."""
        size = len(self)
        with self._lock:
            return MemoryCacheStats(size=size, evictions=self._evictions, expirations=self._expirations)

    def _purge_expired(self) -> None:
        """Drop every expired entry. The caller must hold the lock."""
        now = self._clock()
        expired = [key for key, (_, expires_at) in self._entries.items() if now >= expires_at]
        for key in expired:
            del self._entries[key]
        self._expirations += len(expired)


# ---------------------------------------------------------------------------
# Milestone 2: the cache-aside read path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lookup(Generic[T]):
    """The result of a cache-aside read: the value, and whether it came from the cache."""

    value: T
    hit: bool


def _safe_get(cache: Cache, key: str) -> str | None:
    """``cache.get`` that treats any cache failure as a miss (the cache is an optimisation)."""
    try:
        return cache.get(key)
    except Exception as exc:  # fail open: a broken cache must not break reads
        logger.warning("cache get failed for %s (%s); reading from the source", key, type(exc).__name__)
        return None


def _safe_set(cache: Cache, key: str, value: str, ttl_seconds: float) -> None:
    """``cache.set`` that logs and ignores cache failures. Values are never logged."""
    try:
        cache.set(key, value, ttl_seconds)
    except Exception as exc:  # fail open: the value is still returned to the caller
        logger.warning("cache set failed for %s (%s); value not cached", key, type(exc).__name__)


def _safe_delete(cache: Cache, key: str) -> None:
    """``cache.delete`` that logs cache failures. The TTL bounds how long a stale entry can survive."""
    try:
        cache.delete(key)
    except Exception as exc:  # the write already succeeded; staleness is bounded by the TTL
        logger.warning(
            "cache delete failed for %s (%s); entry may be stale until its TTL", key, type(exc).__name__
        )


def get_or_load(
    cache: Cache,
    key: str,
    loader: Callable[[], T],
    ttl_seconds: float,
    serialize: Callable[[T], str],
    deserialize: Callable[[str], T],
) -> Lookup[T]:
    """Cache-aside read: return the cached value, or load it from the source and cache it.

    * **hit**: the cached string is deserialised and returned; ``loader`` is not called.
    * **miss**: ``loader()`` is called; its result is serialised and stored for ``ttl_seconds``.
      If ``loader`` raises, the exception propagates and nothing is cached.
    * a cached string that cannot be deserialised (corrupt, or written by an older version) is
      deleted and treated as a miss.
    * if the cache itself fails, the read still succeeds from the source (logged as a warning).
    """
    ttl = validate_ttl(ttl_seconds)
    cached = _safe_get(cache, key)
    if cached is not None:
        try:
            return Lookup(value=deserialize(cached), hit=True)
        except ValueError:  # includes pydantic.ValidationError and json.JSONDecodeError
            logger.warning("discarding undecodable cache entry %s", key)
            _safe_delete(cache, key)
    value = loader()
    _safe_set(cache, key, serialize(value), ttl)
    return Lookup(value=value, hit=False)


KEY_VERSION = "v1"
"""Bump when the cached format changes, so old entries are simply never read again."""


def product_key(product_id: int) -> str:
    """The cache key for one product, e.g. ``product:v1:42``."""
    return f"product:{KEY_VERSION}:{product_id}"


class CacheStatsReport(BaseModel):
    """What ``GET /cache/stats`` returns."""

    hits: int
    misses: int
    hit_ratio: float
    size: int | None = Field(description="Live entries, or null if the cache cannot report its size.")


def _cache_size(cache: Cache) -> int | None:
    """``len(cache)`` if the cache supports it and is reachable, else ``None``."""
    try:
        return len(cache)  # type: ignore[arg-type]
    except Exception:  # TypeError (no __len__) or an unreachable backend
        return None


class CachedCatalogue:
    """A ``Catalogue`` that answers reads from a cache and invalidates entries after writes."""

    def __init__(self, backend: Catalogue, cache: Cache, ttl_seconds: float = 30.0) -> None:
        self._backend = backend
        self._cache = cache
        self._ttl_seconds = validate_ttl(ttl_seconds)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def lookup(self, product_id: int) -> Lookup[Product]:
        """Read through the cache and say whether it was a hit. Not-found errors are not cached."""

        def load_from_source() -> Product:
            self._count(hit=False)
            return self._backend.get_product(product_id)

        result = get_or_load(
            self._cache,
            product_key(product_id),
            load_from_source,
            self._ttl_seconds,
            serialize=lambda product: product.model_dump_json(),
            deserialize=Product.model_validate_json,
        )
        if result.hit:
            self._count(hit=True)
        return result

    def get_product(self, product_id: int) -> Product:
        """``Catalogue.get_product`` through the cache."""
        return self.lookup(product_id).value

    def update_price(self, product_id: int, price_cents: int) -> Product:
        """Write to the source of truth first, then delete the cached copy.

        If the write fails, the exception propagates and the cache is left alone. Deleting (rather
        than writing the new value into the cache) avoids racing a concurrent reader that could put
        an older value back after ours.
        """
        updated = self._backend.update_price(product_id, price_cents)
        self.invalidate(product_id)
        return updated

    def invalidate(self, product_id: int) -> None:
        """Drop the cached copy of one product; the next read reloads it."""
        _safe_delete(self._cache, product_key(product_id))

    def stats(self) -> CacheStatsReport:
        """Hits, misses and hit ratio since start-up, plus the cache's size if it can report it."""
        with self._lock:
            hits, misses = self._hits, self._misses
        total = hits + misses
        return CacheStatsReport(
            hits=hits,
            misses=misses,
            hit_ratio=hits / total if total else 0.0,
            size=_cache_size(self._cache),
        )

    def _count(self, *, hit: bool) -> None:
        with self._lock:
            if hit:
                self._hits += 1
            else:
                self._misses += 1


# ---------------------------------------------------------------------------
# Milestone 4: the HTTP layer
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Error body, e.g. ``{"detail": "product 9 not found"}``."""

    detail: str


def get_cached_catalogue(request: Request) -> CachedCatalogue:
    """Dependency: the ``CachedCatalogue`` that belongs to this app instance."""
    return request.app.state.cached_catalogue


CachedCatalogueDep = Annotated[CachedCatalogue, Depends(get_cached_catalogue)]
ProductId = Annotated[int, Path(ge=1, description="Product id (a positive integer).")]


def _add_routes(app: FastAPI) -> None:
    """Register the product and cache endpoints on ``app``."""

    @app.get(
        "/products/{product_id}",
        response_model=Product,
        summary="Read a product (cache-aside)",
        responses={404: {"model": ErrorResponse}},
    )
    def read_product(product_id: ProductId, response: Response, catalogue: CachedCatalogueDep) -> Product:
        try:
            result = catalogue.lookup(product_id)
        except ProductNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        response.headers["X-Cache"] = "HIT" if result.hit else "MISS"
        return result.value

    @app.put(
        "/products/{product_id}/price",
        response_model=Product,
        summary="Change a price and invalidate the cached copy",
        responses={404: {"model": ErrorResponse}},
    )
    def update_price(product_id: ProductId, body: PriceUpdate, catalogue: CachedCatalogueDep) -> Product:
        try:
            return catalogue.update_price(product_id, body.price_cents)
        except ProductNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/cache/stats", response_model=CacheStatsReport, summary="Cache hit/miss statistics")
    def cache_stats(catalogue: CachedCatalogueDep) -> CacheStatsReport:
        return catalogue.stats()


def create_app(
    catalogue: Catalogue | None = None,
    cache: Cache | None = None,
    ttl_seconds: float = 30.0,
    *,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> FastAPI:
    """Build the API. Everything stateful is injected, which is what makes the tests deterministic.

    Defaults: a ``SlowCatalogue`` using ``sleep`` and an ``InMemoryCache`` using ``clock``.
    """
    source = catalogue if catalogue is not None else SlowCatalogue(sleep=sleep)
    store = cache if cache is not None else InMemoryCache(clock=clock)
    app = FastAPI(
        title="Caching demo",
        version="1.0.0",
        description="A cache-aside layer with TTL and invalidation in front of a slow catalogue.",
    )
    app.state.cached_catalogue = CachedCatalogue(source, store, ttl_seconds)
    _add_routes(app)
    return app


# ---------------------------------------------------------------------------
# Milestone 5: Redis behind the same interface (optional extra: python -m pip install redis)
# ---------------------------------------------------------------------------


class RedisLike(Protocol):
    """The subset of the ``redis.Redis`` client that ``RedisCache`` uses."""

    def get(self, name: str) -> bytes | str | None: ...

    def set(self, name: str, value: bytes | str, *, px: int) -> object: ...

    def delete(self, *names: bytes | str) -> object: ...

    def scan_iter(self, match: str) -> Iterable[bytes | str]: ...


NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


class RedisCache:
    """A ``Cache`` backed by Redis. Keys are prefixed with ``namespace`` so apps can share a server.

    Redis expires keys itself (``SET ... PX <milliseconds>``), so no clock is needed here.
    """

    def __init__(self, client: RedisLike, namespace: str = "caching-demo:") -> None:
        if not NAMESPACE_PATTERN.fullmatch(namespace):
            raise ValueError(
                f"namespace must be non-empty and use only letters, digits and _ . : - (got {namespace!r})"
            )
        self._client = client
        self._namespace = namespace

    @classmethod
    def from_url(
        cls,
        url: str = "redis://localhost:6379/0",
        namespace: str = "caching-demo:",
        timeout_seconds: float = 0.5,
    ) -> "RedisCache":
        """Connect with the optional ``redis`` package (imported here, so it stays optional)."""
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "RedisCache needs the optional 'redis' package: python -m pip install redis"
            ) from exc
        client = redis.Redis.from_url(
            url, socket_timeout=timeout_seconds, socket_connect_timeout=timeout_seconds
        )
        return cls(client, namespace)

    def _key(self, key: str) -> str:
        return self._namespace + key

    def get(self, key: str) -> str | None:
        """Return the value (decoded from UTF-8 bytes), or ``None`` if missing or expired."""
        raw = self._client.get(self._key(key))
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        """``SET namespace+key value PX ttl_ms`` (at least 1 ms)."""
        ttl = validate_ttl(ttl_seconds)
        if not isinstance(value, str):
            raise TypeError(f"cache values must be str (serialise first), got {type(value).__name__}")
        self._client.set(self._key(key), value.encode("utf-8"), px=max(1, round(ttl * 1000)))

    def delete(self, key: str) -> None:
        """``DEL namespace+key``."""
        self._client.delete(self._key(key))

    def clear(self) -> None:
        """Delete only this namespace's keys (never ``FLUSHDB``: other apps may share the server)."""
        keys = list(self._client.scan_iter(match=self._namespace + "*"))
        if keys:
            self._client.delete(*keys)

    def __len__(self) -> int:
        """Number of keys in this namespace (uses ``SCAN``, so it is O(keys); fine for a demo)."""
        return sum(1 for _ in self._client.scan_iter(match=self._namespace + "*"))
