"""OneDrive folder/file operations, ported for headless use."""

from __future__ import annotations

from scripts.graph._common import GraphError, graph_get, graph_post, graph_put_bytes


def ensure_folder(path: str, token: str) -> str:
    """Return the folder's id, creating it (and any missing parent) if needed."""
    try:
        info = graph_get(f"/me/drive/root:{path}", token=token)
        return info["id"]
    except GraphError as err:
        if "HTTP 404" not in str(err):
            raise
        parent, name = path.rsplit("/", 1)
        parent_id = ensure_folder(parent, token=token) if parent else "root"
        parent_path = f"/me/drive/items/{parent_id}/children" if parent else "/me/drive/root/children"
        created = graph_post(
            parent_path,
            {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
            token=token,
        )
        return created["id"]


def upload_file(
    folder_path: str, filename: str, content: bytes, content_type: str, token: str
) -> dict:
    folder_id = ensure_folder(folder_path, token=token)
    return graph_put_bytes(
        f"/me/drive/items/{folder_id}:/{filename}:/content",
        content,
        token=token,
        content_type=content_type,
    )
