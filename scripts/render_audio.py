"""audio.txt -> mp3, via edge-tts (free, no API key, no quota)."""

from __future__ import annotations

import asyncio
from pathlib import Path


def _real_synthesizer(text: str, output_path: Path, voice: str) -> None:
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    asyncio.run(_run())


def render_audio(
    text: str, output_path: Path, voice: str, synthesizer=None
) -> None:
    synth = synthesizer or _real_synthesizer
    synth(text, output_path, voice)
