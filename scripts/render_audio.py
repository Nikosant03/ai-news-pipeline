"""audio.txt -> mp3, via edge-tts (free, no API key, no quota)."""

from __future__ import annotations

import asyncio
import importlib
import ssl
import subprocess
import sys
from pathlib import Path


ATTEMPTS = 2


def _import_edge_tts():
    """Import edge_tts, installing it first if the sandbox hasn't got it.

    The routine's cloud sandbox ships with cryptography (the token refresh has
    never once failed) but not with edge-tts, and requirements.txt is plainly
    not being installed before this script runs: every run from 2026-09-23 to
    2026-09-30 failed its first attempt with ModuleNotFoundError. That made
    the script exit non-zero, which made the routine retry, and each retry
    wrote a second bulletin into the mail folder — which is why Nick was
    getting the same brief twice, and three times on 25 September.

    Installing on demand fixes that at the only layer this repository
    controls; the routine's own prompt lives on claude.ai and cannot be
    changed from here."""
    try:
        return importlib.import_module("edge_tts")
    except ModuleNotFoundError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "edge-tts>=6.1"],
            check=True,
        )
        importlib.invalidate_caches()
        return importlib.import_module("edge_tts")


def _real_synthesizer(text: str, output_path: Path, voice: str) -> None:
    edge_tts = _import_edge_tts()

    # edge-tts hardcodes a certifi-only SSL context for the websocket
    # connection that streams the audio, with no constructor argument or env
    # var to override it (a custom `connector` on Communicate does NOT apply,
    # since the websocket call passes its own `ssl=` that wins over the
    # connector). In a Claude Code cloud sandbox, outbound TLS is
    # re-terminated by a local proxy whose certificate is trusted by the OS
    # system store but not by certifi's vendored bundle, so the hardcoded
    # context fails verification there. Point it at the system default trust
    # store instead -- a superset in that environment, never a downgrade. If
    # a future edge-tts release renames or drops this private attribute, this
    # silently no-ops and the original certifi-only behavior applies.
    try:
        edge_tts.communicate._SSL_CTX = ssl.create_default_context()
    except AttributeError:
        pass

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    # One retry. On 2026-09-28 edge-tts raised NoAudioReceived ("No audio was
    # received") — Microsoft's endpoint accepted the connection and sent
    # nothing back. That is a remote hiccup, not a bad request: the identical
    # text rendered fine the next run. It also leaves a 0-byte file behind,
    # which is what reached the podcast feed and stalled it, so the failed
    # output is cleared before trying again.
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            asyncio.run(_run())
        except Exception as exc:
            last_error = exc
        if output_path.exists() and output_path.stat().st_size > 0:
            return
        if output_path.exists():
            output_path.unlink()
        if last_error is None and attempt == ATTEMPTS - 1:
            last_error = RuntimeError("edge-tts returned without writing any audio")
    raise RuntimeError(
        f"edge-tts produced no audio after {ATTEMPTS} attempts: {last_error}"
    )


def render_audio(
    text: str, output_path: Path, voice: str, synthesizer=None
) -> None:
    synth = synthesizer or _real_synthesizer
    synth(text, output_path, voice)
