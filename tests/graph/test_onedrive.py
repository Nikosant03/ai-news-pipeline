from unittest.mock import patch
from scripts.graph.onedrive import ensure_folder, upload_file
from scripts.graph._common import GraphError


def test_ensure_folder_returns_existing_id():
    with patch("scripts.graph.onedrive.graph_get", return_value={"id": "abc123"}):
        assert ensure_folder("/DAILY_AI_NEWS/2026/09", token="t") == "abc123"


def test_ensure_folder_creates_when_missing():
    calls = []

    def fake_get(path, token, params=None):
        calls.append(("get", path))
        raise GraphError("GET -> HTTP 404: not found")

    def fake_post(path, payload, token):
        calls.append(("post", path))
        return {"id": "new-id"}

    with patch("scripts.graph.onedrive.graph_get", side_effect=fake_get), \
         patch("scripts.graph.onedrive.graph_post", side_effect=fake_post):
        folder_id = ensure_folder("/DAILY_AI_NEWS/2026/09", token="t")
    assert folder_id == "new-id"
    assert any(call[0] == "post" for call in calls)


def test_upload_file_puts_content_with_type():
    with patch(
        "scripts.graph.onedrive.graph_get",
        return_value={"id": "folder-1"},
    ), patch(
        "scripts.graph.onedrive.graph_put_bytes",
        return_value={"id": "file-1", "size": 5},
    ) as mock_put:
        result = upload_file(
            "/DAILY_AI_NEWS/2026/09", "brief.md", b"hello", "text/markdown", token="t"
        )
        assert result == {"id": "file-1", "size": 5}
        path_arg = mock_put.call_args[0][0]
        assert "brief.md" in path_arg
