# Contract: portalocker.constants

## Public API

### Constants (module-level integers)
```
LOCK_SH: int = 1
LOCK_EX: int = 2
LOCK_NB: int = 4
LOCK_UN: int = 8
```
Defined only when `os.name in {"nt", "posix"}`; otherwise `RuntimeError` is raised at import.

### `LockFlags(enum.IntFlag)`
Members:
- `LockFlags.SHARED = 1`
- `LockFlags.EXCLUSIVE = 2`
- `LockFlags.NON_BLOCKING = 4`
- `LockFlags.UNBLOCK = 8`

Supports bitwise composition via `IntFlag`. See ADR-0002.
