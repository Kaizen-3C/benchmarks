# Contract: jwt.algorithms

## Module-level

### `get_default_algorithms() -> dict[str, Algorithm]`
Returns a fresh dict mapping algorithm name strings to `Algorithm` instances. Always includes HMAC and NoneAlgorithm entries; includes crypto-based entries only if `cryptography` is installed. See ADR-0001.

### `has_crypto: bool`
Module-level boolean, `True` if `cryptography` was successfully imported.

### `requires_cryptography: set[str]`
Module-level set of algorithm names requiring `cryptography`.

---

## Abstract Base Class: `Algorithm`

### `Algorithm.prepare_key(key: Any) -> Any`
Validates and normalizes a key for use with `sign`/`verify`. Raises `InvalidKeyError` on invalid input.

### `Algorithm.sign(msg: bytes, key: Any) -> bytes`
Produces a digital signature over `msg` using `key`.

### `Algorithm.verify(msg: bytes, key: Any, sig: bytes) -> bool`
Returns `True` if `sig` is a valid signature over `msg` for `key`, `False` otherwise. Never raises on invalid signatures (only on key errors).

### `Algorithm.to_jwk(key_obj, as_dict: bool = False) -> JWKDict | str`
Serializes `key_obj` to JWK. Returns `dict` if `as_dict=True`, else JSON string.

### `Algorithm.from_jwk(jwk: str | JWKDict) -> Any`
Deserializes a key from JWK dict or JSON string. Raises `InvalidKeyError` on invalid input.

### `Algorithm.compute_hash_digest(bytestr: bytes) -> bytes`
Hashes `bytestr` using the algorithm's `hash_alg`. Raises `NotImplementedError` if no `hash_alg` attribute.

---

## `NoneAlgorithm(Algorithm)`

### `prepare_key(key: Any) -> None`
Accepts only `None` or `""` (treats `""` as `None`). Raises `InvalidKeyError` otherwise.

### `sign(msg: bytes, key: None) -> bytes`
Always returns `b""`.

### `verify(msg: bytes, key: None, sig: bytes) -> bool`
Always returns `False`.

### `to_jwk(...)` / `from_jwk(...)`
Both raise `NotImplementedError`.

---

## `HMACAlgorithm(Algorithm)`

Constructor: `HMACAlgorithm(hash_alg: HashlibHash)`. Class attributes `SHA256`, `SHA384`, `SHA512` reference `hashlib` callables.

### `prepare_key(key: str | bytes) -> bytes`
Converts to bytes via `force_bytes`. Raises `InvalidKeyError` if key is in PEM or SSH format.

### `sign(msg: bytes, key: bytes) -> bytes`
Returns `hmac.new(key, msg, self.hash_alg).digest()`.

### `verify(msg: bytes, key: bytes, sig: bytes) -> bool`
Returns `hmac.compare_digest(sig, self.sign(msg, key))`.

### `to_jwk(key_obj, as_dict=False) -> JWKDict | str`
Accepts `bytes` or `str`. Produces `{"k": <base64url>, "kty": "oct"}`.

### `from_jwk(jwk: str | JWKDict) -> bytes`
Requires `kty == "oct"` and `"k"` field. Returns raw key bytes.

---

## `RSAAlgorithm(Algorithm)` *(requires cryptography)*

Constructor: `RSAAlgorithm(hash_alg)`. Class attributes `SHA256`, `SHA384`, `SHA512` are `hashes.SHA*` classes.

### `prepare_key(key) -> RSAPrivateKey | RSAPublicKey`
Accepts RSA key objects, PEM bytes/str, or SSH RSA public key bytes.

### `sign(msg, key: RSAPrivateKey) -> bytes`
Signs with PKCS1v15 padding.

### `verify(msg, key, sig) -> bool`
Verifies with PKCS1v15 padding. Returns `False` on `InvalidSignature`.

### `to_jwk(key_obj, as_dict=False)`
Produces RSA JWK with `kty="RSA"`. Private key includes `n,e,d,p,q,dp,dq,qi`. Public key includes `n,e`.

### `from_jwk(jwk)`
Reconstructs RSA key. Recovers prime factors if `d` present but `p,q,dp,dq,qi` absent. Raises `InvalidKeyError` if only some CRT components present.

---

## `ECAlgorithm(Algorithm)` *(requires cryptography)*

Constructor: `ECAlgorithm(hash_alg)`. Supports curves P-256, P-384, P-521, secp256k1.

### `prepare_key(key) -> EllipticCurvePrivateKey | EllipticCurvePublicKey`
Accepts EC key objects, PEM, or SSH public keys.

### `sign(msg, key: EllipticCurvePrivateKey) -> bytes`
Signs with ECDSA, returns raw `r || s` (not DER). See ADR-0008.

### `verify(msg, key, sig) -> bool`
Converts raw sig to DER, verifies. Returns `False` on invalid signature or value error.

### `to_jwk(key_obj, as_dict=False)`
Produces EC JWK with `kty="EC"`, `crv`, `x`, `y`, and `d` for private keys.

### `from_jwk(jwk)`
Validates coordinate byte lengths match `(curve.key_size + 7) // 8`. Raises `InvalidKeyError` on mismatch.

---

## `RSAPSSAlgorithm(RSAAlgorithm)` *(requires cryptography)*

Inherits from `RSAAlgorithm`. Overrides `sign` and `verify` to use PSS padding with `MGF1` and `salt_length=hash_alg.digest_size`.

---

## `OKPAlgorithm(Algorithm)` *(requires cryptography)*

Supports Ed25519 and Ed448 keys.

### `prepare_key(key) -> Ed25519PrivateKey | Ed25519PublicKey | Ed448PrivateKey | Ed448PublicKey`
Accepts key objects, PEM, or SSH public keys.

### `sign(msg, key) -> bytes`
Calls `key.sign(force_bytes(msg))`.

### `verify(msg, key, sig) -> bool`
If key is private, extracts public key first. Calls `public_key.verify(force_bytes(sig), force_bytes(msg))`.

### `to_jwk(key_obj, as_dict=False)`
Produces OKP JWK with `kty="OKP"`, `crv` (`Ed25519` or `Ed448`), `x` (public bytes), `d` (private bytes) for private keys.

### `from_jwk(jwk)`
Requires `kty="OKP"`, `crv` in `("Ed25519","Ed448")`, `x` field.
