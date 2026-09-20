"""Build feed.xml from the CURRENT release asset list — never from a separately
tracked counter — so it mechanically cannot reference an episode that doesn't
exist. See design spec §5."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CYPRUS = ZoneInfo("Asia/Nicosia")


def _rfc822_date(name: str) -> str:
    date_part = name.removesuffix(".mp3")
    dt = datetime.strptime(date_part, "%Y-%m-%d").replace(hour=7, tzinfo=CYPRUS)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def build_feed_xml(assets: list[dict], feed_title: str, feed_link: str) -> str:
    ordered = sorted(assets, key=lambda a: a["name"], reverse=True)
    items = []
    for asset in ordered:
        date_part = asset["name"].removesuffix(".mp3")
        items.append(
            f"""    <item>
      <title>AI Brief — {date_part}</title>
      <enclosure url="{asset['browser_download_url']}" length="{asset['size']}" type="audio/mpeg"/>
      <pubDate>{_rfc822_date(asset['name'])}</pubDate>
      <guid>{asset['name']}</guid>
    </item>"""
        )
    items_xml = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{feed_title}</title>
    <link>{feed_link}</link>
    <description>Daily AI news bulletin.</description>
{items_xml}
  </channel>
</rss>
"""


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


def push_feed(xml_content: str, repo_path: Path) -> None:
    (repo_path / "feed.xml").write_text(xml_content, encoding="utf-8")
    _run_git(["git", "-C", str(repo_path), "add", "feed.xml"], "git add failed")
    _run_git(
        ["git", "-C", str(repo_path), "commit", "-m", "chore: update feed.xml"],
        "git commit failed",
    )
    _run_git(["git", "-C", str(repo_path), "push"], "git push failed")
