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


def _default_committer(ciphertext: bytes, state_path: Path = STATE_PATH) -> None:
    import subprocess

    # The caller (refresh_and_persist_token) has already written `ciphertext`
    # to state_path before invoking the committer — this just stages, commits
    # and pushes the file that is already on disk. `state_path` is bound to
    # whatever path refresh_and_persist_token was actually called with (see
    # the closure built there), never assumed to be the module-level default.
    subprocess.run(["git", "add", str(state_path)], check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: rotate Microsoft refresh token"], check=True
    )
    # Push straight to origin/main by ref, not a plain `git push` — each
    # routine run starts from a fresh clone on its own throwaway branch with
    # no upstream tracking, so a plain push either fails outright (no
    # upstream) or, once one is set, strands the rotated token on that
    # abandoned branch. Every session reads state/ms_refresh_token.enc from
    # main on its next clone, and Microsoft invalidates the previous refresh
    # token once it's used, so the rotated token MUST land on main every time
    # or the next run's decrypt succeeds but the refresh call fails with
    # invalid_grant.
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)


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

    # If the caller left `committer` as the default, bind it to the actual
    # `state_path` this call was given — never the module-level STATE_PATH —
    # so a custom state_path + default committer can never stage/commit the
    # wrong file. A caller-supplied committer (e.g. in tests) is used as-is
    # and still only ever receives the ciphertext.
    committer_fn = committer
    if committer_fn is _default_committer:
        committer_fn = lambda ciphertext: _default_committer(
            ciphertext, state_path=state_path
        )

    # Persist-first: writing to disk and committing to git are both part of
    # "persisting" the new token, so both are wrapped in the same try/except.
    # Any failure in either step — a bad disk write or a failed git commit —
    # must raise TokenPersistError, never a raw OSError/PermissionError, so a
    # caller catching TokenPersistError specifically (per the design spec's
    # documented recovery path) never misses a persistence failure.
    try:
        state_path.write_bytes(new_ciphertext)
        committer_fn(new_ciphertext)
    except Exception as exc:
        raise TokenPersistError(
            "Token refreshed but could not be persisted — do not re-run "
            "automatically. See recovery steps in the design spec, §6."
        ) from exc

    return payload["access_token"]
