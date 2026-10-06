from unittest.mock import patch

from scripts.run_daily_brief import run


def _fake_render_audio(text, output_path, voice, synthesizer=None):
    """The real function writes a file; mocks that don't would leave
    audio_path.exists() False, silently skipping the whole publish branch below."""
    output_path.write_bytes(b"fake mp3 bytes")


def _write_output_files(output_dir, greek=True):
    """Stand in for what the routine's own Write tool does before invoking
    run() — write the three files run() expects to already exist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "brief.md").write_text("# Brief", encoding="utf-8")
    (output_dir / "brief.json").write_text("{}", encoding="utf-8")
    (output_dir / "audio.txt").write_text("spoken text", encoding="utf-8")
    if greek:
        (output_dir / "brief-el.md").write_text("# Δελτίο", encoding="utf-8")
        (output_dir / "audio-el.txt").write_text("εκφωνημένο κείμενο", encoding="utf-8")


def test_run_returns_zero_when_everything_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=_fake_render_audio), \
         patch("scripts.run_daily_brief.onedrive.upload_file", return_value={"id": "f1"}), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id", return_value="folder-1"), \
         patch("scripts.run_daily_brief.mail_folder.post_message", return_value={"id": "m1"}), \
         patch("scripts.run_daily_brief.publish_feed.clone_repo") as mock_clone, \
         patch("scripts.run_daily_brief.publish_feed.stage_pending_episodes") as mock_stage:
        exit_code = run(today="2026-09-20", output_dir=output_dir)
    assert exit_code == 0
    mock_clone.assert_called_once()
    mock_stage.assert_called_once()


def test_run_returns_nonzero_when_a_component_fails_but_still_posts_banner(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=RuntimeError("tts down")), \
         patch("scripts.run_daily_brief.onedrive.upload_file", return_value={"id": "f1"}), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id", return_value="folder-1"), \
         patch("scripts.run_daily_brief.mail_folder.post_message", return_value={"id": "m1"}) as mock_post, \
         patch("scripts.run_daily_brief.publish_feed.clone_repo"), \
         patch("scripts.run_daily_brief.publish_feed.stage_pending_episodes"):
        exit_code = run(today="2026-09-20", output_dir=output_dir)
    assert exit_code != 0
    # post_message's signature is (folder_id, subject, body, token=...), so the
    # body is the third positional arg (index 2), not the second (index 1,
    # which is the subject line "AI Brief — <date>" and never contains the
    # failure text being asserted here).
    posted_body = mock_post.call_args[0][2]
    assert "tts down" in posted_body or "⚠" in posted_body


def test_a_dead_microsoft_side_no_longer_costs_the_podcast(monkeypatch, tmp_path):
    """A token failure is reported, and the episode still goes out.

    This replaces the old stop-on-the-spot rule (design spec §6). On 2026-10-06
    `cryptography` was unusable in the sandbox, the token step died, and the
    run ended there — so no episode reached the feed either, even though
    staging one needs nothing but a git push. OneDrive and the mail folder are
    the only parts that genuinely need the token, and only they are skipped.
    """
    from scripts.token_state import TokenPersistError

    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)
    with patch(
        "scripts.run_daily_brief.token_state.refresh_and_persist_token",
        side_effect=TokenPersistError("could not persist"),
    ), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=_fake_render_audio), \
         patch("scripts.run_daily_brief.onedrive.upload_file") as mock_upload, \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id") as mock_lookup, \
         patch("scripts.run_daily_brief.publish_feed.clone_repo"), \
         patch("scripts.run_daily_brief.publish_feed.stage_pending_episodes") as mock_stage:
        exit_code = run(today="2026-10-06", output_dir=output_dir)

    assert exit_code != 0, "the token failure must still be reported"
    mock_upload.assert_not_called()
    mock_lookup.assert_not_called()
    mock_stage.assert_called_once()
    assert set(mock_stage.call_args[0][0]) == {"2026-10-06", "2026-10-06-el"}


def test_run_fatal_when_output_files_missing(tmp_path):
    """A routine that fails to write the brief must not proceed either --
    same FATAL-and-stop contract as a token failure, not a silent skip."""
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id") as mock_lookup:
        exit_code = run(today="2026-09-20", output_dir=tmp_path / "output")
    assert exit_code != 0
    mock_lookup.assert_not_called()


def _render_empty_mp3(text, output_path, voice, synthesizer=None):
    """edge-tts's real silent-failure mode, reproduced: return normally having
    created the file and written nothing into it. This is what happened on
    2026-09-28 and it went undetected all the way to the public podcast feed."""
    output_path.write_bytes(b"")


def test_empty_mp3_is_a_failure_and_never_reaches_onedrive_or_the_feed(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)
    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="access-token"), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=_render_empty_mp3), \
         patch("scripts.run_daily_brief.onedrive.upload_file", return_value={"id": "f1"}) as mock_upload, \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id", return_value="folder-1"), \
         patch("scripts.run_daily_brief.mail_folder.post_message", return_value={"id": "m1"}) as mock_post, \
         patch("scripts.run_daily_brief.publish_feed.clone_repo") as mock_clone, \
         patch("scripts.run_daily_brief.publish_feed.stage_pending_episodes") as mock_stage:
        exit_code = run(today="2026-09-28", output_dir=output_dir)

    assert exit_code == 1, "a 0-byte render must be reported as a failure, not passed off as success"

    uploaded_names = [call.args[1] for call in mock_upload.call_args_list]
    assert "2026-09-28-audio.mp3" not in uploaded_names, "an empty mp3 must never reach OneDrive"
    assert "2026-09-28-brief.md" in uploaded_names, "the text brief must still be delivered"

    mock_clone.assert_not_called()
    mock_stage.assert_not_called()

    banner_body = mock_post.call_args.args[2]
    assert "audio render" in banner_body, "the mail message must carry the failure banner"


def _run_with_mocks(output_dir, today="2026-10-01"):
    """Run with every outside system mocked, returning what each one was given."""
    seen = {"voices": [], "uploads": [], "posts": [], "staged": None}

    def record_render(text, output_path, voice, synthesizer=None):
        seen["voices"].append(voice)
        output_path.write_bytes(b"fake mp3 bytes")

    def record_upload(folder, filename, content, content_type, token=None):
        seen["uploads"].append(filename)
        return {"id": filename}

    def record_post(folder_id, subject, body, token=None):
        seen["posts"].append(body)
        return {"id": "m1"}

    def record_stage(episodes, repo_path):
        seen["staged"] = dict(episodes)

    with patch("scripts.run_daily_brief.token_state.refresh_and_persist_token", return_value="tok"), \
         patch("scripts.run_daily_brief.render_audio.render_audio", side_effect=record_render), \
         patch("scripts.run_daily_brief.onedrive.upload_file", side_effect=record_upload), \
         patch("scripts.run_daily_brief.mail_folder.find_folder_id", return_value="folder-1"), \
         patch("scripts.run_daily_brief.mail_folder.post_message", side_effect=record_post), \
         patch("scripts.run_daily_brief.publish_feed.clone_repo"), \
         patch("scripts.run_daily_brief.publish_feed.stage_pending_episodes", side_effect=record_stage):
        seen["exit_code"] = run(today=today, output_dir=output_dir)
    return seen


def test_both_editions_are_delivered_to_onedrive(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)

    seen = _run_with_mocks(output_dir)

    assert seen["exit_code"] == 0
    assert set(seen["uploads"]) == {
        "2026-10-01-brief.md",
        "2026-10-01-brief.json",
        "2026-10-01-audio.txt",
        "2026-10-01-brief-el.md",
        "2026-10-01-audio-el.txt",
        "2026-10-01-audio.mp3",
        "2026-10-01-audio-el.mp3",
    }


def test_the_greek_edition_uses_the_greek_voice_nick_chose(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    monkeypatch.delenv("EDGE_TTS_VOICE", raising=False)
    monkeypatch.delenv("EDGE_TTS_VOICE_EL", raising=False)
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)

    seen = _run_with_mocks(output_dir)

    assert seen["voices"] == ["en-US-AndrewNeural", "el-GR-NestorasNeural"]


def test_both_episodes_are_staged_in_a_single_call(monkeypatch, tmp_path):
    """One commit, one push. Two pushes would fire the publish workflow twice
    and the second would be rejected as non-fast-forward."""
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)

    seen = _run_with_mocks(output_dir)

    assert sorted(seen["staged"]) == ["2026-10-01", "2026-10-01-el"]


def test_the_one_daily_message_carries_both_editions(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir)

    seen = _run_with_mocks(output_dir)

    assert len(seen["posts"]) == 1, "still one message a day, never one per language"
    body = seen["posts"][0]
    assert "# Brief" in body and "Δελτίο" in body


def test_a_missing_greek_edition_is_loud_but_never_costs_the_english_one(monkeypatch, tmp_path):
    """There will be a morning where the routine has not been told to write the
    Greek files yet. English must still be delivered, and the gap must show."""
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir, greek=False)

    seen = _run_with_mocks(output_dir)

    assert seen["exit_code"] == 1, "a silently missing Greek edition is how today's bug happened"
    assert "2026-10-01-brief.md" in seen["uploads"]
    assert "2026-10-01-audio.mp3" in seen["uploads"]
    assert sorted(seen["staged"]) == ["2026-10-01"]
    assert "no Greek edition" in seen["posts"][0]


def test_half_a_greek_edition_is_a_failure_not_a_guess(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_REPO_PUSH_TOKEN", "fake-pat")
    output_dir = tmp_path / "output"
    _write_output_files(output_dir, greek=False)
    (output_dir / "brief-el.md").write_text("# Δελτίο", encoding="utf-8")

    seen = _run_with_mocks(output_dir)

    assert seen["exit_code"] == 1
    assert "audio-el.txt" in seen["posts"][0]
    assert sorted(seen["staged"]) == ["2026-10-01"]
