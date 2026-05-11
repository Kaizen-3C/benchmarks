# ADR-0006: JWS Header Encoding, typ Handling, and Detached Payload

## Status
Accepted

## Context
JWS encoding must handle `typ` suppression, custom headers, and detached payloads per RFC 7797.

## Decision
**Header construction** in `PyJWS.encode`:
1. Base header is `{"typ": self.header_typ, "alg": algorithm_}`. `header_typ` defaults to `"JWT"` on `PyJWS`.
2. If custom `headers` dict is provided, it is merged over the base header.
3. If the resulting header's `"typ"` value is `""` or `None`, the `"typ"` key is deleted entirely.
4. Headers are JSON-serialized with `separators=(",", ":")` and `sort_keys=True` by default (controlled by `sort_headers` parameter).

**Detached payload** (RFC 7797 `b64=false`):
- `is_payload_detached=True` or `headers["b64"] is False` activates detached mode.
- In detached mode, the payload segment in the token is empty (`b""`); the raw payload bytes are used for signing but not embedded.
- `header["b64"]` is set to `False` in the header.
- If `headers["b64"] is True`, the key is removed from the header (treated as default).
- Decoding a token with `b64=false` in header requires passing `detached_payload: bytes` argument; absence raises `DecodeError`.

**Algorithm selection precedence** in encode:
1. `headers["alg"]` overrides the `algorithm` parameter.
2. If `algorithm=None` and `key is None`, uses `"none"`.
3. If `algorithm=None` and `key` is provided, defaults to `"HS256"`.

## Consequences
- `typ` can be suppressed for JWTs that must omit the field.
- Detached payloads allow signing of content not embedded in the token.
- Header sort order is deterministic by default.
