# core/crypto.py
# ─────────────────────────────────────────────────────────────
#  Encrypt / decrypt tenant API keys before storing in Supabase
#  Uses Fernet (AES-256-CBC + HMAC) from the cryptography library
# ─────────────────────────────────────────────────────────────

import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

_raw_key = os.getenv("ENCRYPTION_KEY")
if not _raw_key:
    raise ValueError("ENCRYPTION_KEY must be set in .env")

_fernet = Fernet(_raw_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a base64 token."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token back to plaintext."""
    return _fernet.decrypt(token.encode()).decode()


def mask_key(key: str) -> str:
    """Return a masked version for display — sk-ant-...xxxx"""
    if not key or len(key) < 8:
        return "••••••••"
    return key[:10] + "••••••••" + key[-4:]