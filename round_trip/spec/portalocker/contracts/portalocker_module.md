# Contract: portalocker.portalocker

## Module-level

```python
LOCKER: Optional[Callable[[Union[int, HasFileno], int], Any]]
```
On POSIX: `fcntl.flock`. On Windows: `None` (Windows uses win32 API directly). Monkeypatchable for testing.

### `HasFileno` (Protocol)
```python
class HasFileno(typing.Protocol):
    def fileno(self) -> int: ...
```

## Public Functions

### `lock(file_: Union[int, HasFileno], flags: LockFlags) -> Any`
Acquires a lock on `file_` according to `flags`.
- On POSIX: translates `LockFlags` to `fcntl` constants and calls `LOCKER`. Raises `RuntimeError` if `NON_BLOCKING` is set without `SHARED` or `EXCLUSIVE`.
- On Windows: uses `win32file.LockFileEx`.
- Raises `AlreadyLocked` if lock is held by another; `LockException` for other errors.
- See ADR-0001.

### `unlock(file_: Union[int, HasFileno]) -> Any`
Releases the lock on `file_`.
- On POSIX: calls `LOCKER(target, fcntl.LOCK_UN)`.
- On Windows: calls `win32file.UnlockFileEx`.
- Raises `LockException` on error.
