# ADR-0004: LRU Cache on wcwidth and Version Functions

## Status
Accepted

## Context
`wcwidth()` is frequently called with the same characters (e.g., ASCII) and the same version string in tight loops over text.

## Decision
- `wcwidth(wc, unicode_version)` is decorated with `@lru_cache(maxsize=1000)`. The cache key is `(wc, unicode_version)`.
- `_wcmatch_version(given_version)` is decorated with `@lru_cache(maxsize=8)`. Only a small number of distinct version strings are expected per process.
- `_wcversion_value(ver_string)` is decorated with `@lru_cache(maxsize=128)`.

For Python < 3.2, a third-party `backports.functools_lru_cache` package is used as a drop-in replacement.

The cache is module-level and process-global. No explicit invalidation mechanism is provided.

## Consequences
- ASCII-heavy documents see approximately 40% performance improvement on `wcwidth()`.
- The cache is not thread-safe at insertion time on some Python implementations but read-time safety is acceptable under the GIL.
- Memory overhead is bounded: at most 1000 + 8 + 128 entries across the three caches.
