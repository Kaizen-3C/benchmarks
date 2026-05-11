# Contract: jwt.api_jws

## Class: `PyJWS`

### `__init__(algorithms: list[str] | None = None, options: dict[str, Any] | None = None)`
Initializes with algorithm registry filtered to `algorithms` list (or all defaults). `options` must be a dict or `None`; merged over `{"verify_signature": True}`.

### `register_algorithm(alg_id: str, alg_obj: Algorithm) -> None`
Adds algorithm to registry. Raises `ValueError` if already registered; `TypeError` if not an `Algorithm` instance.

### `unregister_algorithm(alg_id: str) -> None`
Removes algorithm. Raises `KeyError` if not registered.

### `get_algorithms() -> list[str]`
Returns list of valid algorithm ID strings.

### `get_algorithm_by_name(alg_name: str) -> Algorithm`
Returns the `Algorithm` for `alg_name`. Raises `NotImplementedError` if not found (with hint if crypto missing).

### `get_unverified_header(jwt: str | bytes) -> dict[str, Any]`
Parses and returns the JWT header without verifying the signature. Validates `kid` is a string if present. See ADR-0006.

### `encode(payload: bytes, key, algorithm: str | None = None, headers: dict | None = None, json_encoder=None, is_payload_detached: bool = False, sort_headers: bool = True) -> str`
Encodes a JWS token. Returns dot-separated base64url string. See ADR-0006 for algorithm selection and detached payload behavior.

### `decode_complete(jwt: str | bytes, key="", algorithms: list[str] | None = None, options: dict | None = None, detached_payload: bytes | None = None, **kwargs) -> dict[str, Any]`
Returns `{"payload": bytes, "header": dict, "signature": bytes}`. Requires `algorithms` if `verify_signature=True` and key is not a `PyJWS` instance. Deprecated kwargs emit `RemovedInPyjwt3Warning`.

### `decode(jwt, key="", algorithms=None, options=None, detached_payload=None, **kwargs) -> bytes`
Calls `decode_complete` and returns the payload bytes only.

## Module-level singletons
`encode`, `decode_complete`, `decode`, `register_algorithm`, `unregister_algorithm`, `get_algorithm_by_name`, `get_unverified_header` — bound methods of a single `PyJWS()` instance. See ADR-0003.
