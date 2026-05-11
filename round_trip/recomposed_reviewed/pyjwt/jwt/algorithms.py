import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional, Union

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
    from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePrivateKey,
        EllipticCurvePublicKey,
        SECP256K1,
        SECP256R1,
        SECP384R1,
        SECP521R1,
    )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.asymmetric.ed448 import (
        Ed448PrivateKey,
        Ed448PublicKey,
    )
    from cryptography.hazmat.primitives.asymmetric.rsa import (
        RSAPrivateKey,
        RSAPublicKey,
        RSAPrivateNumbers,
        RSAPublicNumbers,
        rsa_crt_iqmp,
        rsa_crt_dmp1,
        rsa_crt_dmq1,
    )
    from cryptography.hazmat.backends import default_backend

    has_crypto = True
except ImportError:
    has_crypto = False

requires_cryptography = {
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES256K",
    "ES384",
    "ES521",
    "ES512",
    "PS256",
    "PS384",
    "PS512",
    "EdDSA",
}


class Algorithm:
    """Abstract base class for JWT signing algorithms."""

    def prepare_key(self, key: Any) -> Any:
        raise NotImplementedError

    def sign(self, msg: bytes, key: Any) -> bytes:
        raise NotImplementedError

    def verify(self, msg: bytes, key: Any, sig: bytes) -> bool:
        raise NotImplementedError

    @staticmethod
    def to_jwk(key_obj, as_dict: bool = False):
        raise NotImplementedError

    @staticmethod
    def from_jwk(jwk):
        raise NotImplementedError

    def compute_hash_digest(self, bytestr: bytes) -> bytes:
        if not hasattr(self, "hash_alg"):
            raise NotImplementedError("Algorithm does not have a hash_alg attribute")
        return self.hash_alg(bytestr).digest()


class NoneAlgorithm(Algorithm):
    def prepare_key(self, key: Any) -> None:
        if key == "":
            return None
        if key is not None:
            raise InvalidKeyError("The 'none' algorithm key must be None or empty string")
        return None

    def sign(self, msg: bytes, key: None) -> bytes:
        return b""

    def verify(self, msg: bytes, key: None, sig: bytes) -> bool:
        return False

    @staticmethod
    def to_jwk(key_obj, as_dict: bool = False):
        raise NotImplementedError

    @staticmethod
    def from_jwk(jwk):
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
    def to_jwk(key_obj, as_dict: bool = False):
        if isinstance(key_obj, str):
            key_obj = key_obj.encode("utf-8")
        if not isinstance(key_obj, bytes):
            raise InvalidKeyError("Key must be bytes or str")
        k = base64url_encode(key_obj).decode("ASCII")
        jwk = {"k": k, "kty": "oct"}
        if as_dict:
            return jwk
        return json.dumps(jwk)

    @staticmethod
    def from_jwk(jwk):
        if isinstance(jwk, str):
            try:
                jwk = json.loads(jwk)
            except Exception:
                raise InvalidKeyError("Key is not valid JSON")
        if not isinstance(jwk, dict):
            raise InvalidKeyError("Key must be a dict or JSON string")
        if jwk.get("kty") != "oct":
            raise InvalidKeyError("Not an HMAC key")
        if "k" not in jwk:
            raise InvalidKeyError("Missing 'k' parameter")
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
                raise InvalidKeyError("Expecting a PEM-formatted or RSA key")

            key_bytes = force_bytes(key)

            try:
                if is_pem_format(key_bytes):
                    try:
                        return serialization.load_pem_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except (ValueError, TypeError, UnsupportedAlgorithm):
                        pass
                    try:
                        return serialization.load_pem_public_key(
                            key_bytes, backend=default_backend()
                        )
                    except (ValueError, TypeError, UnsupportedAlgorithm):
                        raise InvalidKeyError("Could not deserialize key data")
                elif is_ssh_key(key_bytes):
                    return serialization.load_ssh_public_key(
                        key_bytes, backend=default_backend()
                    )
                else:
                    raise InvalidKeyError("Could not deserialize key data")
            except (ValueError, TypeError, UnsupportedAlgorithm) as e:
                raise InvalidKeyError("Could not deserialize key data") from e

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

        def to_jwk(self, key_obj, as_dict: bool = False):
            if isinstance(key_obj, RSAPrivateKey):
                private_numbers = key_obj.private_numbers()
                public_numbers = private_numbers.public_numbers

                def to_b64(n, length):
                    return base64url_encode(
                        n.to_bytes(length, byteorder="big")
                    ).decode("ASCII")

                key_size = key_obj.key_size
                num_bytes = (key_size + 7) // 8

                jwk = {
                    "kty": "RSA",
                    "n": base64url_encode(
                        public_numbers.n.to_bytes(num_bytes, byteorder="big")
                    ).decode("ASCII"),
                    "e": to_base64url_uint(public_numbers.e).decode("ASCII"),
                    "d": base64url_encode(
                        private_numbers.d.to_bytes(num_bytes, byteorder="big")
                    ).decode("ASCII"),
                    "p": base64url_encode(
                        private_numbers.p.to_bytes((private_numbers.p.bit_length() + 7) // 8, byteorder="big")
                    ).decode("ASCII"),
                    "q": base64url_encode(
                        private_numbers.q.to_bytes((private_numbers.q.bit_length() + 7) // 8, byteorder="big")
                    ).decode("ASCII"),
                    "dp": base64url_encode(
                        private_numbers.dmp1.to_bytes((private_numbers.dmp1.bit_length() + 7) // 8, byteorder="big")
                    ).decode("ASCII"),
                    "dq": base64url_encode(
                        private_numbers.dmq1.to_bytes((private_numbers.dmq1.bit_length() + 7) // 8, byteorder="big")
                    ).decode("ASCII"),
                    "qi": base64url_encode(
                        private_numbers.iqmp.to_bytes((private_numbers.iqmp.bit_length() + 7) // 8, byteorder="big")
                    ).decode("ASCII"),
                }
            elif isinstance(key_obj, RSAPublicKey):
                public_numbers = key_obj.public_numbers()
                num_bytes = (key_obj.key_size + 7) // 8
                jwk = {
                    "kty": "RSA",
                    "n": base64url_encode(
                        public_numbers.n.to_bytes(num_bytes, byteorder="big")
                    ).decode("ASCII"),
                    "e": to_base64url_uint(public_numbers.e).decode("ASCII"),
                }
            else:
                raise InvalidKeyError("Not an RSA key")

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk):
            if isinstance(jwk, str):
                try:
                    jwk = json.loads(jwk)
                except Exception:
                    raise InvalidKeyError("Key is not valid JSON")
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Key must be a dict or JSON string")
            if jwk.get("kty") != "RSA":
                raise InvalidKeyError("Not an RSA key")

            if "n" not in jwk or "e" not in jwk:
                raise InvalidKeyError("Missing required RSA parameters")

            n = from_base64url_uint(jwk["n"])
            e = from_base64url_uint(jwk["e"])

            public_numbers = RSAPublicNumbers(e, n)

            if "d" not in jwk:
                # Public key only
                return public_numbers.public_key(default_backend())

            d = from_base64url_uint(jwk["d"])

            # Check if CRT components are present
            crt_params = {"p", "q", "dp", "dq", "qi"}
            has_crt = crt_params.intersection(jwk.keys())

            if has_crt and len(has_crt) < len(crt_params):
                raise InvalidKeyError("Only some CRT components present")

            if has_crt:
                p = from_base64url_uint(jwk["p"])
                q = from_base64url_uint(jwk["q"])
                dp = from_base64url_uint(jwk["dp"])
                dq = from_base64url_uint(jwk["dq"])
                qi = from_base64url_uint(jwk["qi"])
            else:
                # Recover prime factors from n, e, d
                p, q = rsa.rsa_recover_prime_factors(n, e, d)
                dp = rsa_crt_dmp1(d, p)
                dq = rsa_crt_dmq1(d, q)
                qi = rsa_crt_iqmp(p, q)

            private_numbers = RSAPrivateNumbers(p, q, d, dp, dq, qi, public_numbers)
            return private_numbers.private_key(default_backend())

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

    class ECAlgorithm(Algorithm):
        SHA256 = hashes.SHA256
        SHA384 = hashes.SHA384
        SHA512 = hashes.SHA512

        def __init__(self, hash_alg):
            self.hash_alg = hash_alg

        def prepare_key(self, key):
            if isinstance(key, (EllipticCurvePrivateKey, EllipticCurvePublicKey)):
                return key

            if not isinstance(key, (bytes, str)):
                raise InvalidKeyError("Expecting a PEM-formatted or EC key")

            key_bytes = force_bytes(key)

            try:
                if is_pem_format(key_bytes):
                    try:
                        return serialization.load_pem_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except (ValueError, TypeError, UnsupportedAlgorithm):
                        pass
                    try:
                        return serialization.load_pem_public_key(
                            key_bytes, backend=default_backend()
                        )
                    except (ValueError, TypeError, UnsupportedAlgorithm):
                        raise InvalidKeyError("Could not deserialize key data")
                elif is_ssh_key(key_bytes):
                    return serialization.load_ssh_public_key(
                        key_bytes, backend=default_backend()
                    )
                else:
                    raise InvalidKeyError("Could not deserialize key data")
            except (ValueError, TypeError, UnsupportedAlgorithm) as e:
                raise InvalidKeyError("Could not deserialize key data") from e

        def sign(self, msg: bytes, key) -> bytes:
            der_sig = key.sign(msg, ec.ECDSA(self.hash_alg()))
            return der_to_raw_signature(der_sig, key.curve)

        def verify(self, msg: bytes, key, sig: bytes) -> bool:
            try:
                if isinstance(key, EllipticCurvePrivateKey):
                    key = key.public_key()
                der_sig = raw_to_der_signature(sig, key.curve)
                key.verify(der_sig, msg, ec.ECDSA(self.hash_alg()))
                return True
            except (InvalidSignature, ValueError):
                return False

        def to_jwk(self, key_obj, as_dict: bool = False):
            if isinstance(key_obj, EllipticCurvePrivateKey):
                public_key = key_obj.public_key()
                private_numbers = key_obj.private_numbers()
                public_numbers = private_key_numbers = private_numbers.public_numbers
            elif isinstance(key_obj, EllipticCurvePublicKey):
                public_key = key_obj
                public_numbers = key_obj.public_numbers()
                private_numbers = None
            else:
                raise InvalidKeyError("Not an EC key")

            crv_map = {
                SECP256R1: "P-256",
                SECP384R1: "P-384",
                SECP521R1: "P-521",
                SECP256K1: "secp256k1",
            }
            curve = public_key.curve
            crv = crv_map.get(type(curve))
            if crv is None:
                raise InvalidKeyError(f"Unsupported curve: {type(curve)}")

            num_bytes = (curve.key_size + 7) // 8

            x = base64url_encode(
                public_numbers.x.to_bytes(num_bytes, byteorder="big")
            ).decode("ASCII")
            y = base64url_encode(
                public_numbers.y.to_bytes(num_bytes, byteorder="big")
            ).decode("ASCII")

            jwk = {
                "kty": "EC",
                "crv": crv,
                "x": x,
                "y": y,
            }

            if private_numbers is not None:
                d = base64url_encode(
                    private_numbers.private_value.to_bytes(num_bytes, byteorder="big")
                ).decode("ASCII")
                jwk["d"] = d

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk):
            if isinstance(jwk, str):
                try:
                    jwk = json.loads(jwk)
                except Exception:
                    raise InvalidKeyError("Key is not valid JSON")
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Key must be a dict or JSON string")
            if jwk.get("kty") != "EC":
                raise InvalidKeyError("Not an EC key")

            crv_map = {
                "P-256": SECP256R1(),
                "P-384": SECP384R1(),
                "P-521": SECP521R1(),
                "secp256k1": SECP256K1(),
            }

            crv_str = jwk.get("crv")
            curve = crv_map.get(crv_str)
            if curve is None:
                raise InvalidKeyError(f"Invalid curve: {crv_str}")

            num_bytes = (curve.key_size + 7) // 8

            if "x" not in jwk or "y" not in jwk:
                raise InvalidKeyError("Missing EC key parameters")

            x_bytes = base64url_decode(jwk["x"])
            y_bytes = base64url_decode(jwk["y"])

            if len(x_bytes) != num_bytes or len(y_bytes) != num_bytes:
                raise InvalidKeyError("EC key coordinates have wrong length")

            x = int.from_bytes(x_bytes, byteorder="big")
            y = int.from_bytes(y_bytes, byteorder="big")

            public_numbers = ec.EllipticCurvePublicNumbers(x, y, curve)

            if "d" not in jwk:
                return public_numbers.public_key(default_backend())

            d_bytes = base64url_decode(jwk["d"])
            if len(d_bytes) != num_bytes:
                raise InvalidKeyError("EC private key has wrong length")
            d = int.from_bytes(d_bytes, byteorder="big")

            private_numbers = ec.EllipticCurvePrivateNumbers(d, public_numbers)
            return private_numbers.private_key(default_backend())

    class OKPAlgorithm(Algorithm):
        def prepare_key(self, key):
            if isinstance(
                key,
                (Ed25519PrivateKey, Ed25519PublicKey, Ed448PrivateKey, Ed448PublicKey),
            ):
                return key

            if not isinstance(key, (bytes, str)):
                raise InvalidKeyError("Expecting a PEM-formatted or OKP key")

            key_bytes = force_bytes(key)

            try:
                if is_pem_format(key_bytes):
                    try:
                        return serialization.load_pem_private_key(
                            key_bytes, password=None, backend=default_backend()
                        )
                    except (ValueError, TypeError, UnsupportedAlgorithm):
                        pass
                    try:
                        return serialization.load_pem_public_key(
                            key_bytes, backend=default_backend()
                        )
                    except (ValueError, TypeError, UnsupportedAlgorithm):
                        raise InvalidKeyError("Could not deserialize key data")
                elif is_ssh_key(key_bytes):
                    return serialization.load_ssh_public_key(
                        key_bytes, backend=default_backend()
                    )
                else:
                    raise InvalidKeyError("Could not deserialize key data")
            except (ValueError, TypeError, UnsupportedAlgorithm) as e:
                raise InvalidKeyError("Could not deserialize key data") from e

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

        def to_jwk(self, key_obj, as_dict: bool = False):
            if isinstance(key_obj, Ed25519PublicKey):
                crv = "Ed25519"
                x = base64url_encode(
                    key_obj.public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ).decode("ASCII")
                jwk = {"kty": "OKP", "crv": crv, "x": x}
            elif isinstance(key_obj, Ed25519PrivateKey):
                crv = "Ed25519"
                x = base64url_encode(
                    key_obj.public_key().public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ).decode("ASCII")
                d = base64url_encode(
                    key_obj.private_bytes(
                        serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw,
                        serialization.NoEncryption(),
                    )
                ).decode("ASCII")
                jwk = {"kty": "OKP", "crv": crv, "x": x, "d": d}
            elif isinstance(key_obj, Ed448PublicKey):
                crv = "Ed448"
                x = base64url_encode(
                    key_obj.public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ).decode("ASCII")
                jwk = {"kty": "OKP", "crv": crv, "x": x}
            elif isinstance(key_obj, Ed448PrivateKey):
                crv = "Ed448"
                x = base64url_encode(
                    key_obj.public_key().public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ).decode("ASCII")
                d = base64url_encode(
                    key_obj.private_bytes(
                        serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw,
                        serialization.NoEncryption(),
                    )
                ).decode("ASCII")
                jwk = {"kty": "OKP", "crv": crv, "x": x, "d": d}
            else:
                raise InvalidKeyError("Not an OKP key")

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk):
            if isinstance(jwk, str):
                try:
                    jwk = json.loads(jwk)
                except Exception:
                    raise InvalidKeyError("Key is not valid JSON")
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Key must be a dict or JSON string")
            if jwk.get("kty") != "OKP":
                raise InvalidKeyError("Not an OKP key")

            crv = jwk.get("crv")
            if crv not in ("Ed25519", "Ed448"):
                raise InvalidKeyError(f"Invalid or missing curve: {crv}")

            if "x" not in jwk:
                raise InvalidKeyError("Missing 'x' parameter")

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
    default_algorithms = {
        "none": NoneAlgorithm(),
        "HS256": HMACAlgorithm(HMACAlgorithm.SHA256),
        "HS384": HMACAlgorithm(HMACAlgorithm.SHA384),
        "HS512": HMACAlgorithm(HMACAlgorithm.SHA512),
    }

    if has_crypto:
        default_algorithms.update(
            {
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
            }
        )

    return default_algorithms
