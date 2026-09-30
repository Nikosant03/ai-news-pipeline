from unittest.mock import MagicMock
from pathlib import Path
from scripts.render_audio import render_audio


def test_render_audio_calls_synthesizer_with_text_and_voice(tmp_path):
    fake_synth = MagicMock()
    output = tmp_path / "episode.mp3"

    render_audio("Hello, this is the brief.", output, voice="en-US-AndrewNeural", synthesizer=fake_synth)

    fake_synth.assert_called_once()
    args, kwargs = fake_synth.call_args
    assert "Hello, this is the brief." in args or kwargs.get("text") == "Hello, this is the brief."


import sys
from unittest.mock import patch

import pytest

import scripts.render_audio as ra


def _writer(nbytes: int, output_path: Path):
    """Stand in for asyncio.run(communicate.save(...)), writing nbytes."""
    def _side_effect(coro):
        coro.close()          # we never await it; closing keeps pytest quiet
        output_path.write_bytes(b"x" * nbytes)
    return _side_effect


def test_edge_tts_is_installed_on_demand_when_the_sandbox_lacks_it(monkeypatch):
    """Every run from 2026-09-23 to 2026-09-30 failed its first attempt with
    ModuleNotFoundError, which is what triggered the retry that duplicated the
    bulletin email."""
    calls = []
    real_import = ra.importlib.import_module

    def flaky_import(name):
        if name == "edge_tts" and not calls:
            raise ModuleNotFoundError("No module named 'edge_tts'")
        return real_import("json")

    monkeypatch.setattr(ra.importlib, "import_module", flaky_import)
    monkeypatch.setattr(ra.subprocess, "run", lambda *a, **k: calls.append(a[0]))

    ra._import_edge_tts()

    assert calls, "a missing edge-tts must be installed, not left to fail the run"
    assert calls[0][:3] == [sys.executable, "-m", "pip"]
    assert any("edge-tts" in part for part in calls[0])


def test_a_render_that_returns_no_audio_raises_instead_of_leaving_an_empty_file(tmp_path):
    """2026-09-28: edge-tts raised NoAudioReceived and left a 0-byte mp3, which
    passed every existence check and stalled the public podcast feed."""
    output = tmp_path / "episode.mp3"

    def no_audio(coro):
        coro.close()
        output.write_bytes(b"")
        raise RuntimeError("No audio was received. Please verify that your parameters are correct.")

    with patch.object(ra, "_import_edge_tts"), \
         patch.object(ra.asyncio, "run", side_effect=no_audio):
        with pytest.raises(RuntimeError, match="no audio after 2 attempts"):
            ra._real_synthesizer("text", output, "en-US-AndrewNeural")

    assert not output.exists(), "the empty file must be cleared, never handed downstream"


def test_a_transient_failure_is_retried_and_succeeds(tmp_path):
    output = tmp_path / "episode.mp3"
    attempts = []

    def flaky(coro):
        coro.close()
        attempts.append(1)
        if len(attempts) == 1:
            output.write_bytes(b"")
            raise RuntimeError("No audio was received.")
        output.write_bytes(b"real mp3 bytes")

    with patch.object(ra, "_import_edge_tts"), \
         patch.object(ra.asyncio, "run", side_effect=flaky):
        ra._real_synthesizer("text", output, "en-US-AndrewNeural")

    assert len(attempts) == 2
    assert output.read_bytes() == b"real mp3 bytes"


def test_a_clean_render_does_not_retry(tmp_path):
    output = tmp_path / "episode.mp3"
    with patch.object(ra, "_import_edge_tts"), \
         patch.object(ra.asyncio, "run", side_effect=_writer(1234, output)) as mock_run:
        ra._real_synthesizer("text", output, "en-US-AndrewNeural")
    assert mock_run.call_count == 1
    assert output.stat().st_size == 1234
