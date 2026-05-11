# Contract: portalocker.exceptions

## Public API

### `BaseLockException(Exception)`
```python
class BaseLockException(Exception):
    LOCK_FAILED: int = 1
    fh: Optional[IO[Any]]

    def __init__(self, *args: Any, fh: Optional[IO[Any]] = None, **kwargs: Any) -> None: ...
```
Base for all portalocker exceptions. Stores `fh` (file handle) as instance attribute.

### `LockException(BaseLockException)`
Generic locking failure. Raised when a lock operation fails for reasons other than the lock being held.

### `AlreadyLocked(LockException)`
Raised when a non-blocking lock attempt fails because another process/thread holds the lock.

### `FileToLarge(LockException)`
Defined; not currently raised by library code. Reserved.

See ADR-0003.
