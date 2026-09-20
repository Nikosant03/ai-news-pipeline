"""The daily entrypoint. Ordering is not arbitrary: the token refresh+commit is
first and unconditional (design spec §6); everything after it is wrapped so one
component's failure doesn't stop the others, and is reported two ways — a banner
on the mail message if it's still being built, and a non-zero exit code always."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from scripts import generate_brief, publish_feed, publish_release, render_audio, token_state
from scripts.graph import mail_folder, onedrive

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPO = "Nikosant03/daily-ai-brief-feed"
# tempfile.gettempdir() resolves to /tmp on the ubuntu-latest GH Actions runner —
# identical to a hardcoded "/tmp" there — but also works on a Windows dev machine,
# where a bare "/tmp" is not a real path.
PUBLIC_REPO_CLONE_PATH = Path(tempfile.gettempdir()) / "daily-ai-brief-feed"
MAIL_FOLDER_NAME = "DAILY_AI_NEWS"
ONEDRIVE_ROOT = "/DAILY_AI_NEWS"


def run(today: str | None = None) -> int:
    today = today or date.today().isoformat()
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
        brief = generate_brief.generate_brief(
            system_prompt=(REPO_ROOT / "prompts" / "system-prompt.md").read_text(encoding="utf-8"),
            today=today,
            previous_json=None,  # Task 16 follow-up: read yesterday's JSON via onedrive.py
            model=os.environ.get("ANTHROPIC_MODEL"),  # unset -> generate_brief's own default
        )
    except Exception as exc:
        print(f"FATAL: brief generation failed: {exc}", file=sys.stderr)
        return 1

    audio_path = Path(tempfile.gettempdir()) / f"{today}.mp3"
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
        # publish_episode (GitHub Release API), and build_feed_xml/clone_repo/push_feed
        # (local git operations) fail for very different reasons — grouped into two
        # try/excepts, not one, so the failure list names which step actually broke.
        pat = os.environ.get("PUBLIC_REPO_PUSH_TOKEN")
        if pat is None:
            failures.append("release publish failed: PUBLIC_REPO_PUSH_TOKEN is not set")
        else:
            assets = None
            try:
                assets = publish_release.publish_episode(audio_path, today, token=pat, repo=PUBLIC_REPO)
            except Exception as exc:
                failures.append(f"release publish failed: {exc}")

            if assets is not None:
                try:
                    xml = publish_feed.build_feed_xml(
                        assets,
                        feed_title="Daily AI Brief",
                        feed_link=f"https://{PUBLIC_REPO.split('/')[0]}.github.io/daily-ai-brief-feed/",
                    )
                    publish_feed.clone_repo(PUBLIC_REPO, token=pat, dest=PUBLIC_REPO_CLONE_PATH)
                    publish_feed.push_feed(xml, PUBLIC_REPO_CLONE_PATH)
                except Exception as exc:
                    failures.append(f"feed clone/push failed: {exc}")

    if failures:
        print("FAILURES THIS RUN:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
