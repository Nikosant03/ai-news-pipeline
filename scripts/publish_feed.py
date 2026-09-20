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


def clone_repo(repo: str, token: str, dest: Path) -> None:
    """Fresh clone every run — the runner is ephemeral, dest never pre-exists."""
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "config", "user.name", "ai-news-pipeline bot"], check=True)
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.email", "actions@users.noreply.github.com"],
        check=True,
    )


def push_feed(xml_content: str, repo_path: Path) -> None:
    (repo_path / "feed.xml").write_text(xml_content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_path), "add", "feed.xml"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", "chore: update feed.xml"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_path), "push"], check=True)
