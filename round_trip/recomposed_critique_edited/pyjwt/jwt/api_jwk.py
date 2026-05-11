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
            raise InvalidKeyError("kty is not found in JWK")

        crv = jwk_data.get("crv")

        if algorithm is None:
            # Check if JWK has an alg field
            algorithm = jwk_data.get("alg")

        if algorithm is None:
            # Infer from kty/crv
            if kty == "EC":
                if crv is None or crv == "P-256":
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
                if crv is None:
                    raise InvalidKeyError("OKP key requires 'crv' field")
                if crv in ("Ed25519", "Ed448"):
                    algorithm = "EdDSA"
                else:
                    raise InvalidKeyError(f"Unsupported OKP curve: {crv}")
            else:
                raise InvalidKeyError(f"Unsupported key type: {kty}")

        if not has_crypto and algorithm in requires_cryptography:
            raise PyJWKError(f"cryptography is required for algorithm {algorithm}")

        default_algorithms = get_default_algorithms()

        if algorithm not in default_algorithms:
            raise PyJWKError(f"Algorithm {algorithm} is not supported")

        self.Algorithm = default_algorithms[algorithm]
        self.key = self.Algorithm.from_jwk(jwk_data)

        # F1: assign algorithm_name and key_type as plain attributes after successful from_jwk
        # F5: set algorithm_name after successful from_jwk
        self.algorithm_name = algorithm
        self.key_type = kty  # plain attribute assignment, no property needed

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
        if kid is not None and not isinstance(kid, str):
            raise InvalidKeyError("kid must be a string")
        return kid

    @property
    def public_key_use(self) -> Optional[str]:
        return self._jwk_data.get("use")

    @property
    def key_ops(self) -> Optional[List[str]]:
        return self._jwk_data.get("key_ops")


class PyJWKSet:
    def __init__(self, keys: List[JWKDict]):
        if not isinstance(keys, list):
            raise PyJWKSetError("Invalid JWK Set: 'keys' must be a list")
        if len(keys) == 0:
            raise PyJWKSetError("Invalid JWK Set: 'keys' must not be empty")

        self.keys = []
        for key_data in keys:
            try:
                jwk = PyJWK(key_data)
                self.keys.append(jwk)
            except PyJWTError:
                pass

        if len(self.keys) == 0:
            raise PyJWKSetError("Invalid JWK Set: No usable keys found")

    @staticmethod
    def from_dict(obj: dict) -> "PyJWKSet":
        if not isinstance(obj, dict) or "keys" not in obj:
            raise PyJWKSetError("Invalid JWK Set: missing 'keys' field")
        keys = obj["keys"]
        if not isinstance(keys, list):
            raise PyJWKSetError("Invalid JWK Set: 'keys' must be a list")
        return PyJWKSet(keys)

    @staticmethod
    def from_json(data: str) -> "PyJWKSet":
        obj = json.loads(data)
        return PyJWKSet.from_dict(obj)

    def __getitem__(self, kid: str) -> PyJWK:
        for key in self.keys:
            if key.key_id == kid:
                return key
        raise KeyError(f"No key found with kid: {kid}")


class PyJWTSetWithTimestamp:
    def __init__(self, jwk_set: Union["PyJWKSet", dict]):
        self._jwk_set = jwk_set
        self._timestamp = time.monotonic()

    def get_jwk_set(self) -> Union["PyJWKSet", dict]:
        return self._jwk_set

    def get_timestamp(self) -> float:
        return self._timestamp
