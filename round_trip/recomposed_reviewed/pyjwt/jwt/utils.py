import base64
import binascii
import re
from typing import Union

try:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
except ImportError:
    EllipticCurve = None  # type: ignore


def force_bytes(value: Union[bytes, str]) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return value.encode("utf-8")
    else:
        raise TypeError(f"Expected a string value, got {type(value)}")


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
    # Encode as big-endian bytes (minimum length)
    byte_length = (val.bit_length() + 7) // 8
    val_bytes = val.to_bytes(byte_length, byteorder="big")
    return base64url_encode(val_bytes)


def from_base64url_uint(val: Union[bytes, str]) -> int:
    if isinstance(val, str):
        val = val.encode("ascii")
    data = base64url_decode(val)
    return int.from_bytes(data, byteorder="big")


def number_to_bytes(num: int, num_bytes: int) -> bytes:
    return num.to_bytes(num_bytes, byteorder="big")


def bytes_to_number(string: bytes) -> int:
    return int.from_bytes(string, byteorder="big")


def der_to_raw_signature(der_sig: bytes, curve) -> bytes:
    """Convert DER-encoded ECDSA signature to raw r || s format."""
    num_bytes = (curve.key_size + 7) // 8

    # Parse DER sequence
    if der_sig[0] != 0x30:
        raise ValueError("Invalid DER signature")

    # Skip sequence tag and length
    idx = 1
    # Read sequence length
    seq_len_byte = der_sig[idx]
    idx += 1
    if seq_len_byte & 0x80:
        # Long form
        num_len_bytes = seq_len_byte & 0x7F
        idx += num_len_bytes

    def read_int(data, pos):
        if data[pos] != 0x02:
            raise ValueError("Expected INTEGER tag")
        pos += 1
        length = data[pos]
        pos += 1
        if length & 0x80:
            num_len_bytes = length & 0x7F
            length = int.from_bytes(data[pos:pos + num_len_bytes], byteorder="big")
            pos += num_len_bytes
        value = data[pos:pos + length]
        pos += length
        # Strip leading zero bytes for sign
        while len(value) > 1 and value[0] == 0:
            value = value[1:]
        return value, pos

    r_bytes, idx = read_int(der_sig, idx)
    s_bytes, idx = read_int(der_sig, idx)

    # Pad to num_bytes
    r_padded = r_bytes.rjust(num_bytes, b"\x00")
    s_padded = s_bytes.rjust(num_bytes, b"\x00")

    return r_padded + s_padded


def raw_to_der_signature(raw_sig: bytes, curve) -> bytes:
    """Convert raw r || s ECDSA signature to DER format."""
    num_bytes = (curve.key_size + 7) // 8

    if len(raw_sig) != 2 * num_bytes:
        raise ValueError(
            f"Invalid raw signature length: expected {2 * num_bytes}, got {len(raw_sig)}"
        )

    r_bytes = raw_sig[:num_bytes]
    s_bytes = raw_sig[num_bytes:]

    def encode_int(value: bytes) -> bytes:
        # Remove leading zeros
        value = value.lstrip(b"\x00")
        if not value:
            value = b"\x00"
        # Add leading zero if high bit set (to indicate positive)
        if value[0] & 0x80:
            value = b"\x00" + value
        return bytes([0x02, len(value)]) + value

    r_der = encode_int(r_bytes)
    s_der = encode_int(s_bytes)

    seq_content = r_der + s_der
    # Encode sequence length
    if len(seq_content) < 0x80:
        seq_len = bytes([len(seq_content)])
    else:
        len_bytes = len(seq_content).to_bytes((len(seq_content).bit_length() + 7) // 8, byteorder="big")
        seq_len = bytes([0x80 | len(len_bytes)]) + len_bytes

    return bytes([0x30]) + seq_len + seq_content


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
    "ANY PRIVATE KEY",
    "OPENSSH PRIVATE KEY",
    "SSH2 PUBLIC KEY",
)

_PEM_RE = re.compile(
    b"----[- ]BEGIN ("
    + b"|".join(re.escape(t.encode()) for t in _PEM_TYPES)
    + b")[- ]----\r?\n.+\r?\n----[- ]END ("
    + b"|".join(re.escape(t.encode()) for t in _PEM_TYPES)
    + b")[- ]----\r?\n?",
    re.DOTALL,
)

_SSH_KEY_PREFIXES = (
    b"ssh-ed25519",
    b"ssh-rsa",
    b"ssh-dss",
    b"ecdsa-sha2-nistp256",
    b"ecdsa-sha2-nistp384",
    b"ecdsa-sha2-nistp521",
)

_SSH_PUBKEY_RE = re.compile(rb"\A(\S+)[ \t]+(\S+)")


def is_pem_format(key: bytes) -> bool:
    return bool(_PEM_RE.search(key))


def is_ssh_key(key: bytes) -> bool:
    for prefix in _SSH_KEY_PREFIXES:
        if key.startswith(prefix):
            return True

    match = _SSH_PUBKEY_RE.match(key)
    if match:
        key_type = match.group(1)
        # Check if key_type is a recognized SSH key type
        for prefix in _SSH_KEY_PREFIXES:
            if key_type == prefix:
                return True
        # Check for cert format
        if key_type.endswith(b"-cert-v01@openssh.com"):
            base = key_type[: -len(b"-cert-v01@openssh.com")]
            for prefix in _SSH_KEY_PREFIXES:
                if base == prefix:
                    return True
        # Try to decode second group
        try:
            decoded = base64.b64decode(match.group(2))
            for prefix in _SSH_KEY_PREFIXES:
                if decoded.startswith(bytes([0, 0, 0, len(prefix)]) + prefix):
                    return True
        except Exception:
            pass

    return False
