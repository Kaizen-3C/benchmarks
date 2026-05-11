# ADR-0002: Optional cryptography Dependency

## Status
Accepted

## Context
Not all users of PyJWT need asymmetric cryptography. Requiring `cryptography` for all users would add a heavyweight C-extension dependency unnecessarily.

## Decision
`algorithms.py` wraps its `from cryptography...` imports in a `try/except ModuleNotFoundError` block, setting `has_crypto = True` on success and `has_crypto = False` on failure. All classes that depend on cryptography (`RSAAlgorithm`, `ECAlgorithm`, `RSAPSSAlgorithm`, `OKPAlgorithm`) are defined only inside `if has_crypto:` guard blocks. The `requires_cryptography` set is always defined regardless of import success.

Runtime checks in `PyJWS.get_algorithm_by_name` and `PyJWK.__init__` raise `NotImplementedError` or `PyJWKError` respectively when a crypto-requiring algorithm is requested and `cryptography` is not installed.

`setup.cfg` lists `cryptography>=3.4.0` as an optional extra (`[crypto]`), not a hard dependency. However, the `manifest.json` for this specification lists it as a runtime dependency to match typical deployment expectations. A pure HMAC-only deployment may omit it.

## Consequences
- Library imports successfully without `cryptography`.
- HMAC algorithms always available.
- EC/RSA/OKP/PSS algorithms fail at runtime with informative errors if `cryptography` missing.
