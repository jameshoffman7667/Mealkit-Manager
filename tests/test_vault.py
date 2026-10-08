import pytest

from app import vault


def test_round_trip(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a-long-enough-secret-key")
    token = vault.encrypt("me@example.com", "pa55 word")
    assert "pa55" not in token and "example.com" not in token
    assert vault.decrypt(token) == ("me@example.com", "pa55 word")


def test_refuses_without_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert not vault.configured()
    with pytest.raises(vault.VaultError):
        vault.encrypt("a@b.c", "x")
    monkeypatch.setenv("SECRET_KEY", "short")
    assert not vault.configured()


def test_changed_key_cannot_decrypt(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "first-secret-key-value")
    token = vault.encrypt("a@b.c", "x")
    monkeypatch.setenv("SECRET_KEY", "second-secret-key-value")
    with pytest.raises(vault.VaultError):
        vault.decrypt(token)
