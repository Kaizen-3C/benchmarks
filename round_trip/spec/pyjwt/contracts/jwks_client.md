# Contract: jwt.jwks_client

## Class: `PyJWKClient`

### `__init__(uri: str, cache_keys: bool = False, max_cached_keys: int = 16, cache_jwk_set: bool = True, lifespan: int = 300, headers: dict | None = None, timeout: int = 30, ssl_context: SSLContext | None = None)`
Constructs client. If `cache_jwk_set=True` and `lifespan <= 0`, raises `PyJWKClientError`. If `cache_keys=True`, wraps `get_signing_key` with `lru_cache(maxsize=max_cached_keys)`. See ADR-0004.

### `fetch_data() -> Any`
Performs HTTP GET to `self.uri` with `self.headers` and `self.timeout`. If `ssl_context` provided, passes it to `urlopen`. Returns parsed JSON. Raises `PyJWKClientConnectionError` on `URLError` or `TimeoutError`.

### `get_jwk_set(refresh: bool = False) -> PyJWKSet`
Returns cached set if available and not expired (unless `refresh=True`). Otherwise fetches, caches, and constructs `PyJWKSet`. Raises `PyJWKClientError` if fetched data is not a dict.

### `get_signing_keys(refresh: bool = False) -> list[PyJWK]`
Filters JWK set to keys where `public_key_use in ["sig", None]` and `key_id` is set and `key` is set. Raises `PyJWKClientError` if result is empty.

### `get_signing_key(kid: str) -> PyJWK`
Finds key by `kid`. On miss, refreshes and retries. Raises `PyJWKClientError` if not found after refresh. Optionally `lru_cache`d. See ADR-0004.

### `get_signing_key_from_jwt(token: str) -> PyJWK`
Decodes token header without verification, extracts `kid`, calls `get_signing_key(kid)`. Raises `PyJWKClientError` if `kid` is `None`.
