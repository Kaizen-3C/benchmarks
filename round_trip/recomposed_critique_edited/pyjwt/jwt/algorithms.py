import hashlib
import hmac
import json
from typing import Any, Dict, Optional, Union

from .exceptions import InvalidKeyError
from .types import HashlibHash, JWKDict
from .utils import (
    base64url_decode,
    base64url_encode,
    der_to_raw_signature,
    force_bytes,
    from_base64url_uint,
    is_pem_format,
    is_ssh_key,
    raw_to_der_signature,
    to_base64url_uint,
)

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, ed25519, ed448
    from cryptography.hazmat.primitives.asymmetric.rsa import (
        RSAPrivateKey,
        RSAPublicKey,
        RSAPublicNumbers,
        RSAPrivateNumbers,
        rsa_crt_iqmp,
        rsa_crt_dmp1,
        rsa_crt_dmq1,
        rsa_recover_prime_factors,
    )
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePrivateKey,
        EllipticCurvePublicKey,
        EllipticCurvePublicNumbers,
        SECP256K1,
        SECP256R1,
        SECP384R1,
        SECP521R1,
        ECDSA,
    )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives.asymmetric.ed448 import Ed448PrivateKey, Ed448PublicKey
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm  # F11: import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature,
        encode_dss_signature,
    )
    has_crypto = True
except ModuleNotFoundError:
    has_crypto = False

requires_cryptography = {
    "RS256", "RS384", "RS512",
    "ES256", "ES256K", "ES384", "ES521", "ES512",
    "PS256", "PS384", "PS512",
    "EdDSA",
}


class Algorithm:
    def prepare_key(self, key: Any) -> Any:
        raise NotImplementedError

    def sign(self, msg: bytes, key: Any) -> bytes:
        raise NotImplementedError

    def verify(self, msg: bytes, key: Any, sig: bytes) -> bool:
        raise NotImplementedError

    @staticmethod
    def to_jwk(key_obj: Any, as_dict: bool = False) -> Union[JWKDict, str]:
        raise NotImplementedError

    @staticmethod
    def from_jwk(jwk: Union[str, JWKDict]) -> Any:
        raise NotImplementedError

    def compute_hash_digest(self, bytestr: bytes) -> bytes:
        if not hasattr(self, "hash_alg"):
            raise NotImplementedError
        return self.hash_alg(bytestr).digest()


class NoneAlgorithm(Algorithm):
    def prepare_key(self, key: Any) -> None:
        if key == "":
            return None
        if key is not None:
            raise InvalidKeyError("The specified key is not None")
        return None

    def sign(self, msg: bytes, key: None) -> bytes:
        return b""

    def verify(self, msg: bytes, key: None, sig: bytes) -> bool:
        return False

    @staticmethod
    def to_jwk(key_obj: Any = None, as_dict: bool = False) -> Union[JWKDict, str]:
        raise NotImplementedError

    @staticmethod
    def from_jwk(jwk: Union[str, JWKDict]) -> Any:
        raise NotImplementedError


class HMACAlgorithm(Algorithm):
    SHA256 = hashlib.sha256
    SHA384 = hashlib.sha384
    SHA512 = hashlib.sha512

    def __init__(self, hash_alg: HashlibHash):
        self.hash_alg = hash_alg

    def prepare_key(self, key: Union[str, bytes]) -> bytes:
        key_bytes = force_bytes(key)
        if is_pem_format(key_bytes) or is_ssh_key(key_bytes):
            raise InvalidKeyError(
                "The specified key is an asymmetric key or x509 certificate and"
                " should not be used as an HMAC secret."
            )
        return key_bytes

    def sign(self, msg: bytes, key: bytes) -> bytes:
        return hmac.new(key, msg, self.hash_alg).digest()

    def verify(self, msg: bytes, key: bytes, sig: bytes) -> bool:
        return hmac.compare_digest(sig, self.sign(msg, key))

    @staticmethod
    def to_jwk(key_obj: Union[bytes, str], as_dict: bool = False) -> Union[JWKDict, str]:
        key_bytes = force_bytes(key_obj)
        jwk = {
            "k": base64url_encode(key_bytes).decode("ASCII"),
            "kty": "oct",
        }
        if as_dict:
            return jwk
        return json.dumps(jwk)

    @staticmethod
    def from_jwk(jwk: Union[str, JWKDict]) -> bytes:
        if isinstance(jwk, str):
            jwk = json.loads(jwk)
        if not isinstance(jwk, dict):
            raise InvalidKeyError("Invalid JWK")
        if jwk.get("kty") != "oct":
            raise InvalidKeyError("Not an HMAC key")
        if "k" not in jwk:
            raise InvalidKeyError("Missing 'k' field in JWK")
        return base64url_decode(jwk["k"])


if has_crypto:
    class RSAAlgorithm(Algorithm):
        SHA256 = hashes.SHA256
        SHA384 = hashes.SHA384
        SHA512 = hashes.SHA512

        def __init__(self, hash_alg):
            self.hash_alg = hash_alg

        def prepare_key(self, key):
            if isinstance(key, (RSAPrivateKey, RSAPublicKey)):
                return key

            if not isinstance(key, (bytes, str)):
                raise InvalidKeyError("Invalid RSA key")

            key_bytes = force_bytes(key)

            try:
                if is_pem_format(key_bytes):
                    try:
                        return serialization.load_pem_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except Exception:
                        return serialization.load_pem_public_key(
                            key_bytes, backend=default_backend()
                        )
                elif is_ssh_key(key_bytes):
                    return serialization.load_ssh_public_key(
                        key_bytes, backend=default_backend()
                    )
                else:
                    # Try DER
                    try:
                        return serialization.load_der_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except Exception:
                        return serialization.load_der_public_key(
                            key_bytes, backend=default_backend()
                        )
            except (ValueError, TypeError, UnsupportedAlgorithm) as e:  # F11: UnsupportedAlgorithm now imported
                raise InvalidKeyError(f"Could not deserialize key: {e}")

        def sign(self, msg: bytes, key) -> bytes:
            return key.sign(msg, padding.PKCS1v15(), self.hash_alg())

        def verify(self, msg: bytes, key, sig: bytes) -> bool:
            try:
                if isinstance(key, RSAPrivateKey):
                    key = key.public_key()
                key.verify(sig, msg, padding.PKCS1v15(), self.hash_alg())
                return True
            except InvalidSignature:
                return False
            except Exception:
                return False

        @staticmethod
        def to_jwk(key_obj, as_dict: bool = False) -> Union[JWKDict, str]:
            # F3: Test for RSAPrivateKey first, then RSAPublicKey
            if isinstance(key_obj, RSAPrivateKey):
                priv_numbers = key_obj.private_numbers()
                pub_numbers = priv_numbers.public_numbers
                jwk = {
                    "kty": "RSA",
                    "n": to_base64url_uint(pub_numbers.n).decode("ASCII"),
                    "e": to_base64url_uint(pub_numbers.e).decode("ASCII"),
                    "d": to_base64url_uint(priv_numbers.d).decode("ASCII"),
                    "p": to_base64url_uint(priv_numbers.p).decode("ASCII"),
                    "q": to_base64url_uint(priv_numbers.q).decode("ASCII"),
                    "dp": to_base64url_uint(priv_numbers.dmp1).decode("ASCII"),
                    "dq": to_base64url_uint(priv_numbers.dmq1).decode("ASCII"),
                    "qi": to_base64url_uint(priv_numbers.iqmp).decode("ASCII"),
                }
            elif isinstance(key_obj, RSAPublicKey):
                # F3: just use key_obj.public_numbers() directly
                pub_numbers = key_obj.public_numbers()
                jwk = {
                    "kty": "RSA",
                    "n": to_base64url_uint(pub_numbers.n).decode("ASCII"),
                    "e": to_base64url_uint(pub_numbers.e).decode("ASCII"),
                }
            else:
                raise InvalidKeyError("Invalid RSA key")

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk: Union[str, JWKDict]):
            if isinstance(jwk, str):
                jwk = json.loads(jwk)
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Invalid JWK")
            if jwk.get("kty") != "RSA":
                raise InvalidKeyError("Not an RSA key")

            try:
                n = from_base64url_uint(jwk["n"])
                e = from_base64url_uint(jwk["e"])
                pub_numbers = RSAPublicNumbers(e, n)

                if "d" not in jwk:
                    return pub_numbers.public_key(default_backend())

                d = from_base64url_uint(jwk["d"])

                crt_fields = {"p", "q", "dp", "dq", "qi"}
                present = crt_fields & set(jwk.keys())

                if present and len(present) != len(crt_fields):
                    raise InvalidKeyError("Invalid RSA private key: partial CRT components")

                if present:
                    p = from_base64url_uint(jwk["p"])
                    q = from_base64url_uint(jwk["q"])
                    dp = from_base64url_uint(jwk["dp"])
                    dq = from_base64url_uint(jwk["dq"])
                    qi = from_base64url_uint(jwk["qi"])
                else:
                    # Recover prime factors
                    p, q = rsa_recover_prime_factors(n, e, d)
                    dp = rsa_crt_dmp1(d, p)
                    dq = rsa_crt_dmq1(d, q)
                    qi = rsa_crt_iqmp(p, q)

                priv_numbers = RSAPrivateNumbers(p, q, d, dp, dq, qi, pub_numbers)
                return priv_numbers.private_key(default_backend())
            except (KeyError, ValueError) as e:
                raise InvalidKeyError(f"Invalid RSA JWK: {e}")

    class ECAlgorithm(Algorithm):
        SHA256 = hashes.SHA256
        SHA384 = hashes.SHA384
        SHA512 = hashes.SHA512

        _curve_map = {
            "P-256": SECP256R1,
            "P-384": SECP384R1,
            "P-521": SECP521R1,
            "secp256k1": SECP256K1,
        }

        _hash_to_curve = {
            hashes.SHA256: SECP256R1,
            hashes.SHA384: SECP384R1,
            hashes.SHA512: SECP521R1,
        }

        def __init__(self, hash_alg):
            self.hash_alg = hash_alg

        def prepare_key(self, key):
            if isinstance(key, (EllipticCurvePrivateKey, EllipticCurvePublicKey)):
                return key

            if not isinstance(key, (bytes, str)):
                raise InvalidKeyError("Invalid EC key")

            key_bytes = force_bytes(key)

            try:
                if is_pem_format(key_bytes):
                    try:
                        return serialization.load_pem_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except Exception:
                        return serialization.load_pem_public_key(
                            key_bytes, backend=default_backend()
                        )
                elif is_ssh_key(key_bytes):
                    return serialization.load_ssh_public_key(
                        key_bytes, backend=default_backend()
                    )
                else:
                    try:
                        return serialization.load_der_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except Exception:
                        return serialization.load_der_public_key(
                            key_bytes, backend=default_backend()
                        )
            except Exception as e:
                raise InvalidKeyError(f"Could not deserialize EC key: {e}")

        def sign(self, msg: bytes, key) -> bytes:
            der_sig = key.sign(msg, ECDSA(self.hash_alg()))
            return der_to_raw_signature(der_sig, key.curve)

        def verify(self, msg: bytes, key, sig: bytes) -> bool:
            try:
                if isinstance(key, EllipticCurvePrivateKey):
                    key = key.public_key()
                der_sig = raw_to_der_signature(sig, key.curve)
                key.verify(der_sig, msg, ECDSA(self.hash_alg()))
                return True
            except InvalidSignature:
                return False
            except Exception:
                return False

        @staticmethod
        def to_jwk(key_obj, as_dict: bool = False) -> Union[JWKDict, str]:
            if isinstance(key_obj, EllipticCurvePrivateKey):
                pub_key = key_obj.public_key()
                pub_numbers = pub_key.public_numbers()
                priv_numbers = key_obj.private_numbers()
            elif isinstance(key_obj, EllipticCurvePublicKey):
                pub_numbers = key_obj.public_numbers()
                priv_numbers = None
            else:
                raise InvalidKeyError("Invalid EC key")

            curve = pub_numbers.curve
            crv_map = {
                SECP256R1: "P-256",
                SECP384R1: "P-384",
                SECP521R1: "P-521",
                SECP256K1: "secp256k1",
            }
            crv = crv_map.get(type(curve))
            if crv is None:
                raise InvalidKeyError("Unsupported EC curve")

            num_bytes = (curve.key_size + 7) // 8

            jwk = {
                "kty": "EC",
                "crv": crv,
                "x": base64url_encode(pub_numbers.x.to_bytes(num_bytes, byteorder="big")).decode("ASCII"),
                "y": base64url_encode(pub_numbers.y.to_bytes(num_bytes, byteorder="big")).decode("ASCII"),
            }

            if priv_numbers is not None:
                jwk["d"] = base64url_encode(
                    priv_numbers.private_value.to_bytes(num_bytes, byteorder="big")
                ).decode("ASCII")

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk: Union[str, JWKDict]):
            if isinstance(jwk, str):
                jwk = json.loads(jwk)
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Invalid JWK")
            if jwk.get("kty") != "EC":
                raise InvalidKeyError("Not an EC key")

            crv_name = jwk.get("crv", "P-256")
            crv_map = {
                "P-256": SECP256R1,
                "P-384": SECP384R1,
                "P-521": SECP521R1,
                "secp256k1": SECP256K1,
            }
            if crv_name not in crv_map:
                raise InvalidKeyError(f"Unsupported curve: {crv_name}")

            curve_cls = crv_map[crv_name]
            curve = curve_cls()
            num_bytes = (curve.key_size + 7) // 8

            try:
                x_bytes = base64url_decode(jwk["x"])
                y_bytes = base64url_decode(jwk["y"])
            except KeyError as e:
                raise InvalidKeyError(f"Missing field: {e}")

            if len(x_bytes) != num_bytes or len(y_bytes) != num_bytes:
                raise InvalidKeyError(
                    f"EC coordinate length mismatch: expected {num_bytes}, "
                    f"got x={len(x_bytes)}, y={len(y_bytes)}"
                )

            x = int.from_bytes(x_bytes, byteorder="big")
            y = int.from_bytes(y_bytes, byteorder="big")
            pub_numbers = EllipticCurvePublicNumbers(x, y, curve)

            if "d" not in jwk:
                return pub_numbers.public_key(default_backend())

            d_bytes = base64url_decode(jwk["d"])
            if len(d_bytes) != num_bytes:
                raise InvalidKeyError(f"EC private key length mismatch")

            d = int.from_bytes(d_bytes, byteorder="big")
            from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateNumbers
            priv_numbers = EllipticCurvePrivateNumbers(d, pub_numbers)
            return priv_numbers.private_key(default_backend())

    class RSAPSSAlgorithm(RSAAlgorithm):
        def sign(self, msg: bytes, key) -> bytes:
            return key.sign(
                msg,
                padding.PSS(
                    mgf=padding.MGF1(self.hash_alg()),
                    salt_length=self.hash_alg().digest_size,
                ),
                self.hash_alg(),
            )

        def verify(self, msg: bytes, key, sig: bytes) -> bool:
            try:
                if isinstance(key, RSAPrivateKey):
                    key = key.public_key()
                key.verify(
                    sig,
                    msg,
                    padding.PSS(
                        mgf=padding.MGF1(self.hash_alg()),
                        salt_length=self.hash_alg().digest_size,
                    ),
                    self.hash_alg(),
                )
                return True
            except InvalidSignature:
                return False
            except Exception:
                return False

    class OKPAlgorithm(Algorithm):
        def prepare_key(self, key):
            if isinstance(key, (Ed25519PrivateKey, Ed25519PublicKey, Ed448PrivateKey, Ed448PublicKey)):
                return key

            if not isinstance(key, (bytes, str)):
                raise InvalidKeyError("Invalid OKP key")

            key_bytes = force_bytes(key)

            try:
                if is_pem_format(key_bytes):
                    try:
                        return serialization.load_pem_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except Exception:
                        return serialization.load_pem_public_key(
                            key_bytes, backend=default_backend()
                        )
                elif is_ssh_key(key_bytes):
                    return serialization.load_ssh_public_key(
                        key_bytes, backend=default_backend()
                    )
                else:
                    try:
                        return serialization.load_der_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except Exception:
                        return serialization.load_der_public_key(
                            key_bytes, backend=default_backend()
                        )
            except Exception as e:
                raise InvalidKeyError(f"Could not deserialize OKP key: {e}")

        def sign(self, msg: bytes, key) -> bytes:
            return key.sign(force_bytes(msg))

        def verify(self, msg: bytes, key, sig: bytes) -> bool:
            try:
                if isinstance(key, (Ed25519PrivateKey, Ed448PrivateKey)):
                    key = key.public_key()
                key.verify(force_bytes(sig), force_bytes(msg))
                return True
            except InvalidSignature:
                return False
            except Exception:
                return False

        @staticmethod
        def to_jwk(key_obj, as_dict: bool = False) -> Union[JWKDict, str]:
            if isinstance(key_obj, (Ed25519PublicKey, Ed448PublicKey)):
                crv = "Ed25519" if isinstance(key_obj, Ed25519PublicKey) else "Ed448"
                x = key_obj.public_bytes(
                    serialization.Encoding.Raw,
                    serialization.PublicFormat.Raw,
                )
                jwk = {
                    "kty": "OKP",
                    "crv": crv,
                    "x": base64url_encode(x).decode("ASCII"),
                }
            elif isinstance(key_obj, (Ed25519PrivateKey, Ed448PrivateKey)):
                crv = "Ed25519" if isinstance(key_obj, Ed25519PrivateKey) else "Ed448"
                pub_key = key_obj.public_key()
                x = pub_key.public_bytes(
                    serialization.Encoding.Raw,
                    serialization.PublicFormat.Raw,
                )
                d = key_obj.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
                jwk = {
                    "kty": "OKP",
                    "crv": crv,
                    "x": base64url_encode(x).decode("ASCII"),
                    "d": base64url_encode(d).decode("ASCII"),
                }
            else:
                raise InvalidKeyError("Invalid OKP key")

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk: Union[str, JWKDict]):
            if isinstance(jwk, str):
                jwk = json.loads(jwk)
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Invalid JWK")
            if jwk.get("kty") != "OKP":
                raise InvalidKeyError("Not an OKP key")

            crv = jwk.get("crv")
            if crv not in ("Ed25519", "Ed448"):
                raise InvalidKeyError(f"Invalid OKP curve: {crv}")

            if "x" not in jwk:
                raise InvalidKeyError("Missing 'x' field")

            x_bytes = base64url_decode(jwk["x"])

            if "d" not in jwk:
                # Public key
                if crv == "Ed25519":
                    return Ed25519PublicKey.from_public_bytes(x_bytes)
                else:
                    return Ed448PublicKey.from_public_bytes(x_bytes)
            else:
                d_bytes = base64url_decode(jwk["d"])
                if crv == "Ed25519":
                    return Ed25519PrivateKey.from_private_bytes(d_bytes)
                else:
                    return Ed448PrivateKey.from_private_bytes(d_bytes)


def get_default_algorithms() -> Dict[str, Algorithm]:
    algorithms = {
        "none": NoneAlgorithm(),
        "HS256": HMACAlgorithm(HMACAlgorithm.SHA256),
        "HS384": HMACAlgorithm(HMACAlgorithm.SHA384),
        "HS512": HMACAlgorithm(HMACAlgorithm.SHA512),
    }

    if has_crypto:
        algorithms.update({
            "RS256": RSAAlgorithm(RSAAlgorithm.SHA256),
            "RS384": RSAAlgorithm(RSAAlgorithm.SHA384),
            "RS512": RSAAlgorithm(RSAAlgorithm.SHA512),
            "ES256": ECAlgorithm(ECAlgorithm.SHA256),
            "ES256K": ECAlgorithm(ECAlgorithm.SHA256),
            "ES384": ECAlgorithm(ECAlgorithm.SHA384),
            "ES512": ECAlgorithm(ECAlgorithm.SHA512),
            "PS256": RSAPSSAlgorithm(RSAPSSAlgorithm.SHA256),
            "PS384": RSAPSSAlgorithm(RSAPSSAlgorithm.SHA384),
            "PS512": RSAPSSAlgorithm(RSAPSSAlgorithm.SHA512),
            "EdDSA": OKPAlgorithm(),
        })

    return algorithms
