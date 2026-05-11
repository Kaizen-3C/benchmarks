import functools
import json
from ssl import SSLContext
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .api_jwk import PyJWK, PyJWKSet
from .api_jwt import decode_complete as decode_token
from .exceptions import PyJWKClientConnectionError, PyJWKClientError
from .jwk_set_cache import JWKSetCache


class PyJWKClient:
    def __init__(
        self,
        uri: str,
        cache_keys: bool = False,
        max_cached_keys: int = 16,
        cache_jwk_set: bool = True,
        lifespan: int = 300,
        headers: Optional[Dict] = None,
        timeout: int = 30,
        ssl_context: Optional[SSLContext] = None,
    ):
        self.uri = uri
        self.cache_jwk_set = cache_jwk_set
        self.headers = headers or {}
        self.timeout = timeout
        self.ssl_context = ssl_context

        if cache_jwk_set:
            if lifespan <= 0:
                raise PyJWKClientError(
                    "Lifespan must be greater than 0 when cache_jwk_set is True"
                )
            self._jwk_set_cache = JWKSetCache(lifespan)
        else:
            self._jwk_set_cache = None

        if cache_keys:
            self.get_signing_key = functools.lru_cache(maxsize=max_cached_keys)(
                self.get_signing_key
            )

    def fetch_data(self) -> Any:
        try:
            req = Request(self.uri, headers=self.headers)
            if self.ssl_context is not None:
                response = urlopen(req, timeout=self.timeout, context=self.ssl_context)
            else:
                response = urlopen(req, timeout=self.timeout)
            return json.loads(response.read())
        except (URLError, TimeoutError) as e:
            raise PyJWKClientConnectionError(
                f"Failed to fetch JWKS from {self.uri}: {e}"
            ) from e

    def get_jwk_set(self, refresh: bool = False) -> PyJWKSet:
        if self._jwk_set_cache is not None and not refresh:
            cached = self._jwk_set_cache.get()
            if cached is not None:
                if isinstance(cached, PyJWKSet):
                    return cached
                # It's a dict, convert
                return PyJWKSet.from_dict(cached)

        # Fetch data
        data = self.fetch_data()
        if not isinstance(data, dict):
            raise PyJWKClientError("The JWKS endpoint did not return a JSON object")

        jwk_set = PyJWKSet.from_dict(data)

        if self._jwk_set_cache is not None:
            self._jwk_set_cache.put(jwk_set)

        return jwk_set

    def get_signing_keys(self, refresh: bool = False) -> List[PyJWK]:
        jwk_set = self.get_jwk_set(refresh=refresh)
        signing_keys = [
            k
            for k in jwk_set.keys
            if k.public_key_use in ("sig", None) and k.key_id is not None and k.key is not None
        ]
        if not signing_keys:
            raise PyJWKClientError("The JWKS endpoint did not contain any signing keys")
        return signing_keys

    def get_signing_key(self, kid: str) -> PyJWK:
        signing_keys = self.get_signing_keys()
        for key in signing_keys:
            if key.key_id == kid:
                return key

        # Retry with refresh
        signing_keys = self.get_signing_keys(refresh=True)
        for key in signing_keys:
            if key.key_id == kid:
                return key

        raise PyJWKClientError(f"Unable to find a signing key that matches: {kid}")

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        unverified = decode_token(
            token,
            options={"verify_signature": False},
        )
        header = unverified.get("header", {})
        kid = header.get("kid")
        if kid is None:
            raise PyJWKClientError("No 'kid' in token header")
        return self.get_signing_key(kid)
