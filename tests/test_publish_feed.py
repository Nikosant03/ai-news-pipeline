import subprocess
from unittest.mock import patch

import pytest

from scripts.publish_feed import build_feed_xml, clone_repo, push_feed


def test_build_feed_xml_includes_every_asset():
    assets = [
        {"name": "2026-09-19.mp3", "browser_download_url": "https://x/2026-09-19.mp3", "size": 111},
        {"name": "2026-09-20.mp3", "browser_download_url": "https://x/2026-09-20.mp3", "size": 222},
    ]
    xml = build_feed_xml(assets, feed_title="Daily AI Brief", feed_link="https://x.github.io/feed/")
    assert xml.count("<item>") == 2
    assert "https://x/2026-09-20.mp3" in xml
    assert 'length="222"' in xml
    assert 'type="audio/mpeg"' in xml


def test_build_feed_xml_orders_newest_first():
    assets = [
        {"name": "2026-09-18.mp3", "browser_download_url": "u1", "size": 1},
        {"name": "2026-09-20.mp3", "browser_download_url": "u2", "size": 2},
        {"name": "2026-09-19.mp3", "browser_download_url": "u3", "size": 3},
    ]
    xml = build_feed_xml(assets, feed_title="T", feed_link="L")
    assert xml.index("2026-09-20") < xml.index("2026-09-19") < xml.index("2026-09-18")


def test_build_feed_xml_empty_assets_still_valid_shell():
    xml = build_feed_xml([], feed_title="T", feed_link="L")
    assert "<rss" in xml and "</rss>" in xml
    assert "<item>" not in xml


def test_clone_repo_embeds_token_in_url_not_printed_elsewhere(tmp_path):
    dest = tmp_path / "cloned"
    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        clone_repo("owner/daily-ai-brief-feed", token="secret-pat", dest=dest)
    clone_call = mock_run.call_args_list[0]
    cloned_url = clone_call[0][0][4]  # ["git", "clone", "--depth", "1", url, dest]
    assert "secret-pat" in cloned_url
    assert cloned_url.startswith("https://x-access-token:")


def test_clone_repo_failure_does_not_leak_token_in_exception(tmp_path):
    dest = tmp_path / "cloned"
    failing_cmd = ["git", "clone", "--depth", "1", "https://x-access-token:secret-pat@github.com/owner/repo.git", str(dest)]
    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(returncode=128, cmd=failing_cmd)
        with pytest.raises(Exception) as exc_info:
            clone_repo("owner/repo", token="secret-pat", dest=dest)
    assert not isinstance(exc_info.value, subprocess.CalledProcessError)
    assert "secret-pat" not in str(exc_info.value)
    assert "secret-pat" not in repr(exc_info.value)


def test_push_feed_failure_does_not_leak_token_in_exception(tmp_path):
    # push_feed's own argv never carries the token today, but the remote origin
    # was configured by clone_repo from a token-bearing URL — if `git push` ever
    # needs to reference that URL explicitly (e.g. a future change to how the
    # remote is set up), the same leak vector applies. This proves the wrapper
    # sanitizes on that shape of failure too, not just the one clone_repo hits now.
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    failing_cmd = ["git", "-C", str(repo_path), "push", "https://x-access-token:secret-pat@github.com/owner/repo.git"]
    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        mock_run.side_effect = [
            None,
            None,
            subprocess.CalledProcessError(returncode=1, cmd=failing_cmd),
        ]
        with pytest.raises(Exception) as exc_info:
            push_feed("<rss></rss>", repo_path)
    assert not isinstance(exc_info.value, subprocess.CalledProcessError)
    assert "secret-pat" not in str(exc_info.value)
    assert "secret-pat" not in repr(exc_info.value)
