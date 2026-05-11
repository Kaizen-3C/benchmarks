import base64
import binascii
import re
import struct
from typing import Union

# PEM format detection
_PEM_TYPES = (
    "CERTIFICATE",
    "TRUSTED CERTIFICATE",
    "PRIVATE KEY",
    "PUBLIC KEY",
    "ENCRYPTED PRIVATE KEY",
    "OPENSSH PRIVATE KEY",
    "DSA PRIVATE KEY",
    "RSA PRIVATE KEY",
    "RSA PUBLIC KEY",
    "EC PRIVATE KEY",
    "DH PARAMETERS",
    "NEW CERTIFICATE REQUEST",
    "CERTIFICATE REQUEST",
    "SSH2 PUBLIC KEY",
    "SSH2 ENCRYPTED PRIVATE KEY",
    "X509 CRL",
    "PKCS7",
    "CMS",
)

_PEM_RE = re.compile(
    b"-----BEGIN (" + b"|".join(t.encode() for t in _PEM_TYPES) + b")-----\r?\n"
    b".+\r?\n"
    b"-----END (" + b"|".join(t.encode() for t in _PEM_TYPES) + b")-----\r?\n?",
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


def force_bytes(value: Union[bytes, str]) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return value.encode("utf-8")
    else:
        raise TypeError(f"Expected bytes or str, got {type(value)}")


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
        raise ValueError("Must be a positive integer")
    if val == 0:
        return b"AA"
    # Convert to big-endian bytes
    byte_length = (val.bit_length() + 7) // 8
    val_bytes = val.to_bytes(byte_length, byteorder="big")
    return base64url_encode(val_bytes)


def from_base64url_uint(val: Union[bytes, str]) -> int:
    data = base64url_decode(val)
    return int.from_bytes(data, byteorder="big")


def number_to_bytes(num: int, num_bytes: int) -> bytes:
    return num.to_bytes(num_bytes, byteorder="big")


def bytes_to_number(string: bytes) -> int:
    return int.from_bytes(string, byteorder="big")


def der_to_raw_signature(der_sig: bytes, curve) -> bytes:
    num_bits = curve.key_size
    num_bytes = (num_bits + 7) // 8

    # Parse DER-encoded ECDSA signature
    # Format: SEQUENCE { INTEGER r, INTEGER s }
    if len(der_sig) < 2 or der_sig[0] != 0x30:
        raise ValueError("Invalid DER signature")

    # Parse outer sequence length
    idx = 1
    seq_len, idx = _parse_der_length(der_sig, idx)

    # Parse r INTEGER
    if der_sig[idx] != 0x02:
        raise ValueError("Expected INTEGER tag for r")
    idx += 1
    r_len, idx = _parse_der_length(der_sig, idx)
    r_bytes = der_sig[idx:idx + r_len]
    idx += r_len

    # Parse s INTEGER
    if der_sig[idx] != 0x02:
        raise ValueError("Expected INTEGER tag for s")
    idx += 1
    s_len, idx = _parse_der_length(der_sig, idx)
    s_bytes = der_sig[idx:idx + s_len]

    # Strip leading zeros and pad to num_bytes
    r = int.from_bytes(r_bytes, byteorder="big")
    s = int.from_bytes(s_bytes, byteorder="big")

    return (
        r.to_bytes(num_bytes, byteorder="big") +
        s.to_bytes(num_bytes, byteorder="big")
    )


def _parse_der_length(data: bytes, idx: int):
    length = data[idx]
    idx += 1
    if length & 0x80:
        num_bytes = length & 0x7f
        length = int.from_bytes(data[idx:idx + num_bytes], byteorder="big")
        idx += num_bytes
    return length, idx


def _encode_der_integer(val: int) -> bytes:
    # Encode integer as DER INTEGER
    length = (val.bit_length() + 7) // 8
    if length == 0:
        length = 1
    val_bytes = val.to_bytes(length, byteorder="big")
    # Add leading 0x00 if high bit set
    if val_bytes[0] & 0x80:
        val_bytes = b"\x00" + val_bytes
    return b"\x02" + _encode_der_length(len(val_bytes)) + val_bytes


def _encode_der_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    elif length < 0x100:
        return b"\x81" + bytes([length])
    else:
        return b"\x82" + length.to_bytes(2, byteorder="big")


def raw_to_der_signature(raw_sig: bytes, curve) -> bytes:
    num_bits = curve.key_size
    num_bytes = (num_bits + 7) // 8

    if len(raw_sig) != 2 * num_bytes:
        raise ValueError(f"Invalid raw signature length: expected {2 * num_bytes}, got {len(raw_sig)}")

    r = int.from_bytes(raw_sig[:num_bytes], byteorder="big")
    s = int.from_bytes(raw_sig[num_bytes:], byteorder="big")

    r_der = _encode_der_integer(r)
    s_der = _encode_der_integer(s)

    seq_content = r_der + s_der
    return b"\x30" + _encode_der_length(len(seq_content)) + seq_content


def is_pem_format(key: bytes) -> bool:
    return bool(_PEM_RE.search(key))


def is_ssh_key(key: bytes) -> bool:
    # Check for known SSH key prefixes
    for prefix in _SSH_KEY_FORMATS:
        if key.startswith(prefix):
            return True

    # Check for SSH public key format
    match = _SSH_PUBKEY_RE.match(key)
    if match:
        key_type = match.group(1)
        # Strip cert suffix
        if key_type.endswith(b"-cert-v01@openssh.com"):
            key_type = key_type[: -len(b"-cert-v01@openssh.com")]
        if key_type in _SSH_KEY_FORMATS:
            return True
        # Try base64 decoding the second group
        try:
            decoded = base64.b64decode(match.group(2))
            for prefix in _SSH_KEY_FORMATS:
                if decoded.startswith(bytes([0, 0, 0, len(prefix)]) + prefix):
                    return True
        except Exception:
            pass

    return False
