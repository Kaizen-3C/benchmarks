# ADR-0005: BoundedSemaphore and NamedBoundedSemaphore Design

## Status
Accepted

## Context
Some use-cases require limiting concurrent access to a resource to at most N processes, not just 1.

## Decision
`BoundedSemaphore(LockBase)` implements a counting semaphore using N lock files:

- Constructor: `maximum: int`, `name: str = "bounded_semaphore"`, `filename_pattern: str = "{name}.{number:02d}.lock"`, `directory: str = tempfile.gettempdir()`, plus `LockBase` params (default `fail_when_locked=True`).
- `get_filename(number)` → `Path(directory) / filename_pattern.format(name=name, number=number)`.
- `get_filenames()` → list of `maximum` filenames (numbers 0..maximum-1).
- `get_random_filenames()` → shuffled copy of `get_filenames()`.
- `try_lock(filenames)` → tries each filename in order; on first successful `Lock(filename, mode="a", timeout=0, fail_when_locked=True).acquire()`, stores as `self.lock` and returns `True`. Returns `False` if none succeed.
- `acquire()`: loops calling `try_lock(get_random_filenames())`. On failure: if `fail_when_locked`, raises `AlreadyLocked`; if `timeout` exceeded after a final `try_lock`, raises `AlreadyLocked`; otherwise `time.sleep(check_interval)`.
- `release()`: releases `self.lock`, sets to `None`, unlinks the file.
- `__del__` suppresses all exceptions from `release()`.

`NamedBoundedSemaphore(BoundedSemaphore)`:
- If `name` is `None`, generates `"bounded_semaphore.{random.randint(0,1000000)}"`.
- Otherwise identical to `BoundedSemaphore`.

## Consequences
- Randomized filename order reduces thundering-herd on contention.
- Each slot is a separate lock file; up to `maximum` concurrent holders possible.
