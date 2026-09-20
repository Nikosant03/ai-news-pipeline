"""Encrypt/decrypt the Microsoft refresh token stored at state/ms_refresh_token.enc.

Never store this token in plaintext anywhere — not in a GitHub Secret (see the
design spec, §6, for why), not in a log line, not in a commit message.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "ms_refresh_token.enc"


def encrypt_token(plaintext: str, key: bytes) -> bytes:
    return Fernet(key).encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes, key: bytes) -> str:
    return Fernet(key).decrypt(ciphertext).decode("utf-8")
