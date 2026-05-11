# Contract: `cachetools.func`

Importable as `import cachetools.func` or
`from cachetools.func import lru_cache, ...`.
See ADR-0009.

---

## `fifo_cache(maxsize=128, typed=False)`
Decorator backed by `FIFOCache`.  Supports bare `@fifo_cache` usage.

## `lfu_cache(maxsize=128, typed=False)`
Decorator backed by `LFUCache`.

## `lru_cache(maxsize=128, typed=False)`
Decorator backed by `LRUCache`.

## `mru_cache(maxsize=128, typed=False)`
**Deprecated**.  Decorator backed by `MRUCache`.  Emits
`DeprecationWarning` (ADR-0010).

## `rr_cache(maxsize=128, typed=False)`
Decorator backed by `RRCache`.

## `ttl_cache(maxsize=128, ttl=600, timer=None, typed=False)`
Decorator backed by `TTLCache` (or `_UnboundTTLCache` when
`maxsize is None` or `isinf(maxsize)`).  `timer` defaults to
`time.monotonic` when `None`.

---

All decorators produced by the above add to the wrapped function:
`cache`, `cache_key`, `cache_lock`, `cache_clear()`,
`cache_info() -> (hits, misses, maxsize, currsize)`,
`cache_parameters() -> {"maxsize": ..., "typed": ...}`.

Thread safety: all use `threading.RLock` (ADR-0009).
