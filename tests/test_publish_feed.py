import subprocess
from unittest.mock import patch

import pytest

from scripts.publish_feed import clone_repo, stage_pending_episode


def test_clone_repo_embeds_token_in_url_not_printed_elsewhere(tmp_path):
    dest = tmp_path / "cloned"
    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        clone_repo("owner/daily-ai-brief-feed", token="secret-pat", dest=dest)
    clone_call = mock_run.call_args_list[0]
    cloned_url = clone_call[0][0][4]  # ["git", "clone", "--depth", "1", url, dest]
    assert "secret-pat" in cloned_url
    assert cloned_url.startswith("https://x-access-token:")


def test_clone_repo_failure_does_not_leak_token_in_exception(tmp_path):
    dest = tmp_path / "cloned"
    failing_cmd = ["git", "clone", "--depth", "1", "https://x-access-token:secret-pat@github.com/owner/repo.git", str(dest)]
    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(returncode=128, cmd=failing_cmd)
        with pytest.raises(Exception) as exc_info:
            clone_repo("owner/repo", token="secret-pat", dest=dest)
    assert not isinstance(exc_info.value, subprocess.CalledProcessError)
    assert "secret-pat" not in str(exc_info.value)
    assert "secret-pat" not in repr(exc_info.value)


def test_stage_pending_episode_writes_and_commits_mp3(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    mp3_path = tmp_path / "2026-09-21-audio.mp3"
    mp3_path.write_bytes(b"fake mp3 bytes")

    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        stage_pending_episode(mp3_path, "2026-09-21", repo_path)

    assert (repo_path / "pending" / "2026-09-21.mp3").read_bytes() == b"fake mp3 bytes"
    called_args = [call[0][0] for call in mock_run.call_args_list]
    assert ["git", "-C", str(repo_path), "add", "pending/2026-09-21.mp3"] in called_args
    assert any(args[:4] == ["git", "-C", str(repo_path), "commit"] for args in called_args)
    assert ["git", "-C", str(repo_path), "push"] in called_args


def test_stage_pending_episode_failure_does_not_leak_token_in_exception(tmp_path):
    # The remote origin embeds the token (set up by clone_repo before this is
    # called) -- if a future change ever puts that URL back into this
    # function's own git argv, the same leak vector applies as clone_repo's.
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    mp3_path = tmp_path / "audio.mp3"
    mp3_path.write_bytes(b"fake mp3 bytes")
    failing_cmd = ["git", "-C", str(repo_path), "push", "https://x-access-token:secret-pat@github.com/owner/repo.git"]
    with patch("scripts.publish_feed.subprocess.run") as mock_run:
        mock_run.side_effect = [None, None, subprocess.CalledProcessError(returncode=1, cmd=failing_cmd)]
        with pytest.raises(Exception) as exc_info:
            stage_pending_episode(mp3_path, "2026-09-21", repo_path)
    assert not isinstance(exc_info.value, subprocess.CalledProcessError)
    assert "secret-pat" not in str(exc_info.value)
    assert "secret-pat" not in repr(exc_info.value)
