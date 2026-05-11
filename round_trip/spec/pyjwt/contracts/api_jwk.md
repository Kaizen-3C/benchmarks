# Contract: jwt.api_jwk

## Class: `PyJWK`

### `__init__(jwk_data: JWKDict, algorithm: str | None = None)`
Constructs from a JWK dict. Infers algorithm from `kty`/`crv` if not provided. See ADR-0009. Raises `InvalidKeyError` for unknown kty/crv; `PyJWKError` if crypto unavailable for required algorithm.

### `from_dict(obj: JWKDict, algorithm: str | None = None) -> PyJWK` *(staticmethod)*
Convenience constructor from dict.

### `from_json(data: str, algorithm: str | None = None) -> PyJWK` *(staticmethod)*
Parses JSON string to dict then constructs.

### Properties
- `key_type -> str`: the `kty` value.
- `key_id -> str | None`: the `kid` value; raises `InvalidKeyError` if present but not a string.
- `public_key_use -> str | None`: the `use` value.
- `key_ops -> list[str] | None`: the `key_ops` value.

### Attributes
- `key`: the deserialized key object.
- `algorithm_name: str`: the algorithm name string.
- `Algorithm`: the `Algorithm` instance used.

---

## Class: `PyJWKSet`

### `__init__(keys: list[JWKDict])`
Constructs from list of JWK dicts. Silently skips keys that raise `PyJWTError`. Raises `PyJWKSetError` if `keys` is not a list, if empty, or if no usable keys remain.

### `from_dict(obj: dict) -> PyJWKSet` *(staticmethod)*
Extracts `"keys"` list from dict. Raises `PyJWKSetError` if absent or not a list.

### `from_json(data: str) -> PyJWKSet` *(staticmethod)*
Parses JSON string.

### `__getitem__(kid: str) -> PyJWK`
Returns the key with matching `key_id`. Raises `KeyError` if not found.

### Attribute
- `keys: list[PyJWK]`

---

## Class: `PyJWTSetWithTimestamp`

### `__init__(jwk_set: PyJWKSet | dict)`
Stores the set and records `time.monotonic()`.

### `get_jwk_set() -> PyJWKSet | dict`
Returns the stored set.

### `get_timestamp() -> float`
Returns the stored monotonic timestamp.
