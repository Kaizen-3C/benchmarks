from . import __about__, constants, exceptions, portalocker
from .utils import BoundedSemaphore, Lock, NamedBoundedSemaphore, RLock, TemporaryFileLock, open_atomic

try:
    from .redis import RedisLock
except ImportError:
    RedisLock = None  # type: ignore[assignment,misc]

# Module-level aliases from __about__
__package_name__ = __about__.__package_name__
__author__ = __about__.__author__
__email__ = __about__.__email__
__version__ = __about__.__version__
__description__ = __about__.__description__
__url__ = __about__.__url__

# Exception aliases
AlreadyLocked = exceptions.AlreadyLocked
LockException = exceptions.LockException

# Function aliases
lock = portalocker.lock
unlock = portalocker.unlock

# Flag aliases
LOCK_EX = constants.LockFlags.EXCLUSIVE
LOCK_SH = constants.LockFlags.SHARED
LOCK_NB = constants.LockFlags.NON_BLOCKING
LOCK_UN = constants.LockFlags.UNBLOCK
LockFlags = constants.LockFlags

__all__ = [
    "lock",
    "unlock",
    "LOCK_EX",
    "LOCK_SH",
    "LOCK_NB",
    "LOCK_UN",
    "LockFlags",
    "LockException",
    "Lock",
    "RLock",
    "AlreadyLocked",
    "BoundedSemaphore",
    "NamedBoundedSemaphore",
    "TemporaryFileLock",
    "open_atomic",
    "RedisLock",
]
