import json
import warnings as _warnings
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
        self.options = self._get_default_options()
        if options is not None:
            if not isinstance(options, dict):
                raise TypeError("options must be a dict")
            self.options.update(options)

    def _get_default_options(self) -> Dict[str, Any]:
        return {
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "verify_aud": True,
            "verify_iss": True,
            "require": [],
        }

    def encode(
        self,
        payload: Dict[str, Any],
        key,
        algorithm: Optional[str] = "HS256",
        headers: Optional[Dict] = None,
        json_encoder=None,
        sort_headers: bool = True,
    ) -> str:
        payload = dict(payload)

        # Convert datetime values
        for time_claim in ["exp", "iat", "nbf"]:
            if time_claim in payload and isinstance(payload[time_claim], datetime):
                payload[time_claim] = timegm(payload[time_claim].utctimetuple())

        # JSON-encode payload
        payload_bytes = json.dumps(
            payload,
            separators=(",", ":"),
            cls=json_encoder,
        ).encode("utf-8")

        return api_jws._jws_global_obj.encode(
            payload_bytes,
            key,
            algorithm=algorithm,
            headers=headers,
            json_encoder=json_encoder,
            sort_headers=sort_headers,
        )

    def decode_complete(
        self,
        jwt: Union[str, bytes],
        key="",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        verify=None,
        detached_payload: Optional[bytes] = None,
        audience: Optional[Union[str, List[str]]] = None,
        issuer: Optional[str] = None,
        leeway: Union[float, timedelta] = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        if verify is not None:
            _warnings.warn(
                "The verify argument is deprecated. Please use the options parameter instead.",
                RemovedInPyjwt3Warning,
                stacklevel=2,
            )

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

        # When verify_signature is False, set all verify_* to False by default
        if not merged_options.get("verify_signature", True):
            defaults = {
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
                "verify_aud": False,
                "verify_iss": False,
            }
            for k, v in defaults.items():
                if options is None or k not in options:
                    merged_options[k] = v

        decoded = api_jws._jws_global_obj.decode_complete(
            jwt,
            key=key,
            algorithms=algorithms,
            options=merged_options,
            detached_payload=detached_payload,
        )

        payload = self._decode_payload(decoded)

        merged_options["leeway"] = leeway

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
        jwt: Union[str, bytes],
        key="",
        algorithms: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        verify=None,
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

    def _encode_payload(
        self,
        payload: Dict,
        headers: Optional[Dict] = None,
        json_encoder=None,
    ) -> bytes:
        return json.dumps(
            payload,
            separators=(",", ":"),
            cls=json_encoder,
        ).encode("utf-8")

    def _decode_payload(self, decoded: Dict) -> Any:
        try:
            payload = json.loads(decoded["payload"].decode("utf-8"))
        except Exception:
            raise DecodeError("Invalid payload string: not a JSON object")
        if not isinstance(payload, dict):
            raise DecodeError("Invalid payload string: must be a json object")
        return payload

    def _validate_claims(
        self,
        payload: Dict,
        options: Dict,
        audience=None,
        issuer=None,
        leeway: Union[float, timedelta] = 0,
    ) -> None:
        if isinstance(leeway, timedelta):
            leeway = leeway.total_seconds()

        now = timegm(datetime.now(tz=timezone.utc).utctimetuple())

        # Validate required claims
        for required_claim in options.get("require", []):
            if required_claim not in payload:
                raise MissingRequiredClaimError(required_claim)

        if options.get("verify_iat", True) and "iat" in payload:
            self._validate_iat(payload, now, leeway)

        if options.get("verify_nbf", True) and "nbf" in payload:
            self._validate_nbf(payload, now, leeway)

        if options.get("verify_exp", True) and "exp" in payload:
            self._validate_exp(payload, now, leeway)

        if options.get("verify_iss", True) and issuer is not None:
            self._validate_iss(payload, issuer)

        if options.get("verify_aud", True):
            self._validate_aud(payload, audience, options)

    def _validate_iat(self, payload: Dict, now: int, leeway: float) -> None:
        iat = payload["iat"]
        # F2: raise InvalidIssuedAtError if iat is not an integer/float
        if not isinstance(iat, (int, float)):
            raise InvalidIssuedAtError("Issued At claim (iat) must be an integer")

    def _validate_nbf(self, payload: Dict, now: int, leeway: float) -> None:
        nbf = payload["nbf"]
        if not isinstance(nbf, (int, float)):
            raise ImmatureSignatureError("nbf must be an integer")
        if nbf > now + leeway:
            raise ImmatureSignatureError("The token is not yet valid (nbf)")

    def _validate_exp(self, payload: Dict, now: int, leeway: float) -> None:
        exp = payload["exp"]
        if not isinstance(exp, (int, float)):
            raise ExpiredSignatureError("Expiration Time claim (exp) must be an integer")
        if exp <= now - leeway:
            raise ExpiredSignatureError("Signature has expired")

    def _validate_iss(self, payload: Dict, issuer: str) -> None:
        if "iss" not in payload:
            raise MissingRequiredClaimError("iss")
        if payload["iss"] != issuer:
            raise InvalidIssuerError("Invalid issuer")

    def _validate_aud(self, payload: Dict, audience, options: Dict) -> None:
        strict = options.get("strict_aud", False)

        if audience is None:
            if "aud" in payload:
                raise InvalidAudienceError("Invalid audience")
            return

        if "aud" not in payload:
            raise MissingRequiredClaimError("aud")

        audience_claims = payload["aud"]

        if strict:
            # Both audience and aud must be single strings and must be equal
            if not isinstance(audience, str):
                raise InvalidAudienceError("Invalid audience: audience must be a string in strict mode")
            if not isinstance(audience_claims, str):
                raise InvalidAudienceError("Invalid audience: payload aud must be a string in strict mode")
            if audience != audience_claims:
                raise InvalidAudienceError("Invalid audience")
            return

        # Normal mode
        if isinstance(audience_claims, str):
            audience_claims = [audience_claims]

        if not isinstance(audience_claims, list):
            raise InvalidAudienceError("Invalid audience: must be a string or list")

        # audience can be string or iterable
        if isinstance(audience, str):
            audience_list = [audience]
        else:
            audience_list = list(audience)

        # At least one element of audience must appear in audience_claims
        if not any(aud in audience_claims for aud in audience_list):
            raise InvalidAudienceError("Invalid audience")


_jwt_global_obj = PyJWT()
encode = _jwt_global_obj.encode
decode_complete = _jwt_global_obj.decode_complete
decode = _jwt_global_obj.decode
