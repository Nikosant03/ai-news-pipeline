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
DEFAULT_VOICE_EN = "en-US-AndrewNeural"
# Nick chose Nestoras over Athina on 2026-10-01, after hearing both read the
# same bulletin: it matches the English edition's male voice, so the two
# editions sound like one programme rather than two.
DEFAULT_VOICE_EL = "el-GR-NestorasNeural"


def _usable_audio(path: Path) -> bool:
    """True only for an mp3 that actually has audio in it.

    Existence was never proof of success. edge-tts can return normally having
    created the output file and written nothing into it, and on 2026-09-28 it
    did: a 0-byte mp3 passed every `exists()` check below, was uploaded to
    OneDrive, was staged to the feed repo, and then killed that repo's publish
    workflow -- which aborted on the first bad file, so the good 2026-09-30
    episode queued behind it never published either. The podcast feed sat on
    2026-09-25 for three days and nothing in this script had recorded a
    failure. Size is the cheap check that closes it."""
    return path.exists() and path.stat().st_size > 0


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


def _read_greek(output_dir: Path) -> dict | None:
    """The Greek edition, if the routine wrote it.

    Optional on purpose. The routine's own prompt lives on claude.ai and is
    not updated by deploying this repository, so there will be at least one
    morning where this code expects Greek files that nothing has written yet.
    Missing files must not cost Nick the English bulletin he already relies on
    — but they are recorded as a failure, so a Greek edition that silently
    never appears cannot go unnoticed the way the empty mp3 did."""
    md = output_dir / "brief-el.md"
    txt = output_dir / "audio-el.txt"
    if not md.exists() and not txt.exists():
        return None
    missing = [f.name for f in (md, txt) if not f.exists()]
    if missing:
        raise RuntimeError(f"the Greek edition is incomplete — missing {', '.join(missing)}")
    return {
        "brief_md": md.read_text(encoding="utf-8"),
        "audio_txt": txt.read_text(encoding="utf-8"),
    }


def _render(text: str, path: Path, voice: str, label: str, failures: list[str]) -> Path | None:
    """Render one edition's audio. Returns the path only if it is usable."""
    try:
        render_audio.render_audio(text, path, voice=voice)
        if not _usable_audio(path):
            # edge-tts has a documented failure mode of returning normally
            # without producing a usable file, and of raising while leaving an
            # empty one behind. Either way the run must record a failure, or it
            # exits 0 with no banner and no failure email — and on 2026-09-28
            # the empty file went all the way to the public podcast feed.
            raise RuntimeError(
                f"produced no usable output file (exists={path.exists()}, "
                f"bytes={path.stat().st_size if path.exists() else 0})"
            )
    except Exception as exc:
        failures.append(f"{label} audio render failed: {exc}")
        return None
    return path


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

    greek = None
    try:
        greek = _read_greek(output_dir)
        if greek is None:
            failures.append(
                "no Greek edition was written (output/brief-el.md and output/audio-el.txt)"
            )
    except Exception as exc:
        failures.append(f"reading the Greek edition failed: {exc}")

    audio_path = _render(
        brief["audio_txt"],
        output_dir / f"{today}-audio.mp3",
        os.environ.get("EDGE_TTS_VOICE", DEFAULT_VOICE_EN),
        "English",
        failures,
    )
    audio_path_el = None
    if greek is not None:
        audio_path_el = _render(
            greek["audio_txt"],
            output_dir / f"{today}-audio-el.mp3",
            os.environ.get("EDGE_TTS_VOICE_EL", DEFAULT_VOICE_EL),
            "Greek",
            failures,
        )

    year, month = today[:4], today[5:7]
    onedrive_folder = f"{ONEDRIVE_ROOT}/{year}/{month}"
    text_files = [
        (f"{today}-brief.md", brief["brief_md"].encode("utf-8"), "text/markdown"),
        (f"{today}-brief.json", brief["brief_json"].encode("utf-8"), "application/json"),
        (f"{today}-audio.txt", brief["audio_txt"].encode("utf-8"), "text/plain"),
    ]
    if greek is not None:
        # Nick asked for the Greek text as well as the audio: it is the raw
        # material he works from for LinkedIn and Instagram posts.
        text_files += [
            (f"{today}-brief-el.md", greek["brief_md"].encode("utf-8"), "text/markdown"),
            (f"{today}-audio-el.txt", greek["audio_txt"].encode("utf-8"), "text/plain"),
        ]
    for filename, content, content_type in text_files:
        try:
            onedrive.upload_file(onedrive_folder, filename, content, content_type, token=access_token)
        except Exception as exc:
            failures.append(f"OneDrive upload of {filename} failed: {exc}")

    for name, path in ((f"{today}-audio.mp3", audio_path), (f"{today}-audio-el.mp3", audio_path_el)):
        if path is None:
            continue
        try:
            onedrive.upload_file(
                onedrive_folder, name, path.read_bytes(), "audio/mpeg", token=access_token
            )
        except Exception as exc:
            failures.append(f"OneDrive upload of {name} failed: {exc}")

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
            # Both editions in the one message. A second message would undo the
            # one-per-day rule that 2026-10-01 put in, and Nick reads the Greek
            # text to draft posts from, so it needs to be where he already looks.
            full_body = brief["brief_md"]
            if greek is not None:
                separator = "\n\n" + "=" * 60 + "\n\n"
                full_body += separator + greek["brief_md"]
            body = mail_folder.with_failure_banner(full_body, failures)
            mail_folder.post_message(folder_id, f"AI Brief — {today}", body, token=access_token)
        except Exception as exc:
            failures.append(f"mail message creation failed: {exc}")
    elif not any(f.startswith("mail folder lookup failed") for f in failures):
        failures.append(f"mail folder '{MAIL_FOLDER_NAME}' not found")

    episodes = {}
    if audio_path is not None:
        episodes[today] = audio_path
    if audio_path_el is not None:
        episodes[f"{today}-el"] = audio_path_el

    if episodes:
        # Staging (a git push) rather than a direct GitHub Release API call --
        # the sandbox's egress proxy blocks binary POST bodies to
        # uploads.github.com (see publish_feed.py's module docstring). The
        # actual release upload and feed.xml rebuild happen in
        # daily-ai-brief-feed's own publish-episode.yml, triggered by this push.
        # Both editions go in ONE commit; see stage_pending_episodes.
        pat = os.environ.get("PUBLIC_REPO_PUSH_TOKEN")
        if pat is None:
            failures.append("episode staging failed: PUBLIC_REPO_PUSH_TOKEN is not set")
        else:
            try:
                publish_feed.clone_repo(PUBLIC_REPO, token=pat, dest=PUBLIC_REPO_CLONE_PATH)
                publish_feed.stage_pending_episodes(episodes, PUBLIC_REPO_CLONE_PATH)
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
