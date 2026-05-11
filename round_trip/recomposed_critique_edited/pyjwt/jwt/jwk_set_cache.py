import time
from typing import Any, Optional

from .api_jwk import PyJWTSetWithTimestamp


class JWKSetCache:
    def __init__(self, lifespan: int):
        self.lifespan = lifespan
        self._cache: Optional[PyJWTSetWithTimestamp] = None

    def put(self, jwk_set: Any) -> None:
        if jwk_set is None:
            self._cache = None
        else:
            self._cache = PyJWTSetWithTimestamp(jwk_set)

    def get(self) -> Any:
        if self._cache is None:
            return None
        if self.is_expired():
            return None
        return self._cache.get_jwk_set()

    def is_expired(self) -> bool:
        if self._cache is None:
            return True
        return self._cache.get_timestamp() + self.lifespan < time.monotonic()
