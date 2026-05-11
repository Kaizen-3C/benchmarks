import functools
import json
from ssl import SSLContext
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen, Request

from .api_jwk import PyJWK, PyJWKSet
from .api_jwt import decode_complete as decode_token
from .exceptions import PyJWKClientConnectionError, PyJWKClientError
from .jwk_set_cache import JWKSetCache


class PyJWKClient:
    def __init__(
        self,
        uri: str,
