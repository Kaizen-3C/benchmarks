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
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding
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
        EllipticCurvePrivateNumbers,
        SECP256K1,
        SECP256R1,
        SECP384R1,
        SECP521R1,
        ECDSA,
    )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.asymmetric.ed448 import (
        Ed448PrivateKey,
        Ed448PublicKey,
    )
    from cryptography.hazmat.primitives.asymmetric import utils as asym_utils
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
    def to_jwk(key_obj, as_dict: bool = False):
        raise NotImplementedError

    @staticmethod
    def from_jwk(jwk):
        raise NotImplementedError

    def compute_hash_digest(self, bytestr: bytes) -> bytes:
        if not hasattr(self, "hash_alg"):
            raise NotImplementedError("No hash_alg attribute")
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
        key = force_bytes(key)
        if is_pem_format(key) or is_ssh_key(key):
            raise InvalidKeyError(
                "The specified key is an asymmetric key or x509 certificate and"
                " should not be used as an HMAC secret."
            )
        return key

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
            except json.JSONDecodeError as e:
                raise InvalidKeyError("Invalid JWK") from e
        if not isinstance(jwk, dict):
            raise InvalidKeyError("Invalid JWK")
        if jwk.get("kty") != "oct":
            raise InvalidKeyError("Not an oct key")
        if "k" not in jwk:
            raise InvalidKeyError("Missing 'k' field")
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
                raise InvalidKeyError("Expecting a PEM-formatted or RSA key object")

            key_bytes = force_bytes(key)

            if is_ssh_key(key_bytes):
                return serialization.load_ssh_public_key(key_bytes, backend=default_backend())

            try:
                if b"PRIVATE" in key_bytes:
                    return serialization.load_pem_private_key(
                        key_bytes, password=None, backend=default_backend()
                    )
                else:
                    return serialization.load_pem_public_key(
                        key_bytes, backend=default_backend()
                    )
            except Exception as e:
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

        @staticmethod
        def to_jwk(key_obj, as_dict: bool = False):
            if isinstance(key_obj, RSAPublicKey):
                pub_numbers = key_obj.public_key().public_numbers() if hasattr(key_obj, 'private_bytes') else key_obj.public_numbers()
                jwk = {
                    "kty": "RSA",
                    "n": to_base64url_uint(pub_numbers.n).decode("ASCII"),
                    "e": to_base64url_uint(pub_numbers.e).decode("ASCII"),
                }
            elif isinstance(key_obj, RSAPrivateKey):
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
                except json.JSONDecodeError as e:
                    raise InvalidKeyError("Invalid JWK") from e
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Invalid JWK")
            if jwk.get("kty") != "RSA":
                raise InvalidKeyError("Not an RSA key")

            try:
                e = from_base64url_uint(jwk["e"])
                n = from_base64url_uint(jwk["n"])

                pub_numbers = RSAPublicNumbers(e=e, n=n)

                if "d" not in jwk:
                    # Public key
                    return pub_numbers.public_key(default_backend())

                d = from_base64url_uint(jwk["d"])

                # Check which CRT components are present
                crt_fields = {"p", "q", "dp", "dq", "qi"}
                present = {f for f in crt_fields if f in jwk}

                if len(present) == 0:
                    # Recover prime factors
                    p, q = rsa_recover_prime_factors(n, e, d)
                    dp = rsa_crt_dmp1(d, p)
                    dq = rsa_crt_dmq1(d, q)
                    qi = rsa_crt_iqmp(p, q)
                elif len(present) == 5:
                    p = from_base64url_uint(jwk["p"])
                    q = from_base64url_uint(jwk["q"])
                    dp = from_base64url_uint(jwk["dp"])
                    dq = from_base64url_uint(jwk["dq"])
                    qi = from_base64url_uint(jwk["qi"])
                else:
                    raise InvalidKeyError("Partial CRT components present")

                priv_numbers = RSAPrivateNumbers(
                    p=p, q=q, d=d, dmp1=dp, dmq1=dq, iqmp=qi,
                    public_numbers=pub_numbers
                )
                return priv_numbers.private_key(default_backend())

            except (KeyError, ValueError) as e:
                raise InvalidKeyError("Invalid RSA key") from e

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
                raise InvalidKeyError("Expecting a PEM-formatted or EC key object")

            key_bytes = force_bytes(key)

            if is_ssh_key(key_bytes):
                return serialization.load_ssh_public_key(key_bytes, backend=default_backend())

            try:
                if b"PRIVATE" in key_bytes:
                    return serialization.load_pem_private_key(
                        key_bytes, password=None, backend=default_backend()
                    )
                else:
                    return serialization.load_pem_public_key(
                        key_bytes, backend=default_backend()
                    )
            except Exception as e:
                raise InvalidKeyError("Could not deserialize key data") from e

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
            except (InvalidSignature, ValueError):
                return False

        @staticmethod
        def to_jwk(key_obj, as_dict: bool = False):
            if isinstance(key_obj, EllipticCurvePrivateKey):
                priv_numbers = key_obj.private_numbers()
                pub_numbers = priv_numbers.public_numbers
                crv = _curve_to_name(key_obj.curve)
                key_size = (key_obj.key_size + 7) // 8
                jwk = {
                    "kty": "EC",
                    "crv": crv,
                    "x": base64url_encode(pub_numbers.x.to_bytes(key_size, "big")).decode("ASCII"),
                    "y": base64url_encode(pub_numbers.y.to_bytes(key_size, "big")).decode("ASCII"),
                    "d": base64url_encode(priv_numbers.private_value.to_bytes(key_size, "big")).decode("ASCII"),
                }
            elif isinstance(key_obj, EllipticCurvePublicKey):
                pub_numbers = key_obj.public_numbers()
                crv = _curve_to_name(key_obj.curve)
                key_size = (key_obj.key_size + 7) // 8
                jwk = {
                    "kty": "EC",
                    "crv": crv,
                    "x": base64url_encode(pub_numbers.x.to_bytes(key_size, "big")).decode("ASCII"),
                    "y": base64url_encode(pub_numbers.y.to_bytes(key_size, "big")).decode("ASCII"),
                }
            else:
                raise InvalidKeyError("Not an EC key")

            if as_dict:
                return jwk
            return json.dumps(jwk)

        @staticmethod
        def from_jwk(jwk):
            if isinstance(jwk, str):
                try:
                    jwk = json.loads(jwk)
                except json.JSONDecodeError as e:
                    raise InvalidKeyError("Invalid JWK") from e
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Invalid JWK")
            if jwk.get("kty") != "EC":
                raise InvalidKeyError("Not an EC key")

            crv_name = jwk.get("crv", "P-256")
            crv = _name_to_curve(crv_name)
            if crv is None:
                raise InvalidKeyError(f"Invalid curve: {crv_name}")

            try:
                x = from_base64url_uint(jwk["x"])
                y = from_base64url_uint(jwk["y"])
                key_size = (crv.key_size + 7) // 8

                # Validate coordinate byte lengths
                x_bytes = base64url_decode(jwk["x"])
                y_bytes = base64url_decode(jwk["y"])
                if len(x_bytes) != key_size or len(y_bytes) != key_size:
                    raise InvalidKeyError("Invalid EC key: coordinate byte length mismatch")

                pub_numbers = EllipticCurvePublicNumbers(x=x, y=y, curve=crv)

                if "d" not in jwk:
                    return pub_numbers.public_key(default_backend())

                d = from_base64url_uint(jwk["d"])
                priv_numbers = EllipticCurvePrivateNumbers(
                    private_value=d, public_numbers=pub_numbers
                )
                return priv_numbers.private_key(default_backend())

            except (KeyError, ValueError) as e:
                raise InvalidKeyError("Invalid EC key") from e

    def _curve_to_name(curve):
        if isinstance(curve, SECP256R1):
            return "P-256"
        elif isinstance(curve, SECP384R1):
            return "P-384"
        elif isinstance(curve, SECP521R1):
            return "P-521"
        elif isinstance(curve, SECP256K1):
            return "secp256k1"
        else:
            raise InvalidKeyError(f"Unsupported curve: {curve}")

    def _name_to_curve(crv_name):
        curve_map = {
            "P-256": SECP256R1(),
            "P-384": SECP384R1(),
            "P-521": SECP521R1(),
            "secp256k1": SECP256K1(),
        }
        return curve_map.get(crv_name)

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

    class OKPAlgorithm(Algorithm):
        def prepare_key(self, key):
            if isinstance(key, (Ed25519PrivateKey, Ed25519PublicKey, Ed448PrivateKey, Ed448PublicKey)):
                return key

            if not isinstance(key, (bytes, str)):
                raise InvalidKeyError("Expecting a PEM-formatted or OKP key object")

            key_bytes = force_bytes(key)

            if is_ssh_key(key_bytes):
                return serialization.load_ssh_public_key(key_bytes, backend=default_backend())

            try:
                if b"PRIVATE" in key_bytes:
                    return serialization.load_pem_private_key(
                        key_bytes, password=None, backend=default_backend()
                    )
                else:
                    return serialization.load_pem_public_key(
                        key_bytes, backend=default_backend()
                    )
            except Exception as e:
                raise InvalidKeyError("Could not deserialize key data") from e

        def sign(self, msg: bytes, key) -> bytes:
            return key.sign(force_bytes(msg))

        def verify(self, msg: bytes, key, sig: bytes) -> bool:
            try:
                if isinstance(key, (Ed25519PrivateKey, Ed448PrivateKey)):
                    key = key.public_key()
                key.verify(force_bytes(sig), force_bytes(msg))
                return True
            except (InvalidSignature, Exception):
                return False

        @staticmethod
        def to_jwk(key_obj, as_dict: bool = False):
            if isinstance(key_obj, Ed25519PublicKey):
                crv = "Ed25519"
                x = base64url_encode(
                    key_obj.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
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
                    key_obj.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
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
                except json.JSONDecodeError as e:
                    raise InvalidKeyError("Invalid JWK") from e
            if not isinstance(jwk, dict):
                raise InvalidKeyError("Invalid JWK")
            if jwk.get("kty") != "OKP":
                raise InvalidKeyError("Not an OKP key")

            crv = jwk.get("crv")
            if crv not in ("Ed25519", "Ed448"):
                raise InvalidKeyError(f"Invalid OKP curve: {crv}")

            if "x" not in jwk:
                raise InvalidKeyError("Missing 'x' field")

            try:
                x_bytes = base64url_decode(jwk["x"])
                if "d" in jwk:
                    d_bytes = base64url_decode(jwk["d"])
                    if crv == "Ed25519":
                        return Ed25519PrivateKey.from_private_bytes(d_bytes)
                    else:
                        return Ed448PrivateKey.from_private_bytes(d_bytes)
                else:
                    if crv == "Ed25519":
                        return Ed25519PublicKey.from_public_bytes(x_bytes)
                    else:
                        return Ed448PublicKey.from_public_bytes(x_bytes)
            except Exception as e:
                raise InvalidKeyError("Invalid OKP key") from e


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
