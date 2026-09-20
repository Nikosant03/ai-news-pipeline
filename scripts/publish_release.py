"""Upload the day's mp3 as a GitHub Release asset on daily-ai-brief-feed, and drop
whichever assets have aged out past the 30-episode window. Filenames are
YYYY-MM-DD.mp3, so lexicographic sort is chronological sort."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

RELEASE_TAG = "episodes"
GITHUB_API = "https://api.github.com"


def assets_to_delete(existing_names: list[str], keep: int = 30) -> list[str]:
    ordered = sorted(existing_names)
    if len(ordered) <= keep:
        return []
    return ordered[: len(ordered) - keep]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _get_release_id(token: str, repo: str) -> int:
    req = urllib.request.Request(
        f"{GITHUB_API}/repos/{repo}/releases/tags/{RELEASE_TAG}", headers=_headers(token)
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["id"]


def _list_assets(release_id: int, token: str, repo: str) -> list[dict]:
    req = urllib.request.Request(
        f"{GITHUB_API}/repos/{repo}/releases/{release_id}/assets", headers=_headers(token)
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _upload_asset(release_id: int, filename: str, content: bytes, token: str, repo: str) -> dict:
    headers = _headers(token)
    headers["Content-Type"] = "audio/mpeg"
    upload_url = f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name={filename}"
    req = urllib.request.Request(upload_url, data=content, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _delete_asset(asset_id: int, token: str, repo: str) -> None:
    req = urllib.request.Request(
        f"{GITHUB_API}/repos/{repo}/releases/assets/{asset_id}",
        headers=_headers(token),
        method="DELETE",
    )
    urllib.request.urlopen(req, timeout=30)


def publish_episode(mp3_path: Path, date: str, token: str, repo: str) -> list[dict]:
    release_id = _get_release_id(token, repo)
    _upload_asset(release_id, f"{date}.mp3", mp3_path.read_bytes(), token, repo)

    current_assets = _list_assets(release_id, token, repo)
    names_to_ids = {a["name"]: a["id"] for a in current_assets}

    for stale_name in assets_to_delete(list(names_to_ids.keys())):
        _delete_asset(names_to_ids[stale_name], token=token, repo=repo)

    return [a for a in current_assets if a["name"] not in assets_to_delete(list(names_to_ids.keys()))]
