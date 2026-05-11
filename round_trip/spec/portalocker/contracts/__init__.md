# Contract: portalocker (top-level package)

## Re-exported names

All of the following are accessible as `portalocker.<name>`:

| Name | Source |
|------|--------|
| `lock` | `portalocker.portalocker.lock` |
| `unlock` | `portalocker.portalocker.unlock` |
| `LOCK_EX` | `constants.LockFlags.EXCLUSIVE` |
| `LOCK_SH` | `constants.LockFlags.SHARED` |
| `LOCK_NB` | `constants.LockFlags.NON_BLOCKING` |
| `LOCK_UN` | `constants.LockFlags.UNBLOCK` |
| `LockFlags` | `constants.LockFlags` |
| `LockException` | `exceptions.LockException` |
| `AlreadyLocked` | `exceptions.AlreadyLocked` |
| `Lock` | `utils.Lock` |
| `RLock` | `utils.RLock` |
| `BoundedSemaphore` | `utils.BoundedSemaphore` |
| `NamedBoundedSemaphore` | `utils.NamedBoundedSemaphore` |
| `TemporaryFileLock` | `utils.TemporaryFileLock` |
| `open_atomic` | `utils.open_atomic` |
| `RedisLock` | `redis.RedisLock` or `None` |
| `constants` | module |
| `exceptions` | module |
| `portalocker` | submodule |
| `__about__` | module |
| `__version__` | `"2.10.1"` |
| `__package_name__` | `"portalocker"` |
| `__author__` | `"Rick van Hattem"` |
| `__email__` | `"wolph@wol.ph"` |
| `__description__` | `"Wraps the portalocker recipe for easy usage"` |
| `__url__` | `"https://github.com/WoLpH/portalocker"` |
