# ADR-0007: `cachedmethod` Decorator Design

## Status
Accepted

## Context
Instance methods need per-instance caches (e.g., `self._cache`) rather
than a shared module-level cache.

## Decision
`cachedmethod(cache, key, lock)` takes `cache` as a callable
`(self) -> MutableMapping | None` so each instance can return its own
cache object (or `None` to bypass).  `key` defaults to `keys.methodkey`
which strips the `self` argument before hashing.

The wrapper is created with `functools.wraps`.  Attributes attached:
`cache`, `cache_key`, `cache_lock`, `cache_clear`.  `cache_clear(self)`
clears the instance's cache.

Lock protocol: `lock` is a callable `(self) -> lock_object`.

## Consequences
Unlike `cached`, `cachedmethod` does not track hit/miss counts and does
not support `info=True`.
