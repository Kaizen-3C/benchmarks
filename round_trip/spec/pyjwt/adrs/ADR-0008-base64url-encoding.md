# ADR-0008: Base64url Encoding/Decoding Utilities

## Status
Accepted

## Context
JWT uses base64url encoding without padding throughout.

## Decision
`utils.py` provides:
- `base64url_decode(input: bytes | str) -> bytes`: Converts to bytes, pads to multiple of 4 with `=`, then calls `base64.urlsafe_b64decode`.
- `base64url_encode(input: bytes) -> bytes`: Calls `base64.urlsafe_b64encode` then strips all `=` padding.
- `to_base64url_uint(val: int) -> bytes`: Encodes a non-negative integer as big-endian bytes (minimum length), then base64url-encodes. Special case: `val == 0` returns `b"AA"`. Raises `ValueError` for negative input.
- `from_base64url_uint(val: bytes | str) -> int`: Decodes base64url then interprets as big-endian unsigned integer.

EC signature conversion:
- `der_to_raw_signature(der_sig, curve)`: Decodes DER-encoded ECDSA signature to `r || s`, each zero-padded to `(curve.key_size + 7) // 8` bytes.
- `raw_to_der_signature(raw_sig, curve)`: Splits raw `r || s` bytes and DER-encodes. Raises `ValueError` if `len(raw_sig) != 2 * num_bytes`.

## Consequences
- All JWT segment encoding is consistent and padding-free.
- EC signatures are converted between DER (cryptography library format) and raw (JWT format).
