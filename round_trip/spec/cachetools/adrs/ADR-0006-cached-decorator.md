# ADR-0006: `cached` Decorator Design

## Status
Accepted

## Context
A general-purpose memoisation decorator must support: no-op caching
(`cache=None`), lock-free single-threaded use, and thread-safe use with
an explicit lock.

## Decision
`cached(cache, key, lock, info)` returns a decorator that wraps a
function with one of three `wrapper` closures selected at decoration
time:

1. `cache is None` — always calls through, increments `misses` only.
2. `lock is None` (and cache is not None) — lock-free read/write with
   `KeyError` catch on read.
3. `lock is not None` — acquires `lock` for reads and for
   `cache.setdefault` writes; uses `setdefault` to avoid overwriting a
   value written by a concurrent thread.

`functools.update_wrapper` is applied so `__wrapped__`, `__name__`,
`__doc__`, etc. are forwarded.

Attributes attached to `wrapper`: `cache`, `cache_key`, `cache_lock`,
`cache_clear`.  If `info=True`, also `cache_info` (returns a 4-tuple:
`hits, misses, maxsize, currsize`).

`cache_clear()` resets `hits` and `misses` to 0 and clears the cache
(with lock if provided).

`maxsize` in `cache_info` is `None` when `cache.maxsize` is `inf`;
`currsize` falls back to `len(cache)` if no `currsize` attribute exists.

## Consequences
The `key` argument defaults to `keys.hashkey`.  Callers that need
type-sensitive keys should pass `keys.typedkey`.
