# ADR-0005: JWT Claim Validation Logic

## Status
Accepted

## Context
JWT standard defines several registered claims (`exp`, `nbf`, `iat`, `aud`, `iss`) each with specific validation semantics.

## Decision
`PyJWT._validate_claims` is called during `decode_complete`. All time values are obtained via `timegm(datetime.now(tz=timezone.utc).utctimetuple())` for an integer Unix timestamp.

Leeway is accepted as `float` seconds or `timedelta`; `timedelta` is converted to `total_seconds()`.

Validation rules:
- **`iat`** (if present and `verify_iat=True`): must be an integer; if `iat > now + leeway` raise `ImmatureSignatureError`.
- **`nbf`** (if present and `verify_nbf=True`): must be an integer; if `nbf > now + leeway` raise `ImmatureSignatureError`.
- **`exp`** (if present and `verify_exp=True`): must be an integer; if `exp <= now - leeway` raise `ExpiredSignatureError`.
- **`iss`** (if `verify_iss=True` and `issuer` argument provided): payload must contain `iss` key (else `MissingRequiredClaimError`); value must equal `issuer` string (else `InvalidIssuerError`). If `issuer=None`, no validation.
- **`aud`** (if `verify_aud=True`): complex logic described below.

Audience validation (`_validate_aud`):
- `audience=None` and no `aud` in payload → OK.
- `audience=None` and `aud` in payload → `InvalidAudienceError`.
- `audience` provided and no `aud` in payload → `MissingRequiredClaimError("aud")`.
- `strict=True` (via `options["strict_aud"]`): both `audience` and `payload["aud"]` must be single strings and must be equal.
- Normal mode: payload `aud` may be string (treated as single-element list) or list of strings; at least one element of the provided `audience` iterable must appear in `audience_claims`.

Required claims: `options["require"]` is a list of claim names; any listed name missing from payload raises `MissingRequiredClaimError`.

Default options for `PyJWT`:
```
verify_signature=True, verify_exp=True, verify_nbf=True,
verify_iat=True, verify_aud=True, verify_iss=True, require=[]
```
When `verify_signature=False`, all verify_* options default to `False` (unless explicitly overridden).

## Consequences
- Claims are only validated when present, except when listed in `require` or when `audience`/`issuer` arguments are non-None.
- Leeway applies symmetrically to `iat`, `nbf`, and `exp`.
