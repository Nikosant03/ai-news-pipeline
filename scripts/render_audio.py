"""audio.txt -> mp3, via edge-tts (free, no API key, no quota)."""

from __future__ import annotations

import asyncio
import ssl
from pathlib import Path


def _real_synthesizer(text: str, output_path: Path, voice: str) -> None:
    import edge_tts

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

    asyncio.run(_run())


def render_audio(
    text: str, output_path: Path, voice: str, synthesizer=None
) -> None:
    synth = synthesizer or _real_synthesizer
    synth(text, output_path, voice)
