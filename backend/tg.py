"""Minimal Telegram Bot API client used by the platform itself (not by user code)."""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

API_ROOT = os.getenv("TELEGRAM_API_ROOT", "https://api.telegram.org").rstrip("/")
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=512, max_retries=0)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)
# Honor system / env proxies (HTTP_PROXY, HTTPS_PROXY) automatically via requests


class TgError(Exception):
    def __init__(self, description: str, code: int = 0, retry_after: float = 0):
        super().__init__(description)
        self.description = description
        self.code = code
        self.retry_after = retry_after

    @property
    def unreachable(self) -> bool:
        """The user can never receive this bot's messages: blocked the bot, deleted/deactivated Telegram, or never started it.
        Everything else (flood limits, bad formatting, network trouble…) is a temporary or content problem, not the user's fault."""
        d = self.description.lower()
        return any(x in d for x in ("bot was blocked by the user", "user is deactivated", "chat not found", "user not found",
                                    "can't initiate conversation", "cannot initiate conversation", "peer_id_invalid",
                                    "bot can't send messages to the bot", "forbidden: bot was kicked"))

    @property
    def blocked(self) -> bool:
        d = self.description.lower()
        return self.code == 403 or "blocked" in d or "deactivated" in d or "chat not found" in d or "kicked" in d


def _post_json(url: str, payload: Optional[dict], timeout: float):
    last_err: Optional[BaseException] = None
    attempts = 3
    for i in range(attempts):
        try:
            return _session.post(url, json=payload or {}, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(0.5 * (i + 1))
    assert last_err is not None
    raise last_err


def call(token: str, method: str, payload: Optional[dict] = None, timeout: float = 20) -> Any:
    url = f"{API_ROOT}/bot{token}/{method}"
    try:
        r = _post_json(url, payload, timeout)
    except requests.RequestException as e:
        detail = f"{type(e).__name__}: {e}"
        raise TgError(f"Could not reach Telegram ({detail})", 0) from e
    try:
        data = r.json()
    except Exception:
        raise TgError(f"Unexpected Telegram response ({r.status_code})", r.status_code)
    if not data.get("ok"):
        params = data.get("parameters") or {}
        raise TgError(data.get("description") or "Telegram error", data.get("error_code") or r.status_code,
                      float(params.get("retry_after") or 0))
    return data.get("result")


def get_me(token: str) -> dict:
    return call(token, "getMe", timeout=15)


def get_updates(token: str, offset: int = 0, timeout: int = 25, allowed_updates=None, limit: int = 100):
    """Long-poll getUpdates. HTTP timeout is slightly larger than the long-poll wait."""
    payload = {
        "offset": int(offset or 0),
        "timeout": int(timeout or 0),
        "limit": max(1, min(int(limit or 100), 100)),
    }
    if allowed_updates is not None:
        payload["allowed_updates"] = list(allowed_updates)
    http_timeout = float(timeout) + 10.0 if timeout else 20.0
    return call(token, "getUpdates", payload, timeout=http_timeout) or []


def profile_photo_url(token: str, user_id: int) -> str:
    """Telegram file path of the first profile photo, or ''. The file URL embeds the bot token,
    so callers must proxy it (see /api/media) instead of exposing it to browsers."""
    try:
        ph = call(token, "getUserProfilePhotos", {"user_id": int(user_id), "limit": 1}, timeout=10)
        photos = (ph or {}).get("photos") or []
        if not photos or not photos[0]:
            return ""
        file_id = photos[0][-1]["file_id"]
        fi = call(token, "getFile", {"file_id": file_id}, timeout=10)
        return (fi or {}).get("file_path") or ""
    except TgError:
        return ""


def download_file(token: str, file_path: str, max_bytes: int = 2_000_000) -> Optional[bytes]:
    try:
        r = _session.get(f"{API_ROOT}/file/bot{token}/{file_path}", timeout=15, stream=True)
        if r.status_code != 200:
            return None
        data = r.raw.read(max_bytes + 1, decode_content=True)
        return data if len(data) <= max_bytes else None
    except requests.RequestException:
        return None


def call_upload(token: str, method: str, payload: dict, field: str, filename: str, content: bytes, mime: str = "application/octet-stream", timeout: float = 120) -> Any:
    """Send a method with a file uploaded straight from memory (nothing touches the disk)."""
    import json as _json
    data = {k: (_json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in (payload or {}).items() if v is not None}
    last_err: Optional[BaseException] = None
    for i in range(3):
        try:
            r = _session.post(f"{API_ROOT}/bot{token}/{method}", data=data, files={field: (filename, content, mime)}, timeout=timeout)
            last_err = None
            break
        except requests.RequestException as e:
            last_err = e
            if i < 2:
                time.sleep(0.5 * (i + 1))
    if last_err is not None:
        raise TgError(f"Could not reach Telegram ({type(last_err).__name__}: {last_err})", 0) from last_err
    try:
        j = r.json()
    except Exception:
        raise TgError(f"Unexpected Telegram response ({r.status_code})", r.status_code)
    if not j.get("ok"):
        params = j.get("parameters") or {}
        raise TgError(j.get("description") or "Telegram error", j.get("error_code") or r.status_code, float(params.get("retry_after") or 0))
    return j.get("result")


def file_id_of(result: dict, field: str) -> str:
    """Pull the reusable file_id out of a send* result."""
    if not isinstance(result, dict):
        return ""
    v = result.get(field)
    if field == "photo" and isinstance(v, list) and v:
        return v[-1].get("file_id", "")
    if isinstance(v, dict):
        return v.get("file_id", "")
    for alt in ("animation", "document", "video", "audio", "voice", "video_note", "sticker", "photo"):
        w = result.get(alt)
        if isinstance(w, dict) and w.get("file_id"):
            return w["file_id"]
        if alt == "photo" and isinstance(w, list) and w:
            return w[-1].get("file_id", "")
    return ""
