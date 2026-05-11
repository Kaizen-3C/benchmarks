import logging
import time
import json
import random
import threading
from typing import Any, Dict, Optional

from . import exceptions, utils

logger = logging.getLogger(__name__)

try:
    import redis as redis_module

    class _PubSubWorkerBase(redis_module.client.PubSubWorkerThread):
        pass

    class PubSubWorkerThread(_PubSubWorkerBase):
        def run(self) -> None:
            try:
                super().run()
            except Exception:
                logger.exception("Error in PubSubWorkerThread")
                raise

    class RedisLock(utils.LockBase):
        DEFAULT_REDIS_KWARGS: Dict[str, Any] = {"health_check_interval": 10}

        def __init__(
            self,
            channel: str,
            connection: Optional[Any] = None,
            timeout: Optional[float] = None,
            check_interval: Optional[float] = None,
            fail_when_locked: Optional[bool] = False,
            thread_sleep_time: float = 0.1,
            unavailable_timeout: float = 1,
            redis_kwargs: Optional[Dict[str, Any]] = None,
        ) -> None:
            self.channel = channel
            self._connection = connection
            self.close_connection = connection is None
            self.thread_sleep_time = thread_sleep_time
            self.unavailable_timeout = unavailable_timeout
            self.redis_kwargs = redis_kwargs or {}
            self._token: Optional[str] = None
            self._pubsub: Any = None
            self._thread: Optional[PubSubWorkerThread] = None
            super().__init__(
                timeout=timeout,
                check_interval=check_interval,
                fail_when_locked=fail_when_locked,
            )

        @property
        def client_name(self) -> Optional[str]:
            return f"portalocker:{self.channel}"

        def get_connection(self) -> Any:
            if self._connection is None:
                kwargs = dict(self.DEFAULT_REDIS_KWARGS)
                kwargs.update(self.redis_kwargs)
                self._connection = redis_module.Redis(**kwargs)
            return self._connection

        def _get_lock_key(self) -> str:
            return f"portalocker:redislock:{self.channel}"

        def _make_token(self) -> str:
            data = {
                "rand": random.random(),
                "thread": threading.get_ident(),
                "time": time.time(),
            }
            return json.dumps(data, sort_keys=True)

        def acquire(
            self,
            timeout: Optional[float] = None,
            check_interval: Optional[float] = None,
            fail_when_locked: Optional[bool] = None,
        ) -> "RedisLock":
            timeout = utils.coalesce(timeout, self.timeout)
            check_interval = utils.coalesce(check_interval, self.check_interval)
            fail_when_locked = utils.coalesce(fail_when_locked, self.fail_when_locked)

            connection = self.get_connection()
            lock_key = self._get_lock_key()
            token = self._make_token()

            start_time = time.monotonic()

            pubsub = connection.pubsub()
            pubsub.subscribe(lock_key)
            self._pubsub = pubsub

            thread = PubSubWorkerThread(pubsub, sleep_time=self.thread_sleep_time, daemon=True)
            thread.start()
            self._thread = thread

            while True:
                result = connection.set(lock_key, token, nx=True)
                if result:
                    self._token = token
                    return self

                if fail_when_locked:
                    raise exceptions.AlreadyLocked(
                        f"Could not acquire Redis lock on channel {self.channel!r}"
                    )

                elapsed = time.monotonic() - start_time
                if timeout is not None and elapsed >= timeout:
                    raise exceptions.AlreadyLocked(
                        f"Could not acquire Redis lock on channel {self.channel!r}"
                    )

                pubsub.get_message(timeout=check_interval)

                elapsed = time.monotonic() - start_time
                if timeout is not None and elapsed >= timeout:
                    raise exceptions.AlreadyLocked(
                        f"Could not acquire Redis lock on channel {self.channel!r}"
                    )

        def release(self) -> None:
            connection = self.get_connection()
            lock_key = self._get_lock_key()

            if self._token is not None:
                current = connection.get(lock_key)
                if current is not None and current.decode() == self._token:
                    connection.delete(lock_key)
                    connection.publish(lock_key, "released")
                self._token = None

            if self._thread is not None:
                try:
                    self._thread.stop()
                except Exception:
                    pass
                self._thread = None

            if self._pubsub is not None:
                try:
                    self._pubsub.close()
                except Exception:
                    pass
                self._pubsub = None

            if self.close_connection and self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None

        def __del__(self) -> None:
            try:
                self.release()
            except Exception:
                pass

except ImportError:
    class _PubSubWorkerBase:  # type: ignore[no-redef]
        def start(self) -> None:
            raise RuntimeError('Redis support requires the "redis" package.')

        def run(self) -> None:
            raise RuntimeError('Redis support requires the "redis" package.')

    class PubSubWorkerThread(_PubSubWorkerBase):  # type: ignore[no-redef]
        pass

    RedisLock = None  # type: ignore[assignment,misc]
