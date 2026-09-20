"""Calls the Anthropic API with the flattened ai-news-brief skill as system
prompt, web search enabled, and asks for all three output files in one response."""

from __future__ import annotations

import anthropic

DEFAULT_MODEL = "claude-opus-5"
MAX_TOKENS = 32000

USER_INSTRUCTIONS = """Generate today's AI news bulletin. Today's date is {today}.

{continuity}

Produce all three files from the skill (the written brief, the JSON, and the audio
script) in this single response, in exactly this order, each preceded by its own
marker line on its own line:

===BRIEF_MD===
(the full markdown brief here)
===BRIEF_JSON===
(the full JSON here, valid JSON, no markdown fences)
===AUDIO_TXT===
(the full spoken audio script here)
"""


def _continuity_text(previous_json: str | None) -> str:
    if previous_json is None:
        return "No previous bulletin was found — this is the first run. Use the last 24 hours as the window."
    return (
        "Yesterday's brief JSON is below for continuity. Don't repeat these "
        "stories unless there's a genuine update, in which case label it as one.\n\n"
        f"{previous_json}"
    )


def parse_three_files(raw_text: str) -> dict:
    parts = raw_text.split("===BRIEF_JSON===")
    brief_md = parts[0].split("===BRIEF_MD===", 1)[1]
    rest = parts[1].split("===AUDIO_TXT===")
    brief_json = rest[0]
    audio_txt = rest[1]
    return {
        "brief_md": brief_md.strip(),
        "brief_json": brief_json.strip(),
        "audio_txt": audio_txt.strip(),
    }


def generate_brief(
    system_prompt: str,
    today: str,
    previous_json: str | None,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
) -> dict:
    client = client or anthropic.Anthropic()
    model = model or DEFAULT_MODEL

    user_message = USER_INSTRUCTIONS.format(
        today=today, continuity=_continuity_text(previous_json)
    )

    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 25}],
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        final_message = stream.get_final_message()

    if final_message.stop_reason == "refusal":
        raise RuntimeError("Anthropic API refused the request — check stop_details.")

    text_blocks = [b.text for b in final_message.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(f"No text content in response, stop_reason={final_message.stop_reason}")

    return parse_three_files("".join(text_blocks))
