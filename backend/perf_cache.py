"""Hot-path cache for bot config / commands (in-process TTL + optional Redis).

Design goals:
- Millisecond lookups for webhook handling under thousands of bots
- No cross-user data leakage (keys always include bot_id / user_id)
- Safe degradation when Redis is down (memory cache only)
- Explicit invalidate on bot/command edits
- Reliable Railway Redis connection (retry + sensible timeouts)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

log = logging.getLogger("perf_cache")

_lock = threading.RLock()
_store: dict[str, tuple[float, Any]] = {}
_MAX = int(os.environ.get("BM_CACHE_MAX_KEYS", "20000"))
_DEFAULT_TTL = float(os.environ.get("BM_CACHE_TTL", "30"))

_redis = None
_redis_tried = False
_redis_ok = False
_redis_last_error = ""
_redis_lock = threading.Lock()


def _redis_url() -> str:
    return (os.environ.get("REDIS_URL") or os.environ.get("BM_REDIS_URL") or "").strip()


def _get_redis(force: bool = False):
    global _redis, _redis_tried, _redis_ok, _redis_last_error
    with _redis_lock:
        if _redis_tried and not force:
            return _redis if _redis_ok else None
        _redis_tried = True
        url = _redis_url()
        if not url:
            _redis = None
            _redis_ok = False
            return None
        try:
            import redis  # type: ignore
            connect_to = float(os.environ.get("REDIS_CONNECT_TIMEOUT", "2.5"))
            socket_to = float(os.environ.get("REDIS_SOCKET_TIMEOUT", "2.5"))
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=connect_to,
                socket_timeout=socket_to,
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
                decode_responses=True,
            )
            client.ping()
            _redis = client
            _redis_ok = True
            _redis_last_error = ""
            log.info("Redis connected (cache ready)")
            return _redis
        except Exception as e:
            _redis = None
            _redis_ok = False
            _redis_last_error = type(e).__name__
            log.warning("Redis unavailable (%s) — using in-memory cache only", type(e).__name__)
            return None


def get(key: str) -> Any:
    now = time.time()
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > now:
            return hit[1]
        if hit:
            _store.pop(key, None)
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get("bm:" + key)
            if raw is not None:
                val = json.loads(raw)
                put(key, val, ttl=_DEFAULT_TTL, _local_only=True)
                return val
        except Exception:
            pass
    return None


def put(key: str, value: Any, ttl: Optional[float] = None, _local_only: bool = False) -> None:
    exp = time.time() + (ttl if ttl is not None else _DEFAULT_TTL)
    with _lock:
        if len(_store) >= _MAX:
            for k, _ in sorted(_store.items(), key=lambda kv: kv[1][0])[: max(1, _MAX // 10)]:
                _store.pop(k, None)
        _store[key] = (exp, value)
    if _local_only:
        return
    r = _get_redis()
    if r is not None:
        try:
            sec = int(ttl if ttl is not None else _DEFAULT_TTL)
            r.setex("bm:" + key, max(1, sec), json.dumps(value, default=str))
        except Exception:
            pass


def invalidate(key: str) -> None:
    with _lock:
        _store.pop(key, None)
    r = _get_redis()
    if r is not None:
        try:
            r.delete("bm:" + key)
        except Exception:
            pass


def invalidate_prefix(prefix: str) -> None:
    with _lock:
        for k in [k for k in _store if k.startswith(prefix)]:
            _store.pop(k, None)
    r = _get_redis()
    if r is not None:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match="bm:" + prefix + "*", count=100)
                if keys:
                    r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass


def bot_commands_key(bot_id: str) -> str:
    return f"bot:{bot_id}:commands"


def bot_meta_key(bot_id: str) -> str:
    return f"bot:{bot_id}:meta"


def stats() -> dict:
    with _lock:
        n = len(_store)
    r = _get_redis()
    return {
        "local_keys": n,
        "redis_configured": bool(_redis_url()),
        "redis": r is not None,
        "redis_error": _redis_last_error or None,
        "ttl": _DEFAULT_TTL,
        "max": _MAX,
    }


def health_check() -> dict:
    """Explicit ping for /api/health. Retries once if previously failed."""
    url_set = bool(_redis_url())
    if not url_set:
        return {"configured": False, "ok": False, "detail": "REDIS_URL not set"}
    r = _get_redis(force=not _redis_ok)
    if r is None:
        return {"configured": True, "ok": False, "detail": _redis_last_error or "connect failed"}
    try:
        t0 = time.time()
        r.ping()
        ms = round((time.time() - t0) * 1000, 1)
        return {"configured": True, "ok": True, "ping_ms": ms}
    except Exception as e:
        return {"configured": True, "ok": False, "detail": type(e).__name__}
