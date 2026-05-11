# Contract: portalocker.redis

See ADR-0006.

## `PubSubWorkerThread(_PubSubWorkerBase)`
Wraps `redis.client.PubSubWorkerThread` (or stub). Overrides `run()` to log exceptions.

## `RedisLock(utils.LockBase)`
```python
DEFAULT_REDIS_KWARGS: ClassVar[Dict[str, Any]] = {"health_check_interval": 10}

def __init__(self, channel: str,
             connection: Optional[Redis] = None,
             timeout: Optional[float] = None,
             check_interval: Optional[float] = None,
             fail_when_locked: Optional[bool] = False,
             thread_sleep_time: float = 0.1,
             unavailable_timeout: float = 1,
             redis_kwargs: Optional[Dict[str, Any]] = None) -> None: ...

def acquire(self, timeout=None, check_interval=None, fail_when_locked=None) -> "RedisLock": ...
def release(self) -> None: ...
def get_connection(self) -> Redis: ...

@property
def client_name(self) -> Optional[str]: ...
```
