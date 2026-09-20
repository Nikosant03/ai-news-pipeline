from unittest.mock import MagicMock
from scripts.generate_brief import generate_brief, parse_three_files


def test_parse_three_files_splits_on_markers():
    raw = (
        "===BRIEF_MD===\n# Brief\ncontent\n"
        "===BRIEF_JSON===\n{\"date\": \"2026-09-20\"}\n"
        "===AUDIO_TXT===\nSpoken text here.\n"
    )
    result = parse_three_files(raw)
    assert result["brief_md"].strip() == "# Brief\ncontent"
    assert result["brief_json"].strip() == '{"date": "2026-09-20"}'
    assert result["audio_txt"].strip() == "Spoken text here."


def test_generate_brief_calls_api_with_web_search_tool():
    fake_client = MagicMock()
    fake_stream = MagicMock()
    fake_final_message = MagicMock()
    fake_final_message.content = [
        MagicMock(type="text", text=(
            "===BRIEF_MD===\n# B\n"
            "===BRIEF_JSON===\n{}\n"
            "===AUDIO_TXT===\nA\n"
        ))
    ]
    fake_stream.get_final_message.return_value = fake_final_message
    fake_stream.__enter__.return_value = fake_stream
    fake_client.messages.stream.return_value = fake_stream

    result = generate_brief(
        system_prompt="system text",
        today="2026-09-20",
        previous_json=None,
        client=fake_client,
    )

    assert result["brief_md"].strip() == "# B"
    call_kwargs = fake_client.messages.stream.call_args.kwargs
    tool_types = [t["type"] for t in call_kwargs["tools"]]
    assert "web_search_20260209" in tool_types
    assert call_kwargs["system"] == "system text"
