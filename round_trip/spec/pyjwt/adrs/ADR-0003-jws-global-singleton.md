# ADR-0003: Module-Level Singleton Functions in api_jws and api_jwt

## Status
Accepted

## Context
Many callers want simple top-level `encode`/`decode` functions without instantiating a class.

## Decision
`api_jws.py` instantiates a single module-level `PyJWS` object `_jws_global_obj = PyJWS()` and binds its bound methods to module-level names:
- `encode = _jws_global_obj.encode`
- `decode_complete = _jws_global_obj.decode_complete`
- `decode = _jws_global_obj.decode`
- `register_algorithm = _jws_global_obj.register_algorithm`
- `unregister_algorithm = _jws_global_obj.unregister_algorithm`
- `get_algorithm_by_name = _jws_global_obj.get_algorithm_by_name`
- `get_unverified_header = _jws_global_obj.get_unverified_header`

Similarly `api_jwt.py` instantiates `_jwt_global_obj = PyJWT()` and binds:
- `encode = _jwt_global_obj.encode`
- `decode_complete = _jwt_global_obj.decode_complete`
- `decode = _jwt_global_obj.decode`

These are re-exported from `jwt/__init__.py` so callers can use `jwt.encode(...)` directly.

## Consequences
- Mutating the global singleton (registering algorithms) affects all callers using the module-level functions.
- Class instantiation allows isolated instances with separate options and algorithm sets.
