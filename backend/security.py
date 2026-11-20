"""Passwords, session tokens, secret encryption, rate limiting."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from backend import appdb

PBKDF2_ROUNDS = 240_000
_SECRET_FILE = os.path.join(os.path.dirname(appdb.DB_PATH), ".secret_key")


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2$"):
            _, rounds, salt, dk = stored.split("$")
            calc = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), base64.b64decode(salt), int(rounds))
            return hmac.compare_digest(calc, base64.b64decode(dk))
        legacy = hashlib.sha256((pw + "telebot_cluster_salt_2026").encode()).hexdigest()
        return hmac.compare_digest(legacy, stored)
    except Exception:
        return False


def needs_rehash(stored: str) -> bool:
    return not stored.startswith("pbkdf2$")


def dummy_verify(pw: str) -> None:
    try:
        salt = b"0" * 16
        hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), salt, min(PBKDF2_ROUNDS, 120_000))
    except Exception:
        pass


def valid_password(pw: str) -> Optional[str]:
    if not isinstance(pw, str) or len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 200:
        return "Password is too long."
    classes = sum([
        any(c.islower() for c in pw),
        any(c.isupper() for c in pw),
        any(c.isdigit() for c in pw),
        any(not c.isalnum() for c in pw),
    ])
    if len(pw) < 10 and classes < 3:
        return "Use a stronger password (10+ chars or mix upper/lower/digit/symbol)."
    return None


def password_strength(pw: str) -> dict:
    if not isinstance(pw, str) or not pw:
        return {"score": 0, "label": "empty"}
    score = 0
    score += min(40, len(pw) * 3)
    score += 15 if any(c.islower() for c in pw) else 0
    score += 15 if any(c.isupper() for c in pw) else 0
    score += 15 if any(c.isdigit() for c in pw) else 0
    score += 15 if any(not c.isalnum() for c in pw) else 0
    if len(pw) >= 14:
        score += 10
    score = max(0, min(100, score))
    if score < 30:
        label = "weak"
    elif score < 55:
        label = "fair"
    elif score < 80:
        label = "good"
    else:
        label = "strong"
    return {"score": score, "label": label}


def new_session_token() -> str:
    return "s_" + secrets.token_urlsafe(32)


def token_hash(tok: str) -> str:
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


def new_code(n: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(n))


_fernet = None
_fl = threading.Lock()


def _key() -> bytes:
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        return base64.urlsafe_b64encode(hashlib.sha256(env.encode()).digest())
    if os.path.exists(_SECRET_FILE):
        return open(_SECRET_FILE, "rb").read().strip()
    from cryptography.fernet import Fernet
    k = Fernet.generate_key()
    os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
    fd = os.open(_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(k)
    return k


def _f():
    global _fernet
    with _fl:
        if _fernet is None:
            from cryptography.fernet import Fernet
            _fernet = Fernet(_key())
        return _fernet


def encrypt(s: str) -> str:
    if not s:
        return ""
    return "enc:" + _f().encrypt(s.encode()).decode()


def decrypt(s: str) -> str:
    if not s:
        return ""
    if not str(s).startswith("enc:"):
        return s
    try:
        return _f().decrypt(s[4:].encode()).decode()
    except Exception:
        return ""


def mask_token(tok: str) -> str:
    if not tok:
        return ""
    if len(tok) < 16:
        return "•" * len(tok)
    return tok[:8] + "••••••" + tok[-4:]


def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip().strip("\"'").strip().lower()
    if v in ("0", "false", "off", "no", "n", "disabled", ""):
        return False
    return True


_ALWAYS = ("erral:", "lowpts:", "cb:")
_hits = defaultdict(deque)
_hl = threading.Lock()


def rate_limit(key: str, limit: int, window: float) -> float:
    _auth_prefixes = ("login:", "register:", "otp:", "forgot:", "reset:", "wh:", "api_key:")
    always = key.startswith(_ALWAYS) or any(key.startswith(p) for p in _auth_prefixes)
    if not env_flag("RATE_LIMITS", False) and not always:
        return 0.0
    if os.environ.get("BM_TEST_NO_RATE_LIMIT") == "1" and not always:
        return 0.0
    now = time.time()
    with _hl:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return max(1.0, q[0] + window - now)
        q.append(now)
        if len(_hits) > 20000:
            for k in list(_hits)[:5000]:
                if not _hits[k]:
                    _hits.pop(k, None)
        return 0.0


def clear_limit(key: str) -> None:
    with _hl:
        _hits.pop(key, None)


def clean_text(s, maxlen: int = 500) -> str:
    if s is None:
        return ""
    s = str(s).replace("\x00", "")
    return s.strip()[:maxlen]


def valid_email(e: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,}", e or ""))


def count_hits(key: str, window: float) -> int:
    now = time.time()
    with _hl:
        return len([t for t in _hits.get(key, ()) if t > now - window])


def sign(msg: str) -> str:
    return hmac.new(_key(), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def redact_secrets(text: str) -> str:
    import re
    if not text:
        return text
    s = str(text)
    s = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", s)
    s = re.sub(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[^\s'\"]{8,}", r"\1=[REDACTED]", s)
    return s
