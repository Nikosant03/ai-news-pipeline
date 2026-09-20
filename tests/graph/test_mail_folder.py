from unittest.mock import patch
from scripts.graph.mail_folder import find_folder_id, post_message, with_failure_banner


def test_find_folder_id_checks_top_level_first():
    def fake_get(path, token, params=None):
        assert "$filter" in params
        if path == "/me/mailFolders":
            return {"value": [{"id": "top-level-id"}]}
        raise AssertionError("should not check childFolders when top level matched")

    with patch("scripts.graph.mail_folder.graph_get", side_effect=fake_get):
        assert find_folder_id("DAILY_AI_NEWS", token="t") == "top-level-id"


def test_find_folder_id_falls_back_to_inbox_children():
    calls = []

    def fake_get(path, token, params=None):
        calls.append(path)
        if path == "/me/mailFolders":
            return {"value": []}
        if path == "/me/mailFolders/inbox/childFolders":
            return {"value": [{"id": "child-id"}]}
        raise AssertionError(f"unexpected path {path}")

    with patch("scripts.graph.mail_folder.graph_get", side_effect=fake_get):
        assert find_folder_id("DAILY_AI_NEWS", token="t") == "child-id"
    assert calls == ["/me/mailFolders", "/me/mailFolders/inbox/childFolders"]


def test_find_folder_id_returns_none_when_missing():
    with patch("scripts.graph.mail_folder.graph_get", return_value={"value": []}):
        assert find_folder_id("NOPE", token="t") is None


def test_post_message_sends_to_folder_endpoint():
    with patch(
        "scripts.graph.mail_folder.graph_post", return_value={"id": "msg-1"}
    ) as mock_post:
        result = post_message("folder-id", "Subject", "Body text", token="t")
        assert result == {"id": "msg-1"}
        path_arg = mock_post.call_args[0][0]
        assert path_arg == "/me/mailFolders/folder-id/messages"


def test_with_failure_banner_prepends_when_failures_present():
    body = "# The Brief\n\nContent here."
    result = with_failure_banner(body, ["TTS render failed"])
    assert result.startswith("**")
    assert "TTS render failed" in result
    assert result.endswith(body)


def test_with_failure_banner_returns_body_unchanged_when_no_failures():
    body = "# The Brief\n\nContent here."
    assert with_failure_banner(body, []) == body
