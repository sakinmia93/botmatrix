"""REST API v2 (TeleBot Studio style): /v2/... authenticated with the account API key.

Auth:   Authorization: Bearer KEY  |  ?api_key=KEY  |  JSON body {"api_key": "KEY"}
Limits: 60 requests/min per IP, 1000 requests/hour per API key (X-RateLimit-* headers on every answer; always on)
Errors: {"ok": false, "result": "<message>"}
"""
import base64
import collections
import json
import os
import threading
import time

from backend import appdb, runtime
from backend.errors import ApiError

_hits = collections.defaultdict(collections.deque)
_lock = threading.Lock()


def _limit(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def _rate(key, limit, window):
    """-> (allowed, remaining, reset_ts)"""
    now = time.time()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False, 0, int(q[0] + window)
        q.append(now)
        return True, limit - len(q), int((q[0] if q else now) + window)


def _find_user(raw):
    """Account API key -> user id. The key is never stored in reversible form: only its SHA-256
    hash is kept (backend/models.py::AccountAPIKey), so authentication is a hash lookup, not a
    decrypt-and-compare over every stored key."""
    if not raw or len(raw) > 200:
        return None
    from backend import models as em
    from backend.database import SessionLocal
    from backend.routers.bots import _api_key_hash
    db = SessionLocal()
    try:
        row = db.query(em.AccountAPIKey).filter_by(key_hash=_api_key_hash(raw), revoked_at=None).first()
        if not row:
            return None
        acc = db.query(em.Account).filter_by(id=row.account_id).first()
        if not acc or not acc.email.endswith("@matrix.local"):
            return None
        return acc.email.rsplit("@matrix.local", 1)[0]
    finally:
        db.close()


def authenticate(x):
    """Returns (uid, rate_headers). Raises ApiError with the v2 messages."""
    h = x.h.headers.get("Authorization") or ""
    raw = h[7:].strip() if h.lower().startswith("bearer ") else ""
    raw = raw or ((x.query.get("api_key") or [""])[0]) or str((x.body or {}).get("api_key") or "")
    ip = x.h.client_ip()
    ok, rem, reset = _rate(f"v2ip:{ip}", _limit("V2_RATE_PER_MIN", 60), 60)
    hdr = {"X-RateLimit-Limit": str(_limit("V2_RATE_PER_MIN", 60)), "X-RateLimit-Remaining": str(rem), "X-RateLimit-Reset": str(reset)}
    if not ok:
        raise ApiError("Rate limit exceeded. Try again in 60 seconds.", 429, {"_headers": hdr})
    if not raw:
        raise ApiError("Authentication required", 401, {"_headers": hdr})
    uid = _find_user(raw)
    if not uid:
        raise ApiError("Invalid API key", 401, {"_headers": hdr})
    ok2, rem2, reset2 = _rate("v2key:" + uid, _limit("V2_RATE_PER_HOUR", 1000), 3600)
    hdr = {"X-RateLimit-Limit": str(_limit("V2_RATE_PER_HOUR", 1000)), "X-RateLimit-Remaining": str(rem2), "X-RateLimit-Reset": str(reset2)}
    if not ok2:
        raise ApiError("Rate limit exceeded. Try again in 60 seconds.", 429, {"_headers": hdr})
    try:
        from backend import security_center
        security_center.note_api_access(uid, ip)
    except Exception:
        pass
    return uid, hdr


def _S():
    from backend import services
    return services


def _own(uid, botid):
    try:
        return _S().own_bot(uid, str(botid))
    except ApiError:
        raise ApiError("Bot not found or not owned by you", 404)


def _cmds(b):
    return appdb.jload(b["commands_json"], []) or []


def _match(cmds, name):
    n = str(name or "")
    for i, c in enumerate(cmds):
        if c.get("name") in (n, n.lstrip("/"), "/" + n.lstrip("/")):
            return i
    return -1


def _view(c):
    return {"command": c.get("name"), "code": c.get("code", ""), "is_pinned": bool(c.get("isPinned"))}


def _reply(hdr, payload, status=200):
    return ("raw", "application/json", json.dumps(payload).encode(), hdr)


def register(route, Ctx):
    def wrap(fn):
        def run(x):
            uid, hdr = authenticate(x)
            try:
                return _reply(hdr, fn(uid, x))
            except ApiError as e:
                e.extra = {**e.extra, "_headers": hdr}
                raise
        return run

    @route("POST", "/v2/create-bot", auth=False)
    @wrap
    def create_bot(uid, x):
        tok = str((x.body or {}).get("bot_token") or "").strip()
        if not tok:
            raise ApiError("Bot token is required", 400)
        if ":" not in tok or len(tok) < 20 or not tok.split(":")[0].isdigit():
            raise ApiError("Invalid bot token format", 400)
        r = _S().create_bot(uid, {"token": tok})
        return {"ok": True, "result": {"botid": r.get("id"), "bot_name": r.get("name"), "bot_username": r.get("username")}}

    @route("DELETE", r"/v2/bots/([^/]+)", auth=False)
    @wrap
    def delete_bot(uid, x):
        _own(uid, x.p())
        _S().delete_bot(uid, x.p())
        return {"ok": True, "result": "Bot deleted (data preserved in the recycle bin)"}

    @route("POST", r"/v2/bots/([^/]+)/update-bot-token", auth=False)
    @wrap
    def update_token(uid, x):
        _own(uid, x.p())
        tok = str((x.body or {}).get("token") or "").strip()
        if not tok:
            raise ApiError("Bot token is required", 400)
        if ":" not in tok or not tok.split(":")[0].isdigit():
            raise ApiError("Invalid bot token format", 400)
        _S().update_bot(uid, x.p(), {"token": tok})
        res = runtime.set_running(x.p(), True)
        return {"ok": True, "result": "Token updated" + ("; bot started" if res.get("ok") else "")}

    @route("POST", r"/v2/bots/([^/]+)/commands", auth=False)
    @wrap
    def add_command(uid, x):
        b = _own(uid, x.p())
        name = str((x.body or {}).get("command") or "").strip()
        if not name:
            raise ApiError("command is required", 400)
        cmds = _cmds(b)
        i = _match(cmds, name)
        item = {"id": appdb.new_id("cmd_", 6), "name": name, "code": str((x.body or {}).get("code") or "")}
        if i >= 0:
            cmds[i] = {**cmds[i], "code": item["code"]}
        else:
            cmds.append(item)
        _S().update_bot(uid, x.p(), {"commands": cmds}, strict=True)
        return {"ok": True, "result": "Command saved"}

    @route("GET", r"/v2/bots/([^/]+)/command/by-name", auth=False)
    @wrap
    def get_by_name(uid, x):
        b = _own(uid, x.p())
        name = (x.query.get("command_name") or [""])[0]
        if not name:
            raise ApiError("command_name is required", 400)
        cmds = _cmds(b)
        i = _match(cmds, name)
        if i < 0:
            raise ApiError("Command not found", 404)
        return {"ok": True, "command": _view(cmds[i])}

    @route("POST", r"/v2/bots/([^/]+)/command/by-name/update", auth=False)
    @wrap
    def update_by_name(uid, x):
        b = _own(uid, x.p())
        name = str((x.body or {}).get("command_name") or "")
        cmds = _cmds(b)
        i = _match(cmds, name)
        if i < 0:
            raise ApiError("Command not found", 404)
        cmds[i] = {**cmds[i], "code": str((x.body or {}).get("code") or ""), "updatedAt": appdb.now_iso()}
        _S().update_bot(uid, x.p(), {"commands": cmds}, strict=True)
        return {"ok": True, "result": "Command updated"}

    @route("POST", r"/v2/bots/([^/]+)/command/by-name/delete", auth=False)
    @wrap
    def delete_by_name(uid, x):
        b = _own(uid, x.p())
        name = str((x.body or {}).get("command_name") or "")
        cmds = _cmds(b)
        i = _match(cmds, name)
        if i < 0:
            raise ApiError("Command not found", 404)
        cmds.pop(i)
        _S().update_bot(uid, x.p(), {"commands": cmds}, strict=True)
        return {"ok": True, "result": "Command deleted"}

    @route("GET", r"/v2/bots/([^/]+)/commands", auth=False)
    @wrap
    def list_commands(uid, x):
        b = _own(uid, x.p())
        return {"ok": True, "commands": [_view(c) for c in _cmds(b)]}

    @route("GET", r"/v2/bots/([^/]+)/commands/([A-Za-z0-9_\-=]+)", auth=False)
    @wrap
    def legacy_command(uid, x):
        b = _own(uid, x.p(0))
        try:
            s = x.p(1)
            name = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8")
        except Exception:
            raise ApiError("Command not found", 404)
        cmds = _cmds(b)
        i = _match(cmds, name)
        if i < 0:
            raise ApiError("Command not found", 404)
        return {"ok": True, "command": _view(cmds[i])}

    def _ctl(uid, x, want):
        b = _own(uid, x.p())
        if not b["token"]:
            raise ApiError("Add the bot token first.", 400)
        res = runtime.set_running(x.p(), want)
        if not res.get("ok"):
            raise ApiError(res.get("error") or "Couldn't change the bot state.", res.get("status") or 400)
        return {"ok": True, "result": "Bot started" if want else "Bot stopped"}

    @route("POST", r"/v2/bots/([^/]+)/start", auth=False)
    @wrap
    def start(uid, x):
        return _ctl(uid, x, True)

    @route("POST", r"/v2/bots/([^/]+)/stop", auth=False)
    @wrap
    def stop(uid, x):
        return _ctl(uid, x, False)

    @route("POST", r"/v2/bots/([^/]+)/restart", auth=False)
    @wrap
    def restart(uid, x):
        _ctl(uid, x, False)
        return {**_ctl(uid, x, True), "result": "Bot restarted"}
