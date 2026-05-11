import binascii
import json
import warnings as _warnings
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
        self._valid_algs = set(self._algorithms.keys())

        if algorithms is not None:
            # Filter to only the specified algorithms
            self._valid_algs = set(algorithms) & self._valid_algs
            keys_to_remove = [k for k in self._algorithms if k not in self._valid_algs]
            for k in keys_to_remove:
                del self._algorithms[k]

        if options is not None:
            if not isinstance(options, dict):
                raise TypeError("options must be a dict")
            self.options = {"verify_signature": True, **options}
        else:
            self.options = {"verify_signature": True}

    def register_algorithm(self, alg_id: str, alg_obj: Algorithm) -> None:
        if alg_id in self._algorithms:
            raise ValueError(f"Algorithm {alg_id} is already registered")
        if not isinstance(alg_obj, Algorithm):
            raise TypeError("alg_obj must be an Algorithm instance")
        self._algorithms[alg_id] = alg_obj
        self._valid_algs.add(alg_id)

    def unregister_algorithm(self, alg_id: str) -> None:
        if alg_id not in self._algorithms:
            raise KeyError(f"Algorithm {alg_id} is not registered")
        del self._algorithms[alg_id]
        self._valid_algs.discard(alg_id)

    def get_algorithms(self) -> List[str]:
        return list(self._valid_algs)

    def get_algorithm_by_name(self, alg_name: str) -> Algorithm:
        if alg_name not in self._algorithms:
            if alg_name in requires_cryptography:
                raise NotImplementedError(
                    f"Algorithm '{alg_name}' requires the 'cryptography' package to be installed."
                )
            raise NotImplementedError(f"Algorithm '{alg_name}' is not supported")
        return self._algorithms[alg_name]

    def get_unverified_header(self, jwt: Union[str, bytes]) -> Dict[str, Any]:
        if isinstance(jwt, str):
            jwt = jwt.encode("utf-8")

        parts = jwt.split(b".")
        if len(parts) < 3:
            raise DecodeError("Not enough segments")

        try:
            header_data = base64url_decode(parts[0])
        except Exception:
            raise DecodeError("Invalid header padding")

        try:
            header = json.loads(header_data.decode("utf-8"))
        except Exception:
            raise DecodeError("Invalid header string: not a JSON object")

        if not isinstance(header, dict):
            raise DecodeError("Invalid header: not a JSON object")

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
        # Determine algorithm
        if headers and "alg" in headers:
            algorithm = headers["alg"]
        elif algorithm is None:
            # F7: only key is None triggers 'none', not empty string
            if key is None:
                algorithm = "none"
            else:
                algorithm = "HS256"

        # Build header
        header = {"typ": self.header_typ, "alg": algorithm}

        if headers:
            header.update(headers)

        # Handle typ suppression
        if header.get("typ") == "" or header.get("typ") is None:
            header.pop("typ", None)

        # Handle b64 field
        is_detached = is_payload_detached
        if "b64" in header:
            if header["b64"] is False:
                is_detached = True
            elif header["b64"] is True:
                del header["b64"]

        if is_detached and "b64" not in header:
            header["b64"] = False

        # Get algorithm object
        try:
            alg_obj = self.get_algorithm_by_name(algorithm)
        except NotImplementedError:
            raise InvalidAlgorithmError(f"The specified alg value is not allowed")

        # Prepare key
        key = alg_obj.prepare_key(key)

        # Encode header
        if json_encoder:
            header_data = json_encoder().encode(header).encode("utf-8")
        else:
            header_data = json.dumps(
                header,
                separators=(",", ":"),
                sort_keys=sort_headers,
            ).encode("utf-8")

        header_b64 = base64url_encode(header_data)

        # Encode payload
        if is_detached:
            payload_b64 = b""
        else:
            payload_b64 = base64url_encode(payload)

        # Sign
        signing_input = header_b64 + b"." + (payload if is_detached else payload_b64)
        signature = alg_obj.sign(signing_input, key)
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
        if kwargs:
            _warnings.warn(
                "Passing additional keyword arguments to decode_complete() is deprecated "
                "and will be removed in PyJWT v3. "
                f"Unrecognized keys: {list(kwargs.keys())}",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        merged_options = dict(self.options)
        if options is not None:
            merged_options.update(options)

        if isinstance(jwt, str):
            jwt = jwt.encode("utf-8")

        parts = jwt.split(b".")
        if len(parts) != 3:
            if len(parts) < 3:
                raise DecodeError("Not enough segments")
            raise DecodeError("Too many segments")

        # Decode header
        try:
            header_data = base64url_decode(parts[0])
        except Exception:
            raise DecodeError("Invalid header padding")

        try:
            header = json.loads(header_data.decode("utf-8"))
        except Exception:
            raise DecodeError("Invalid header string: not a JSON object")

        if not isinstance(header, dict):
            raise DecodeError("Invalid header: not a JSON object")

        if "kid" in header and not isinstance(header["kid"], str):
            raise InvalidTokenError("Key ID header parameter must be a string")

        # Handle detached payload
        is_b64_false = header.get("b64") is False
        if is_b64_false:
            if detached_payload is None:
                raise DecodeError(
                    "It is required that you pass in a value for the detached_payload argument to decode a message using unencoded payload."
                )
            payload = detached_payload
            payload_b64 = b""
        else:
            try:
                payload = base64url_decode(parts[1])
            except Exception:
                raise DecodeError("Invalid payload padding")
            payload_b64 = parts[1]

        # Decode signature
        try:
            signature = base64url_decode(parts[2])
        except Exception:
            raise DecodeError("Invalid crypto padding")

        verify_signature = merged_options.get("verify_signature", True)

        if verify_signature:
            # F4: raise DecodeError whenever algorithms is falsy (None or empty) and not a PyJWS key
            if not algorithms and not isinstance(key, PyJWS):
                raise DecodeError(
                    'It is required that you pass in a value for the "algorithms" argument when calling decode(). '
                    "This argument prevents decoding tokens signed with unexpected algorithms."
                )

            # Determine algorithm from header
            alg = header.get("alg", "")

            if algorithms and alg not in algorithms:
                raise InvalidAlgorithmError("The specified alg value is not allowed")

            try:
                alg_obj = self.get_algorithm_by_name(alg)
            except NotImplementedError:
                raise InvalidAlgorithmError(f"Algorithm '{alg}' is not supported")

            # Prepare key
            try:
                key = alg_obj.prepare_key(key)
            except Exception as e:
                raise InvalidAlgorithmError(str(e))

            # Verify signature
            signing_input = parts[0] + b"." + (payload if is_b64_false else parts[1])
            if not alg_obj.verify(signing_input, key, signature):
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
