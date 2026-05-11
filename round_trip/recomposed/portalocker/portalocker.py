import os
import typing
from typing import Any, Callable, Optional, Union

from . import constants, exceptions

LockFlags = constants.LockFlags


class HasFileno(typing.Protocol):
    def fileno(self) -> int: ...


LOCKER: Optional[Callable[[Union[int, HasFileno], int], Any]] = None

if os.name == "posix":
    import fcntl

    LOCKER = fcntl.flock

    def lock(file_: Union[int, HasFileno], flags: LockFlags) -> Any:
        lk_flags = 0

        if flags & LockFlags.SHARED:
            lk_flags |= fcntl.LOCK_SH
        if flags & LockFlags.EXCLUSIVE:
            lk_flags |= fcntl.LOCK_EX
        if flags & LockFlags.NON_BLOCKING:
            lk_flags |= fcntl.LOCK_NB
        if flags & LockFlags.UNBLOCK:
            lk_flags |= fcntl.LOCK_UN

        if (flags & LockFlags.NON_BLOCKING) and not (
            flags & LockFlags.SHARED or flags & LockFlags.EXCLUSIVE
        ):
            raise RuntimeError(
                "NON_BLOCKING flag requires SHARED or EXCLUSIVE flag"
            )

        try:
            return LOCKER(file_, lk_flags)  # type: ignore[misc]
        except OSError as e:
            import errno
            if e.errno in (errno.EACCES, errno.EAGAIN):
                raise exceptions.AlreadyLocked(e, fh=file_)  # type: ignore[arg-type]
            else:
                raise exceptions.LockException(e, fh=file_)  # type: ignore[arg-type]

    def unlock(file_: Union[int, HasFileno]) -> Any:
        try:
            return LOCKER(file_, fcntl.LOCK_UN)  # type: ignore[misc]
        except OSError as e:
            raise exceptions.LockException(e, fh=file_)  # type: ignore[arg-type]

elif os.name == "nt":
    import msvcrt
    import pywintypes
    import win32con
    import win32file
    import winerror

    __overlapped = pywintypes.OVERLAPPED()

    def lock(file_: Union[int, HasFileno], flags: LockFlags) -> Any:
        try:
            if isinstance(file_, int):
                handle = msvcrt.get_osfhandle(file_)
            else:
                handle = msvcrt.get_osfhandle(file_.fileno())

            win32_flags = 0
            if flags & LockFlags.EXCLUSIVE:
                win32_flags |= win32con.LOCKFILE_EXCLUSIVE_LOCK
            if flags & LockFlags.NON_BLOCKING:
                win32_flags |= win32con.LOCKFILE_FAIL_IMMEDIATELY

            win32file.LockFileEx(handle, win32_flags, 0, -0x10000, __overlapped)
        except pywintypes.error as e:
            if e.winerror in (winerror.ERROR_LOCK_VIOLATION, winerror.ERROR_SHARING_VIOLATION):
                raise exceptions.AlreadyLocked(e, fh=file_)  # type: ignore[arg-type]
            else:
                raise exceptions.LockException(e, fh=file_)  # type: ignore[arg-type]

    def unlock(file_: Union[int, HasFileno]) -> Any:
        try:
            if isinstance(file_, int):
                handle = msvcrt.get_osfhandle(file_)
            else:
                handle = msvcrt.get_osfhandle(file_.fileno())

            win32file.UnlockFileEx(handle, 0, -0x10000, __overlapped)
        except pywintypes.error as e:
            raise exceptions.LockException(e, fh=file_)  # type: ignore[arg-type]

else:
    raise RuntimeError(f"Unsupported platform: {os.name}")
