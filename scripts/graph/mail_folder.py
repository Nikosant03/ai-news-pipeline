"""Look up a mail folder by name and post a message directly into it — never
Drafts, never sent. Covered by Mail.ReadWrite; Mail.Send is not granted."""

from __future__ import annotations

import urllib.parse

from scripts.graph._common import graph_get, graph_patch, graph_post


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


def find_message_by_subject(folder_id: str, subject: str, token: str) -> dict | None:
    """The message this script already wrote for the same day, if any."""
    escaped = subject.replace("'", "''")
    found = graph_get(
        f"/me/mailFolders/{folder_id}/messages",
        token=token,
        params={"$filter": f"subject eq '{escaped}'", "$select": "id,subject", "$top": 1},
    )
    values = found.get("value") or []
    return values[0] if values else None


def post_message(folder_id: str, subject: str, body: str, token: str) -> dict:
    """Write the day's bulletin into the folder — updating the day's existing
    message rather than adding a second one.

    The routine re-runs this script whenever it exits non-zero, and it exited
    non-zero every single day from 2026-09-23 to 2026-09-30 because edge-tts
    was missing from the sandbox on the first attempt. Each retry posted
    another bulletin, so Nick got the failure copy and then the good copy:
    two messages on 23, 24 and 30 September, three on 25 September. One
    message per day is the contract, and the newest attempt is the one worth
    keeping, so overwrite in place.

    Updating rather than deleting-and-reposting is deliberate: these are
    unsent drafts, PATCH replaces the body cleanly, and nothing of Nick's ever
    gets deleted by this pipeline."""
    existing = find_message_by_subject(folder_id, subject, token=token)
    if existing is not None:
        return graph_patch(
            f"/me/messages/{existing['id']}",
            {"body": {"contentType": "Text", "content": body}},
            token=token,
        )
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
