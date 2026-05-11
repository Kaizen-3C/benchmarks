import json
import time
from typing import Any, Dict, List, Optional, Union

from .algorithms import get_default_algorithms, has_crypto, requires_cryptography
from .exceptions import InvalidKeyError, PyJWKError, PyJWKSetError, PyJWTError
from .types import JWKDict


class PyJWK:
    def __init__(self, jwk_data: JWKDict, algorithm: Optional[str] = None):
        self._jwk_data = jwk_data

        kty = jwk_data.get("kty")
        if not kty:
            raise InvalidKeyError("kty is not found: %s" % jwk_data)

        # Set key_type as plain attribute
        self.key_type = kty

        # Determine algorithm
        if algorithm is None:
            algorithm = jwk_data.get("alg")

        if algorithm is None:
            # Infer from kty/crv
            if kty == "EC":
                crv = jwk_data.get("crv", "P-256")
                if crv in ("P-256", None):
                    algorithm = "ES256"
                elif crv == "P-384":
                    algorithm = "ES384"
                elif crv == "P-521":
                    algorithm = "ES512"
                elif crv == "secp256k1":
                    algorithm = "ES256K"
                else:
                    raise InvalidKeyError(f"Unsupported EC curve: {crv}")
            elif kty == "RSA":
                algorithm = "RS256"
            elif kty == "oct":
                algorithm = "HS256"
            elif kty == "OKP":
                crv = jwk_data.get("crv")
                if crv is None:
                    raise InvalidKeyError("OKP key missing 'crv'")
                elif crv in ("Ed25519", "Ed448"):
                    algorithm = "EdDSA"
                else:
                    raise InvalidKeyError(f"Unsupported OKP curve: {crv}")
            else:
                raise InvalidKeyError(f"Unknown key type: {kty}")

        self.algorithm_name = algorithm

        if not has_crypto and algorithm in requires_cryptography:
            raise PyJWKError(
                f"cryptography is required to use {algorithm}. "
                "Install it with `pip install cryptography`."
            )

        # Get the algorithm object
        algorithms = get_default_algorithms()
        if algorithm not in algorithms:
            if algorithm in requires_cryptography:
                raise PyJWKError(
                    f"cryptography is required to use {algorithm}. "
                    "Install it with `pip install cryptography`."
                )
            raise InvalidKeyError(f"Unknown algorithm: {algorithm}")

        self.Algorithm = algorithms[algorithm]

        # Deserialize the key
        try:
            self.key = self.Algorithm.from_jwk(jwk_data)
        except InvalidKeyError:
            raise
        except Exception as e:
            raise InvalidKeyError(f"Failed to load key: {e}") from e

    @staticmethod
    def from_dict(obj: JWKDict, algorithm: Optional[str] = None) -> "PyJWK":
        return PyJWK(obj, algorithm)

    @staticmethod
    def from_json(data: str, algorithm: Optional[str] = None) -> "PyJWK":
        obj = json.loads(data)
        return PyJWK.from_dict(obj, algorithm)

    @property
    def key_id(self) -> Optional[str]:
        kid = self._jwk_data.get("kid")
        if kid is None:
            return None
        if not isinstance(kid, str):
            raise InvalidKeyError("kid is not a string")
        return kid

    @property
    def public_key_use(self) -> Optional[str]:
        return self._jwk_data.get("use")

    @property
    def key_ops(self):
        ko = self._jwk_data.get("key_ops")
        if ko is None:
            return None
        return list(ko)


class PyJWKSet:
    def __init__(self, keys: list):
        if not isinstance(keys, list):
            raise PyJWKSetError("keys must be a list")
        if len(keys) == 0:
            raise PyJWKSetError("keys must not be empty")

        self.keys = []
        for key_data in keys:
            try:
                jwk = PyJWK(key_data)
                self.keys.append(jwk)
            except PyJWTError:
                pass

        if not self.keys:
            raise PyJWKSetError(
                "No usable keys found. All provided keys were invalid."
            )

    @staticmethod
    def from_dict(obj: dict) -> "PyJWKSet":
        if "keys" not in obj:
            raise PyJWKSetError("The JWK Set did not contain a 'keys' key")
        keys = obj["keys"]
        if not isinstance(keys, list):
            raise PyJWKSetError("'keys' must be a list")
        return PyJWKSet(keys)

    @staticmethod
    def from_json(data: str) -> "PyJWKSet":
        try:
            obj = json.loads(data)
        except Exception as e:
            raise PyJWKSetError(f"Failed to parse JSON: {e}") from e
        return PyJWKSet.from_dict(obj)

    def __getitem__(self, kid: str) -> "PyJWK":
        for key in self.keys:
            try:
                if key.key_id == kid:
                    return key
            except InvalidKeyError:
                pass
        raise KeyError(f"Key with kid '{kid}' not found")


class PyJWTSetWithTimestamp:
    def __init__(self, jwk_set):
        self._jwk_set = jwk_set
        self._timestamp = time.monotonic()

    def get_jwk_set(self):
        return self._jwk_set

    def get_timestamp(self) -> float:
        return self._timestamp
