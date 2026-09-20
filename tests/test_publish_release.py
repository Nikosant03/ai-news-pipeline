from unittest.mock import patch, MagicMock
from scripts.publish_release import assets_to_delete, publish_episode


def test_assets_to_delete_keeps_newest_30():
    names = [f"2026-08-{d:02d}.mp3" for d in range(1, 32)]  # 31 names
    assert len(names) == 31
    to_delete = assets_to_delete(names, keep=30)
    assert to_delete == ["2026-08-01.mp3"]


def test_assets_to_delete_returns_empty_under_the_limit():
    names = ["2026-09-18.mp3", "2026-09-19.mp3"]
    assert assets_to_delete(names, keep=30) == []


def test_publish_episode_uploads_then_deletes_aged_out_asset(tmp_path):
    mp3 = tmp_path / "2026-09-20.mp3"
    mp3.write_bytes(b"fake mp3 bytes")

    existing_assets = [
        {"id": i, "name": f"2026-08-{d:02d}.mp3"} for i, d in enumerate(range(1, 31), start=1)
    ]
    all_assets_after_upload = existing_assets + [{"id": 999, "name": "2026-09-20.mp3"}]

    with patch("scripts.publish_release._get_release_id", return_value=42) as mock_release_id, \
         patch("scripts.publish_release._list_assets", return_value=all_assets_after_upload) as mock_list, \
         patch("scripts.publish_release._upload_asset", return_value={"id": 999, "name": "2026-09-20.mp3"}) as mock_upload, \
         patch("scripts.publish_release._delete_asset") as mock_delete:
        result = publish_episode(mp3, "2026-09-20", token="t", repo="owner/daily-ai-brief-feed")

    mock_upload.assert_called_once()
    mock_delete.assert_called_once_with(1, token="t", repo="owner/daily-ai-brief-feed")  # id of 2026-08-01
    assert len(result) == 30
