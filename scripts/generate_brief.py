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


MARKER_MD = "===BRIEF_MD==="
MARKER_JSON = "===BRIEF_JSON==="
MARKER_AUDIO = "===AUDIO_TXT==="


def parse_three_files(raw_text: str) -> dict:
    """Split the model's single response into its three constituent files.

    Raises RuntimeError (never a bare IndexError) if a marker is missing,
    duplicated, or out of order — this feeds an unattended daily pipeline, so a
    malformed response must fail loudly rather than silently drop content.
    """
    for marker in (MARKER_MD, MARKER_JSON, MARKER_AUDIO):
        count = raw_text.count(marker)
        if count != 1:
            raise RuntimeError(
                f"Expected marker '{marker}' exactly once in the response, "
                f"found {count} times"
            )

    md_pos = raw_text.index(MARKER_MD)
    json_pos = raw_text.index(MARKER_JSON)
    audio_pos = raw_text.index(MARKER_AUDIO)

    if not (md_pos < json_pos < audio_pos):
        raise RuntimeError(
            "Markers found out of expected order — expected "
            f"{MARKER_MD} before {MARKER_JSON} before {MARKER_AUDIO}"
        )

    brief_md = raw_text[md_pos + len(MARKER_MD):json_pos]
    brief_json = raw_text[json_pos + len(MARKER_JSON):audio_pos]
    audio_txt = raw_text[audio_pos + len(MARKER_AUDIO):]

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
