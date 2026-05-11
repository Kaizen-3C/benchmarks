# ADR-0010: Deprecation Warning Strategy

## Status
Accepted

## Context
PyJWT 3 will remove certain keyword arguments. Users need advance warning.

## Decision
A custom warning class `RemovedInPyjwt3Warning(DeprecationWarning)` is defined in `jwt/warnings.py`.

It is issued (via `warnings.warn(..., RemovedInPyjwt3Warning, stacklevel=2)`) in:
1. `PyJWS.decode_complete` and `PyJWT.decode_complete`: when any unexpected `**kwargs` are passed.
2. `PyJWT.decode_complete`: when the `verify` argument is not `None` (the argument is accepted but does nothing).

## Consequences
- Users receive actionable deprecation warnings at the call site (`stacklevel=2`).
- `DeprecationWarning` subclass means it is silenced by default in non-`__main__` contexts unless warnings filters are adjusted.
