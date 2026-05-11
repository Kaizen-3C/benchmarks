# ADR-0003: Exception Hierarchy

## Status
Accepted

## Context
Callers need to distinguish between "lock is already held by another process" and generic locking failures.

## Decision
Three exception classes are defined in `exceptions.py`:

1. `BaseLockException(Exception)`: base class. Has class attribute `LOCK_FAILED = 1`. Constructor accepts `*args`, keyword-only `fh: Optional[IO[Any]] = None`, and `**kwargs`. Stores `fh` as instance attribute; passes `*args` to `Exception.__init__`.
2. `LockException(BaseLockException)`: generic locking failure.
3. `AlreadyLocked(LockException)`: raised when a non-blocking lock attempt fails because another process holds the lock.
4. `FileToLarge(LockException)`: defined but not raised by current code (reserved for future use).

`LockException` and `AlreadyLocked` are re-exported from `portalocker.__init__`.

## Consequences
- Tests catch `portalocker.LockException` and `portalocker.AlreadyLocked` by name.
- The `fh` attribute on exceptions gives callers access to the file handle involved.
