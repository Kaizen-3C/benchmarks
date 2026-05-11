# ADR-0004: JWK Set Cache with TTL

## Status
Accepted

## Context
`PyJWKClient` fetches JWK Sets from a remote URI. Repeated fetches on every token verification are expensive and can hit rate limits.

## Decision
`PyJWKClient` optionally uses a `JWKSetCache` (enabled by default via `cache_jwk_set=True`). The cache stores a `PyJWTSetWithTimestamp` wrapping the raw fetched dict and recording `time.monotonic()` at insertion time.

Cache parameters:
- `lifespan`: integer seconds, default **300**. Must be `> 0` or `PyJWKClientError` is raised at construction.
- `cache_jwk_set`: bool, default `True`.

`JWKSetCache.get()` returns `None` if the stored timestamp plus `lifespan` is less than `time.monotonic()` (i.e., expired). `put(None)` clears the cache. `put(data)` stores a new `PyJWTSetWithTimestamp`.

Additionally, `PyJWKClient` optionally caches the result of `get_signing_key(kid)` using `functools.lru_cache` with `maxsize=max_cached_keys` (default **16**), enabled by `cache_keys=True` (default `False`).

When a key is not found in `get_signing_key`, the client first tries the cached JWK set, then retries with `refresh=True` before raising `PyJWKClientError`.

## Consequences
- Remote JWK Set fetches are bounded by `lifespan` seconds between refreshes.
- Per-kid signing key lookups are optionally O(1) after first fetch.
- Cache eviction is purely time-based (TTL), no LRU eviction for the JWK set itself.
