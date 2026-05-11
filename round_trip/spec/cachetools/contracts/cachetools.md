# Contract: `cachetools` (package public API)

All symbols listed here are importable directly from `cachetools`.
See ADR-0001 through ADR-0007.

---

## `Cache(maxsize, getsizeof=None)`
Base mutable-mapping cache.  `maxsize` is the capacity in units.
Optional `getsizeof(value) -> int` overrides the default of `1` per
value.  Raises `ValueError` if a single value's size exceeds `maxsize`.
Calls `self.popitem()` to evict until the item fits (ADR-0001).

Properties: `maxsize` (read-only), `currsize` (read-only).
Static method: `getsizeof(value) -> 1`.

### `Cache.__missing__(key)`
Raises `KeyError(key)`.  Override in subclasses for default-value
semantics.

---

## `FIFOCache(maxsize, getsizeof=None)`
Evicts the oldest-inserted item.  Backed by `collections.OrderedDict`
(ADR-0002).

---

## `LFUCache(maxsize, getsizeof=None)`
Evicts the least-frequently-used item.  Backed by
`collections.Counter` (ADR-0002).

---

## `LRUCache(maxsize, getsizeof=None)`
Evicts the least-recently-used item.  Backed by
`collections.OrderedDict` with `move_to_end` (ADR-0002).

---

## `MRUCache(maxsize, getsizeof=None)`
**Deprecated** — emits `DeprecationWarning` on construction (ADR-0010).
Evicts the most-recently-used item.

---

## `RRCache(maxsize, choice=random.choice, getsizeof=None)`
Evicts a randomly chosen item.  `choice` is the selection callable.
Property: `choice` (read-only).

---

## `TTLCache(maxsize, ttl, timer=time.monotonic, getsizeof=None)`
Time-to-live cache.  Items expire `ttl` seconds after insertion.
Property: `ttl` (read-only).  Method: `expire(time=None) -> list[(key, value)]`.
See ADR-0003, ADR-0004.

---

## `TLRUCache(maxsize, ttu, timer=time.monotonic, getsizeof=None)`
Time-aware LRU cache.  `ttu(key, value, now) -> expires` computes an
absolute expiry time per item.  Items with `expires <= now` are
silently dropped on insertion.
Property: `ttu` (read-only).  Method: `expire(time=None) -> list[(key, value)]`.
See ADR-0003, ADR-0005.

---

## `cached(cache, key=keys.hashkey, lock=None, info=False)`
Memoisation decorator factory (ADR-0006).
Returns a decorator.  Decorated function gains attributes:
`cache`, `cache_key`, `cache_lock`, `cache_clear()`.
If `info=True`, also `cache_info() -> (hits, misses, maxsize, currsize)`.

---

## `cachedmethod(cache, key=keys.methodkey, lock=None)`
Instance-method memoisation decorator factory (ADR-0007).
`cache` is a callable `(self) -> MutableMapping | None`.
Decorated method gains: `cache`, `cache_key`, `cache_lock`,
`cache_clear(self)`.

---

## `keys`
Sub-module; see contract `cachetools.keys`.
