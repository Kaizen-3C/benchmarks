# ADR-0002: Eviction Policy Implementations

## Status
Accepted

## Context
Multiple eviction strategies are needed: FIFO, LFU, LRU, MRU, Random
Replacement (RR), TTL-based, and TLRU (time-aware LRU).

## Decision
Each policy is a subclass of `Cache` (or `_TimedCache` for timed
variants) and overrides only `__setitem__`, `__delitem__`, and
`popitem()`.

| Class | Evicts | Backing structure |
|---|---|---|
| `FIFOCache` | Oldest inserted | `collections.OrderedDict` insertion order |
| `LFUCache` | Least frequently used | `collections.Counter` (negative counts for `most_common`) |
| `LRUCache` | Least recently used | `collections.OrderedDict` with `move_to_end` |
| `MRUCache` | Most recently used | `collections.OrderedDict`, moves to front on access (deprecated) |
| `RRCache` | Random | `random.choice` over `list(self)` |
| `TTLCache` | Expired by TTL, then LRU | Doubly-linked expiry ring + `OrderedDict` |
| `TLRUCache` | Expired by per-item TTU function, then LRU | Min-heap (`heapq`) + `OrderedDict` |

`MRUCache` emits `DeprecationWarning` on construction.

## Consequences
`TTLCache` requires a `ttl` argument (seconds, float).  `TLRUCache`
requires a `ttu` callable `(key, value, now) -> expires` where `expires`
is an absolute time value.  Items whose computed expiry is not strictly
greater than `now` are silently discarded on insertion.
