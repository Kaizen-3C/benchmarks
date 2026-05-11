import json
import warnings as _warnings_module
from calendar import timegm
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from . import api_jws
from .exceptions import (
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuedAtError,
    InvalidIssuerError,
    MissingRequiredClaimError,
)
from .warnings import RemovedInPyjwt3Warning


class PyJWT:
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        self.options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "verify_aud": True,
            "verify_iss": True,
            "require": [],
        }
        if options:
            self.options.update(options)

    def encode(
        self,
        payload: Dict[str, Any],
        key: Any,
        algorithm: Optional[str] = "HS256",
        headers: Optional[Dict] = None,
        json_encoder=None,
        sort_headers: bool = True,
    ) -> str:
        payload = dict(payload)

        # Convert datetime values in exp, iat, nbf
        for claim in ("exp", "iat", "nbf"):
            if claim in payload and isinstance(payload[claim], datetime):
                payload[claim] = timegm(payload[claim].utctimetuple())

        # Encode payload to bytes
        payload_bytes = self._encode_payload(payload, headers=headers, json_encoder=json_encoder)

        return api_jws._jws_global_obj.encode(
            payload_bytes,
            key,
            algorithm=algorithm,
            headers=headers,
            json_encoder=json_encoder,
            sort_headers=sort_headers,
        )

    def _encode_payload(
        self,
        payload: dict,
        headers: Optional[Dict] = None,
        json_encoder=None,
    ) -> bytes:
        if json_encoder:
            data = json_encoder().encode(payload)
            if isinstance(data, str):
                data = data.encode("utf-8")
            return data
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def decode_complete(
        self,
        jwt: Union[str, bytes],
        key: Any = "",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict] = None,
        verify: Optional[bool] = None,
        detached_payload: Optional[bytes] = None,
        audience: Optional[Union[str, List[str]]] = None,
        issuer: Optional[str] = None,
        leeway: Union[float, timedelta] = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        # Handle deprecated verify param
        if verify is not None:
            _warnings_module.warn(
                "The verify argument is deprecated and will be removed in PyJWT v3.",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        # Handle deprecated kwargs
        if kwargs:
            _warnings_module.warn(
                "Passing additional keyword arguments to decode_complete() is deprecated "
                "and will be removed in PyJWT v3.",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        # Merge options
        merged_options = dict(self.options)
        if options:
            merged_options.update(options)

        if not merged_options.get("verify_signature", True):
            # When not verifying signature, default all verify_* to False
            for opt in ("verify_exp", "verify_nbf", "verify_iat", "verify_aud", "verify_iss"):
                if options is None or opt not in options:
                    merged_options[opt] = False

        decoded = api_jws._jws_global_obj.decode_complete(
            jwt,
            key=key,
            algorithms=algorithms,
            options={"verify_signature": merged_options.get("verify_signature", True)},
            detached_payload=detached_payload,
        )

        payload_dict = self._decode_payload(decoded)

        self._validate_claims(
            payload_dict,
            merged_options,
            audience=audience,
            issuer=issuer,
            leeway=leeway,
        )

        return {
            "payload": payload_dict,
            "header": decoded["header"],
            "signature": decoded["signature"],
        }

    def _decode_payload(self, decoded: dict) -> Any:
        try:
            payload = json.loads(decoded["payload"])
        except json.JSONDecodeError as e:
            raise DecodeError(f"Invalid payload: {e}") from e

        if not isinstance(payload, dict):
            raise DecodeError("Invalid payload: not a JSON object")

        return payload

    def decode(
        self,
        jwt: Union[str, bytes],
        key: Any = "",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict] = None,
        verify: Optional[bool] = None,
        detached_payload: Optional[bytes] = None,
        audience: Optional[Union[str, List[str]]] = None,
        issuer: Optional[str] = None,
        leeway: Union[float, timedelta] = 0,
        **kwargs,
    ) -> Any:
        decoded = self.decode_complete(
            jwt,
            key=key,
            algorithms=algorithms,
            options=options,
            verify=verify,
            detached_payload=detached_payload,
            audience=audience,
            issuer=issuer,
            leeway=leeway,
            **kwargs,
        )
        return decoded["payload"]

    def _validate_claims(
        self,
        payload: dict,
        options: dict,
        audience=None,
        issuer=None,
        leeway: Union[float, timedelta] = 0,
    ) -> None:
        if isinstance(leeway, timedelta):
            leeway = leeway.total_seconds()

        now = timegm(datetime.now(tz=timezone.utc).utctimetuple())

        # Check required claims
        required = options.get("require", [])
        for claim in required:
            if claim not in payload:
                raise MissingRequiredClaimError(claim)

        # Validate iat
        if options.get("verify_iat", True) and "iat" in payload:
            iat = payload["iat"]
            if not isinstance(iat, (int, float)):
                raise InvalidIssuedAtError("Issued At claim (iat) must be an integer")
            if iat > now + leeway:
                raise ImmatureSignatureError("The token is not yet valid (iat)")

        # Validate nbf
        if options.get("verify_nbf", True) and "nbf" in payload:
            nbf = payload["nbf"]
            if not isinstance(nbf, (int, float)):
                raise ImmatureSignatureError("Not Before claim (nbf) must be an integer")
            if nbf > now + leeway:
                raise ImmatureSignatureError("The token is not yet valid (nbf)")

        # Validate exp
        if options.get("verify_exp", True) and "exp" in payload:
            exp = payload["exp"]
            if not isinstance(exp, (int, float)):
                raise ExpiredSignatureError("Expiration Time claim (exp) must be an integer")
            if exp <= now - leeway:
                raise ExpiredSignatureError("Signature has expired")

        # Validate iss
        if options.get("verify_iss", True) and issuer is not None:
            if "iss" not in payload:
                raise MissingRequiredClaimError("iss")
            if payload["iss"] != issuer:
                raise InvalidIssuerError("Invalid issuer")

        # Validate aud
        if options.get("verify_aud", True):
            self._validate_aud(payload, audience, options)

    def _validate_aud(self, payload: dict, audience, options: dict) -> None:
        if audience is None:
            if "aud" in payload:
                raise InvalidAudienceError(
                    "Invalid audience: audience claim present but no audience provided"
                )
            return

        if "aud" not in payload:
            raise MissingRequiredClaimError("aud")

        audience_claims = payload["aud"]
        strict = options.get("strict_aud", False)

        if strict:
            # Both audience and payload["aud"] must be single strings and equal
            if not isinstance(audience_claims, str):
                raise InvalidAudienceError("Invalid audience: strict mode requires a single string audience claim")
            if not isinstance(audience, str):
                raise InvalidAudienceError("Invalid audience: strict mode requires a single string audience")
            if audience_claims != audience:
                raise InvalidAudienceError("Invalid audience")
            return

        # Normal mode
        if isinstance(audience_claims, str):
            audience_claims = [audience_claims]
        elif not isinstance(audience_claims, list):
            raise InvalidAudienceError("Invalid audience claim format")

        # audience can be string or iterable
        if isinstance(audience, str):
            audience_list = [audience]
        else:
            audience_list = list(audience)

        # At least one element of the provided audience must appear in audience_claims
        if not any(aud in audience_claims for aud in audience_list):
            raise InvalidAudienceError("Invalid audience")


# Module-level singleton
_jwt_global_obj = PyJWT()
encode = _jwt_global_obj.encode
decode_complete = _jwt_global_obj.decode_complete
decode = _jwt_global_obj.decode
