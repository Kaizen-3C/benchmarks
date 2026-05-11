import json
import ssl
from functools import lru_cache
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
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        self.uri = uri
        self.headers = headers or {}
        self.timeout = timeout
        self.ssl_context = ssl_context

        if cache_jwk_set:
            if lifespan <= 0:
                raise PyJWKClientError(
                    "lifespan must be greater than 0 when cache_jwk_set is True"
                )
            self.jwk_set_cache = JWKSetCache(lifespan)
        else:
            self.jwk_set_cache = None

        if cache_keys:
            self.get_signing_key = lru_cache(maxsize=max_cached_keys)(self.get_signing_key)  # type: ignore

    def fetch_data(self) -> Any:
        try:
            request = Request(self.uri, headers=self.headers)
            if self.ssl_context is not None:
                response = urlopen(request, timeout=self.timeout, context=self.ssl_context)
            else:
                response = urlopen(request, timeout=self.timeout)
            return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError) as e:
            raise PyJWKClientConnectionError(f"Failed to fetch data: {e}")

    def get_jwk_set(self, refresh: bool = False) -> PyJWKSet:
        if self.jwk_set_cache is not None and not refresh:
            cached = self.jwk_set_cache.get()
            if cached is not None:
                if isinstance(cached, PyJWKSet):
                    return cached
                # cached might be a dict
                if isinstance(cached, dict):
                    return PyJWKSet.from_dict(cached)

        data = self.fetch_data()
        if not isinstance(data, dict):
            raise PyJWKClientError("The data returned from the JWKS endpoint must be a dict")

        jwk_set = PyJWKSet.from_dict(data)

        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(jwk_set)

        return jwk_set

    def get_signing_keys(self, refresh: bool = False) -> List[PyJWK]:
        jwk_set = self.get_jwk_set(refresh=refresh)
        signing_keys = [
            key for key in jwk_set.keys
            if key.public_key_use in ("sig", None) and key.key_id is not None and key.key is not None
        ]
        if not signing_keys:
            raise PyJWKClientError("The JWKS endpoint did not contain any signing keys")
        return signing_keys

    def get_signing_key(self, kid: str) -> PyJWK:
        signing_keys = self.get_signing_keys()
        for key in signing_keys:
            if key.key_id == kid:
                return key

        # Key not found, try refreshing
        signing_keys = self.get_signing_keys(refresh=True)
        for key in signing_keys:
            if key.key_id == kid:
                return key

        raise PyJWKClientError(f"Unable to find a signing key that matches: {kid!r}")

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        from .api_jws import get_unverified_header
        header = get_unverified_header(token)
        kid = header.get("kid")
        if kid is None:
            raise PyJWKClientError("No kid header parameter found in the token")
        return self.get_signing_key(kid)
