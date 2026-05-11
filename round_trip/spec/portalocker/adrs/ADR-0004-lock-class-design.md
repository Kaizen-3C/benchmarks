# ADR-0004: Lock Class Design and Context Manager Protocol

## Status
Accepted

## Context
Most callers want a context-manager interface that acquires on entry and releases on exit, with configurable timeout and retry behaviour.

## Decision
`utils.py` provides an abstract base class `LockBase` and concrete implementations:

### `LockBase(abc.ABC)`
- Constructor params: `timeout: Optional[float]`, `check_interval: Optional[float]`, `fail_when_locked: Optional[bool]`.
- Defaults via `coalesce()`: `DEFAULT_TIMEOUT=5`, `DEFAULT_CHECK_INTERVAL=0.25`, `DEFAULT_FAIL_WHEN_LOCKED=False`.
- `__enter__` returns `self.acquire()`.
- `__exit__` calls `self.release()`, returns `None`.
- Abstract methods: `acquire(*args, **kwargs)`, `release()`.

### `Lock(LockBase)`
- Additional constructor params: `filename: Filename`, `mode: str = "a"`, `flags: LockFlags = LOCK_EX | LOCK_NB`, `**file_open_kwargs`.
- If `"w"` in mode, sets `truncate=True` and replaces `"w"` with `"a"` for opening (so file is not immediately truncated on open).
- If `timeout is not None` and flags do not include `NON_BLOCKING`, emits `UserWarning("timeout has no effect in blocking mode")` at construction and again at `acquire()` if `timeout` is passed there.
- `acquire()` loops with `time.sleep(check_interval)` until lock is obtained, `timeout` expires, or `fail_when_locked` causes immediate raise.
- `release()` calls `portalocker.unlock(fh)` then `fh.close()`.
- `__del__` suppresses all exceptions from `release()`.
- `_get_fh()`: opens file with `open(filename, mode, **file_open_kwargs)`.
- `_get_lock(fh)`: calls `portalocker.lock(fh, self.flags)`.
- `_prepare_fh(fh)`: if `truncate`, seeks to 0 and truncates; always seeks to 0.

### `RLock(Lock)`
- Adds `_acquire_count: int` (starts at 0).
- `acquire()`: if `self.fh is not None`, increments count and returns existing `fh` (reentrant). Otherwise calls `super().acquire()` and sets count to 1.
- `release()`: raises `LockException("Cannot release an unacquired lock")` if `_acquire_count <= 0`. Decrements; calls `super().release()` only when count reaches 0.

### `TemporaryFileLock(Lock)`
- Default `filename=".lock"`, `mode="w"`, `fail_when_locked=True`.
- Uses `weakref.finalize` to delete the lock file on GC.
- Registers `atexit` handler to release and delete file at interpreter exit.
- `release()` calls `super().release()`, then `_cleanup_file(self.filename)`, then detaches finalizer if alive.
- `__del__` suppresses all exceptions from `release()`.

### Helper: `coalesce(*args, test_value=None) -> Any`
Returns the first argument that is not `test_value` (default `None`). Returns `None` if all are `test_value`.

### Helper: `open_atomic(filename, binary=True)` (context manager)
Creates parent dirs, writes to a temp file in the same directory, fsyncs, then atomically replaces the target. On exception, unlinks the temp file.

## Consequences
- `Lock` is not reentrant; `RLock` is.
- `TemporaryFileLock` always deletes its file on release/GC/exit.
- `LOCK_METHOD` constant in `utils.py` = `LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING`.
