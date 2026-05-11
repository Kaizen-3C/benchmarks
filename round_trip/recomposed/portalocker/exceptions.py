from typing import Any, IO, Optional


class BaseLockException(Exception):
    LOCK_FAILED: int = 1

    def __init__(self, *args: Any, fh: Optional[IO[Any]] = None, **kwargs: Any) -> None:
        self.fh = fh
        super().__init__(*args)


class LockException(BaseLockException):
    pass


class AlreadyLocked(LockException):
    pass


class FileToLarge(LockException):
    pass
