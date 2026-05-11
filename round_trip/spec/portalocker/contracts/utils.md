# Contract: portalocker.utils

See ADR-0004 and ADR-0005 for design rationale.

## Constants
```python
DEFAULT_TIMEOUT: float = 5
DEFAULT_CHECK_INTERVAL: float = 0.25
DEFAULT_FAIL_WHEN_LOCKED: bool = False
LOCK_METHOD: LockFlags = LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING
Filename = Union[str, pathlib.Path]
```

## `coalesce(*args: Any, test_value: Any = None) -> Any`
Returns first argument not equal to `test_value`. Returns `None` if all match.

## `open_atomic(filename: Filename, binary: bool = True) -> Iterator[IO[Any]]`
Context manager. Writes to a temp file, fsyncs, atomically replaces `filename`. Cleans up temp file on exception.

## `LockBase(abc.ABC)`
```python
def __init__(self, timeout=None, check_interval=None, fail_when_locked=None): ...
def __enter__(self) -> Any: ...
def __exit__(self, exc_type, exc_value, traceback) -> None: ...
def acquire(self, *args, **kwargs) -> Any: ...  # abstract
def release(self) -> None: ...  # abstract
```

## `Lock(LockBase)`
```python
def __init__(self, filename: Filename, mode: str = "a",
             timeout: Optional[float] = DEFAULT_TIMEOUT,
             check_interval: float = DEFAULT_CHECK_INTERVAL,
             fail_when_locked: bool = DEFAULT_FAIL_WHEN_LOCKED,
             flags: LockFlags = LOCK_METHOD,
             **file_open_kwargs) -> None: ...
def acquire(self, timeout=None, check_interval=None, fail_when_locked=None) -> IO[Any]: ...
def release(self) -> None: ...
def _get_fh(self) -> IO[Any]: ...
def _get_lock(self, fh: IO[Any]) -> IO[Any]: ...
def _prepare_fh(self, fh: IO[Any]) -> IO[Any]: ...
```

## `RLock(Lock)`
```python
def __init__(self, filename, mode="a", timeout=DEFAULT_TIMEOUT,
             check_interval=DEFAULT_CHECK_INTERVAL,
             fail_when_locked=False, flags=LOCK_METHOD) -> None: ...
def acquire(self, timeout=None, check_interval=None, fail_when_locked=None) -> IO[Any]: ...
def release(self) -> None: ...
```
Reentrant: multiple `acquire()` calls without intervening `release()` are allowed on the same instance.

## `TemporaryFileLock(Lock)`
```python
def __init__(self, filename: Filename = ".lock",
             timeout=DEFAULT_TIMEOUT, check_interval=DEFAULT_CHECK_INTERVAL,
             fail_when_locked=True, flags=LOCK_METHOD) -> None: ...
def release(self) -> None: ...
```
Deletes `filename` on `release()`, GC (`__del__`), and process exit (`atexit`).

## `BoundedSemaphore(LockBase)`
```python
def __init__(self, maximum: int, name: str = "bounded_semaphore",
             filename_pattern: str = "{name}.{number:02d}.lock",
             directory: str = tempfile.gettempdir(),
             timeout=None, check_interval=None, fail_when_locked=True) -> None: ...
def get_filename(self, number: int) -> pathlib.Path: ...
def get_filenames(self) -> Sequence[pathlib.Path]: ...
def get_random_filenames(self) -> Sequence[pathlib.Path]: ...
def try_lock(self, filenames: Sequence[Union[str, pathlib.Path]]) -> bool: ...
def acquire(self, timeout=None, check_interval=None, fail_when_locked=None) -> Optional[Lock]: ...
def release(self) -> None: ...
```

## `NamedBoundedSemaphore(BoundedSemaphore)`
```python
def __init__(self, maximum: int, name: Optional[str] = None, ...) -> None: ...
```
If `name` is `None`, auto-generates `"bounded_semaphore.{randint(0,1000000)}"`.
