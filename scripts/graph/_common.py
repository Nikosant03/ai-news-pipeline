"""Graph HTTP helpers. Every call takes an access token explicitly — this repo has
no .env; the token comes from token_state.refresh_and_persist_token()."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


def graph_get(path: str, token: str, params: dict | None = None) -> dict:
    url = f"{GRAPH}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raise GraphError(f"GET {path} -> HTTP {err.code}: {err.read().decode('utf-8', 'replace')}") from err


def graph_post(path: str, payload: dict, token: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{GRAPH}{path}", data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise GraphError(f"POST {path} -> HTTP {err.code}: {err.read().decode('utf-8', 'replace')}") from err


def graph_put_bytes(path: str, data: bytes, token: str, content_type: str) -> dict:
    req = urllib.request.Request(f"{GRAPH}{path}", data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raise GraphError(f"PUT {path} -> HTTP {err.code}: {err.read().decode('utf-8', 'replace')}") from err
