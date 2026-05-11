# Contract: jwt.api_jwt

## Class: `PyJWT`

### `__init__(options: dict[str, Any] | None = None)`
Merges provided options over defaults. Default options: `verify_signature=True`, `verify_exp=True`, `verify_nbf=True`, `verify_iat=True`, `verify_aud=True`, `verify_iss=True`, `require=[]`.

### `encode(payload: dict[str, Any], key, algorithm: str | None = "HS256", headers: dict | None = None, json_encoder=None, sort_headers: bool = True) -> str`
Payload must be a dict. `datetime` values in `exp`, `iat`, `nbf` are converted to integer UTC timestamps via `timegm`. Encodes to JSON bytes, then delegates to `api_jws.encode`.

### `decode_complete(jwt, key="", algorithms=None, options=None, verify=None, detached_payload=None, audience=None, issuer=None, leeway: float | timedelta = 0, **kwargs) -> dict[str, Any]`
Returns `{"payload": dict, "header": dict, "signature": bytes}`. `verify` param is deprecated (emits `RemovedInPyjwt3Warning`, does nothing). `verify_signature=False` sets all other verify_* to False by default. See ADR-0005 for claim validation.

### `decode(jwt, key="", algorithms=None, options=None, verify=None, detached_payload=None, audience=None, issuer=None, leeway: float | timedelta = 0, **kwargs) -> Any`
Calls `decode_complete` and returns the payload dict only.

### `_encode_payload(payload: dict, headers=None, json_encoder=None) -> bytes`
JSON-encodes payload with compact separators. Intended for subclass override.

### `_decode_payload(decoded: dict) -> Any`
JSON-decodes `decoded["payload"]` bytes. Raises `DecodeError` if not valid JSON object. Intended for subclass override.

### `_validate_claims(payload, options, audience=None, issuer=None, leeway=0) -> None`
Validates all registered claims. See ADR-0005.

## Module-level singletons
`encode`, `decode_complete`, `decode` — bound methods of a single `PyJWT()` instance. See ADR-0003.
