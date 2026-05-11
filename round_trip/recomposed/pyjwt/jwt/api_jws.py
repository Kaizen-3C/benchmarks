import binascii
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
        self._valid_algs = set(self._algorithms.keys())

        if algorithms is not None:
            # Filter to only the specified algorithms
            self._valid_algs = set(algorithms) & self._valid_algs
            # Remove algorithms not in the filter
            keys_to_remove = [k for k in self._algorithms if k not in algorithms]
            for k in keys_to_remove:
                del self._algorithms[k]

        if options is not None:
            if not isinstance(options, dict):
                raise TypeError("options must be a dict")

        self.options = {"verify_signature": True}
        if options:
            self.options.update(options)

    def register_algorithm(self, alg_id: str, alg_obj: Algorithm) -> None:
        if alg_id in self._algorithms:
            raise ValueError(f"Algorithm {alg_id} is already registered")
        if not isinstance(alg_obj, Algorithm):
            raise TypeError("alg_obj must be an instance of Algorithm")
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
        alg = self._algorithms.get(alg_name)
        if alg is None:
            if alg_name in requires_cryptography and not has_crypto:
                raise NotImplementedError(
                    f"Algorithm '{alg_name}' requires the 'cryptography' package"
                )
            raise NotImplementedError(f"Algorithm '{alg_name}' could not be found")
        return alg

    def get_unverified_header(self, jwt: Union[str, bytes]) -> Dict[str, Any]:
        if isinstance(jwt, str):
            jwt = jwt.encode("utf-8")

        parts = jwt.split(b".")
        if len(parts) != 3:
            raise DecodeError("Not enough segments")

        try:
            header_data = base64url_decode(parts[0])
        except Exception as e:
            raise DecodeError("Invalid header padding") from e

        try:
            header = json.loads(header_data)
        except json.JSONDecodeError as e:
            raise DecodeError(f"Invalid header: {e}") from e

        if not isinstance(header, dict):
            raise DecodeError("Invalid header: not a dict")

        kid = header.get("kid")
        if kid is not None and not isinstance(kid, str):
            raise InvalidTokenError("Invalid header: kid must be a string")

        return header

    def encode(
        self,
        payload: bytes,
        key: Any,
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
            if key is None or key == "":
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

        # Handle b64 header for detached payloads
        if is_payload_detached or (headers and headers.get("b64") is False):
            header["b64"] = False
        elif "b64" in header and header["b64"] is True:
            del header["b64"]

        # Serialize header
        if json_encoder:
            header_data = json_encoder().encode(header)
            if isinstance(header_data, str):
                header_data = header_data.encode("utf-8")
        else:
            header_data = json.dumps(
                header,
                separators=(",", ":"),
                sort_keys=sort_headers,
            ).encode("utf-8")

        header_b64 = base64url_encode(header_data)

        # Handle payload
        is_detached = header.get("b64") is False

        if is_detached:
            payload_b64 = b""
            signing_input = header_b64 + b"." + payload
        else:
            payload_b64 = base64url_encode(payload)
            signing_input = header_b64 + b"." + payload_b64

        # Sign
        alg_obj = self.get_algorithm_by_name(algorithm)
        key = alg_obj.prepare_key(key)
        signature = alg_obj.sign(signing_input, key)
        sig_b64 = base64url_encode(signature)

        token = header_b64 + b"." + payload_b64 + b"." + sig_b64
        return token.decode("utf-8")

    def decode_complete(
        self,
        jwt: Union[str, bytes],
        key: Any = "",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict] = None,
        detached_payload: Optional[bytes] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        # Handle deprecated kwargs
        if kwargs:
            _warnings_module.warn(
                "Passing additional keyword arguments to decode_complete() is deprecated "
                "and will be removed in PyJWT v3.",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        if isinstance(jwt, str):
            jwt = jwt.encode("utf-8")

        # Merge options
        merged_options = dict(self.options)
        if options:
            merged_options.update(options)

        verify_signature = merged_options.get("verify_signature", True)

        # Split token
        parts = jwt.split(b".")
        if len(parts) != 3:
            raise DecodeError("Not enough segments")

        try:
            header_data = base64url_decode(parts[0])
        except Exception as e:
            raise DecodeError("Invalid header padding") from e

        try:
            header = json.loads(header_data)
        except json.JSONDecodeError as e:
            raise DecodeError(f"Invalid header: {e}") from e

        if not isinstance(header, dict):
            raise DecodeError("Invalid header: not a dict")

        kid = header.get("kid")
        if kid is not None and not isinstance(kid, str):
            raise InvalidTokenError("Invalid header: kid must be a string")

        # Handle detached payload
        is_detached = header.get("b64") is False

        if is_detached:
            if detached_payload is None:
                raise DecodeError("Detached payload requires detached_payload argument")
            payload_bytes = detached_payload
            signing_input = parts[0] + b"." + detached_payload
        else:
            try:
                payload_bytes = base64url_decode(parts[1])
            except Exception as e:
                raise DecodeError("Invalid payload padding") from e
            signing_input = parts[0] + b"." + parts[1]

        try:
            sig = base64url_decode(parts[2])
        except Exception as e:
            raise DecodeError("Invalid signature padding") from e

        if not verify_signature:
            return {"payload": payload_bytes, "header": header, "signature": sig}

        # Verify signature
        if algorithms is None:
            raise DecodeError(
                'It is required that you pass in a value for the "algorithms" argument when calling decode().'
            )

        alg = header.get("alg", "")
        if not alg:
            raise InvalidAlgorithmError("Algorithm was not specified")

        if alg not in algorithms:
            raise InvalidAlgorithmError(f"The specified alg value is not allowed")

        try:
            alg_obj = self.get_algorithm_by_name(alg)
        except NotImplementedError:
            raise InvalidAlgorithmError(f"Algorithm '{alg}' is not supported")

        prepared_key = alg_obj.prepare_key(key)

        if not alg_obj.verify(signing_input, prepared_key, sig):
            raise InvalidSignatureError("Signature verification failed")

        return {"payload": payload_bytes, "header": header, "signature": sig}

    def decode(
        self,
        jwt: Union[str, bytes],
        key: Any = "",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict] = None,
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


# Module-level singleton
_jws_global_obj = PyJWS()
encode = _jws_global_obj.encode
decode_complete = _jws_global_obj.decode_complete
decode = _jws_global_obj.decode
register_algorithm = _jws_global_obj.register_algorithm
unregister_algorithm = _jws_global_obj.unregister_algorithm
get_algorithm_by_name = _jws_global_obj.get_algorithm_by_name
get_unverified_header = _jws_global_obj.get_unverified_header
