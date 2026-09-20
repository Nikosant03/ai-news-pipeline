"""Look up a mail folder by name and post a message directly into it — never
Drafts, never sent. Covered by Mail.ReadWrite; Mail.Send is not granted."""

from __future__ import annotations

import urllib.parse

from scripts.graph._common import graph_get, graph_post


def find_folder_id(display_name: str, token: str) -> str | None:
    filter_q = {"$filter": f"displayName eq '{display_name}'"}

    top_level = graph_get("/me/mailFolders", token=token, params=filter_q)
    if top_level.get("value"):
        return top_level["value"][0]["id"]

    children = graph_get(
        "/me/mailFolders/inbox/childFolders", token=token, params=filter_q
    )
    if children.get("value"):
        return children["value"][0]["id"]

    return None


def post_message(folder_id: str, subject: str, body: str, token: str) -> dict:
    message = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [],
    }
    return graph_post(f"/me/mailFolders/{folder_id}/messages", message, token=token)


def with_failure_banner(body: str, failures: list[str]) -> str:
    if not failures:
        return body
    banner = "**⚠ Partial delivery today — " + "; ".join(failures) + "**\n\n---\n\n"
    return banner + body
