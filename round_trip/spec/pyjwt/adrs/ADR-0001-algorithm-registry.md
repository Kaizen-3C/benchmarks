# ADR-0001: Algorithm Registry Design

## Status
Accepted

## Context
PyJWT must support multiple cryptographic signing algorithms (HMAC, RSA, EC, OKP, PSS, none) and allow users to register custom algorithms at runtime.

## Decision
A module-level function `get_default_algorithms()` returns a fresh `dict[str, Algorithm]` mapping algorithm name strings to `Algorithm` instances each time it is called. The default set always includes:
- `"none"` → `NoneAlgorithm()`
- `"HS256"` → `HMACAlgorithm(SHA256)`
- `"HS384"` → `HMACAlgorithm(SHA384)`
- `"HS512"` → `HMACAlgorithm(SHA512)`

If the `cryptography` package is importable (`has_crypto = True`), the following are also added:
- `"RS256"`, `"RS384"`, `"RS512"` → `RSAAlgorithm` variants
- `"ES256"`, `"ES256K"`, `"ES384"`, `"ES512"` → `ECAlgorithm` variants
- `"PS256"`, `"PS384"`, `"PS512"` → `RSAPSSAlgorithm` variants
- `"EdDSA"` → `OKPAlgorithm()`

The `PyJWS` class stores its own copy of this dict in `self._algorithms`, allowing per-instance registration/deregistration via `register_algorithm(alg_id, alg_obj)` and `unregister_algorithm(alg_id)`. A parallel `self._valid_algs` set tracks which algorithm IDs are permitted for encoding/decoding.

The `requires_cryptography` module-level set lists the algorithm name strings that need `cryptography` installed: `{"RS256","RS384","RS512","ES256","ES256K","ES384","ES521","ES512","PS256","PS384","PS512","EdDSA"}`.

## Consequences
- Custom algorithms can be plugged in without modifying library internals.
- Each `PyJWS` instance has isolated algorithm state.
- Algorithms requiring `cryptography` raise `NotImplementedError` (from `get_algorithm_by_name`) or `PyJWKError` (from `PyJWK`) when `cryptography` is absent.
