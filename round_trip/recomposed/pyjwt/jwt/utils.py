import base64
import binascii
import re
from typing import Union

try:
    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature,
        encode_dss_signature,
    )
    has_crypto = True
except ModuleNotFoundError:
    has_crypto = False


def force_bytes(value: Union[bytes, str]) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return value.encode("utf-8")
    else:
        raise TypeError(f"Expected str or bytes, got {type(value)}")


def base64url_decode(input: Union[bytes, str]) -> bytes:
    if isinstance(input, str):
        input = input.encode("ascii")
    # Add padding
    rem = len(input) % 4
    if rem > 0:
        input += b"=" * (4 - rem)
    return base64.urlsafe_b64decode(input)


def base64url_encode(input: bytes) -> bytes:
    return base64.urlsafe_b64encode(input).rstrip(b"=")


def to_base64url_uint(val: int) -> bytes:
    if val < 0:
        raise ValueError("Value must be non-negative")
    if val == 0:
        return b"AA"
    # Convert to big-endian bytes, minimum length
    byte_length = (val.bit_length() + 7) // 8
    val_bytes = val.to_bytes(byte_length, byteorder="big")
    return base64url_encode(val_bytes)


def from_base64url_uint(val: Union[bytes, str]) -> int:
    decoded = base64url_decode(val)
    return int.from_bytes(decoded, byteorder="big")


def number_to_bytes(num: int, num_bytes: int) -> bytes:
    return num.to_bytes(num_bytes, byteorder="big")


def bytes_to_number(string: bytes) -> int:
    return int.from_bytes(string, byteorder="big")


def der_to_raw_signature(der_sig: bytes, curve) -> bytes:
    if not has_crypto:
        raise NotImplementedError("cryptography is required for EC signature conversion")
    key_size = (curve.key_size + 7) // 8
    r, s = decode_dss_signature(der_sig)
    return number_to_bytes(r, key_size) + number_to_bytes(s, key_size)


def raw_to_der_signature(raw_sig: bytes, curve) -> bytes:
    if not has_crypto:
        raise NotImplementedError("cryptography is required for EC signature conversion")
    key_size = (curve.key_size + 7) // 8
    if len(raw_sig) != 2 * key_size:
        raise ValueError(f"Invalid raw signature length: {len(raw_sig)}")
    r = bytes_to_number(raw_sig[:key_size])
    s = bytes_to_number(raw_sig[key_size:])
    return encode_dss_signature(r, s)


# PEM format detection
_PEM_TYPES = (
    "CERTIFICATE",
    "CERTIFICATE REQUEST",
    "ENCRYPTED PRIVATE KEY",
    "PRIVATE KEY",
    "PUBLIC KEY",
    "RSA PRIVATE KEY",
    "RSA PUBLIC KEY",
    "EC PRIVATE KEY",
    "EC PARAMETERS",
    "DH PARAMETERS",
    "NEW CERTIFICATE REQUEST",
    "PKCS7",
    "PKCS #7 SIGNED DATA",
    "TRUSTED CERTIFICATE",
    "X509 CRL",
    "CMS",
    "ATTRIBUTE CERTIFICATE",
    "DSA PRIVATE KEY",
    "DSA PARAMETERS",
)

_PEM_RE = re.compile(
    b"-----BEGIN ("
    + b"|".join(t.encode() for t in _PEM_TYPES)
    + b")-----\r?\n.+\r?\n-----END \\1-----\r?\n?",
    re.DOTALL,
)

_SSH_KEY_FORMATS = [
    b"ssh-ed25519",
    b"ssh-rsa",
    b"ssh-dss",
    b"ecdsa-sha2-nistp256",
    b"ecdsa-sha2-nistp384",
    b"ecdsa-sha2-nistp521",
]

_SSH_PUBKEY_RE = re.compile(rb"\A(\S+)[ \t]+(\S+)")


def is_pem_format(key: bytes) -> bool:
    return bool(_PEM_RE.search(key))


def is_ssh_key(key: bytes) -> bool:
    # Check for known SSH key prefixes
    for prefix in _SSH_KEY_FORMATS:
        if key.startswith(prefix):
            return True

    # Check SSH public key format: "<type> <base64data> [comment]"
    m = _SSH_PUBKEY_RE.match(key)
    if m:
        key_type = m.group(1)
        # Strip cert suffix
        cert_suffix = b"-cert-v01@openssh.com"
        if key_type.endswith(cert_suffix):
            key_type = key_type[: -len(cert_suffix)]
        if key_type in _SSH_KEY_FORMATS:
            return True
        # Try to decode the second group and check if it starts with key type bytes
        try:
            decoded = base64.b64decode(m.group(2))
            # The decoded bytes start with a 4-byte length-prefixed key type string
            if len(decoded) >= 4:
                type_len = int.from_bytes(decoded[:4], byteorder="big")
                if len(decoded) >= 4 + type_len:
                    embedded_type = decoded[4 : 4 + type_len]
                    if embedded_type in _SSH_KEY_FORMATS:
                        return True
        except Exception:
            pass

    return False
