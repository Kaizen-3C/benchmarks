# ADR-0009: JWK Key Type to Algorithm Mapping

## Status
Accepted

## Context
`PyJWK` must select a default algorithm when none is specified, based on the `kty` and optional `crv` fields of the JWK dict.

## Decision
`PyJWK.__init__` applies the following mapping when `algorithm` is not provided and the JWK dict has no `"alg"` field:

| kty | crv | algorithm |
|-----|-----|-----------|
| `EC` | `P-256` or absent | `ES256` |
| `EC` | `P-384` | `ES384` |
| `EC` | `P-521` | `ES512` |
| `EC` | `secp256k1` | `ES256K` |
| `EC` | other | raise `InvalidKeyError` |
| `RSA` | — | `RS256` |
| `oct` | — | `HS256` |
| `OKP` | `Ed25519` or `Ed448` | `EdDSA` |
| `OKP` | absent | raise `InvalidKeyError` |
| `OKP` | other | raise `InvalidKeyError` |
| other | — | raise `InvalidKeyError` |

The `PyJWK` object exposes: `key` (the deserialized key object), `algorithm_name` (string), `Algorithm` (the `Algorithm` instance), `key_type` (the `kty` string), `key_id` (the `kid` string or `None`), `public_key_use` (the `use` string or `None`), `key_ops` (list of strings or `None`).

`key_id` property raises `InvalidKeyError` if the `kid` value exists but is not a string.

## Consequences
- Algorithm inference is deterministic from JWK metadata.
- Explicit `algorithm` parameter always overrides inference.
