from unittest.mock import patch
from scripts.graph.mail_folder import (
    find_folder_id,
    find_message_by_subject,
    post_message,
    with_failure_banner,
)


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


def test_post_message_sends_to_folder_endpoint_when_the_day_has_no_message_yet():
    with patch("scripts.graph.mail_folder.graph_get", return_value={"value": []}),          patch("scripts.graph.mail_folder.graph_post", return_value={"id": "msg-1"}) as mock_post:
        result = post_message("folder-id", "Subject", "Body text", token="t")
        assert result == {"id": "msg-1"}
        path_arg = mock_post.call_args[0][0]
        assert path_arg == "/me/mailFolders/folder-id/messages"


def test_a_retry_updates_the_days_message_instead_of_adding_a_second():
    """The duplicate-bulletin bug. Every run from 2026-09-23 to 2026-09-30
    failed its first attempt and was retried, and each retry posted another
    copy: two messages on 23, 24 and 30 September, three on 25 September."""
    with patch("scripts.graph.mail_folder.graph_get",
               return_value={"value": [{"id": "already-there", "subject": "AI Brief — 2026-09-30"}]}),          patch("scripts.graph.mail_folder.graph_post") as mock_post,          patch("scripts.graph.mail_folder.graph_patch", return_value={"id": "already-there"}) as mock_patch:
        result = post_message("folder-id", "AI Brief — 2026-09-30", "The good copy", token="t")

    mock_post.assert_not_called(), "a retry must never create a second message"
    assert result == {"id": "already-there"}
    assert mock_patch.call_args[0][0] == "/me/messages/already-there"
    assert mock_patch.call_args[0][1]["body"]["content"] == "The good copy"


def test_post_message_never_deletes_anything():
    """Nothing in this pipeline is allowed to remove Nick's mail. Overwriting
    an unsent draft in place is the whole mechanism."""
    import scripts.graph._common as common

    assert not hasattr(common, "graph_delete")


def test_find_message_by_subject_escapes_quotes_for_the_odata_filter():
    captured = {}

    def fake_get(path, token, params=None):
        captured.update(params)
        return {"value": []}

    with patch("scripts.graph.mail_folder.graph_get", side_effect=fake_get):
        assert find_message_by_subject("folder-id", "Nick's Brief", token="t") is None

    assert captured["$filter"] == "subject eq 'Nick''s Brief'"


def test_with_failure_banner_prepends_when_failures_present():
    body = "# The Brief\n\nContent here."
    result = with_failure_banner(body, ["TTS render failed"])
    assert result.startswith("**")
    assert "TTS render failed" in result
    assert result.endswith(body)


def test_with_failure_banner_returns_body_unchanged_when_no_failures():
    body = "# The Brief\n\nContent here."
    assert with_failure_banner(body, []) == body
