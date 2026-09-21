"""The daily entrypoint. Reads a brief the caller has ALREADY written to
output/ (see below) rather than generating one itself — the ai-news-pipeline
routine writes those files directly, using its own web-research and Write
tools, before invoking this script; nothing here calls the Anthropic API,
deliberately (see decisions/log.md, 2026-09-20 — no API key, ever).

Ordering is not arbitrary: the token refresh+commit is first and
unconditional (design spec §6); everything after it is wrapped so one
component's failure doesn't stop the others, and is reported two ways — a
banner on the mail message if it's still being built, and a non-zero exit
code always."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

from scripts import publish_feed, render_audio, token_state
from scripts.graph import mail_folder, onedrive

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPO = "Nikosant03/daily-ai-brief-feed"
OUTPUT_DIR = REPO_ROOT / "output"
PUBLIC_REPO_CLONE_PATH = REPO_ROOT.parent / "daily-ai-brief-feed-clone"
MAIL_FOLDER_NAME = "DAILY_AI_NEWS"
ONEDRIVE_ROOT = "/DAILY_AI_NEWS"


def _read_brief(output_dir: Path) -> dict:
    """Read the three files the routine already wrote to output/. Raises with
    a clear message naming which file is missing, rather than a bare
    FileNotFoundError, if the routine's writing step didn't run or failed."""
    missing = [
        name
        for name in ("brief.md", "brief.json", "audio.txt")
        if not (output_dir / name).exists()
    ]
    if missing:
        raise RuntimeError(
            f"output/ is missing {', '.join(missing)} — the routine must write "
            "all three files before running this script"
        )
    return {
        "brief_md": (output_dir / "brief.md").read_text(encoding="utf-8"),
        "brief_json": (output_dir / "brief.json").read_text(encoding="utf-8"),
        "audio_txt": (output_dir / "audio.txt").read_text(encoding="utf-8"),
    }


def run(today: str | None = None, output_dir: Path | None = None) -> int:
    today = today or date.today().isoformat()
    output_dir = output_dir or OUTPUT_DIR
    failures: list[str] = []

    try:
        access_token = token_state.refresh_and_persist_token()
    except Exception as exc:
        # Broadened from `except TokenPersistError` — that left a bare RuntimeError
        # (malformed Microsoft response), a KeyError (unset env var), or a network
        # error to propagate uncaught, breaking the run(...) -> int contract this
        # function promises everywhere else.
        print(f"FATAL: token refresh/persist failed: {exc}", file=sys.stderr)
        return 1

    try:
        brief = _read_brief(output_dir)
    except Exception as exc:
        print(f"FATAL: reading the written brief failed: {exc}", file=sys.stderr)
        return 1

    audio_path = output_dir / f"{today}-audio.mp3"
    try:
        voice = os.environ.get("EDGE_TTS_VOICE", "en-US-AndrewNeural")
        render_audio.render_audio(brief["audio_txt"], audio_path, voice=voice)
        if not audio_path.exists():
            # edge-tts has a documented failure mode of returning normally without
            # producing a usable file. Without this check that silent no-op would
            # be indistinguishable from success: nothing gets appended to
            # `failures`, and every `if audio_path.exists():` branch below just
            # skips quietly — the run could exit 0 with no banner and no failure
            # email, violating the design spec's §9 requirement that any
            # component failure produces a non-zero exit.
            raise RuntimeError("audio render produced no output file")
    except Exception as exc:
        failures.append(f"audio render failed: {exc}")

    year, month = today[:4], today[5:7]
    onedrive_folder = f"{ONEDRIVE_ROOT}/{year}/{month}"
    for filename, content, content_type in (
        (f"{today}-brief.md", brief["brief_md"].encode("utf-8"), "text/markdown"),
        (f"{today}-brief.json", brief["brief_json"].encode("utf-8"), "application/json"),
        (f"{today}-audio.txt", brief["audio_txt"].encode("utf-8"), "text/plain"),
    ):
        try:
            onedrive.upload_file(onedrive_folder, filename, content, content_type, token=access_token)
        except Exception as exc:
            failures.append(f"OneDrive upload of {filename} failed: {exc}")

    if audio_path.exists():
        try:
            onedrive.upload_file(
                onedrive_folder, f"{today}-audio.mp3", audio_path.read_bytes(), "audio/mpeg", token=access_token
            )
        except Exception as exc:
            failures.append(f"OneDrive upload of audio failed: {exc}")

    # Lookup and post are split into their own try/except blocks — sharing one
    # meant a lookup failure got reported as "mail message creation failed",
    # even though no message was ever attempted.
    folder_id = None
    try:
        folder_id = mail_folder.find_folder_id(MAIL_FOLDER_NAME, token=access_token)
    except Exception as exc:
        failures.append(f"mail folder lookup failed: {exc}")

    if folder_id is not None:
        try:
            body = mail_folder.with_failure_banner(brief["brief_md"], failures)
            mail_folder.post_message(folder_id, f"AI Brief — {today}", body, token=access_token)
        except Exception as exc:
            failures.append(f"mail message creation failed: {exc}")
    elif not any(f.startswith("mail folder lookup failed") for f in failures):
        failures.append(f"mail folder '{MAIL_FOLDER_NAME}' not found")

    if audio_path.exists():
        # Staging (a git push) rather than a direct GitHub Release API call --
        # the sandbox's egress proxy blocks binary POST bodies to
        # uploads.github.com (see publish_feed.py's module docstring). The
        # actual release upload and feed.xml rebuild happen in
        # daily-ai-brief-feed's own publish-episode.yml, triggered by this push.
        pat = os.environ.get("PUBLIC_REPO_PUSH_TOKEN")
        if pat is None:
            failures.append("episode staging failed: PUBLIC_REPO_PUSH_TOKEN is not set")
        else:
            try:
                publish_feed.clone_repo(PUBLIC_REPO, token=pat, dest=PUBLIC_REPO_CLONE_PATH)
                publish_feed.stage_pending_episode(audio_path, today, PUBLIC_REPO_CLONE_PATH)
            except Exception as exc:
                failures.append(f"episode staging failed: {exc}")

    if failures:
        print("FAILURES THIS RUN:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
