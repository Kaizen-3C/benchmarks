import enum
import os

LOCK_SH: int = 1
LOCK_EX: int = 2
LOCK_NB: int = 4
LOCK_UN: int = 8


class LockFlags(enum.IntFlag):
    SHARED = 1
    EXCLUSIVE = 2
    NON_BLOCKING = 4
    UNBLOCK = 8


if os.name not in ("nt", "posix"):
    raise RuntimeError(f"Unsupported platform: {os.name}")
