"""Mat khau (scrypt, thu vien chuan) va ma hoa API key cua don vi (Fernet, khoa suy tu PORTAL_SECRET_KEY)."""
import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet

_N, _R, _P = 2**14, 8, 1


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${salt.hex()}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, n, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=_R, p=_P)
        return hmac.compare_digest(got.hex(), dk)
    except ValueError:
        return False


def fernet(secret_key: str) -> Fernet:
    # Khoa rieng cho ma hoa, khac khoa ky cookie (cung nguon nhung khac muc dich)
    k = hashlib.sha256(b"campus-portal/api-key/" + secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(k))


def session_key(secret_key: str) -> str:
    return hashlib.sha256(b"campus-portal/session/" + secret_key.encode()).hexdigest()
