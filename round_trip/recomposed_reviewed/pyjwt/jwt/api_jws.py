import json
import warnings as _warnings_module
from typing import Any, Dict, List, Optional, Union

from .algorithms import Algorithm, get_default_algorithms, has_crypto, requires_cryptography
from .exceptions import DecodeError, InvalidAlgorithmError, InvalidSignatureError, InvalidTokenError
from .utils import base64url_decode, base64url_encode
from .warnings import RemovedInPyjwt3Warning


class PyJWS:
    header_typ = "JWT"

    def __init__(
        self,
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        self._algorithms = get_default_algorithms()
        self._valid_algs: set

        if algorithms is None:
            self._valid_algs = set(self._algorithms.keys())
        else:
            self._valid_algs = set(algorithms)
            # Remove algorithms not in the provided list
            self._algorithms = {
                k: v for k, v in self._algorithms.items() if k in self._valid_algs
            }

        if options is None:
            self.options = {"verify_signature": True}
        else:
            if not isinstance(options, dict):
                raise TypeError("options must be a dict")
            self.options = {"verify_signature": True}
            self.options.update(options)

    def register_algorithm(self, alg_id: str, alg_obj: Algorithm) -> None:
        if alg_id in self._algorithms:
            raise ValueError(f"Algorithm already registered: {alg_id}")
        if not isinstance(alg_obj, Algorithm):
            raise TypeError("alg_obj must be an instance of Algorithm")
        self._algorithms[alg_id] = alg_obj
        self._valid_algs.add(alg_id)

    def unregister_algorithm(self, alg_id: str) -> None:
        if alg_id not in self._algorithms:
            raise KeyError(f"Algorithm not registered: {alg_id}")
        del self._algorithms[alg_id]
        self._valid_algs.discard(alg_id)

    def get_algorithms(self) -> List[str]:
        return list(self._valid_algs)

    def get_algorithm_by_name(self, alg_name: str) -> Algorithm:
        alg = self._algorithms.get(alg_name)
        if alg is None:
            if not has_crypto and alg_name in requires_cryptography:
                raise NotImplementedError(
                    f"Algorithm '{alg_name}' could not be found. Do you have cryptography installed?"
                )
            raise NotImplementedError(
                f"Algorithm '{alg_name}' could not be found. Do you have cryptography installed?"
            )
        return alg

    def get_unverified_header(self, jwt: Union[str, bytes]) -> Dict[str, Any]:
        if isinstance(jwt, str):
            jwt = jwt.encode("utf-8")

        parts = jwt.split(b".")
        if len(parts) != 3:
            raise DecodeError("Not enough segments")

        header_data = parts[0]
        try:
            header_bytes = base64url_decode(header_data)
        except Exception as e:
            raise DecodeError("Invalid header padding") from e

        try:
            header = json.loads(header_bytes)
        except Exception as e:
            raise DecodeError("Invalid header string: must be a json object") from e

        if not isinstance(header, dict):
            raise DecodeError("Invalid header string: must be a json object")

        # Validate kid
        if "kid" in header and not isinstance(header["kid"], str):
            raise InvalidTokenError("Key ID header parameter must be a string")

        return header

    def encode(
        self,
        payload: bytes,
        key,
        algorithm: Optional[str] = None,
        headers: Optional[Dict] = None,
        json_encoder=None,
        is_payload_detached: bool = False,
        sort_headers: bool = True,
    ) -> str:
        # Build base header
        if self.header_typ:
            header = {"typ": self.header_typ, "alg": algorithm or "HS256"}
        else:
            header = {"alg": algorithm or "HS256"}

        # Merge custom headers
        if headers:
            header.update(headers)

        # Algorithm selection precedence per ADR-0006
        # headers["alg"] overrides algorithm param (already merged above)
        algorithm_ = header.get("alg", algorithm)

        # If algorithm not specified
        if algorithm is None and "alg" not in (headers or {}):
            if key is None:
                algorithm_ = "none"
            else:
                algorithm_ = "HS256"
        else:
            algorithm_ = header.get("alg", algorithm)

        header["alg"] = algorithm_

        # Handle typ suppression
        if header.get("typ") in ("", None):
            header.pop("typ", None)

        # Handle detached payload / b64
        is_detached = is_payload_detached
        if headers and headers.get("b64") is False:
            is_detached = True
        elif headers and headers.get("b64") is True:
            # Remove b64=true from header (treated as default)
            header.pop("b64", None)

        if is_detached:
            header["b64"] = False

        # Encode header
        if sort_headers:
            header_data = json.dumps(
                header, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        else:
            header_data = json.dumps(header, separators=(",", ":")).encode("utf-8")

        header_b64 = base64url_encode(header_data)

        # Encode payload
        if is_detached:
            payload_b64 = b""
            signing_payload = payload
        else:
            payload_b64 = base64url_encode(payload)
            signing_payload = payload_b64

        # Signing input
        signing_input = header_b64 + b"." + signing_payload

        # Get algorithm object
        if algorithm_ not in self._algorithms:
            if algorithm_ in requires_cryptography and not has_crypto:
                raise NotImplementedError(
                    f"cryptography is required for {algorithm_}"
                )
            raise InvalidAlgorithmError(f"Unknown algorithm: {algorithm_}")

        alg_obj = self._algorithms[algorithm_]
        prepared_key = alg_obj.prepare_key(key)
        signature = alg_obj.sign(signing_input, prepared_key)
        signature_b64 = base64url_encode(signature)

        return (header_b64 + b"." + payload_b64 + b"." + signature_b64).decode("utf-8")

    def decode_complete(
        self,
        jwt: Union[str, bytes],
        key="",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        detached_payload: Optional[bytes] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        # Emit deprecation warning for unexpected kwargs
        if kwargs:
            _warnings_module.warn(
                "passing additional keyword arguments to decode() is deprecated "
                "and will be removed in PyJWT v3",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        # Merge options
        merged_options = dict(self.options)
        if options is not None:
            merged_options.update(options)

        verify_signature = merged_options.get("verify_signature", True)

        if isinstance(jwt, str):
            jwt = jwt.encode("utf-8")

        parts = jwt.split(b".")
        if len(parts) != 3:
            raise DecodeError("Not enough segments")

        header_data, payload_data, crypto_segment = parts

        # Decode header
        try:
            header_bytes = base64url_decode(header_data)
        except Exception as e:
            raise DecodeError("Invalid header padding") from e

        try:
            header = json.loads(header_bytes)
        except Exception as e:
            raise DecodeError("Invalid header string: must be a json object") from e

        if not isinstance(header, dict):
            raise DecodeError("Invalid header string: must be a json object")

        # Validate kid
        if "kid" in header and not isinstance(header["kid"], str):
            raise InvalidTokenError("Key ID header parameter must be a string")

        # Check for detached payload
        is_detached = header.get("b64") is False
        if is_detached:
            if detached_payload is None:
                raise DecodeError(
                    "It is required that you pass in a value for the detached_payload argument"
                )
            payload = detached_payload
            payload_b64 = b""
        else:
            try:
                payload = base64url_decode(payload_data)
            except Exception as e:
                raise DecodeError("Invalid payload padding") from e
            payload_b64 = payload_data

        # Decode signature
        try:
            signature = base64url_decode(crypto_segment)
        except Exception as e:
            raise DecodeError("Invalid crypto padding") from e

        if verify_signature:
            # Check algorithms
            if not algorithms:
                raise DecodeError(
                    'It is required that you pass in a value for the "algorithms" argument when calling decode(). '
                    "Please refer to https://pyjwt.readthedocs.io/en/stable/usage.html#specifying-an-algorithm "
                    "for more information."
                )

            alg = header.get("alg", "")

            if not alg:
                raise InvalidAlgorithmError("No 'alg' value found in header")

            if alg not in self._algorithms:
                raise InvalidAlgorithmError(f"The specified alg value is not allowed")

            if algorithms and alg not in algorithms:
                raise InvalidAlgorithmError(f"The specified alg value is not allowed")

            alg_obj = self._algorithms[alg]

            # Build signing input
            if is_detached:
                signing_input = header_data + b"." + detached_payload
            else:
                signing_input = header_data + b"." + payload_b64

            prepared_key = alg_obj.prepare_key(key)
            if not alg_obj.verify(signing_input, prepared_key, signature):
                raise InvalidSignatureError("Signature verification failed")

        return {
            "payload": payload,
            "header": header,
            "signature": signature,
        }

    def decode(
        self,
        jwt: Union[str, bytes],
        key="",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        detached_payload: Optional[bytes] = None,
        **kwargs,
    ) -> bytes:
        decoded = self.decode_complete(
            jwt,
            key=key,
            algorithms=algorithms,
            options=options,
            detached_payload=detached_payload,
            **kwargs,
        )
        return decoded["payload"]


_jws_global_obj = PyJWS()
encode = _jws_global_obj.encode
decode_complete = _jws_global_obj.decode_complete
decode = _jws_global_obj.decode
register_algorithm = _jws_global_obj.register_algorithm
unregister_algorithm = _jws_global_obj.unregister_algorithm
get_algorithm_by_name = _jws_global_obj.get_algorithm_by_name
get_unverified_header = _jws_global_obj.get_unverified_header
