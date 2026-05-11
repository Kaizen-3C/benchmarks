# ADR-0006: RedisLock Design

## Status
Accepted

## Context
For distributed locking across multiple machines, a Redis-backed lock is needed.

## Decision
`redis.py` provides `RedisLock(utils.LockBase)`:

- Optional dependency: `redis` package. If not installed, `RedisLock` is still importable (imported in `__init__.py` inside `try/except ImportError`; on failure `RedisLock = None`).
- Constructor params: `channel: str`, `connection: Optional[Redis] = None`, `timeout`, `check_interval`, `fail_when_locked=False`, `thread_sleep_time: float = 0.1`, `unavailable_timeout: float = 1`, `redis_kwargs: Optional[Dict] = None`.
- Class variable `DEFAULT_REDIS_KWARGS = {"health_check_interval": 10}`.
- Token: a JSON string of `{"thread": thread_id, "time": timestamp, "rand": random_float}` (keys sorted).
- Lock key: `"portalocker:redislock:" + channel`.
- `acquire()`: uses Redis `SET key token NX` (set-if-not-exists). On success, stores token, starts a `PubSubWorkerThread` (daemon) subscribed to the lock key channel. On failure, waits using pubsub `get_message(timeout=check_interval)` then retries until timeout.
- `release()`: if token matches current Redis value, deletes key and publishes `"released"` to channel. Stops thread, closes pubsub, optionally closes connection (if `close_connection=True`, i.e., connection was not provided by caller).
- `__del__` suppresses all exceptions from `release()`.
- `PubSubWorkerThread(redis_client.PubSubWorkerThread)`: overrides `run()` to log exceptions via `logger.exception(...)` before re-raising.
- When `redis` is unavailable, a stub `_PubSubWorkerBase` class is defined whose `start()` and `run()` raise `RuntimeError('Redis support requires the "redis" package.')`.

## Consequences
- `RedisLock` is `None` in `portalocker` namespace when `redis` is not installed.
- Distributed locking correctness depends on Redis atomicity of `SET NX`.
