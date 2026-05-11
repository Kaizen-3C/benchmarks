# ADR-0007: PEM and SSH Key Format Detection

## Status
Accepted

## Context
`HMACAlgorithm` must reject asymmetric keys passed as HMAC secrets. EC and RSA algorithms must correctly identify the key format for loading.

## Decision
Two utility functions in `utils.py` perform detection:

`is_pem_format(key: bytes) -> bool`: Uses a compiled regex `_PEM_RE` that matches `----[- ]BEGIN <TYPE>[- ]----\r?\n...\r?\n----[- ]END <TYPE>[- ]----\r?\n?` (DOTALL). Recognized types are a fixed set of 18 PEM label strings (e.g., `CERTIFICATE`, `PRIVATE KEY`, `PUBLIC KEY`, `RSA PRIVATE KEY`, `EC PRIVATE KEY`, etc.).

`is_ssh_key(key: bytes) -> bool`: Returns `True` if the key bytes contain any of 6 SSH key format prefixes (`ssh-ed25519`, `ssh-rsa`, `ssh-dss`, `ecdsa-sha2-nistp256`, `ecdsa-sha2-nistp384`, `ecdsa-sha2-nistp521`) OR if it matches the SSH public key regex `\A(\S+)[ \t]+(\S+)` where the first group is a recognized format or ends with `-cert-v01@openssh.com` (stripping the cert suffix before checking), OR if the base64-decoded second group starts with the key type bytes.

`HMACAlgorithm.prepare_key` raises `InvalidKeyError` if `is_pem_format` or `is_ssh_key` returns `True`.

## Consequences
- Prevents accidental use of asymmetric keys as HMAC secrets.
- SSH public keys can be loaded directly for RSA/EC/OKP algorithms.
