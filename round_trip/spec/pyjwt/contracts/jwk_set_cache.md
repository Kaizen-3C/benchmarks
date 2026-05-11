# Contract: jwt.jwk_set_cache

## Class: `JWKSetCache`

### `__init__(lifespan: int)`
Initializes with TTL in seconds. Starts with no cached data.

### `put(jwk_set: Any) -> None`
If `jwk_set` is `None`, clears cache. Otherwise wraps in `PyJWTSetWithTimestamp` and stores.

### `get() -> Any`
Returns the cached JWK set (via `get_jwk_set()`) if present and not expired; else `None`.

### `is_expired() -> bool`
Returns `True` if no cached data or if `timestamp + lifespan < time.monotonic()`.
