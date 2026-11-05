# Caching demo: cache-aside with TTL and invalidation

A product catalogue sits behind a **slow upstream**: every lookup takes about half a second (think of
a remote pricing API or a heavy SQL query). The product page reads the same few products thousands of
times a minute, so most of that time and load is wasted on answers we already had.

You will put a **cache-aside** layer in front of it:

* **Read path**: look in the cache first; on a miss, read the source and store the answer with a
  **time to live (TTL)**.
* **Write path**: write to the source of truth first, then **invalidate** (delete) the cached copy.
* **Interface first**: the same code works with an in-memory cache (tested with a fake clock) and,
  optionally, with **Redis**.

```text
GET /products/1            -> 200 X-Cache: MISS   (~0.5 s: went to the slow source)
GET /products/1            -> 200 X-Cache: HIT    (~1 ms: served from the cache)
PUT /products/1/price {"price_cents": 7999} -> 200 (source updated, cache entry deleted)
GET /products/1            -> 200 X-Cache: MISS   (reloaded: the new price, never the stale one)
GET /cache/stats           -> {"hits": 1, "misses": 2, "hit_ratio": 0.3333333333333333, "size": 1}
```

## Setup

Windows PowerShell:

```powershell
cd projects\caching-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/caching-demo
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

Until milestone 1 is done, most later tests report *errors* rather than failures: their fixtures build
a `CachedCatalogue`, which calls your `validate_ttl`. Work through the milestones in order.

### Why a fake clock?

TTL bugs hide at the boundary (`>` instead of `>=`) and in timing. Tests that call `time.sleep(30)` are
slow and flaky. Instead, `InMemoryCache` takes a `clock` function and `SlowCatalogue` takes a `sleep`
function. The tests pass a `FakeClock` (`clock.advance(30)` moves time instantly) and a
`RecordingSleep` (records each delay without waiting), so "the source was called once" is something
the tests count exactly, and the whole suite runs in a couple of seconds.

## Running the API

```powershell
python -m uvicorn --factory cache_aside:create_app --app-dir starter --reload
# in a second terminal:
(Invoke-WebRequest http://127.0.0.1:8000/products/1).Headers["X-Cache"]   # MISS
(Invoke-WebRequest http://127.0.0.1:8000/products/1).Headers["X-Cache"]   # HIT
Invoke-RestMethod -Method Put http://127.0.0.1:8000/products/1/price -ContentType application/json -Body '{"price_cents": 7999}'
Invoke-RestMethod http://127.0.0.1:8000/cache/stats
```

```bash
python -m uvicorn --factory cache_aside:create_app --app-dir starter --reload
# in a second terminal:
curl -si http://127.0.0.1:8000/products/1 | grep -i x-cache   # MISS (slow)
curl -si http://127.0.0.1:8000/products/1 | grep -i x-cache   # HIT (fast)
curl -s -X PUT http://127.0.0.1:8000/products/1/price -H 'content-type: application/json' -d '{"price_cents": 7999}'
curl -s http://127.0.0.1:8000/cache/stats
```

Use `--app-dir solution` to run the reference. Open <http://127.0.0.1:8000/docs> for the OpenAPI UI.
`curl -w '%{time_total}\n' -o /dev/null -s http://127.0.0.1:8000/products/2` shows the latency drop.

## Milestones

| # | Tests | What you build |
|---|-------|----------------|
| 1 | `TestMilestone1InMemoryCache` | `validate_ttl`, `InMemoryCache`: TTL with an injected clock (expired exactly at `t + ttl`), lazy expiry, LRU eviction, stats |
| 2 | `TestMilestone2CacheAsideReads` | `get_or_load` (hit, miss, errors not cached, corrupt entries, broken cache falls back to the source), `CachedCatalogue.lookup` and `stats` |
| 3 | `TestMilestone3InvalidationAndExpiry` | `update_price` (write the source first, then delete the key), `invalidate`, reload after the TTL |
| 4 | `TestMilestone4HttpLayer` | `GET /products/{id}` with `X-Cache`, `PUT /products/{id}/price`, `GET /cache/stats`, 404/422 handling |
| 5 | `TestMilestone5RedisAdapter` | `RedisCache`: namespaced keys, `PX` milliseconds, UTF-8 decoding, `clear()` that only touches its own keys, lazy `import redis` |

## Layout

```text
caching-demo/
  README.md
  requirements.txt
  conftest.py               # GW_TARGET=solution switches the tests to the reference solution
  starter/cache_aside.py    # your code: functions raise NotImplementedError until you implement them
  solution/cache_aside.py   # reference solution
  tests/test_cache_aside.py # fakes: FakeClock, RecordingSleep, BrokenCache, FakeRedisClient
```

## Optional: a real Redis server

Milestone 5 is fully tested against a small in-test `FakeRedisClient`, so Redis is **not** required.
To try the adapter against a real server:

1. Install the client library: `python -m pip install redis`.
2. Start a server on `localhost:6379`, for example with Docker (`docker run --rm -p 6379:6379 redis:7`),
   Memurai or WSL on Windows, `brew install redis && redis-server` on macOS, or your Linux package manager.
3. Run the optional tests (they are skipped by default, and skip themselves if no server answers):

   ```powershell
   $env:GW_REDIS_URL="redis://localhost:6379/0"; python -m pytest -m network
   ```

   ```bash
   GW_REDIS_URL=redis://localhost:6379/0 python -m pytest -m network
   ```

4. Use it in the API from a Python shell or a small script:
   `create_app(cache=RedisCache.from_url("redis://localhost:6379/0"))`.

The optional tests only use keys under `caching-demo-test:` and delete them afterwards. Never point
them at a production Redis.
