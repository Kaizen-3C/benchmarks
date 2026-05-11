import abc
import atexit
import contextlib
import os
import pathlib
import random
import tempfile
import time
import warnings
import weakref
from typing import Any, IO, Iterator, Optional, Sequence, Union

from . import constants, exceptions, portalocker as portalocker_module

LockFlags = constants.LockFlags
Filename = Union[str, pathlib.Path]

DEFAULT_TIMEOUT: float = 5
DEFAULT_CHECK_INTERVAL: float = 0.25
DEFAULT_FAIL_WHEN_LOCKED: bool = False
LOCK_METHOD: LockFlags = LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING


def coalesce(*args: Any, test_value: Any = None) -> Any:
    for arg in args:
        if arg is not test_value:
            return arg
    return None


@contextlib.contextmanager
def open_atomic(filename: Filename, binary: bool = True) -> Iterator[IO[Any]]:
    filename = pathlib.Path(filename)
    parent = filename.parent
    parent.mkdir(parents=True, exist_ok=True)

    mode = "w+b" if binary else "w+"
    tmp_path = None
    try:
        fd, tmp_path_str = tempfile.mkstemp(dir=str(parent))
        tmp_path = pathlib.Path(tmp_path_str)
        with os.fdopen(fd, mode) as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(filename)
        tmp_path = None
    except Exception:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


class LockBase(abc.ABC):
    def __init__(
        self,
        timeout: Optional[float] = None,
        check_interval: Optional[float] = None,
        fail_when_locked: Optional[bool] = None,
    ) -> None:
        self.timeout = coalesce(timeout, DEFAULT_TIMEOUT)
        self.check_interval = coalesce(check_interval, DEFAULT_CHECK_INTERVAL)
        self.fail_when_locked = coalesce(fail_when_locked, DEFAULT_FAIL_WHEN_LOCKED)

    def __enter__(self) -> Any:
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.release()

    @abc.abstractmethod
    def acquire(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    @abc.abstractmethod
    def release(self) -> None:
        raise NotImplementedError


class Lock(LockBase):
    def __init__(
        self,
        filename: Filename,
        mode: str = "a",
        timeout: Optional[float] = DEFAULT_TIMEOUT,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        fail_when_locked: bool = DEFAULT_FAIL_WHEN_LOCKED,
        flags: LockFlags = LOCK_METHOD,
        **file_open_kwargs: Any,
    ) -> None:
        self.filename = filename
        self.truncate = False

        if "w" in mode:
            self.truncate = True
            mode = mode.replace("w", "a")

        self.mode = mode
        self.flags = flags
        self.file_open_kwargs = file_open_kwargs
        self.fh: Optional[IO[Any]] = None

        if timeout is not None and not (flags & LockFlags.NON_BLOCKING):
            warnings.warn(
                "timeout has no effect in blocking mode",
                UserWarning,
                stacklevel=2,
            )

        super().__init__(
            timeout=timeout,
            check_interval=check_interval,
            fail_when_locked=fail_when_locked,
        )

    def acquire(
        self,
        timeout: Optional[float] = None,
        check_interval: Optional[float] = None,
        fail_when_locked: Optional[bool] = None,
    ) -> IO[Any]:
        timeout = coalesce(timeout, self.timeout)
        check_interval = coalesce(check_interval, self.check_interval)
        fail_when_locked = coalesce(fail_when_locked, self.fail_when_locked)

        if timeout is not None and not (self.flags & LockFlags.NON_BLOCKING):
            warnings.warn(
                "timeout has no effect in blocking mode",
                UserWarning,
                stacklevel=2,
            )

        start_time = time.monotonic()
        watch_time = coalesce(timeout, 0.0)

        while True:
            try:
                fh = self._get_fh()
                try:
                    fh = self._get_lock(fh)
                    fh = self._prepare_fh(fh)
                    self.fh = fh
                    return fh
                except exceptions.AlreadyLocked:
                    fh.close()
                    raise
            except exceptions.AlreadyLocked:
                if fail_when_locked:
                    raise

                elapsed = time.monotonic() - start_time
                if timeout is not None and elapsed >= watch_time:
                    raise

                time.sleep(check_interval)

                elapsed = time.monotonic() - start_time
                if timeout is not None and elapsed >= watch_time:
                    raise

    def release(self) -> None:
        if self.fh is not None:
            portalocker_module.unlock(self.fh)
            self.fh.close()
            self.fh = None

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def _get_fh(self) -> IO[Any]:
        return open(self.filename, self.mode, **self.file_open_kwargs)

    def _get_lock(self, fh: IO[Any]) -> IO[Any]:
        portalocker_module.lock(fh, self.flags)
        return fh

    def _prepare_fh(self, fh: IO[Any]) -> IO[Any]:
        if self.truncate:
            fh.seek(0)
            fh.truncate()
        fh.seek(0)
        return fh


class RLock(Lock):
    def __init__(
        self,
        filename: Filename,
        mode: str = "a",
        timeout: Optional[float] = DEFAULT_TIMEOUT,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        fail_when_locked: bool = False,
        flags: LockFlags = LOCK_METHOD,
        **file_open_kwargs: Any,
    ) -> None:
        super().__init__(
            filename=filename,
            mode=mode,
            timeout=timeout,
            check_interval=check_interval,
            fail_when_locked=fail_when_locked,
            flags=flags,
            **file_open_kwargs,
        )
        self._acquire_count: int = 0

    def acquire(
        self,
        timeout: Optional[float] = None,
        check_interval: Optional[float] = None,
        fail_when_locked: Optional[bool] = None,
    ) -> IO[Any]:
        if self.fh is not None:
            self._acquire_count += 1
            return self.fh

        fh = super().acquire(
            timeout=timeout,
            check_interval=check_interval,
            fail_when_locked=fail_when_locked,
        )
        self._acquire_count = 1
        return fh

    def release(self) -> None:
        if self._acquire_count <= 0:
            raise exceptions.LockException("Cannot release an unacquired lock")
        self._acquire_count -= 1
        if self._acquire_count == 0:
            super().release()


class TemporaryFileLock(Lock):
    def __init__(
        self,
        filename: Filename = ".lock",
        timeout: Optional[float] = DEFAULT_TIMEOUT,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        fail_when_locked: bool = True,
        flags: LockFlags = LOCK_METHOD,
        **file_open_kwargs: Any,
    ) -> None:
        super().__init__(
            filename=filename,
            mode="w",
            timeout=timeout,
            check_interval=check_interval,
            fail_when_locked=fail_when_locked,
            flags=flags,
            **file_open_kwargs,
        )
        self._finalizer = weakref.finalize(
            self, self._cleanup_file, self.filename
        )
        atexit.register(self._atexit_release)

    def _atexit_release(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    @staticmethod
    def _cleanup_file(filename: Filename) -> None:
        try:
            os.unlink(filename)
        except OSError:
            pass

    def release(self) -> None:
        try:
            super().release()
        except Exception:
            pass
        self._cleanup_file(self.filename)
        if self._finalizer.alive:
            self._finalizer.detach()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


class BoundedSemaphore(LockBase):
    def __init__(
        self,
        maximum: int,
        name: str = "bounded_semaphore",
        filename_pattern: str = "{name}.{number:02d}.lock",
        directory: str = tempfile.gettempdir(),
        timeout: Optional[float] = None,
        check_interval: Optional[float] = None,
        fail_when_locked: Optional[bool] = True,
    ) -> None:
        self.maximum = maximum
        self.name = name
        self.filename_pattern = filename_pattern
        self.directory = directory
        self.lock: Optional[Lock] = None
        super().__init__(
            timeout=timeout,
            check_interval=check_interval,
            fail_when_locked=fail_when_locked,
        )

    def get_filename(self, number: int) -> pathlib.Path:
        return pathlib.Path(self.directory) / self.filename_pattern.format(
            name=self.name, number=number
        )

    def get_filenames(self) -> Sequence[pathlib.Path]:
        return [self.get_filename(i) for i in range(self.maximum)]

    def get_random_filenames(self) -> Sequence[pathlib.Path]:
        filenames = list(self.get_filenames())
        random.shuffle(filenames)
        return filenames

    def try_lock(self, filenames: Sequence[Union[str, pathlib.Path]]) -> bool:
        for filename in filenames:
            try:
                lock = Lock(
                    filename,
                    mode="a",
                    timeout=0,
                    fail_when_locked=True,
                )
                lock.acquire()
                self.lock = lock
                return True
            except exceptions.AlreadyLocked:
                continue
        return False

    def acquire(
        self,
        timeout: Optional[float] = None,
        check_interval: Optional[float] = None,
        fail_when_locked: Optional[bool] = None,
    ) -> Optional[Lock]:
        timeout = coalesce(timeout, self.timeout)
        check_interval = coalesce(check_interval, self.check_interval)
        fail_when_locked = coalesce(fail_when_locked, self.fail_when_locked)

        start_time = time.monotonic()

        while True:
            if self.try_lock(self.get_random_filenames()):
                return self.lock

            if fail_when_locked:
                raise exceptions.AlreadyLocked(
                    "Could not acquire lock within timeout"
                )

            elapsed = time.monotonic() - start_time
            if timeout is not None and elapsed >= timeout:
                if not self.try_lock(self.get_random_filenames()):
                    raise exceptions.AlreadyLocked(
                        "Could not acquire lock within timeout"
                    )
                return self.lock

            time.sleep(check_interval)

            elapsed = time.monotonic() - start_time
            if timeout is not None and elapsed >= timeout:
                if not self.try_lock(self.get_random_filenames()):
                    raise exceptions.AlreadyLocked(
                        "Could not acquire lock within timeout"
                    )
                return self.lock

    def release(self) -> None:
        if self.lock is not None:
            filename = self.lock.filename
            self.lock.release()
            self.lock = None
            try:
                os.unlink(filename)
            except OSError:
                pass

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


class NamedBoundedSemaphore(BoundedSemaphore):
    def __init__(
        self,
        maximum: int,
        name: Optional[str] = None,
        filename_pattern: str = "{name}.{number:02d}.lock",
        directory: str = tempfile.gettempdir(),
        timeout: Optional[float] = None,
        check_interval: Optional[float] = None,
        fail_when_locked: Optional[bool] = True,
    ) -> None:
        if name is None:
            name = f"bounded_semaphore.{random.randint(0, 1000000)}"
        super().__init__(
            maximum=maximum,
            name=name,
            filename_pattern=filename_pattern,
            directory=directory,
            timeout=timeout,
            check_interval=check_interval,
            fail_when_locked=fail_when_locked,
        )
