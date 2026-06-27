"""Encryption for credentials-at-rest. Uses Fernet (AES128-CBC + HMAC SHA256).

The single master key in env (JSA_MASTER_KEY) decrypts sessionids stored in
provider_credentials.sessionid_enc. NEVER log plaintext or ciphertext.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.master_key.strip()
        if not key:
            raise RuntimeError(
                "JSA_MASTER_KEY is not set. Generate one with:\n"
                '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string, return base64 ciphertext."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt; raises InvalidToken if tampered or wrong key."""
    return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def is_valid_master_key(key: str) -> bool:
    """True if `key` is a valid Fernet key string."""
    try:
        Fernet(key.encode())
        return True
    except (ValueError, TypeError):
        return False
