"""Security Center — restored after accidental empty push (from 322f74b + conflict fixes)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from typing import Dict, List, Optional

from backend import appdb, security
from backend.errors import ApiError

log = logging.getLogger("security")
SEV = {"info": 0, "warn": 1, "bad": 2, "critical": 3}

TOKEN_RE = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
KEY_PATTERNS = [
    ("Telegram bot token", TOKEN_RE),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def _ensure():
    with appdb.db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS security_events (
            id TEXT PRIMARY KEY, ts TEXT, user_id TEXT, bot_id TEXT, kind TEXT, severity TEXT, title TEXT, detail TEXT,
            ip TEXT, fp TEXT, resolved INTEGER DEFAULT 0)""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_secev_user ON security_events(user_id, ts)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_secev_fp ON security_events(fp, ts)")


_ready = False


def _init():
    global _ready
    if not _ready:
        _ensure()
        _ready = True


def record(kind: str, severity: str, title: str, detail: str = "", user_id: str = "", bot_id: str = "", ip: str = "",
           fp: Optional[str] = None, notify: bool = True, window_h: int = 24) -> bool:
    _init()
    fp = fp or hashlib.sha1(f"{kind}|{user_id}|{bot_id}|{title}".encode()).hexdigest()[:20]
    with appdb.db() as c:
        if appdb.one(c, "SELECT id FROM security_events WHERE fp=? AND ts>=? AND resolved=0", (fp, appdb.iso_in(hours=-window_h))):
            return False
        c.execute("INSERT INTO security_events (id,ts,user_id,bot_id,kind,severity,title,detail,ip,fp) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (appdb.new_id("se_", 8), appdb.now_iso(), user_id or "", bot_id or "", kind, severity, title[:200], detail[:1500], ip, fp))
    if notify and user_id and SEV.get(severity, 0) >= SEV["warn"]:
        appdb.notify(user_id, "🛡️ " + title, detail, "warning" if severity in ("warn", "bad") else "error", "tab:Settings#security")
        try:
            from backend import connect_bot
            threading.Thread(target=connect_bot.alert, args=(user_id, "securityAlerts", f"🛡️ <b>{connect_bot._h(title)}</b>\n{connect_bot._h(detail[:600])}"), daemon=True).start()
        except Exception:
            pass
    return True


def scan_text(text: str) -> List[str]:
    found = []
    for label, rx in KEY_PATTERNS:
        if rx.search(text or ""):
            found.append(label)
    return found


def check_tokens(user_id: str = "", limit: int = 40) -> list:
    from backend import tg
    q = "SELECT id,name,user_id,username,bot_numeric_id,token,status,webhook_url FROM bots WHERE token IS NOT NULL AND token!='' AND status='working'"
    a = ()
    if user_id:
        q, a = q + " AND user_id=?", (user_id,)
    with appdb.read() as c:
        bots = appdb.rows(c, q + " ORDER BY RANDOM() LIMIT ?", (*a, limit))
    res = []
    for b in bots:
        tok = security.decrypt(b["token"] or "")
        if not tok:
            continue
        item = {"botId": b["id"], "bot": b["name"], "status": "valid"}
        try:
            me = tg.call(tok, "getMe", {}, timeout=10)
            if b["bot_numeric_id"] and str(me.get("id")) != str(b["bot_numeric_id"]):
                item["status"] = "changed"
                record("token-health", "critical", f"Bot token of “{b['name']}” now belongs to a different bot",
                       f"Saved token answers as @{me.get('username')} (id {me.get('id')}).",
                       b["user_id"], b["id"])
            try:
                wh = tg.call(tok, "getWebhookInfo", {}, timeout=10) or {}
                url = (wh.get("url") or "").strip()
                if url:
                    base = (os.environ.get("BASE_URL") or "").strip().rstrip("/")
                    ours = bool(base and url.startswith(base))
                    if not ours:
                        try:
                            from urllib.parse import urlparse
                            host = (urlparse(url).hostname or "").lower()
                            if host and any(x in host for x in ("railway.app", "botmatrix", "up.railway")):
                                ours = True
                        except Exception:
                            pass
                    if ours:
                        item["status"] = "webhook-ours"
                    else:
                        item["status"] = "webhook"
                        record("token-health", "bad", f"Unknown webhook on “{b['name']}”",
                               f"Telegram is sending updates to {url[:80]}. If that is not you, revoke the token in @BotFather.",
                               b["user_id"], b["id"], fp=f"wh:{b['id']}:{url[:40]}")
            except Exception:
                pass
        except tg.TgError as e:
            if e.code in (401, 404):
                item["status"] = "revoked"
                record("token-health", "critical", f"Bot token of “{b['name']}” was revoked or changed",
                       "Telegram no longer accepts this token.", b["user_id"], b["id"])
                try:
                    from backend import runtime
                    runtime.set_running(b["id"], False)
                except Exception:
                    pass
            else:
                item["status"] = "unreachable"
        except Exception:
            item["status"] = "unreachable"
        res.append(item)
    return res


def note_conflict(bot_id: str) -> None:
    """Telegram 409 conflict. Do not alarm when webhook is ours or on first restart cycle."""
    with appdb.read() as c:
        b = appdb.one(c, "SELECT name,user_id,token,status FROM bots WHERE id=?", (bot_id,))
    if not b:
        return
    try:
        from backend import tg, security as sec
        tok = sec.decrypt(b["token"] or "")
        if tok:
            wh = tg.call(tok, "getWebhookInfo", {}, timeout=8) or {}
            url = (wh.get("url") or "").strip()
            base = (os.environ.get("BASE_URL") or "").strip().rstrip("/")
            if url and base and url.startswith(base):
                return
            if url:
                try:
                    tg.call(tok, "deleteWebhook", {"drop_pending_updates": False}, timeout=8)
                except Exception:
                    pass
                return
    except Exception:
        pass
    record("token-conflict", "warn", f"Another program is using the token of “{b['name']}”",
           "Telegram reports a conflict. If you only run this bot inside BOT MATRIX, ignore a single alert after deploy/restart. "
           "If it keeps repeating, revoke the token in @BotFather.",
           b["user_id"], bot_id, window_h=12)


def note_token_change(user_id: str, bot_id: str, ip: str = "", removed: bool = False) -> None:
    _init()
    with appdb.db() as c:
        c.execute("INSERT INTO security_events (id,ts,user_id,bot_id,kind,severity,title,detail,ip,fp) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (appdb.new_id("se_", 8), appdb.now_iso(), user_id, bot_id, "token-change", "info",
                   "Bot token " + ("removed" if removed else "replaced"), "", ip, f"tc:{appdb.new_id('', 6)}"))
        n = appdb.one(c, "SELECT COUNT(*) n FROM security_events WHERE user_id=? AND kind='token-change' AND ts>=?", (user_id, appdb.iso_in(minutes=-10)))["n"]
    if n >= 5:
        record("bulk-changes", "critical", f"{n} bot tokens were replaced in 10 minutes",
               "This looks like an account takeover. Change your password and check your bots.",
               user_id, "", ip, fp=f"bulk:{user_id}:{int(time.time() // 900)}")


def list_events(user_id: str = "", limit: int = 50) -> list:
    _init()
    with appdb.read() as c:
        if user_id:
            rows = appdb.rows(c, "SELECT * FROM security_events WHERE user_id=? ORDER BY ts DESC LIMIT ?", (user_id, limit))
        else:
            rows = appdb.rows(c, "SELECT * FROM security_events ORDER BY ts DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def resolve_event(event_id: str) -> None:
    with appdb.db() as c:
        c.execute("UPDATE security_events SET resolved=1 WHERE id=?", (event_id,))


def start_watcher() -> None:
    def loop():
        while True:
            try:
                check_tokens(limit=20)
            except Exception:
                log.exception("token watch")
            time.sleep(300)
    threading.Thread(target=loop, daemon=True, name="sec-watch").start()


def encrypt_legacy_env() -> None:
    pass


def note_login(user_id: str, ip: str, ua: str = "") -> None:
    """Record login; escalate on rapid multi-IP activity."""
    _init()
    record("login", "info", "Sign-in", f"IP {ip}" + (f" · {ua[:80]}" if ua else ""), user_id, "", ip,
           fp=f"login:{user_id}:{ip}:{int(time.time() // 3600)}", notify=False, window_h=1)
    with appdb.read() as c:
        n = appdb.one(
            c,
            "SELECT COUNT(DISTINCT ip) n FROM security_events WHERE user_id=? AND kind='login' AND ts>=?",
            (user_id, appdb.iso_in(hours=-1)),
        )["n"]
    if n >= 4:
        record("multi-ip", "warn", f"Sign-ins from {n} different IPs in 1 hour",
               "If this was not you, change your password and review sessions.",
               user_id, "", ip, fp=f"multiip:{user_id}:{int(time.time() // 3600)}")


def _sessions_of(uid: str) -> dict:
    try:
        with appdb.read() as c:
            n = appdb.one(c, "SELECT COUNT(*) n FROM sessions WHERE user_id=?", (uid,))
            return {"count": int(n["n"] if n else 0)}
    except Exception:
        return {"count": 0}


def events_of(user_id: Optional[str], limit: int = 60) -> list:
    rows = list_events(user_id or "", limit)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "ts": r.get("ts"),
            "kind": r.get("kind"),
            "severity": r.get("severity"),
            "title": r.get("title"),
            "detail": r.get("detail"),
            "resolved": bool(r.get("resolved")),
            "botId": r.get("bot_id") or "",
        })
    return out


def resolve(user_id: Optional[str], eid: str) -> dict:
    resolve_event(eid)
    return {"ok": True}


def scan_bot_code(commands: list, env_vars: list = None) -> List[dict]:
    hits = []
    for cmd in commands or []:
        code = (cmd.get("code") or "") if isinstance(cmd, dict) else ""
        found = scan_text(code)
        if found:
            hits.append({"command": (cmd.get("name") if isinstance(cmd, dict) else "") or "?", "findings": found})
    for e in env_vars or []:
        if not isinstance(e, dict):
            continue
        found = scan_text(str(e.get("value") or ""))
        if found:
            hits.append({"command": f"env:{e.get('key') or e.get('name')}", "findings": found})
    return hits


def check_secrets(user_id: Optional[str] = None) -> List[dict]:
    q = "SELECT id,name,commands_json,env_vars_json FROM bots"
    a: tuple = ()
    if user_id:
        q += " WHERE user_id=?"
        a = (user_id,)
    out = []
    with appdb.read() as c:
        bots = appdb.rows(c, q, a)
    for b in bots:
        hits = scan_bot_code(appdb.jload(b["commands_json"], []), appdb.jload(b["env_vars_json"], []))
        if hits:
            out.append({"botId": b["id"], "bot": b["name"], "items": hits})
    return out


def user_status(uid: str, scan: bool = False) -> dict:
    """What the account owner sees: the state of THEIR bots and account only."""
    _init()
    secrets = check_secrets(uid) if scan else []
    tokens = check_tokens(uid, 15) if scan else []
    if not scan:
        with appdb.read() as c:
            bots = appdb.rows(c, "SELECT id,name,commands_json FROM bots WHERE user_id=?", (uid,))
        for b in bots:
            hits = scan_bot_code(appdb.jload(b["commands_json"], []))
            if hits:
                secrets.append({"botId": b["id"], "bot": b["name"], "items": hits})
    ev = events_of(uid, 40)
    open_ev = [e for e in ev if not e["resolved"] and SEV.get(e["severity"], 0) >= 1]
    ses = _sessions_of(uid)
    checks = [
        {"id": "secrets", "title": "No keys pasted in code", "ok": not secrets, "detail": f"{len(secrets)} bot(s) flagged" if secrets else "Clean"},
        {"id": "tokens", "title": "Bot tokens healthy", "ok": not any(t.get("status") in ("revoked", "changed", "webhook") for t in tokens), "detail": f"{len(tokens)} checked" if scan else "Open Security to scan"},
        {"id": "events", "title": "No open security alerts", "ok": not open_ev, "detail": f"{len(open_ev)} open" if open_ev else "None"},
        {"id": "sessions", "title": "Active sessions", "ok": True, "detail": str(ses.get("count", 0))},
    ]
    score = 100
    if secrets:
        score -= min(40, 10 * len(secrets))
    if open_ev:
        score -= min(30, 8 * len(open_ev))
    if any(t.get("status") in ("revoked", "changed") for t in tokens):
        score -= 25
    return {
        "score": max(0, score),
        "checks": checks,
        "events": ev,
        "secrets": secrets,
        "tokens": tokens,
        "sessions": ses,
    }


def admin_status(scan: bool = False, fix: Optional[str] = None) -> dict:
    """Platform-wide security view for admins."""
    _init()
    if fix == "encrypt-env":
        encrypt_legacy_env()
    tokens = check_tokens("", 25) if scan else []
    secrets = check_secrets(None) if scan else []
    ev = events_of(None, 60)
    open_ev = [e for e in ev if not e["resolved"] and SEV.get(e["severity"], 0) >= 1]
    checks = [
        {"id": "tokens", "title": "Token health", "ok": not any(t.get("status") in ("revoked", "changed", "webhook") for t in tokens), "detail": f"{len(tokens)} scanned" if scan else "Run scan"},
        {"id": "secrets", "title": "No secrets in code", "ok": not secrets, "detail": f"{len(secrets)} bots" if secrets else "OK"},
        {"id": "events", "title": "Open alerts", "ok": not open_ev, "detail": str(len(open_ev))},
    ]
    return {"checks": checks, "events": ev, "tokens": tokens, "secrets": secrets, "score": max(0, 100 - 15 * len(open_ev))}
