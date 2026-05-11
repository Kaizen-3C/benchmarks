import time
from typing import Any, Optional

from .api_jwk import PyJWTSetWithTimestamp


class JWKSetCache:
    def __init__(self, lifespan: int):
        self.lifespan = lifespan
        self._jwk_set_with_timestamp: Optional[PyJWTSetWithTimestamp] = None

    def put(self, jwk_set: Any) -> None:
        if jwk_set is None:
            self._jwk_set_with_timestamp = None
        else:
            self._jwk_set_with_timestamp = PyJWTSetWithTimestamp(jwk_set)

    def get(self) -> Any:
        if self.is_expired():
            return None
        return self._jwk_set_with_timestamp.get_jwk_set()

    def is_expired(self) -> bool:
        if self._jwk_set_with_timestamp is None:
            return True
        timestamp = self._jwk_set_with_timestamp.get_timestamp()
        return timestamp + self.lifespan < time.monotonic()
