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
