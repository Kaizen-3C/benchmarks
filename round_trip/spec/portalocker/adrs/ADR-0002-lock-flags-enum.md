# ADR-0002: LockFlags as IntFlag Enum

## Status
Accepted

## Context
The original portalocker recipe used plain integer constants. A typed enum improves safety and discoverability.

## Decision
`constants.py` defines four integer constants (`LOCK_SH=1`, `LOCK_EX=2`, `LOCK_NB=4`, `LOCK_UN=8`) and a `LockFlags(enum.IntFlag)` enum with members:
- `SHARED = 1`
- `EXCLUSIVE = 2`
- `NON_BLOCKING = 4`
- `UNBLOCK = 8`

These constants are only defined when `os.name` is `"nt"` or `"posix"`; otherwise a `RuntimeError` is raised at module import time.

The `__init__.py` re-exports convenience aliases: `LOCK_EX`, `LOCK_SH`, `LOCK_NB`, `LOCK_UN` pointing to the corresponding `LockFlags` enum members, plus `LockFlags` itself.

## Consequences
- Callers may use either the enum members or the integer aliases; `IntFlag` supports bitwise OR composition (e.g., `LOCK_EX | LOCK_NB`).
- The `lock()` function accepts a `LockFlags` parameter and uses bitwise `&` to test individual flags.
