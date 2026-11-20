from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import time
from typing import Any, Dict, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt

from ai_core.config import get_settings

_ph = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _ph.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(user_id: str, email: Optional[str] = None, expires_minutes: Optional[int] = None) -> str:
    settings = get_settings()
    ttl = expires_minutes or settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def sign_upload_path(rel_path: str, expires_seconds: int = 3600) -> str:
    """Return query params 'sig=...&exp=...' for time-limited upload file access."""
    settings = get_settings()
    exp = int(time.time()) + expires_seconds
    clean_rel = rel_path.lstrip("/")
    msg = f"{clean_rel}:{exp}".encode("utf-8")
    sig = hmac.new(settings.file_signing_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"sig={sig}&exp={exp}"


def verify_upload_signature(rel_path: str, sig: str, exp: int) -> bool:
    if not sig or not exp:
        return False
    if int(time.time()) > int(exp):
        return False
    settings = get_settings()
    clean_rel = rel_path.lstrip("/")
    msg = f"{clean_rel}:{int(exp)}".encode("utf-8")
    expected = hmac.new(settings.file_signing_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def hash_share_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
