"""Authenticated encryption for secrets at rest (AES-256-GCM with key rotation)."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretBox:
    """Encrypts with the first configured key; decrypts with whichever key id the value names."""

    def __init__(self, keys_spec: str) -> None:
        keys: dict[str, bytes] = {}
        order: list[str] = []
        for part in keys_spec.split(","):
            key_id, _, encoded = part.strip().partition(":")
            raw = base64.b64decode(encoded)
            if not key_id or len(raw) != 32:
                raise ValueError("Each secret key must be '<id>:<base64 of 32 bytes>'.")
            keys[key_id] = raw
            order.append(key_id)
        if not order:
            raise ValueError("At least one secret key is required.")
        self._keys = keys
        self._active = order[0]

    def encrypt(self, plaintext: str, *, context: str) -> str:
        """`context` binds the ciphertext to its purpose (e.g. the owning row) as AAD."""
        nonce = os.urandom(12)
        ct = AESGCM(self._keys[self._active]).encrypt(nonce, plaintext.encode(), context.encode())
        return f"{self._active}:{base64.urlsafe_b64encode(nonce + ct).decode()}"

    def decrypt(self, value: str, *, context: str) -> str:
        key_id, _, payload = value.partition(":")
        raw = base64.urlsafe_b64decode(payload)
        return AESGCM(self._keys[key_id]).decrypt(raw[:12], raw[12:], context.encode()).decode()
