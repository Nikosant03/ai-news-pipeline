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


import os
import json
import urllib.parse
import urllib.request

AUTHORITY = "https://login.microsoftonline.com"
SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Files.ReadWrite",
    "offline_access",
]


class TokenPersistError(RuntimeError):
    """The new refresh token could not be committed. Do not retry automatically —
    see the recovery steps in docs/superpowers/specs/2026-09-20-ai-news-pipeline-design.md, §6."""


def _default_post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_committer(ciphertext: bytes) -> None:
    import subprocess

    # The caller (refresh_and_persist_token) has already written `ciphertext`
    # to state_path before invoking the committer — this just stages, commits
    # and pushes the file that is already on disk.
    subprocess.run(["git", "add", str(STATE_PATH)], check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: rotate Microsoft refresh token"], check=True
    )
    subprocess.run(["git", "push"], check=True)


def refresh_and_persist_token(
    state_path: Path = STATE_PATH,
    post_form=_default_post_form,
    committer=_default_committer,
) -> str:
    key = os.environ["STATE_ENCRYPTION_KEY"].encode()
    tenant = os.environ["MS_TENANT_ID"]
    client_id = os.environ["MS_CLIENT_ID"]

    current_refresh_token = decrypt_token(state_path.read_bytes(), key)

    payload = post_form(
        f"{AUTHORITY}/{tenant}/oauth2/v2.0/token",
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": current_refresh_token,
            "scope": " ".join(SCOPES),
        },
    )

    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise RuntimeError(f"Microsoft's reply was missing a token: {payload}")

    new_ciphertext = encrypt_token(payload["refresh_token"], key)

    # Write the new refresh token to disk first (persist-first): even if the
    # git commit below fails, the encrypted file on disk already holds the
    # new token rather than the stale one.
    state_path.write_bytes(new_ciphertext)

    try:
        committer(new_ciphertext)
    except Exception as exc:
        raise TokenPersistError(
            "Token refreshed but could not be persisted — do not re-run "
            "automatically. See recovery steps in the design spec, §6."
        ) from exc

    return payload["access_token"]
