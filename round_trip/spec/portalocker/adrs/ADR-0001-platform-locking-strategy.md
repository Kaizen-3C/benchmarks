# ADR-0001: Platform-Specific Locking Strategy

## Status
Accepted

## Context
File locking APIs differ fundamentally between Windows (`nt`) and POSIX (`posix`) systems. A unified interface must abstract these differences without sacrificing correctness.

## Decision
The `portalocker.py` module uses `os.name` at import time to select the locking backend:

- **POSIX** (`os.name == "posix"`): Uses `fcntl.flock` as the default `LOCKER` callable. The `LOCKER` module-level variable is `typing.Optional[Callable[[Union[int, HasFileno], int], Any]]` and defaults to `fcntl.flock`. It can be monkeypatched to `fcntl.lockf` for testing. `fcntl.LOCK_SH`, `fcntl.LOCK_EX`, `fcntl.LOCK_NB`, `fcntl.LOCK_UN` are used as low-level flags.
- **Windows** (`os.name == "nt"`): Uses `msvcrt.get_osfhandle` to get a Windows file handle, then calls `win32file.LockFileEx` / `win32file.UnlockFileEx`. Requires `pywin32` package (`pywintypes`, `win32con`, `win32file`, `winerror`). A single module-level `pywintypes.OVERLAPPED()` instance (`__overlapped`) is reused for all lock operations.
- Any other platform raises `RuntimeError` at import time.

## Consequences
- Tests can monkeypatch `portalocker.portalocker.LOCKER` to switch between `fcntl.flock` and `fcntl.lockf`.
- `lock()` and `unlock()` functions are defined conditionally at module level (not in a class), so they are plain callables.
- Windows errors `ERROR_LOCK_VIOLATION` and `ERROR_SHARING_VIOLATION` map to `AlreadyLocked`; all other win32 errors map to `LockException`.
- POSIX errno `EACCES` and `EAGAIN` map to `AlreadyLocked`; all other `OSError` map to `LockException`.
