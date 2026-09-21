"""Stage the day's mp3 into the public daily-ai-brief-feed repo for its own
GitHub Actions workflow to publish.

This used to call the GitHub REST API directly (upload the mp3 as a release
asset, then rebuild feed.xml) from inside this process. That broke
permanently once run from a Claude Code cloud routine: the sandbox's own
egress proxy rejects binary (non-JSON) POST bodies to uploads.github.com with
an HTTP 415 whose error body points at Anthropic's own docs, not GitHub's --
confirmed 2026-09-21, see decisions/log.md. A plain `git push` is not subject
to that restriction, so the release upload and feed.xml rebuild now happen in
daily-ai-brief-feed's own `.github/workflows/publish-episode.yml`, triggered
by the push this module makes."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(args: list[str], error_message: str) -> None:
    """Run a git subprocess call, raising a sanitized error on failure.

    subprocess.CalledProcessError's string form includes the full argv it was given —
    for `git clone` that argv embeds the raw PAT in the clone URL. A bare `except
    Exception as exc: print(str(exc))` upstream (Task 16's orchestrator) would then
    print the token in cleartext. GitHub Actions masks known secrets in its own log
    output, but that is a platform backstop, not something this code should depend on
    — a local run, a different CI, or a future refactor has no such masking. So on
    failure we swallow the original exception (`from None` — its traceback also
    carries the argv) and raise a message-only error instead. Every git call in this
    module goes through this helper, not just `clone`, because a future change to how
    the remote is configured (e.g. an explicit push URL) could put the token back into
    some other call's argv without this file being touched again.
    """
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError:
        raise RuntimeError(error_message) from None


def clone_repo(repo: str, token: str, dest: Path) -> None:
    """Fresh clone every run — the runner is ephemeral, dest never pre-exists."""
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    _run_git(["git", "clone", "--depth", "1", url, str(dest)], "git clone failed")
    _run_git(
        ["git", "-C", str(dest), "config", "user.name", "ai-news-pipeline bot"],
        "git config user.name failed",
    )
    _run_git(
        ["git", "-C", str(dest), "config", "user.email", "actions@users.noreply.github.com"],
        "git config user.email failed",
    )


def stage_pending_episode(mp3_path: Path, date: str, repo_path: Path) -> None:
    """Commit the day's mp3 to pending/<date>.mp3 in the already-cloned repo
    and push. The push (to a path matching the workflow's `paths` trigger) is
    what fires publish-episode.yml, which uploads the asset, prunes anything
    aged out past the 30-episode window, and rebuilds feed.xml.

    Pushes with an explicit `HEAD:main` refspec, not a bare `git push` --
    confirmed 2026-09-21 that a bare push from inside a Claude Code cloud
    routine lands on a new `claude/*` branch instead of main (same fix
    token_state.py already needed for the same reason; see its comment).
    A commit that never reaches main never fires the workflow."""
    dest = repo_path / "pending" / f"{date}.mp3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(mp3_path.read_bytes())
    _run_git(["git", "-C", str(repo_path), "add", f"pending/{date}.mp3"], "git add failed")
    _run_git(
        ["git", "-C", str(repo_path), "commit", "-m", f"chore: stage {date} episode"],
        "git commit failed",
    )
    _run_git(["git", "-C", str(repo_path), "push", "origin", "HEAD:main"], "git push failed")
