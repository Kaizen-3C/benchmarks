# Contract: jwt.utils

### `force_bytes(value: bytes | str) -> bytes`
Encodes `str` to UTF-8 bytes; passes `bytes` through. Raises `TypeError` for other types.

### `base64url_decode(input: bytes | str) -> bytes`
Decodes base64url-encoded input (adds padding as needed).

### `base64url_encode(input: bytes) -> bytes`
Encodes to base64url without padding.

### `to_base64url_uint(val: int) -> bytes`
Encodes non-negative integer to base64url. Returns `b"AA"` for 0. Raises `ValueError` for negative.

### `from_base64url_uint(val: bytes | str) -> int`
Decodes base64url to unsigned integer.

### `number_to_bytes(num: int, num_bytes: int) -> bytes`
Big-endian encoding of `num` in exactly `num_bytes` bytes.

### `bytes_to_number(string: bytes) -> int`
Big-endian decoding to integer.

### `der_to_raw_signature(der_sig: bytes, curve: EllipticCurve) -> bytes`
Converts DER ECDSA signature to raw `r || s` padded to curve byte size.

### `raw_to_der_signature(raw_sig: bytes, curve: EllipticCurve) -> bytes`
Converts raw `r || s` to DER. Raises `ValueError` if length is wrong.

### `is_pem_format(key: bytes) -> bool`
Returns `True` if key matches PEM header/footer regex. See ADR-0007.

### `is_ssh_key(key: bytes) -> bool`
Returns `True` if key appears to be an SSH key. See ADR-0007.
