"""Caching demo: a cache-aside layer with TTL and invalidation in front of a deliberately slow source.

The pieces, from the bottom up:

* ``SlowCatalogue`` (provided) stands in for a slow upstream (a remote API, a heavy SQL query).
  Every call costs ``delay_seconds`` through an injected ``sleep`` function, so tests can count
  calls instead of waiting.
* ``Cache`` (provided) is the interface every cache implements: string values, a TTL on every
  ``set``. You implement ``InMemoryCache`` (milestone 1) and ``RedisCache`` (milestone 5).
* ``get_or_load`` is the cache-aside read path (milestone 2); ``CachedCatalogue`` uses it for reads
  and invalidates entries after writes (milestone 3).
* ``create_app`` exposes it over HTTP with an ``X-Cache: HIT|MISS`` header (milestone 4).

Work through the ``TODO(milestone N)`` markers in order and run ``python -m pytest -k MilestoneN``.

Run it locally::

    python -m uvicorn --factory cache_aside:create_app --app-dir starter --reload
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
# The slow source of truth (provided -- read it, you do not need to change it)
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
    # TODO(milestone 1): accept ints and floats (but not bools: True is an int in Python!) that are
    # finite (math.isfinite) and > 0, and return them as float. Otherwise raise
    # ValueError(f"ttl_seconds must be a finite number greater than 0, got {ttl_seconds!r}").
    raise NotImplementedError("TODO(milestone 1): validate_ttl")


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
        # key -> (value, expires_at). OrderedDict remembers order: oldest-used first, newest-used last.
        self._entries: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._evictions = 0
        self._expirations = 0

    def get(self, key: str) -> str | None:
        """Return the live value for ``key`` and mark it as recently used, else ``None``."""
        # TODO(milestone 1): under self._lock, look the key up. If it is expired
        # (self._clock() >= expires_at), delete it, count an expiration and return None.
        # Otherwise self._entries.move_to_end(key) (now most recently used) and return the value.
        raise NotImplementedError("TODO(milestone 1): InMemoryCache.get")

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        """Store ``value`` until ``clock() + ttl_seconds``; evict if the cache is over capacity."""
        # TODO(milestone 1):
        #   1. ttl = validate_ttl(ttl_seconds); raise TypeError if value is not a str
        #   2. under the lock, store (value, now + ttl) and move the key to the end
        #   3. if over max_entries: first self._purge_expired(), then popitem(last=False) (the least
        #      recently used) until the size fits, counting each eviction
        raise NotImplementedError("TODO(milestone 1): InMemoryCache.set")

    def delete(self, key: str) -> None:
        """Remove ``key`` if present."""
        raise NotImplementedError("TODO(milestone 1): InMemoryCache.delete")

    def clear(self) -> None:
        """Remove every entry."""
        raise NotImplementedError("TODO(milestone 1): InMemoryCache.clear")

    def __len__(self) -> int:
        """Number of live (unexpired) entries."""
        # TODO(milestone 1): purge expired entries (under the lock), then return the size.
        raise NotImplementedError("TODO(milestone 1): InMemoryCache.__len__")

    def stats(self) -> MemoryCacheStats:
        """Current size and how many entries were evicted (LRU) or expired so far."""
        raise NotImplementedError("TODO(milestone 1): InMemoryCache.stats")

    def _purge_expired(self) -> None:
        """Drop every expired entry. The caller must hold the lock."""
        # TODO(milestone 1): collect the expired keys first (do not delete while iterating), then
        # delete them and add how many there were to self._expirations.
        raise NotImplementedError("TODO(milestone 1): InMemoryCache._purge_expired")


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
    # TODO(milestone 2): try cache.get(key); on any Exception log a warning with the key and the
    # exception type (never the cached value) and return None.
    raise NotImplementedError("TODO(milestone 2): _safe_get")


def _safe_set(cache: Cache, key: str, value: str, ttl_seconds: float) -> None:
    """``cache.set`` that logs and ignores cache failures. Values are never logged."""
    raise NotImplementedError("TODO(milestone 2): _safe_set")


def _safe_delete(cache: Cache, key: str) -> None:
    """``cache.delete`` that logs cache failures. The TTL bounds how long a stale entry can survive."""
    raise NotImplementedError("TODO(milestone 2): _safe_delete")


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
    # TODO(milestone 2):
    #   1. ttl = validate_ttl(ttl_seconds)
    #   2. cached = _safe_get(cache, key); if not None, try to return Lookup(deserialize(cached), hit=True)
    #      -- catch ValueError (pydantic's ValidationError is one), log, _safe_delete and fall through
    #   3. value = loader()  (let exceptions propagate: errors are not cached)
    #   4. _safe_set(cache, key, serialize(value), ttl) and return Lookup(value, hit=False)
    raise NotImplementedError("TODO(milestone 2): get_or_load")


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
        # TODO(milestone 2): call get_or_load with product_key(product_id), a loader that counts a
        # miss and calls self._backend.get_product(product_id), self._ttl_seconds,
        # serialize=lambda p: p.model_dump_json() and deserialize=Product.model_validate_json.
        # Count a hit when result.hit is True.
        raise NotImplementedError("TODO(milestone 2): CachedCatalogue.lookup")

    def get_product(self, product_id: int) -> Product:
        """``Catalogue.get_product`` through the cache."""
        return self.lookup(product_id).value

    def update_price(self, product_id: int, price_cents: int) -> Product:
        """Write to the source of truth first, then delete the cached copy.

        If the write fails, the exception propagates and the cache is left alone. Deleting (rather
        than writing the new value into the cache) avoids racing a concurrent reader that could put
        an older value back after ours.
        """
        raise NotImplementedError("TODO(milestone 3): CachedCatalogue.update_price")

    def invalidate(self, product_id: int) -> None:
        """Drop the cached copy of one product; the next read reloads it."""
        raise NotImplementedError("TODO(milestone 3): CachedCatalogue.invalidate")

    def stats(self) -> CacheStatsReport:
        """Hits, misses and hit ratio since start-up, plus the cache's size if it can report it."""
        # TODO(milestone 2): read the counters under the lock; hit_ratio is hits / (hits + misses),
        # or 0.0 when there were no lookups; size=_cache_size(self._cache).
        raise NotImplementedError("TODO(milestone 2): CachedCatalogue.stats")

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
        # TODO(milestone 4): result = catalogue.lookup(product_id); turn ProductNotFoundError into
        # HTTPException(404, detail=str(exc)); set response.headers["X-Cache"] to "HIT" or "MISS".
        raise NotImplementedError("TODO(milestone 4): GET /products/{product_id}")

    @app.put(
        "/products/{product_id}/price",
        response_model=Product,
        summary="Change a price and invalidate the cached copy",
        responses={404: {"model": ErrorResponse}},
    )
    def update_price(product_id: ProductId, body: PriceUpdate, catalogue: CachedCatalogueDep) -> Product:
        # TODO(milestone 4): return catalogue.update_price(...); 404 for unknown products.
        raise NotImplementedError("TODO(milestone 4): PUT /products/{product_id}/price")

    @app.get("/cache/stats", response_model=CacheStatsReport, summary="Cache hit/miss statistics")
    def cache_stats(catalogue: CachedCatalogueDep) -> CacheStatsReport:
        raise NotImplementedError("TODO(milestone 4): GET /cache/stats")


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
    # One CachedCatalogue per app instance -- never a module-level global.
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
        # TODO(milestone 5): raise ValueError (mentioning "namespace") unless NAMESPACE_PATTERN
        # fully matches. This keeps glob characters such as * out of the SCAN pattern used by clear().
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
        # TODO(milestone 5): `import redis` *inside* this method; on ImportError raise
        # RuntimeError("RedisCache needs the optional 'redis' package: python -m pip install redis").
        # Then redis.Redis.from_url(url, socket_timeout=..., socket_connect_timeout=...).
        raise NotImplementedError("TODO(milestone 5): RedisCache.from_url")

    def _key(self, key: str) -> str:
        return self._namespace + key

    def get(self, key: str) -> str | None:
        """Return the value (decoded from UTF-8 bytes), or ``None`` if missing or expired."""
        raise NotImplementedError("TODO(milestone 5): RedisCache.get")

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        """``SET namespace+key value PX ttl_ms`` (at least 1 ms)."""
        # TODO(milestone 5): validate the TTL, then
        # self._client.set(self._key(key), value.encode("utf-8"), px=max(1, round(ttl * 1000)))
        raise NotImplementedError("TODO(milestone 5): RedisCache.set")

    def delete(self, key: str) -> None:
        """``DEL namespace+key``."""
        raise NotImplementedError("TODO(milestone 5): RedisCache.delete")

    def clear(self) -> None:
        """Delete only this namespace's keys (never ``FLUSHDB``: other apps may share the server)."""
        # TODO(milestone 5): keys = list(self._client.scan_iter(match=self._namespace + "*")) and
        # delete them in one call if there are any.
        raise NotImplementedError("TODO(milestone 5): RedisCache.clear")

    def __len__(self) -> int:
        """Number of keys in this namespace (uses ``SCAN``, so it is O(keys); fine for a demo)."""
        raise NotImplementedError("TODO(milestone 5): RedisCache.__len__")
