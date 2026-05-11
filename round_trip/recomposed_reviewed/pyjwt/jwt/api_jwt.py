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
        if options is not None:
            self.options.update(options)

    def encode(
        self,
        payload: Dict[str, Any],
        key,
        algorithm: Optional[str] = "HS256",
        headers: Optional[Dict] = None,
        json_encoder=None,
        sort_headers: bool = True,
    ) -> str:
        if not isinstance(payload, dict):
            raise TypeError(
                "Expecting a mapping object, as JSON object are mapping types."
            )

        payload = dict(payload)

        # Convert datetime values in exp, iat, nbf to integer timestamps
        for time_claim in ("exp", "iat", "nbf"):
            if time_claim in payload:
                claim_value = payload[time_claim]
                if isinstance(claim_value, datetime):
                    payload[time_claim] = timegm(claim_value.utctimetuple())

        # Encode payload to JSON bytes
        payload_bytes = self._encode_payload(
            payload, headers=headers, json_encoder=json_encoder
        )

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
        payload: Dict,
        headers: Optional[Dict] = None,
        json_encoder=None,
    ) -> bytes:
        if json_encoder is not None:
            return json.dumps(payload, cls=json_encoder, separators=(",", ":")).encode(
                "utf-8"
            )
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def _decode_payload(self, decoded: Dict) -> Any:
        try:
            payload = json.loads(decoded["payload"])
        except Exception as e:
            raise DecodeError("Invalid payload string: must be a json object") from e

        if not isinstance(payload, dict):
            raise DecodeError("Invalid payload string: must be a json object")

        return payload

    def decode_complete(
        self,
        jwt,
        key="",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        verify=None,
        detached_payload: Optional[bytes] = None,
        audience=None,
        issuer: Optional[str] = None,
        leeway: Union[float, timedelta] = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        # Handle deprecated verify parameter
        if verify is not None:
            _warnings_module.warn(
                "The `verify` argument to `decode` does nothing in PyJWT 2.x "
                "and will be removed in 3.0.0",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        if kwargs:
            _warnings_module.warn(
                "passing additional keyword arguments to decode() is deprecated "
                "and will be removed in PyJWT v3",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

        # Build merged options
        merged_options = dict(self.options)
        if options is not None:
            merged_options.update(options)

        # If verify_signature is False, default all verify_* to False
        # (unless explicitly set in user's options)
        if not merged_options.get("verify_signature", True):
            for opt in ("verify_exp", "verify_nbf", "verify_iat", "verify_aud", "verify_iss"):
                if options is None or opt not in options:
                    merged_options[opt] = False

        # Decode via JWS layer
        jws_options = {
            "verify_signature": merged_options.get("verify_signature", True),
        }

        decoded = api_jws._jws_global_obj.decode_complete(
            jwt,
            key=key,
            algorithms=algorithms,
            options=jws_options,
            detached_payload=detached_payload,
        )

        # Decode payload
        try:
            payload = self._decode_payload(decoded)
        except DecodeError:
            raise

        # Validate claims
        if merged_options.get("verify_signature", True):
            self._validate_claims(
                payload,
                merged_options,
                audience=audience,
                issuer=issuer,
                leeway=leeway,
            )

        decoded["payload"] = payload
        return decoded

    def decode(
        self,
        jwt,
        key="",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        verify=None,
        detached_payload: Optional[bytes] = None,
        audience=None,
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
        payload: Dict,
        options: Dict,
        audience=None,
        issuer: Optional[str] = None,
        leeway: Union[float, timedelta] = 0,
    ) -> None:
        if isinstance(leeway, timedelta):
            leeway = leeway.total_seconds()

        # Check required claims
        if options.get("require"):
            for required_claim in options["require"]:
                if required_claim not in payload:
                    raise MissingRequiredClaimError(required_claim)

        now = timegm(datetime.now(tz=timezone.utc).utctimetuple())

        if options.get("verify_iat", True):
            self._validate_iat(payload, now, leeway)

        if options.get("verify_nbf", True):
            self._validate_nbf(payload, now, leeway)

        if options.get("verify_exp", True):
            self._validate_exp(payload, now, leeway)

        if options.get("verify_iss", True):
            self._validate_iss(payload, issuer)

        if options.get("verify_aud", True):
            self._validate_aud(payload, audience, options)

    def _validate_iat(self, payload: Dict, now: int, leeway: float) -> None:
        if "iat" not in payload:
            return
        iat = payload["iat"]
        if not isinstance(iat, (int, float)):
            raise InvalidIssuedAtError("Issued At claim (iat) must be an integer.")
        if iat > now + leeway:
            raise ImmatureSignatureError("The token is not yet valid (iat)")

    def _validate_nbf(self, payload: Dict, now: int, leeway: float) -> None:
        if "nbf" not in payload:
            return
        nbf = payload["nbf"]
        if not isinstance(nbf, (int, float)):
            raise ImmatureSignatureError("Not Before claim (nbf) must be an integer.")
        if nbf > now + leeway:
            raise ImmatureSignatureError("The token is not yet valid (nbf)")

    def _validate_exp(self, payload: Dict, now: int, leeway: float) -> None:
        if "exp" not in payload:
            return
        exp = payload["exp"]
        if not isinstance(exp, (int, float)):
            raise ExpiredSignatureError("Expiration Time claim (exp) must be an integer.")
        if exp <= now - leeway:
            raise ExpiredSignatureError("Signature has expired")

    def _validate_iss(self, payload: Dict, issuer: Optional[str]) -> None:
        if issuer is None:
            return
        if "iss" not in payload:
            raise MissingRequiredClaimError("iss")
        if payload["iss"] != issuer:
            raise InvalidIssuerError("Invalid issuer")

    def _validate_aud(self, payload: Dict, audience, options: Dict) -> None:
        if audience is None:
            if "aud" in payload:
                raise InvalidAudienceError(
                    "Invalid audience"
                )
            return

        if "aud" not in payload:
            raise MissingRequiredClaimError("aud")

        audience_claims = payload["aud"]

        # Normalize audience_claims to a list
        if isinstance(audience_claims, str):
            audience_claims = [audience_claims]
        elif not isinstance(audience_claims, list):
            raise InvalidAudienceError("Invalid audience")

        strict = options.get("strict_aud", False)

        if strict:
            # Both audience and payload aud must be single strings and equal
            if not isinstance(audience, str):
                raise InvalidAudienceError("Invalid audience (strict mode requires string)")
            aud_claim = payload["aud"]
            if not isinstance(aud_claim, str):
                raise InvalidAudienceError("Invalid audience (strict mode: payload aud must be a string)")
            if audience != aud_claim:
                raise InvalidAudienceError("Invalid audience")
            return

        # Normal mode: at least one element of audience must be in audience_claims
        if isinstance(audience, str):
            audience_to_check = [audience]
        else:
            audience_to_check = list(audience)

        if not any(aud in audience_claims for aud in audience_to_check):
            raise InvalidAudienceError("Invalid audience")


_jwt_global_obj = PyJWT()
encode = _jwt_global_obj.encode
decode_complete = _jwt_global_obj.decode_complete
decode = _jwt_global_obj.decode
