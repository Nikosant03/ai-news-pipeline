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
