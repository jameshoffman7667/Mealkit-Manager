"""Encrypts service logins at rest with a key the operator supplies (SECRET_KEY).

The key is stretched with PBKDF2 and used with Fernet (AES-128-CBC + HMAC). Without the key a stored
login cannot be read, so losing or changing SECRET_KEY means logins must be entered again.
"""
import base64
import hashlib
import json
from functools import lru_cache

from . import config

MIN_KEY_LEN = 16


class VaultError(Exception):
    pass


def configured() -> bool:
    return len(config.secret_key()) >= MIN_KEY_LEN


@lru_cache(maxsize=4)
def _derive(key: str) -> bytes:
    raw = hashlib.pbkdf2_hmac("sha256", key.encode(), b"mealkit-manager-vault-v1", 200_000)
    return base64.urlsafe_b64encode(raw)


def _fernet():
    if not configured():
        raise VaultError(
            f"SECRET_KEY is not set (at least {MIN_KEY_LEN} characters). Set it to link accounts."
        )
    from cryptography.fernet import Fernet
    return Fernet(_derive(config.secret_key()))


def encrypt(email: str, password: str) -> str:
    return _fernet().encrypt(json.dumps({"e": email, "p": password}).encode()).decode()


def decrypt(token: str) -> tuple:
    from cryptography.fernet import InvalidToken
    try:
        data = json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken:
        raise VaultError("The stored login cannot be decrypted. SECRET_KEY has changed; link the account again.")
    return data["e"], data["p"]
