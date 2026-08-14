"""Authenticated seal for secrets at rest (stdlib HMAC-SHA256 counter mode).

Used for webhook signing secrets so plaintext is not stored in PostgreSQL.
Never log sealed or unsealed values.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


def seal_secret(plaintext: str, master_key: str) -> str:
    if not plaintext:
        raise ValueError("Secret plaintext is required")
    if not master_key:
        raise ValueError("Master key is required")

    nonce = os.urandom(16)
    key = hashlib.sha256(master_key.encode("utf-8")).digest()
    data = plaintext.encode("utf-8")
    stream = _keystream(key, nonce, len(data))
    cipher = bytes(a ^ b for a, b in zip(data, stream, strict=True))
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")


def unseal_secret(token: str, master_key: str) -> str:
    if not token:
        raise ValueError("Sealed secret is required")
    if not master_key:
        raise ValueError("Master key is required")

    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid sealed secret encoding") from exc
    if len(raw) < 48:
        raise ValueError("Invalid sealed secret")

    nonce, tag, cipher = raw[:16], raw[16:48], raw[48:]
    key = hashlib.sha256(master_key.encode("utf-8")).digest()
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Sealed secret authenticity check failed")

    stream = _keystream(key, nonce, len(cipher))
    data = bytes(a ^ b for a, b in zip(cipher, stream, strict=True))
    return data.decode("utf-8")


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])
