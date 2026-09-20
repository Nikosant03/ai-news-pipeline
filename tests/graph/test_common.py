from unittest.mock import patch, MagicMock
import json
from scripts.graph._common import graph_get, graph_post, GRAPH


def _fake_response(body: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_graph_get_sends_bearer_token():
    with patch("urllib.request.urlopen", return_value=_fake_response({"id": "123"})) as mock_open:
        result = graph_get("/me", token="fake-token")
        assert result == {"id": "123"}
        sent_request = mock_open.call_args[0][0]
        assert sent_request.get_header("Authorization") == "Bearer fake-token"
        assert sent_request.full_url == f"{GRAPH}/me"


def test_graph_post_sends_json_body():
    with patch("urllib.request.urlopen", return_value=_fake_response({"id": "456"})) as mock_open:
        result = graph_post("/me/messages", {"subject": "hi"}, token="fake-token")
        assert result == {"id": "456"}
        sent_request = mock_open.call_args[0][0]
        assert sent_request.get_header("Content-type") == "application/json"
