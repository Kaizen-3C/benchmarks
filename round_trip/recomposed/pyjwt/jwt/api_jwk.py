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
            algorithm = jwk_data.get("alg")

        if algorithm is None:
            # Infer algorithm from kty/crv
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
                    raise InvalidKeyError("OKP key missing 'crv' field")
                if crv in ("Ed25519", "Ed448"):
                    algorithm = "EdDSA"
                else:
                    raise InvalidKeyError(f"Unsupported OKP curve: {crv}")
            else:
                raise InvalidKeyError(f"Unsupported key type: {kty}")

        if algorithm in requires_cryptography and not has_crypto:
            raise PyJWKError(
                f"Algorithm '{algorithm}' requires the 'cryptography' package"
            )

        self.algorithm_name = algorithm
        self.key_type = kty

        algorithms = get_default_algorithms()
        if algorithm not in algorithms:
            raise InvalidKeyError(f"Unknown algorithm: {algorithm}")

        alg_obj = algorithms[algorithm]
        self.Algorithm = alg_obj

        # Deserialize the key
        try:
            if kty == "oct":
                self.key = alg_obj.from_jwk(jwk_data)
            else:
                self.key = alg_obj.from_jwk(jwk_data)
        except Exception as e:
            if isinstance(e, (InvalidKeyError, PyJWKError, PyJWTError)):
                raise
            raise InvalidKeyError(f"Could not deserialize key: {e}") from e

    @staticmethod
    def from_dict(obj: JWKDict, algorithm: Optional[str] = None) -> "PyJWK":
        return PyJWK(obj, algorithm=algorithm)

    @staticmethod
    def from_json(data: str, algorithm: Optional[str] = None) -> "PyJWK":
        obj = json.loads(data)
        return PyJWK.from_dict(obj, algorithm=algorithm)

    @property
    def key_type(self) -> str:
        return self._key_type

    @key_type.setter
    def key_type(self, value: str):
        self._key_type = value

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
    def __init__(self, keys: list):
        if not isinstance(keys, list):
            raise PyJWKSetError("Invalid JWK Set: keys must be a list")
        if len(keys) == 0:
            raise PyJWKSetError("Invalid JWK Set: keys list is empty")

        self.keys = []
        for key_data in keys:
            try:
                jwk = PyJWK(key_data)
                self.keys.append(jwk)
            except PyJWTError:
                # Silently skip invalid keys
                pass

        if not self.keys:
            raise PyJWKSetError("Invalid JWK Set: no usable keys found")

    @staticmethod
    def from_dict(obj: dict) -> "PyJWKSet":
        if not isinstance(obj, dict):
            raise PyJWKSetError("Invalid JWK Set: must be a dict")
        keys = obj.get("keys")
        if keys is None:
            raise PyJWKSetError("Invalid JWK Set: missing 'keys' field")
        if not isinstance(keys, list):
            raise PyJWKSetError("Invalid JWK Set: 'keys' must be a list")
        return PyJWKSet(keys)

    @staticmethod
    def from_json(data: str) -> "PyJWKSet":
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as e:
            raise PyJWKSetError(f"Invalid JWK Set JSON: {e}") from e
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
