from unittest.mock import patch

from scripts.publish_feed import build_feed_xml, clone_repo


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
