from cryptography.fernet import Fernet, InvalidToken
import pytest
from scripts.token_state import encrypt_token, decrypt_token


def test_round_trip():
    key = Fernet.generate_key()
    original = "a-fake-refresh-token-value"
    ciphertext = encrypt_token(original, key)
    assert ciphertext != original.encode()
    assert decrypt_token(ciphertext, key) == original


def test_wrong_key_fails():
    key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    ciphertext = encrypt_token("secret", key)
    with pytest.raises(InvalidToken):
        decrypt_token(ciphertext, wrong_key)


from unittest.mock import Mock, call
from scripts.token_state import refresh_and_persist_token, TokenPersistError


def test_commits_before_returning_access_token(monkeypatch, tmp_path):
    key = Fernet.generate_key()
    state_file = tmp_path / "ms_refresh_token.enc"
    state_file.write_bytes(encrypt_token("old-refresh-token", key))
    monkeypatch.setenv("STATE_ENCRYPTION_KEY", key.decode())
    monkeypatch.setenv("MS_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("MS_CLIENT_ID", "fake-client")

    call_order = []
    fake_ms_response = {"access_token": "new-access", "refresh_token": "new-refresh"}

    def fake_post_form(url, fields):
        call_order.append("ms_token_endpoint")
        return fake_ms_response

    def fake_committer(ciphertext: bytes) -> None:
        call_order.append("commit")

    access_token = refresh_and_persist_token(
        state_path=state_file,
        post_form=fake_post_form,
        committer=fake_committer,
    )

    assert access_token == "new-access"
    assert call_order == ["ms_token_endpoint", "commit"]
    # the file on disk now holds the NEW refresh token, encrypted
    assert decrypt_token(state_file.read_bytes(), key) == "new-refresh"


def test_commit_failure_raises_before_returning(monkeypatch, tmp_path):
    key = Fernet.generate_key()
    state_file = tmp_path / "ms_refresh_token.enc"
    state_file.write_bytes(encrypt_token("old-refresh-token", key))
    monkeypatch.setenv("STATE_ENCRYPTION_KEY", key.decode())
    monkeypatch.setenv("MS_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("MS_CLIENT_ID", "fake-client")

    def fake_post_form(url, fields):
        return {"access_token": "new-access", "refresh_token": "new-refresh"}

    def failing_committer(ciphertext: bytes) -> None:
        raise RuntimeError("git push failed")

    with pytest.raises(TokenPersistError):
        refresh_and_persist_token(
            state_path=state_file,
            post_form=fake_post_form,
            committer=failing_committer,
        )
