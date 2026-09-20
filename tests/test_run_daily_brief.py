from unittest.mock import patch

from scripts.run_daily_brief import run


def _fake_render_audio(text, output_path, voice, synthesizer=None):
    """The real function writes a file; mocks that don't would leave
    audio_path.exists() False, silently skipping the whole publish branch below."""
    output_path.write_bytes(b"fake mp3 bytes")


def _write_output_files(output_dir):
    """Stand in for what the routine's own Write tool does before invoking
    run() — write the three files run() expects to already exist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "brief.md").write_text("# Brief", encoding="utf-8")
    (output_dir / "brief.json").write_text("{}", encoding="utf-8")
    (output_dir / "audio.txt").write_text("spoken text", encoding="utf-8")


def test_run_returns_zero_when_everything_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=_fake_render_audio), \
         patch("scripts.run_daily_brief.onedrive.upload_file", return_value={"id": "f1"}), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id", return_value="folder-1"), \
         patch("scripts.run_daily_brief.mail_folder.post_message", return_value={"id": "m1"}), \
         patch("scripts.run_daily_brief.publish_release.publish_episode", return_value=[]), \
         patch("scripts.run_daily_brief.publish_feed.build_feed_xml", return_value="<rss></rss>"), \
         patch("scripts.run_daily_brief.publish_feed.clone_repo") as mock_clone, \
         patch("scripts.run_daily_brief.publish_feed.push_feed") as mock_push:
        exit_code = run(today="2026-09-20", output_dir=output_dir)
    assert exit_code == 0
    mock_clone.assert_called_once()
    mock_push.assert_called_once()


def test_run_returns_nonzero_when_a_component_fails_but_still_posts_banner(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=RuntimeError("tts down")), \
         patch("scripts.run_daily_brief.onedrive.upload_file", return_value={"id": "f1"}), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id", return_value="folder-1"), \
         patch("scripts.run_daily_brief.mail_folder.post_message", return_value={"id": "m1"}) as mock_post, \
         patch("scripts.run_daily_brief.publish_release.publish_episode", return_value=[]), \
         patch("scripts.run_daily_brief.publish_feed.build_feed_xml", return_value="<rss></rss>"), \
         patch("scripts.run_daily_brief.publish_feed.push_feed"):
        exit_code = run(today="2026-09-20", output_dir=output_dir)
    assert exit_code != 0
    # post_message's signature is (folder_id, subject, body, token=...), so the
    # body is the third positional arg (index 2), not the second (index 1,
    # which is the subject line "AI Brief — <date>" and never contains the
    # failure text being asserted here).
    posted_body = mock_post.call_args[0][2]
    assert "tts down" in posted_body or "⚠" in posted_body


def test_run_stops_immediately_when_token_persist_fails(tmp_path):
    from scripts.token_state import TokenPersistError

    with patch(
        "scripts.run_daily_brief.token_state.refresh_and_persist_token",
        side_effect=TokenPersistError("could not persist"),
    ), patch("scripts.run_daily_brief.mail_folder.find_folder_id") as mock_lookup:
        # output/ is deliberately left empty — a token failure must stop before
        # anything ever tries to read it.
        exit_code = run(today="2026-09-20", output_dir=tmp_path / "output")
    assert exit_code != 0
    mock_lookup.assert_not_called()


def test_run_fatal_when_output_files_missing(tmp_path):
    """A routine that fails to write the brief must not proceed either --
    same FATAL-and-stop contract as a token failure, not a silent skip."""
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id") as mock_lookup:
        exit_code = run(today="2026-09-20", output_dir=tmp_path / "output")
    assert exit_code != 0
    mock_lookup.assert_not_called()
