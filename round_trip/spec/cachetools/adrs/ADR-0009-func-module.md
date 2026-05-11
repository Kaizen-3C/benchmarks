# ADR-0009: `func` Module — `functools.lru_cache`-Compatible Decorators

## Status
Accepted

## Context
Users familiar with `functools.lru_cache` expect decorators with
`cache_parameters()`, `cache_info()`, and `cache_clear()`.

## Decision
`func.py` provides: `fifo_cache`, `lfu_cache`, `lru_cache`, `mru_cache`,
`rr_cache`, `ttl_cache`.  All are thin wrappers around `cached` with
`lock=RLock()` and `info=True`.

A shared internal helper `_cache(cache_cls, maxsize, typed, **kwargs)`
handles the common pattern:
- If `maxsize` is a callable (bare decorator usage), wraps immediately.
- `maxsize=None` or `isinf(maxsize)` → uses a plain `dict` as the cache
  (except `ttl_cache` which uses `_UnboundTTLCache`).
- `maxsize=0` → uses `cache_cls(0)`.
- Otherwise → uses `cache_cls(maxsize)`.
- `typed=True` → key is `keys.typedkey`; otherwise `keys.hashkey`.

`_UnboundTTLCache` subclasses `TTLCache` with `maxsize=math.inf`.

Each wrapper gains a `cache_parameters()` method returning
`{"maxsize": maxsize, "typed": typed}`.

`mru_cache` emits `DeprecationWarning` (delegated from `MRUCache`).

`ttl_cache` default `timer` is `time.monotonic` (resolved at call time,
not import time).

## Consequences
`RLock` is imported from `threading`; a fallback to `dummy_threading` is
provided for environments without threading support.
