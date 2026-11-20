"""Business logic for the web API. Every function takes the signed-in user's id and only touches that user's rows."""
from __future__ import annotations

import datetime
import json
import re
import time
from typing import Optional

from backend import plans, appdb, runtime, security, tg, platform_hooks
from backend.errors import ApiError

BOT_COST = 50
TOKEN_RE = re.compile(r"^\d{6,14}:[A-Za-z0-9_-]{30,60}$")
CATEGORIES = {"Operations", "Utilities", "Games", "Finance", "Education", "Social", "Shopping", "Entertainment"}
PENDING_MAX = 20


# ------------------------------------------------------------------ bots
def _photo_url(b) -> str:
    p = b["photo_url"] or ""
    if p.startswith("tgfile:"):
        return f"/api/media/bot/{b['id']}?v={abs(hash(p)) % 10**8}"
    return p or f"/api/avatar/{b['id']}.svg"


def bot_dict(b, with_details=True, conn=None) -> dict:
    cmds = appdb.jload(b["commands_json"], [])
    with appdb.read() as c:
        n = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id=? AND bot_blocked=0 AND is_blocked=0", (b["id"],))["n"]
    working = b["status"] == "working" and runtime.is_running(b["id"])
    d = {
        "id": b["id"], "botNumericId": b["bot_numeric_id"] or b["id"], "username": b["username"], "name": b["name"],
        "status": "working" if working else ("stopped" if b["status"] == "working" else b["status"]),
        "activeUsers": n, "totalCommands": len([x for x in cmds if x.get("name") not in (None, "")]),
        "category": b["category"] or "Operations", "lastActive": b["last_active"] or "", "version": b["version"] or "v1.0.0",
        "uptime": runtime.uptime_text(b["uptime"]) if working else "",
        "createdAt": b["created_at"] or "",
        "folder": b["folder"] or "", "isPinned": bool(b["is_pinned"]), "photoUrl": _photo_url(b),
        "hasToken": bool(b["token"]), "tokenMasked": security.mask_token(security.decrypt(b["token"] or "")),
        "fasterResponse": bool(b["faster_response"]), "autoTranslate": bool(b["auto_translate"]),
        "miniAppTitle": b["mini_app_title"] or "", "miniAppUrl": b["mini_app_url"] or "", "description": b["description"] or "",
    }
    if with_details:
        d["commands"] = cmds
        d["envVars"] = appdb.jload(b["env_vars_json"], [])
        d["errors"] = bot_errors(b["id"])
    return d


_health_cache: dict = {}


def _token_ok(bot_id: str, token: str):
    """Is the bot's token accepted by Telegram right now? (cached for a minute so the Intro page stays cheap)"""
    hit = _health_cache.get(bot_id)
    if hit and time.time() - hit[0] < 60:
        return hit[1], hit[2]
    try:
        tg.get_me(token)
        res = (True, "Telegram accepts the token")
    except tg.TgError as e:
        res = (False, e.description or "Telegram rejected the request")
    _health_cache[bot_id] = (time.time(), *res)
    return res


def intro(uid: str, bot_id: str, tz_minutes: int = 0) -> dict:
    """Live numbers for the bot's Intro page: users, today's new users, uptime and a real health check."""
    from backend import models as em
    from backend.database import SessionLocal
    b = own_bot(uid, bot_id)
    now = appdb.utcnow()
    local_now = now + datetime.timedelta(minutes=tz_minutes)
    day_start = (local_now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(minutes=tz_minutes))
    iso = lambda d: d.isoformat(timespec="milliseconds") + "Z"
    with appdb.read() as c:
        row = appdb.one(c, "SELECT COUNT(*) total, SUM(CASE WHEN is_blocked=0 AND bot_blocked=0 THEN 1 ELSE 0 END) active, "
                           "SUM(CASE WHEN bot_blocked=1 THEN 1 ELSE 0 END) left_bot, SUM(CASE WHEN is_blocked=1 THEN 1 ELSE 0 END) blocked, "
                           "SUM(CASE WHEN first_seen>=? THEN 1 ELSE 0 END) new_today, SUM(CASE WHEN first_seen>=? THEN 1 ELSE 0 END) new_24h, "
                           "SUM(CASE WHEN last_active>=? THEN 1 ELSE 0 END) active_24h, MAX(last_active) last_update FROM chats WHERE bot_id=?",
                        (iso(day_start), iso(now - datetime.timedelta(hours=24)), iso(now - datetime.timedelta(hours=24)), bot_id))
    working = b["status"] == "working" and runtime.is_running(bot_id)
    started = appdb.parse_iso(b["uptime"]) if working else None
    errs_h = errs_24 = errs_30 = 0
    db = SessionLocal()
    try:
        pk = runtime.engine_pk(bot_id, db)
        if pk is not None:
            cnt = lambda since: db.query(em.ErrorLog).filter(em.ErrorLog.bot_id == pk, em.ErrorLog.created_at >= since.replace(tzinfo=None)).count()
            errs_h, errs_24, errs_30 = cnt(now - datetime.timedelta(hours=1)), cnt(now - datetime.timedelta(hours=24)), cnt(now - datetime.timedelta(days=30))
    except Exception:
        pass
    finally:
        db.close()
    checks = [{"name": "Bot process", "ok": working, "detail": "Running" if working else "Stopped"}]
    token = security.decrypt(b["token"] or "")
    if token:
        ok, why = _token_ok(bot_id, token)
        checks.append({"name": "Telegram connection", "ok": ok, "detail": why})
    else:
        checks.append({"name": "Telegram connection", "ok": False, "detail": "No bot token yet"})
    checks.append({"name": "Errors in the last hour", "ok": errs_h < 5, "detail": f"{errs_h} error(s)"})
    if not working:
        state = "stopped"
    elif not checks[1]["ok"]:
        state = "error"
    elif errs_h >= 5:
        state = "degraded"
    else:
        state = "healthy"
    return {"createdAt": b["created_at"] or "", "running": working, "startedAt": b["uptime"] if working else "",
            "uptimeSeconds": int((now - started).total_seconds()) if started else 0,
            "users": {"total": int(row["total"] or 0), "active": int(row["active"] or 0), "leftBot": int(row["left_bot"] or 0),
                      "blocked": int(row["blocked"] or 0), "newToday": int(row["new_today"] or 0), "new24h": int(row["new_24h"] or 0),
                      "active24h": int(row["active_24h"] or 0)},
            "lastUpdate": row["last_update"] or "", "errors": {"lastHour": errs_h, "last24h": errs_24, "last30d": errs_30},
            "commands": len([x for x in appdb.jload(b["commands_json"], []) if x.get("name")]),
            "health": {"state": state, "checks": checks}}


def clear_errors(uid: str, bot_id: str) -> dict:
    from backend import models as em
    from backend.database import SessionLocal
    own_bot(uid, bot_id)
    db = SessionLocal()
    try:
        pk = runtime.engine_pk(bot_id, db)
        n = db.query(em.ErrorLog).filter_by(bot_id=pk).delete() if pk is not None else 0
        db.commit()
    finally:
        db.close()
    return {"success": True, "cleared": n}


from backend import error_clean as _ec


def _clean_stack(tb: str) -> str:
    """Old rows may still hold a raw Python traceback: never show server paths / internal frames."""
    if "Traceback" in tb or 'File "' in tb:
        return _ec.user_stack(tb)
    return _ec.redact(tb)


def bot_errors(bot_id: str) -> list:
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        pk = runtime.engine_pk(bot_id, db)
        if pk is None:
            return []
        since = appdb.utcnow().replace(tzinfo=None) - datetime.timedelta(days=30)      # the log shows the last 30 days
        rows = db.query(em.ErrorLog).filter(em.ErrorLog.bot_id == pk, em.ErrorLog.created_at >= since).order_by(em.ErrorLog.id.desc()).limit(500).all()
        out = []
        for r in rows:
            msg = _ec.redact((r.message or "")[:2000])
            stack = _clean_stack(r.traceback or "")
            line = None
            for src in (msg, stack):
                m = re.search(r"\bline\s+(\d+)\b", src or "", re.I)
                if m:
                    try:
                        line = int(m.group(1))
                    except Exception:
                        line = None
                    if line:
                        break
            out.append({
                "id": str(r.id),
                "time": (r.created_at.isoformat() + "Z") if r.created_at else "",
                "command": r.command_trigger or "",
                "message": msg,
                "stack": stack,
                "line": line,
            })
        return out
    except Exception:
        return []
    finally:
        db.close()


def own_bot(uid: str, bot_id: str):
    with appdb.read() as c:
        b = appdb.one(c, "SELECT * FROM bots WHERE id=? AND user_id=?", (bot_id, uid))
    if not b:
        raise ApiError("Bot not found", 404)
    return b


def list_bots(uid: str) -> list:
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT * FROM bots WHERE user_id=? ORDER BY is_pinned DESC, updated_at DESC", (uid,))
    return [bot_dict(b) for b in rows]


def fetch_identity(token: str) -> dict:
    token = (token or "").strip().replace(" ", "")
    if not TOKEN_RE.match(token):
        raise ApiError("That doesn't look like a bot token. Copy the full token from @BotFather (it looks like 123456789:ABC…).", 400)
    try:
        me = tg.get_me(token)
    except tg.TgError as e:
        if e.code in (401, 404):
            raise ApiError("Telegram didn't accept this token. Check it and try again.", 400)
        if e.code:
            raise ApiError(f"Telegram error ({e.code}): {e.description}", 502)
        # Network / DNS / TLS failures
        raise ApiError(
            "Couldn't reach Telegram right now. Check your internet, firewall, or VPN, then try again. "
            f"Detail: {e.description}",
            502,
        )
    if not me.get("is_bot"):
        raise ApiError("This token doesn't belong to a bot.", 400)
    photo = ""
    try:
        path = tg.profile_photo_url(token, me["id"])
        photo = "tgfile:" + path if path else ""
    except Exception:
        pass
    return {"id": str(me["id"]), "name": me.get("first_name") or me.get("username") or "Bot",
            "username": "@" + me["username"] if me.get("username") else "", "photo": photo}


def _clean_commands(cmds) -> list:
    out, seen = [], set()
    if not isinstance(cmds, list):
        raise ApiError("Commands must be a list.", 400)
    for c in cmds[:500]:
        if not isinstance(c, dict):
            continue
        name = security.clean_text(c.get("name"), 100)
        if not name:
            continue
        if name in seen:
            raise ApiError(f'The command "{name}" already exists. Choose a different name.', 409)
        seen.add(name)
        item = {"id": security.clean_text(c.get("id"), 60) or appdb.new_id("cmd_", 6), "name": name,
                "code": str(c.get("code") or "")[:400_000], "updatedAt": c.get("updatedAt") or appdb.now_iso()}
        for k in ("isPinned", "isAdminOnly"):
            if c.get(k):
                item[k] = True
        if isinstance(c.get("aliases"), list):
            item["aliases"] = [security.clean_text(a, 100) for a in c["aliases"][:10]]
        if c.get("folder"):
            item["folder"] = security.clean_text(c["folder"], 100)
        out.append(item)
    return out


def _check_code(cmds: list) -> list:
    """Finds syntax / sandbox problems. It NEVER blocks saving: what the user wrote is always stored, the problems are reported back
    (a command with errors is stopped by the sandbox at run time and the error shows in the Errors tab)."""
    from backend import tpy_tools
    bad = []
    for c in cmds:
        try:
            r = tpy_tools.validate(c["code"], c["name"])
        except Exception as e:
            r = {"errors": [{"line": 1, "message": str(e)[:150], "severity": "error"}]}
        for e in r["errors"]:
            if e["severity"] == "error":
                bad.append({"command": c["name"], "line": e["line"], "message": e["message"]})
    return bad[:50]


def _clean_env(env) -> list:
    out = []
    for e in (env or [])[:200]:
        if isinstance(e, dict) and str(e.get("key") or "").strip():
            out.append({"id": security.clean_text(e.get("id"), 60) or appdb.new_id("env_", 4),
                        "key": security.clean_text(e.get("key"), 100), "value": str(e.get("value") if e.get("value") is not None else "")[:5000],
                        **({"raw": True} if e.get("raw") else {})})
    return out


def create_bot(uid: str, body: dict) -> dict:
    token = security.clean_text(body.get("token"), 200)
    is_clone = bool(body.get("isClone"))
    cmds = _clean_commands(body.get("commands") or [])
    code_errors = _check_code(cmds) if cmds else []
    ident = None
    if not token:
        if not is_clone:
            raise ApiError("Enter your bot token to continue.", 400)
    else:
        ident = fetch_identity(token)
    with appdb.read() as c:
        if token and appdb.one(c, "SELECT id FROM bots WHERE token=?", (security.encrypt(token),)) is not None:
            raise ApiError("This bot is already added.", 409)
        # encrypted values are salted: compare by decrypting candidates with the same numeric id
        if ident:
            for r in appdb.rows(c, "SELECT id,token FROM bots WHERE bot_numeric_id=?", (ident["id"],)):
                raise ApiError("This bot is already added to an account.", 409)
    plans.check_bots(uid)
    left = appdb.charge_points(uid, BOT_COST)
    if left is None:
        raise ApiError(f"Adding a bot needs {BOT_COST} points. You don't have enough.", 402)
    bid = appdb.new_id("bot_", 8)
    now = appdb.now_iso()
    cat = body.get("category") if body.get("category") in CATEGORIES else "Operations"
    folder = security.clean_text(body.get("folder"), 80)
    try:
        with appdb.db() as c:
            if folder:
                c.execute("INSERT OR IGNORE INTO folders (id,user_id,name,created_at) VALUES (?,?,?,?)", (appdb.new_id("fld_", 4), uid, folder, now))
            c.execute(
                "INSERT INTO bots (id,user_id,bot_numeric_id,username,name,status,active_users,total_commands,category,last_active,uptime,version,folder,"
                "is_pinned,photo_url,webhook_url,token,faster_response,auto_translate,mini_app_title,mini_app_url,description,commands_json,env_vars_json,"
                "errors_json,created_at,updated_at) VALUES (?,?,?,?,?,?,0,?,?,?,'','v1.0.0',?,0,?,NULL,?,1,0,?,?,?,?,?,'[]',?,?)",
                (bid, uid, (ident or {}).get("id") or bid, (ident or {}).get("username") or security.clean_text(body.get("username"), 64) or "",
                 (ident or {}).get("name") or security.clean_text(body.get("name"), 80) or "New bot",
                 "stopped" if ident else "cloned", len(cmds), cat, now, folder, (ident or {}).get("photo") or "",
                 security.encrypt(token), security.clean_text(body.get("miniAppTitle"), 80), security.clean_text(body.get("miniAppUrl"), 300),
                 security.clean_text(body.get("description"), 500), json.dumps(cmds), security.encrypt(json.dumps(_clean_env(body.get("envVars")))), now, now))
    except Exception:
        with appdb.db() as c:
            c.execute("UPDATE users SET points=points+? WHERE id=?", (BOT_COST, uid))
        raise
    try:
        runtime.sync_bot(bid)
    except Exception:
        pass
    if ident:
        try:
            runtime.set_running(bid, True)
        except Exception:
            pass
    try:
        appdb.notify(uid, "Bot added", f"{(ident or {}).get('name') or 'Your bot'} is ready.", "success", "bot:" + bid)
    except Exception:
        pass
    # Lightweight response after insert — never fail the request because of secondary reads
    try:
        out = bot_dict(own_bot(uid, bid), with_details=False)
    except Exception:
        out = {
            "id": bid,
            "botNumericId": (ident or {}).get("id") or bid,
            "username": (ident or {}).get("username") or "",
            "name": (ident or {}).get("name") or "New bot",
            "status": "working" if ident else "stopped",
            "activeUsers": 0,
            "totalCommands": 0,
            "category": cat,
            "folder": folder or "",
            "isPinned": False,
            "photoUrl": (ident or {}).get("photo") or "",
            "hasToken": bool(token),
            "commands": [],
            "envVars": [],
            "errors": [],
        }
    out["codeErrors"] = code_errors
    return out


def update_bot(uid: str, bot_id: str, body: dict, strict: bool = False) -> dict:
    b = own_bot(uid, bot_id)
    sets, args = [], []

    def put(col, val):
        sets.append(f"{col}=?")
        args.append(val)
    if "name" in body and security.clean_text(body["name"], 80):
        put("name", security.clean_text(body["name"], 80))
    if "version" in body:
        put("version", security.clean_text(body["version"], 30) or "v1.0.0")
    if "folder" in body:
        f = security.clean_text(body["folder"], 80)
        put("folder", f)
        if f:
            with appdb.db() as c:
                c.execute("INSERT OR IGNORE INTO folders (id,user_id,name,created_at) VALUES (?,?,?,?)", (appdb.new_id("fld_", 4), uid, f, appdb.now_iso()))
    if "isPinned" in body:
        put("is_pinned", 1 if body["isPinned"] else 0)
    if "description" in body:
        put("description", security.clean_text(body["description"], 500))
    if "category" in body and body["category"] in CATEGORIES:
        put("category", body["category"])
    if "miniAppTitle" in body:
        put("mini_app_title", security.clean_text(body["miniAppTitle"], 80))
    if "miniAppUrl" in body:
        put("mini_app_url", security.clean_text(body["miniAppUrl"], 300))
    restart = False
    code_errors = []
    if "fasterResponse" in body:
        put("faster_response", 1 if body["fasterResponse"] else 0)
        restart = True
    if "autoTranslate" in body:
        put("auto_translate", 1 if body["autoTranslate"] else 0)
    if body.get("commands") is not None:
        cmds = _clean_commands(body["commands"])
        plans.check_commands(uid, len(cmds))
        code_errors = _check_code(cmds)
        if strict and code_errors:         # the TBC-compatible v2 API refuses code that does not compile; the web editor always saves
            f = code_errors[0]
            raise ApiError(f"{f['command']} · line {f['line']}: {f['message']}", 400, {"errors": code_errors[:20]})
        put("commands_json", json.dumps(cmds))
        try:
            from backend import perf_cache
            perf_cache.invalidate(perf_cache.bot_commands_key(bot_id))
            perf_cache.invalidate(perf_cache.bot_meta_key(bot_id))
        except Exception:
            pass
        put("total_commands", len(cmds))
        try:        # warn at once when a key / token / seed phrase is pasted into code
            from backend import security_center
            if security_center.scan_bot_code(cmds):
                security_center.check_secrets(uid)
        except Exception:
            pass
    if body.get("envVars") is not None:
        put("env_vars_json", security.encrypt(json.dumps(_clean_env(body["envVars"]))))
    tok = body.get("token")
    if isinstance(tok, str) and tok.strip() and "•" not in tok:
        tok = tok.strip()
        ident = fetch_identity(tok)
        with appdb.read() as c:
            other = appdb.one(c, "SELECT id FROM bots WHERE bot_numeric_id=? AND id!=?", (ident["id"], bot_id))
        if other:
            raise ApiError("This bot is already added to an account.", 409)
        put("token", security.encrypt(tok))
        try:
            from backend import security_center
            security_center.note_token_change(uid, bot_id)
        except Exception:
            pass
        put("bot_numeric_id", ident["id"])
        put("username", ident["username"])
        put("name", ident["name"])
        put("photo_url", ident["photo"])
        if b["status"] == "cloned":
            put("status", "stopped")
        restart = True
    if sets:
        put("updated_at", appdb.now_iso())
        with appdb.db() as c:
            c.execute(f"UPDATE bots SET {', '.join(sets)} WHERE id=? AND user_id=?", (*args, bot_id, uid))
    runtime.sync_bot(bot_id)
    if restart:
        runtime.restart_if_running(bot_id)
    out = bot_dict(own_bot(uid, bot_id))
    out["codeErrors"] = code_errors
    return out


def toggle_bot(uid: str, bot_id: str) -> dict:
    b = own_bot(uid, bot_id)
    if not b["token"]:
        raise ApiError("Add the bot token first.", 400)
    want = not (b["status"] == "working" and runtime.is_running(bot_id))
    res = runtime.set_running(bot_id, want)
    if not res.get("ok"):
        raise ApiError(res.get("error") or "Couldn't change the bot state.", res.get("status") or 400)
    b = own_bot(uid, bot_id)
    appdb.notify(uid, "Bot " + ("started" if want else "stopped"), f"{b['name']} is now {'running' if want else 'stopped'}.", "info", "bot:" + bot_id)
    try:
        from backend import connect_bot
        connect_bot.alert(uid, "botStartStop", f"{'🟢' if want else '⚪️'} {b['name']} {'started' if want else 'stopped'}.")
    except Exception:
        pass
    d = bot_dict(b, with_details=False)
    return {"id": bot_id, "status": d["status"], "uptime": d["uptime"], "activeUsers": d["activeUsers"]}


def sync_telegram(uid: str, bot_id: str) -> dict:
    b = own_bot(uid, bot_id)
    tok = security.decrypt(b["token"] or "")
    if not tok:
        raise ApiError("This bot has no token yet.", 400)
    ident = fetch_identity(tok)
    with appdb.db() as c:
        c.execute("UPDATE bots SET name=?, username=?, bot_numeric_id=?, photo_url=?, updated_at=? WHERE id=?",
                  (ident["name"], ident["username"], ident["id"], ident["photo"], appdb.now_iso(), bot_id))
    runtime.sync_bot(bot_id)
    nb = own_bot(uid, bot_id)
    return {"success": True, "id": bot_id, "name": nb["name"], "username": nb["username"], "photoUrl": _photo_url(nb),
            "botNumericId": nb["bot_numeric_id"]}


def delete_bot(uid: str, bot_id: str) -> dict:
    b = own_bot(uid, bot_id)
    runtime.stop_worker(bot_id)
    data = dict(b)
    with appdb.db() as c:
        c.execute("INSERT OR REPLACE INTO recycle_bin (id,item_type,data_json,deleted_at,user_id) VALUES (?, 'bot', ?, ?, ?)",
                  (bot_id, json.dumps(data), appdb.now_iso(), uid))
        c.execute("DELETE FROM bots WHERE id=? AND user_id=?", (bot_id, uid))
    runtime.drop_engine_bot(bot_id)
    return {"success": True, "id": bot_id}


def recycle_list(uid: str) -> list:
    out = []
    with appdb.read() as c:
        for r in appdb.rows(c, "SELECT * FROM recycle_bin WHERE user_id=? ORDER BY deleted_at DESC", (uid,)):
            d = appdb.jload(r["data_json"], {})
            cmds = appdb.jload(d.get("commands_json"), [])
            out.append({"id": r["id"], "name": d.get("name"), "username": d.get("username"), "botNumericId": d.get("bot_numeric_id"),
                        "status": "stopped", "category": d.get("category"), "version": d.get("version"), "folder": d.get("folder") or "",
                        "photoUrl": f"/api/avatar/{r['id']}.svg", "totalCommands": len(cmds), "activeUsers": 0,
                        "lastActive": "", "uptime": "", "deletedAt": r["deleted_at"], "inRecycleBin": True})
    return out


def recycle_restore(uid: str, item_id: str) -> dict:
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM recycle_bin WHERE id=? AND user_id=?", (item_id, uid))
        if not r:
            raise ApiError("Item not found in the recycle bin.", 404)
        d = appdb.jload(r["data_json"], {})
        if appdb.one(c, "SELECT id FROM bots WHERE id=?", (item_id,)):
            raise ApiError("This bot already exists.", 409)
        cols = [k for k in d.keys() if re.fullmatch(r"[a-z_]+", k)]
        d["user_id"], d["status"], d["uptime"] = uid, ("stopped" if d.get("token") else "cloned"), ""
        d["updated_at"] = appdb.now_iso()
        c.execute(f"INSERT INTO bots ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [d[k] for k in cols])
        c.execute("DELETE FROM recycle_bin WHERE id=?", (item_id,))
    runtime.sync_bot(item_id)
    return {"success": True, "restored": bot_dict(own_bot(uid, item_id), with_details=False)}


def recycle_purge(uid: str, item_id: str) -> dict:
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM recycle_bin WHERE id=? AND user_id=?", (item_id, uid))
        if not r:
            raise ApiError("Item not found in the recycle bin.", 404)
        dt = appdb.parse_iso(r["deleted_at"])
        if dt:
            days = (appdb.utcnow() - dt).total_seconds() / 86400
            if days < 10:
                left = max(1, int(10 - days))
                raise ApiError(f"Safety hold: this bot can be deleted for good in {left} more day(s).", 400,
                               {"daysRemaining": left, "deletedAt": r["deleted_at"]})
        c.execute("DELETE FROM recycle_bin WHERE id=?", (item_id,))
    return {"success": True, "deleted": item_id}


# ------------------------------------------------------------------ chats
def chat_list(uid: str, bot_id: str, q: dict) -> dict:
    own_bot(uid, bot_id)
    try:
        page = max(1, int(q.get("page") or 1))
        limit = min(1000, max(1, int(q.get("limit") or 20)))
    except Exception:
        page, limit = 1, 20
    search = security.clean_text(q.get("search"), 60).lower()
    flt = (q.get("filter") or "all").lower()
    where, args = ["bot_id=?"], [bot_id]
    if search:
        where.append("(lower(name) LIKE ? OR lower(username) LIKE ? OR telegram_id LIKE ?)")
        args += [f"%{search}%"] * 3
    if flt == "blocked":
        where.append("is_blocked=1")
    elif flt in ("active", "unblocked"):
        where.append("is_blocked=0 AND bot_blocked=0")
    elif flt in ("left", "leftbot"):
        where.append("bot_blocked=1")
    w = " AND ".join(where)
    with appdb.read() as c:
        total = appdb.one(c, f"SELECT COUNT(*) n FROM chats WHERE {w}", args)["n"]
        rows = appdb.rows(c, f"SELECT * FROM chats WHERE {w} ORDER BY last_active DESC LIMIT ? OFFSET ?", (*args, limit, (page - 1) * limit))
        cnt = appdb.one(c, "SELECT COUNT(*) a, SUM(CASE WHEN is_blocked=1 THEN 1 ELSE 0 END) b, SUM(CASE WHEN bot_blocked=1 THEN 1 ELSE 0 END) l FROM chats WHERE bot_id=?", (bot_id,))
    users = [{"id": r["id"], "telegramId": r["telegram_id"], "name": r["name"] or "", "username": r["username"] or "",
              "languageCode": r["language_code"] or "", "firstSeen": r["first_seen"] or "", "botBlocked": bool(r["bot_blocked"]),
              "avatarColor": r["avatar_color"] or "blue", "photoUrl": f"/api/media/chat/{bot_id}/{r['telegram_id']}", "lastActive": r["last_active"] or "",
              "lastMessage": r["last_message"] or "", "isBlocked": bool(r["is_blocked"]), "messagesCount": r["messages_count"] or 0} for r in rows]
    return {"users": users, "total": total, "page": page, "totalPages": max(1, -(-total // limit)),
            "counts": {"all": cnt["a"] or 0, "blocked": cnt["b"] or 0, "active": max(0, (cnt["a"] or 0) - (cnt["b"] or 0) - (cnt["l"] or 0)), "leftBot": cnt["l"] or 0}}


def chat_block(uid: str, bot_id: str, chat_row_id: str) -> dict:
    own_bot(uid, bot_id)
    with appdb.db() as c:
        r = appdb.one(c, "SELECT id,is_blocked FROM chats WHERE bot_id=? AND (id=? OR telegram_id=?)", (bot_id, chat_row_id, chat_row_id))
        if not r:
            raise ApiError("User not found", 404)
        nv = 0 if r["is_blocked"] else 1
        c.execute("UPDATE chats SET is_blocked=? WHERE id=?", (nv, r["id"]))
    return {"success": True, "isBlocked": bool(nv)}


def chat_send(uid: str, bot_id: str, who: str, text: str) -> dict:
    b = own_bot(uid, bot_id)
    text = security.clean_text(text, 4096)
    if not text:
        raise ApiError("Write a message first.", 400)
    with appdb.read() as c:
        r = appdb.one(c, "SELECT telegram_id FROM chats WHERE bot_id=? AND (id=? OR telegram_id=?)", (bot_id, who, who))
    if not r:
        raise ApiError("User not found", 404)
    if security.rate_limit(f"send:{uid}", 60, 60):
        raise ApiError("You're sending too fast. Wait a moment.", 429)
    try:
        tg.call(security.decrypt(b["token"]), "sendMessage", {"chat_id": int(r["telegram_id"]), "text": text})
    except tg.TgError as e:
        raise ApiError("Couldn't deliver: " + ("the user blocked this bot." if e.blocked else e.description), 400)
    return {"success": True}


_HIDDEN = ("__", "secret:")


def _dec(v):
    """stored value (JSON text) -> (display text, type)"""
    v = v if isinstance(v, str) else ("" if v is None else str(v))
    try:
        j = json.loads(v)
    except Exception:
        return v, "string"
    if isinstance(j, bool):
        return ("true" if j else "false"), "boolean"
    if isinstance(j, (int, float)):
        return v, "number"
    if isinstance(j, str):
        return j, "string"
    if j is None:
        return "null", "string"
    return json.dumps(j, ensure_ascii=False, indent=2), "json"


def _enc(text: str, typ: str) -> str:
    text = "" if text is None else str(text)
    if typ == "number":
        try:
            n = float(text)
        except ValueError:
            raise ApiError("That is not a valid number.", 400)
        return json.dumps(int(n) if n.is_integer() and "." not in text and "e" not in text.lower() else n)
    if typ == "boolean":
        if text.strip().lower() not in ("true", "false"):
            raise ApiError("A boolean must be true or false.", 400)
        return json.dumps(text.strip().lower() == "true")
    if typ == "json":
        try:
            return json.dumps(json.loads(text), ensure_ascii=False)
        except ValueError:
            raise ApiError("That is not valid JSON.", 400)
    return json.dumps(text, ensure_ascii=False)


def kv_data(uid: str, bot_id: str, q: dict | None = None) -> dict:
    """Real bot database: bot-wide keys (bot.saveData) and per-user keys (user.saveData), paged + searchable."""
    own_bot(uid, bot_id)
    q = q or {}
    scope = "user" if q.get("scope") == "user" else "bot"
    try:
        page = max(1, int(q.get("page") or 1))
        limit = min(1000, max(1, int(q.get("limit") or 25)))
    except Exception:
        page, limit = 1, 25
    search = security.clean_text(q.get("search"), 80)
    from sqlalchemy import or_, and_
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        pk = runtime.engine_pk(bot_id, db)
        if not pk:
            return {"scope": scope, "rows": [], "total": 0, "page": 1, "totalPages": 1, "counts": {"bot": 0, "user": 0, "users": 0}}
        hidden = lambda col: and_(*[~col.startswith(h, autoescape=True) for h in _HIDDEN])
        bq = db.query(em.BotData).filter(em.BotData.bot_id == pk, hidden(em.BotData.key))
        uq = db.query(em.UserData).filter(em.UserData.bot_id == pk, hidden(em.UserData.key))
        counts = {"bot": bq.count(), "user": uq.count(), "users": db.query(em.UserData.telegram_user_id).filter(em.UserData.bot_id == pk).distinct().count()}
        if scope == "bot":
            qq = bq
            if search:
                qq = qq.filter(or_(em.BotData.key.ilike(f"%{search}%"), em.BotData.value.ilike(f"%{search}%")))
            total = qq.count()
            rows = qq.order_by(em.BotData.key).offset((page - 1) * limit).limit(limit).all()
            out = []
            for r in rows:
                val, typ = _dec(r.value)
                out.append({"id": str(r.id), "key": r.key, "value": val[:20000], "type": typ})
        else:
            qq = uq
            if q.get("userId"):
                qq = qq.filter(em.UserData.telegram_user_id == int(q["userId"])) if str(q["userId"]).isdigit() else qq
            if search:
                qq = qq.filter(or_(em.UserData.key.ilike(f"%{search}%"), em.UserData.value.ilike(f"%{search}%")))
            total = qq.count()
            rows = qq.order_by(em.UserData.telegram_user_id, em.UserData.key).offset((page - 1) * limit).limit(limit).all()
            ids = [str(r.telegram_user_id) for r in rows]
            names = {}
            if ids:
                with appdb.read() as c:
                    for r in c.execute(f"SELECT telegram_id,name,username FROM chats WHERE bot_id=? AND telegram_id IN ({','.join('?' * len(ids))})", (bot_id, *ids)):
                        names[r["telegram_id"]] = (r["name"], r["username"])
            out = []
            for r in rows:
                val, typ = _dec(r.value)
                nm = names.get(str(r.telegram_user_id), ("", ""))
                out.append({"id": str(r.id), "userId": str(r.telegram_user_id), "name": nm[0] or "", "username": nm[1] or "",
                            "key": r.key, "value": val[:20000], "type": typ})
        return {"scope": scope, "rows": out, "total": total, "page": page, "totalPages": max(1, -(-total // limit)), "counts": counts}
    finally:
        db.close()


def kv_set(uid: str, bot_id: str, body: dict) -> dict:
    own_bot(uid, bot_id)
    scope = "user" if body.get("scope") == "user" else "bot"
    key = security.clean_text(body.get("key"), 200)
    if not key:
        raise ApiError("A key is required.", 400)
    if key.startswith(_HIDDEN):
        raise ApiError("That key is reserved by the platform.", 400)
    val = _enc(body.get("value"), body.get("type") or "string")
    if len(val) > 400_000:
        raise ApiError("That value is too large.", 400)
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        pk = runtime.engine_pk(bot_id, db)
        if not pk:
            raise ApiError("Start the bot once so its database exists.", 400)
        if scope == "bot":
            row = db.query(em.BotData).filter_by(bot_id=pk, key=key).first()
            if row:
                row.value = val
            else:
                db.add(em.BotData(bot_id=pk, key=key, value=val))
        else:
            tid = str(body.get("userId") or "")
            if not tid.lstrip("-").isdigit():
                raise ApiError("A Telegram user ID is required.", 400)
            row = db.query(em.UserData).filter_by(bot_id=pk, telegram_user_id=int(tid), key=key).first()
            if row:
                row.value = val
            else:
                db.add(em.UserData(bot_id=pk, telegram_user_id=int(tid), key=key, value=val))
        db.commit()
    finally:
        db.close()
    return {"success": True}


def kv_delete(uid: str, bot_id: str, q: dict) -> dict:
    own_bot(uid, bot_id)
    scope = "user" if q.get("scope") == "user" else "bot"
    key = security.clean_text(q.get("key"), 200)
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        pk = runtime.engine_pk(bot_id, db)
        if not pk or not key:
            raise ApiError("Not found.", 404)
        if scope == "bot":
            n = db.query(em.BotData).filter_by(bot_id=pk, key=key).delete()
        else:
            tid = str(q.get("userId") or "")
            if not tid.lstrip("-").isdigit():
                raise ApiError("A Telegram user ID is required.", 400)
            n = db.query(em.UserData).filter_by(bot_id=pk, telegram_user_id=int(tid), key=key).delete()
        db.commit()
    finally:
        db.close()
    if not n:
        raise ApiError("Not found.", 404)
    return {"success": True}


def folders(uid):
    with appdb.read() as c:
        return [r["name"] for r in appdb.rows(c, "SELECT name FROM folders WHERE user_id=? ORDER BY name", (uid,))]


def add_folder(uid, name):
    name = security.clean_text(name, 80)
    if not name:
        raise ApiError("Folder name is required", 400)
    with appdb.db() as c:
        c.execute("INSERT OR IGNORE INTO folders (id,user_id,name,created_at) VALUES (?,?,?,?)", (appdb.new_id("fld_", 4), uid, name, appdb.now_iso()))
    return folders(uid)


def admins(uid):
    with appdb.read() as c:
        return [r["telegram_id"] for r in appdb.rows(c, "SELECT telegram_id FROM global_admins WHERE user_id=? ORDER BY added_at", (uid,))]


def add_admin(uid, tid):
    tid = security.clean_text(tid, 20)
    if not tid.isdigit():
        raise ApiError("Enter a numeric Telegram ID.", 400)
    if len(admins(uid)) >= 20:
        raise ApiError("Maximum 20 global administrators allowed", 400)
    with appdb.db() as c:
        c.execute("INSERT OR IGNORE INTO global_admins (user_id,telegram_id,added_at) VALUES (?,?,?)", (uid, tid, appdb.now_iso()))
    return admins(uid)


def remove_admin(uid, tid):
    with appdb.db() as c:
        c.execute("DELETE FROM global_admins WHERE user_id=? AND telegram_id=?", (uid, tid))
    return admins(uid)


# ------------------------------------------------------------------ store
def store_list():
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT s.*, u.name AS author_n, u.email AS author_e FROM store_bots s LEFT JOIN users u ON u.id=s.owner_id ORDER BY forks DESC LIMIT 200")
    out = []
    for r in rows:
        cmds = appdb.jload(r["commands_json"], [])
        desc = r["description"] or ""
        out.append({
            "id": r["id"], "name": r["name"], "username": r["username"] or "", "description": desc, "shortDesc": desc[:140], "about": desc,
            "rating": r["rating"] or 0, "stars": 0, "forks": r["forks"] or 0, "clones": r["forks"] or 0, "category": r["category"] or "Utilities",
            "tags": appdb.jload(r["tags_json"], []), "commandsCount": len(cmds), "author": r["author_name"] or r["author_n"] or "Community",
            "authorEmail": "", "authorType": "Community", "isVerified": False, "price": 0, "priceDisplay": "Free",
            "version": r["version"] or "v1.0.0", "avatarUrl": "", "keyFeatures": [c.get("name") for c in cmds[:6] if c.get("name")],
            "aiOverview": {"summary": desc, "faqs": []}, "similarBots": [], "commands": [{"name": c.get("name")} for c in cmds],
            "botPayload": {"name": r["name"], "category": r["category"] or "Utilities", "totalCommands": len(cmds), "version": r["version"] or "v1.0.0"},
        })
    return out


def store_clone(uid, sid):
    with appdb.read() as c:
        s = appdb.one(c, "SELECT * FROM store_bots WHERE id=?", (sid,))
    if not s:
        raise ApiError("Bot not found in the store.", 404)
    cmds = appdb.jload(s["commands_json"], [])
    with appdb.db() as c:
        c.execute("UPDATE store_bots SET forks=forks+1 WHERE id=?", (sid,))
    bot = create_bot(uid, {"name": s["name"], "isClone": True, "category": s["category"], "commands": cmds,
                           "description": s["description"], "folder": ""})
    with appdb.db() as c:
        c.execute("UPDATE bots SET origin='store' WHERE id=?", (bot["id"],))
    return {"success": True, "bot": bot}


def store_publish(uid, body):
    plans.require(uid, "storePublish", "Publishing to the Bot Store")
    b = own_bot(uid, str(body.get("botId") or ""))
    with appdb.read() as c:
        u = appdb.one(c, "SELECT name FROM users WHERE id=?", (uid,))
    cmds = [{"id": x.get("id"), "name": x.get("name"), "code": x.get("code")} for x in appdb.jload(b["commands_json"], [])]
    if not cmds:
        raise ApiError("Add at least one command before publishing.", 400)
    sid = appdb.new_id("st_", 6)
    tags = [security.clean_text(t, 30) for t in (body.get("tags") or [])[:8]]
    with appdb.db() as c:
        c.execute("INSERT INTO store_bots (id,name,username,description,rating,forks,category,tags_json,commands_count,author_name,version,avatar_url,commands_json,owner_id)"
                  " VALUES (?,?,?,?,0,0,?,?,?,?,?,'',?,?)",
                  (sid, b["name"], "", security.clean_text(body.get("description") or b["description"], 600), body.get("category") or b["category"],
                   json.dumps(tags), len(cmds), u["name"], b["version"], json.dumps(cmds), uid))
    return {"success": True, "id": sid}


# ------------------------------------------------------------------ transfers
def _settings(uid) -> dict:
    with appdb.read() as c:
        r = appdb.one(c, "SELECT settings_json FROM settings WHERE user_id=?", (uid,))
    return appdb.jload(r["settings_json"], {}) if r else {}


def transfer_limit(uid) -> dict:
    st = _settings(uid)
    try:
        lim = int(st.get("outgoingLimit") or 10)
    except Exception:
        lim = 10
    lim = max(1, min(50, lim))
    since = appdb.iso_in(minutes=-10)
    with appdb.read() as c:
        used = appdb.one(c, "SELECT COUNT(*) n FROM transfers WHERE from_user_id=? AND created_at>=?", (uid, since))["n"]
        pend = appdb.one(c, "SELECT COUNT(*) n FROM transfers WHERE from_user_id=? AND status='pending'", (uid,))["n"]
    return {"perTenMinutes": lim, "used": used, "remaining": max(0, lim - used), "maxPendingOutgoing": PENDING_MAX, "pending": pend}


def _tdict(r, me) -> dict:
    return {"id": r["id"], "botId": r["bot_id"], "botName": r["bot_name"], "botUsername": r["bot_username"], "botNumericId": r["bot_numeric_id"],
            "fromEmail": r["from_email"], "toEmail": r["to_email"], "senderEmail": r["from_email"], "recipientEmail": r["to_email"],
            "status": r["status"], "type": "outgoing" if r["from_user_id"] == me else "incoming",
            "direction": "outgoing" if r["from_user_id"] == me else "incoming",
            "createdAt": r["created_at"], "expiresAt": r["expires_at"], "respondedAt": r["responded_at"],
            "verificationToken": (r["verification_token"] or "")[:12], "commandsCount": r["cmds"] if "cmds" in r.keys() else 0, "foldersCount": 0}


def _expire():
    with appdb.db() as c:
        c.execute("UPDATE transfers SET status='expired' WHERE status='pending' AND expires_at<?", (appdb.now_iso(),))


def transfers_overview(uid) -> dict:
    _expire()
    since = appdb.iso_in(days=-30)
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT t.*, 0 AS cmds FROM transfers t WHERE (from_user_id=? OR to_user_id=?) AND created_at>=? ORDER BY created_at DESC", (uid, uid, since))
    items = [_tdict(r, uid) for r in rows]
    with appdb.read() as c:
        for it in items:
            b = appdb.one(c, "SELECT commands_json FROM bots WHERE id=?", (it["botId"],))
            it["commandsCount"] = len(appdb.jload(b["commands_json"], [])) if b else 0
    return {"incoming": [i for i in items if i["direction"] == "incoming" and i["status"] == "pending"],
            "outgoing": [i for i in items if i["direction"] == "outgoing" and i["status"] == "pending"],
            "history": [i for i in items if i["status"] != "pending"], "limits": transfer_limit(uid)}


TRANSFER_PARTS = ("data", "chats", "errors", "env")


def _transfer_opts(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {k: bool(raw.get(k)) for k in TRANSFER_PARTS}


def _copy_into_clone(src_id: str, dst_id: str, opts: dict) -> None:
    """Copy the ticked parts of a bot into its clone. The original stays untouched."""
    from backend import models as em
    from backend.database import SessionLocal
    with appdb.db() as c:
        if opts.get("data"):
            for r in appdb.rows(c, "SELECT record_key,record_value,value_type,updated_at FROM bot_kv WHERE bot_id=?", (src_id,)):
                c.execute("INSERT OR REPLACE INTO bot_kv (bot_id,record_key,record_value,value_type,updated_at) VALUES (?,?,?,?,?)",
                          (dst_id, r["record_key"], r["record_value"], r["value_type"], r["updated_at"]))
        if opts.get("chats"):
            n = 0
            for r in appdb.rows(c, "SELECT * FROM chats WHERE bot_id=?", (src_id,)):
                c.execute("INSERT INTO chats (id,bot_id,telegram_id,name,username,avatar_color,photo_url,last_active,last_message,is_blocked,messages_count)"
                          " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (appdb.new_id("chat_", 8), dst_id, r["telegram_id"], r["name"], r["username"], r["avatar_color"], "",
                           r["last_active"], r["last_message"], r["is_blocked"], r["messages_count"]))
                n += 1
            c.execute("UPDATE bots SET active_users=? WHERE id=?", (n, dst_id))
    db = SessionLocal()
    try:
        spk, dpk = runtime.engine_pk(src_id, db), runtime.engine_pk(dst_id, db)
        if spk is not None and dpk is not None:
            models_ = []
            if opts.get("data"):
                models_ += [em.BotData, em.UserData, em.UserState, em.Resource]
            if opts.get("errors"):
                models_.append(em.ErrorLog)
            if opts.get("chats"):
                models_.append(em.BotMember)
            for m in models_:
                try:
                    cols = [c.key for c in m.__table__.columns if c.key not in ("id", "bot_id")]
                    for row in db.query(m).filter_by(bot_id=spk).all():
                        db.add(m(bot_id=dpk, **{k: getattr(row, k) for k in cols}))
                    db.commit()
                except Exception:
                    db.rollback()
    finally:
        db.close()


def start_transfer(uid: str, bot_id: str, email: str, auto_ok: bool = True, options=None) -> dict:
    plans.require(uid, "botTransfer", "Sending a bot copy")
    email = security.clean_text(email, 200).lower()
    b = own_bot(uid, bot_id)
    if not security.valid_email(email):
        raise ApiError("Enter a valid email address.", 400)
    with appdb.read() as c:
        me = appdb.one(c, "SELECT id,email FROM users WHERE id=?", (uid,))
        to = appdb.one(c, "SELECT id,email FROM users WHERE email=?", (email,))
    if not to:
        raise ApiError("No account found with that email.", 404)
    if to["id"] == uid:
        raise ApiError("You can't transfer a bot to yourself.", 400)
    lim = transfer_limit(uid)
    if lim["remaining"] <= 0:
        raise ApiError(f"Transfer limit reached ({lim['perTenMinutes']} per 10 minutes). Try again a little later.", 429)
    if lim["pending"] >= PENDING_MAX:
        raise ApiError("You have too many pending transfers.", 429)
    cfg = _settings(to["id"])
    mode = cfg.get("transferConfig") or "open"
    wl = [str(x).lower() for x in (cfg.get("senderWhitelist") or [])]
    whitelisted = me["email"].lower() in wl
    if mode == "disabled":
        raise ApiError("That account isn't accepting bot transfers.", 400)
    if mode == "whitelist_only" and not whitelisted:
        raise ApiError("That account only accepts transfers from approved senders.", 400)
    with appdb.db() as c:
        if appdb.one(c, "SELECT id FROM transfers WHERE bot_id=? AND to_user_id=? AND status='pending'", (bot_id, to["id"])):
            raise ApiError("You already sent this bot to that account and it is waiting to be accepted.", 409)
        tid = appdb.new_id("tr_", 8)
        c.execute("INSERT INTO transfers (id,bot_id,bot_name,bot_username,bot_numeric_id,from_user_id,to_user_id,from_email,to_email,status,verification_token,created_at,expires_at,options_json)"
                  " VALUES (?,?,?,?,?,?,?,?,?, 'pending', ?, ?, ?, ?)",
                  (tid, bot_id, b["name"], b["username"], b["bot_numeric_id"], uid, to["id"], me["email"], to["email"],
                   security.token_hash(tid + appdb.now_iso()), appdb.now_iso(), appdb.iso_in(days=3), json.dumps(_transfer_opts(options))))
    appdb.notify(to["id"], "Bot transfer request", f"{me['email']} wants to send you a copy of “{b['name']}”.", "info", "tab:Transfers")
    try:
        from backend import connect_bot
        connect_bot.alert(to["id"], "botTransfers", f"🔁 {me['email']} wants to transfer “{b['name']}” to you. Open Transfers on the website to accept.")
    except Exception:
        pass
    if mode == "whitelist_auto" and whitelisted and auto_ok:
        return {"success": True, "transfer": accept_transfer(to["id"], tid, auto=True)}
    return {"success": True, "transfer": _tget(uid, tid)}


def _tget(uid, tid):
    with appdb.read() as c:
        r = appdb.one(c, "SELECT t.*, 0 AS cmds FROM transfers t WHERE id=? AND (from_user_id=? OR to_user_id=?)", (tid, uid, uid))
    if not r:
        raise ApiError("Transfer not found", 404)
    return _tdict(r, uid)


def accept_transfer(uid: str, tid: str, auto=False) -> dict:
    """A transfer is a clone: the sender keeps the bot, the receiver gets a copy WITHOUT the bot token."""
    _expire()
    plans.check_bots(uid)
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM transfers WHERE id=? AND to_user_id=?", (tid, uid))
        if not r:
            raise ApiError("Transfer not found", 404)
        if r["status"] != "pending":
            raise ApiError(f"This transfer is already {r['status']}.", 409)
        bot = appdb.one(c, "SELECT * FROM bots WHERE id=? AND user_id=?", (r["bot_id"], r["from_user_id"]))
        if not bot:
            c.execute("UPDATE transfers SET status='cancelled', responded_at=? WHERE id=?", (appdb.now_iso(), tid))
            raise ApiError("The bot is no longer available.", 409)
        opts = _transfer_opts(appdb.jload(r["options_json"] if "options_json" in r.keys() else "", {}))
        nid = appdb.new_id("bot_", 8)
        now = appdb.now_iso()
        env = bot["env_vars_json"] if opts.get("env") else "[]"
        errs = bot["errors_json"] if opts.get("errors") else "[]"
        c.execute(
            "INSERT INTO bots (id,user_id,bot_numeric_id,username,name,status,active_users,total_commands,category,last_active,uptime,version,folder,"
            "is_pinned,photo_url,webhook_url,token,faster_response,auto_translate,mini_app_title,mini_app_url,description,commands_json,env_vars_json,"
            "errors_json,created_at,updated_at,origin) VALUES (?,?,?,?,?,'cloned',0,?,?,?,'',?, '',0,'',NULL,'',?,?,?,?,?,?,?,?,?,?,'transfer')",
            (nid, uid, nid, "", bot["name"], bot["total_commands"], bot["category"], now, bot["version"], bot["faster_response"],
             bot["auto_translate"], bot["mini_app_title"], bot["mini_app_url"], bot["description"], bot["commands_json"], env, errs, now, now))
        c.execute("UPDATE transfers SET status='accepted', responded_at=? WHERE id=?", (now, tid))
    runtime.sync_bot(nid)
    _copy_into_clone(r["bot_id"], nid, opts)
    runtime.sync_bot(nid)
    appdb.notify(r["from_user_id"], "Transfer accepted", f"{r['to_email']} received a copy of “{r['bot_name']}”.", "success", "tab:Transfers")
    appdb.notify(uid, "Bot received", f"A copy of “{r['bot_name']}” was added to your account. Add your own bot token to start it.", "success", "bot:" + nid)
    try:
        from backend import connect_bot
        connect_bot.alert(r["from_user_id"], "botTransfers", f"✅ {r['to_email']} received a copy of “{r['bot_name']}”.")
        connect_bot.alert(uid, "botTransfers", f"📥 A copy of “{r['bot_name']}” was added. Add your own bot token to start it.")
    except Exception:
        pass
    return _tget(uid, tid)


def _finish(uid, tid, side, new_status, notify_title):
    _expire()
    col = "to_user_id" if side == "to" else "from_user_id"
    with appdb.db() as c:
        r = appdb.one(c, f"SELECT * FROM transfers WHERE id=? AND {col}=?", (tid, uid))
        if not r:
            raise ApiError("Transfer not found", 404)
        if r["status"] != "pending":
            raise ApiError(f"This transfer is already {r['status']}.", 409)
        c.execute("UPDATE transfers SET status=?, responded_at=? WHERE id=?", (new_status, appdb.now_iso(), tid))
    other = r["from_user_id"] if side == "to" else r["to_user_id"]
    appdb.notify(other, notify_title, f"“{r['bot_name']}” transfer was {new_status}.", "info", "tab:Transfers")
    return _tget(uid, tid)


def reject_transfer(uid, tid):
    return _finish(uid, tid, "to", "rejected", "Transfer rejected")


def cancel_transfer(uid, tid):
    return _finish(uid, tid, "from", "cancelled", "Transfer cancelled")


def _hook_transfer(db, acc, bot_public_id, email, **kw):
    """Called from bot code: Account.Transfer(...). Same rules and limit as the dashboard."""
    uid = (acc.email or "").split("@")[0]
    try:
        opts = {k: kw.get(f"include_{k}", True) for k in TRANSFER_PARTS}
        res = start_transfer(uid, str(bot_public_id), email, options=opts)
        tr = res["transfer"]
        return {"ok": True, "bot_id": str(bot_public_id), "new_owner": email, "transfer_id": tr.get("id"), "status": tr.get("status"),
                "expires_at": tr.get("expiresAt"), "transfer": tr, "error": None}
    except ApiError as e:
        return {"ok": False, "error": e.message}


def _hook_set_running(db, engine_bot, running):
    res = runtime.set_running(engine_bot.public_id, running)
    return {"ok": bool(res.get("ok")), "error": res.get("error")} if not res.get("ok") else {"ok": True}


def register_hooks():
    platform_hooks.register("transfer_bot", _hook_transfer)
    platform_hooks.register("set_running", _hook_set_running)


# ------------------------------------------------------------------ telegram connect
def telegram_status(uid) -> dict:
    from backend import connect_bot
    with appdb.read() as c:
        u = appdb.one(c, "SELECT * FROM users WHERE id=?", (uid,))
        total = appdb.one(c, "SELECT COUNT(*) n FROM bots WHERE user_id=?", (uid,))["n"]
        run = appdb.one(c, "SELECT COUNT(*) n FROM bots WHERE user_id=? AND status='working'", (uid,))["n"]
        bc = appdb.one(c, "SELECT id,title,status,sent_count,failed_count,total_target_users FROM broadcasts WHERE user_id=? AND status IN ('Active','Paused')", (uid,))
    conn = bool(u["telegram_connected"])
    bu = connect_bot.username()
    return {
        "connected": conn, "username": (u["telegram_username"] or "") if conn else "", "firstName": (u["telegram_first_name"] or "") if conn else "",
        "telegramId": str(u["telegram_chat_id"] or "") if conn else "", "connectedAt": u["telegram_connected_at"] if conn else None,
        "connectBotUsername": ("@" + bu) if bu else "", "connectBotLink": f"https://t.me/{bu}" if bu else "",
        "available": bool(bu), "alerts": connect_bot.alerts_of(u),
        "account": {"name": u["name"], "email": u["email"], "plan": u["plan"] or "Free", "points": int(u["points"] or 0), "botsTotal": total, "botsRunning": run,
                    "activeBroadcast": ({"id": bc["id"], "title": bc["title"], "status": bc["status"],
                                         "percent": int(100 * (bc["sent_count"] + bc["failed_count"]) / max(1, bc["total_target_users"]))} if bc else None)} if conn else None,
    }


# ------------------------------------------------------------------ dashboard
def dashboard(uid) -> dict:
    import datetime as _dt
    since = appdb.iso_in(hours=-48)
    d24 = appdb.iso_in(hours=-24)
    d7 = appdb.iso_in(days=-7)
    with appdb.read() as c:
        bl = appdb.rows(c, "SELECT id,name,username,status,photo_url,origin FROM bots WHERE user_id=?", (uid,))
        ids = [b["id"] for b in bl]
        aud = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id IN (SELECT id FROM bots WHERE user_id=?) AND bot_blocked=0", (uid,))["n"]
        blocked = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id IN (SELECT id FROM bots WHERE user_id=?) AND (bot_blocked=1 OR is_blocked=1)", (uid,))["n"]
        act24 = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id IN (SELECT id FROM bots WHERE user_id=?) AND last_active>=?", (uid, d24))["n"]
        act7 = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id IN (SELECT id FROM bots WHERE user_id=?) AND last_active>=?", (uid, d7))["n"]
        ev = appdb.rows(c, "SELECT bot_id, kind, tg_user, ts FROM events WHERE owner_id=? AND ts>=?", (uid, since))
        ms_list = [r["ms"] for r in c.execute("SELECT ms FROM events WHERE owner_id=? AND kind='command' AND ts>=? AND ms IS NOT NULL", (uid, d24))]
        bc = appdb.one(c, "SELECT COUNT(*) n FROM broadcasts WHERE user_id=? AND status IN ('Active','Paused')", (uid,))["n"]
        pts = appdb.one(c, "SELECT points FROM users WHERE id=?", (uid,))["points"]
    now = appdb.utcnow()
    buckets = {}
    for i in range(24):
        h = (now - _dt.timedelta(hours=23 - i)).replace(minute=0, second=0, microsecond=0)
        buckets[h.strftime("%Y-%m-%d %H")] = {"time": h.strftime("%H:00"), "ts": h.isoformat(timespec="seconds") + "Z", "users": set(), "commands": 0}
    ev24 = [e for e in ev if e["ts"] >= d24]
    for e in ev24:
        t = appdb.parse_iso(e["ts"])
        if not t:
            continue
        k = t.strftime("%Y-%m-%d %H")
        if k in buckets:
            if e["kind"] == "command":
                buckets[k]["commands"] += 1
            if e["kind"] == "message" and e["tg_user"]:
                buckets[k]["users"].add(e["tg_user"])
    act = [{"time": b["time"], "ts": b["ts"], "users": len(b["users"]), "commands": b["commands"]} for b in buckets.values()]
    new24 = sum(1 for e in ev24 if e["kind"] == "new_user")
    newprev = sum(1 for e in ev if e["kind"] == "new_user" and e["ts"] < d24)
    per = []
    for b in bl:
        mine = [e for e in ev24 if e["bot_id"] == b["id"]]
        users = len({e["tg_user"] for e in mine if e["kind"] == "message" and e["tg_user"]})
        per.append({"id": b["id"], "name": b["name"], "username": b["username"], "status": b["status"], "activeUsers24h": users,
                    "messages24h": sum(1 for e in mine if e["kind"] == "message"),
                    "commands24h": sum(1 for e in mine if e["kind"] == "command"),
                    "errors24h": sum(1 for e in mine if e["kind"] == "error")})
    per.sort(key=lambda r: (r["messages24h"], r["activeUsers24h"]), reverse=True)
    return {"totals": {"bots": len(bl), "running": sum(1 for b in bl if b["status"] == "working"), "audience": aud, "blocked": blocked,
                       "active24h": act24, "active7d": act7, "newUsers24h": new24, "newUsersPrev24h": newprev,
                       "retention7d": round(100 * act7 / aud, 1) if aud else None,
                       "growth24h": (round(100 * (new24 - newprev) / newprev, 1) if newprev else (100.0 if new24 else 0.0)),
                       "messages24h": sum(1 for e in ev24 if e["kind"] == "message"),
                       "commands24h": sum(1 for e in ev24 if e["kind"] == "command"),
                       "errors24h": sum(1 for e in ev24 if e["kind"] == "error"),
                       "broadcastsRunning": bc, "points": int(pts or 0),
                       "avgResponseMs": (round(sum(ms_list) / len(ms_list)) if ms_list else None),
                       "errorRate24h": round(100 * sum(1 for e in ev24 if e["kind"] == "error") / max(1, sum(1 for e in ev24 if e["kind"] == "command")), 1) if any(e["kind"] == "command" for e in ev24) else None,
                       "fromStore": sum(1 for b in bl if b["origin"] == "store"),
                       "transferredIn": sum(1 for b in bl if b["origin"] == "transfer")},
            "activity": act, "bots": per[:10], "serverTime": appdb.now_iso()}



# ------------------------------------------------------------------ admin tab (per bot)
_LANG_NAMES = {
    "en": "English", "ru": "Russian", "es": "Spanish", "pt": "Portuguese", "pt-br": "Portuguese (Brazil)", "ar": "Arabic", "fa": "Persian", "tr": "Turkish",
    "id": "Indonesian", "hi": "Hindi", "bn": "Bengali", "ur": "Urdu", "fr": "French", "de": "German", "it": "Italian", "uk": "Ukrainian", "vi": "Vietnamese",
    "th": "Thai", "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "zh-hans": "Chinese (Simplified)", "zh-hant": "Chinese (Traditional)", "pl": "Polish",
    "nl": "Dutch", "uz": "Uzbek", "kk": "Kazakh", "az": "Azerbaijani", "ms": "Malay", "ne": "Nepali", "si": "Sinhala", "ta": "Tamil", "te": "Telugu",
    "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "ro": "Romanian", "cs": "Czech", "el": "Greek", "he": "Hebrew", "hu": "Hungarian", "sv": "Swedish",
    "fi": "Finnish", "no": "Norwegian", "da": "Danish", "bg": "Bulgarian", "sr": "Serbian", "hr": "Croatian", "sk": "Slovak", "ka": "Georgian", "hy": "Armenian",
    "be": "Belarusian", "ky": "Kyrgyz", "tg": "Tajik", "tk": "Turkmen", "sw": "Swahili", "am": "Amharic", "ps": "Pashto", "ku": "Kurdish", "my": "Burmese",
    "km": "Khmer", "lo": "Lao", "fil": "Filipino", "ca": "Catalan", "af": "Afrikaans", "sq": "Albanian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian",
}


def _lang_name(code: str) -> str:
    c = (code or "").lower()
    return _LANG_NAMES.get(c) or _LANG_NAMES.get(c.split("-")[0]) or ("Unknown" if not c else c.upper())


def admin_overview(uid: str, bot_id: str, days: int = 7) -> dict:
    import datetime as _dt
    b = own_bot(uid, bot_id)
    days = days if days in (1, 7, 30) else 7
    since = appdb.iso_in(days=-days)
    d24, d7, d30 = appdb.iso_in(hours=-24), appdb.iso_in(days=-7), appdb.iso_in(days=-30)
    names = [c.get("name") for c in (appdb.jload(b["commands_json"], []) or []) if c.get("name")]
    with appdb.read() as c:
        ev = appdb.rows(c, "SELECT kind, cmd, ms, ts, tg_user FROM events WHERE bot_id=? AND ts>=?", (bot_id, since if days >= 30 else min(since, d30)))
        chats = appdb.rows(c, "SELECT language_code, first_seen, last_active, is_blocked, bot_blocked FROM chats WHERE bot_id=?", (bot_id,))
    evw = [e for e in ev if e["ts"] >= since]
    runs, errs, msum, last = {}, {}, {}, {}
    for e in evw:
        if e["kind"] == "command":
            k = e["cmd"] or "(unknown)"
            runs[k] = runs.get(k, 0) + 1
            if e["ms"] is not None:
                msum.setdefault(k, []).append(e["ms"])
            if e["ts"] > last.get(k, ""):
                last[k] = e["ts"]
        elif e["kind"] == "error":
            k = e["cmd"] or "(unknown)"
            errs[k] = errs.get(k, 0) + 1
    allk = list(dict.fromkeys(names + sorted(runs, key=lambda k: -runs[k]) + [k for k in errs if k not in runs]))
    top = max(runs.values()) if runs else 0
    commands = [{"name": k, "runs": runs.get(k, 0), "errors": errs.get(k, 0), "avgMs": round(sum(msum[k]) / len(msum[k])) if msum.get(k) else None,
                 "lastRun": last.get(k, ""), "percent": round(100 * runs.get(k, 0) / top) if top else 0,
                 "share": round(100 * runs.get(k, 0) / max(1, sum(runs.values())), 1), "defined": k in names} for k in allk]
    commands.sort(key=lambda r: (-r["runs"], r["name"]))
    # execution chart: hourly for 1 day, daily otherwise
    now = appdb.utcnow()
    series = []
    if days == 1:
        for i in range(24):
            h = (now - _dt.timedelta(hours=23 - i)).replace(minute=0, second=0, microsecond=0)
            series.append({"label": h.strftime("%H:00"), "key": h.strftime("%Y-%m-%d %H"), "commands": 0, "errors": 0})
        fmt = "%Y-%m-%d %H"
    else:
        for i in range(days):
            d = now - _dt.timedelta(days=days - 1 - i)
            series.append({"label": d.strftime("%b %d"), "key": d.strftime("%Y-%m-%d"), "commands": 0, "errors": 0})
        fmt = "%Y-%m-%d"
    idx = {s["key"]: s for s in series}
    for e in evw:
        t = appdb.parse_iso(e["ts"])
        s = idx.get(t.strftime(fmt)) if t else None
        if s:
            if e["kind"] == "command":
                s["commands"] += 1
            elif e["kind"] == "error":
                s["errors"] += 1
    tot_runs, tot_err = sum(runs.values()), sum(errs.values())
    all_ms = [m for v in msum.values() for m in v]
    # users
    def cnt(col, since_):
        return sum(1 for r in chats if (r[col] or "") >= since_)
    langs = {}
    for r in chats:
        code = (r["language_code"] or "").lower()
        langs[code] = langs.get(code, 0) + 1
    ltotal = max(1, len(chats))
    languages = sorted(({"code": k or "—", "name": _lang_name(k), "users": v, "percent": round(100 * v / ltotal, 1)} for k, v in langs.items()), key=lambda r: -r["users"])
    ugrow = []
    for i in range(30):
        d = now - _dt.timedelta(days=29 - i)
        ugrow.append({"label": d.strftime("%b %d"), "key": d.strftime("%Y-%m-%d"), "new": 0, "active": 0})
    gi = {g["key"]: g for g in ugrow}
    for r in chats:
        if r["first_seen"] and r["first_seen"][:10] in gi:
            gi[r["first_seen"][:10]]["new"] += 1
    seen = {}
    for e in ev:
        if e["kind"] == "message" and e["tg_user"] and e["ts"][:10] in gi:
            seen.setdefault(e["ts"][:10], set()).add(e["tg_user"])
    for k, v in seen.items():
        gi[k]["active"] = len(v)
    users = {
        "total": len(chats), "active24h": cnt("last_active", d24), "active7d": cnt("last_active", d7), "active30d": cnt("last_active", d30),
        "new24h": cnt("first_seen", d24), "new7d": cnt("first_seen", d7), "new30d": cnt("first_seen", d30),
        "blocked": sum(1 for r in chats if r["is_blocked"]), "left": sum(1 for r in chats if r["bot_blocked"]),
        "growth": ugrow, "languages": languages,
    }
    return {"days": days, "executions": {"total": tot_runs, "errors": tot_err, "errorRate": round(100 * tot_err / tot_runs, 1) if tot_runs else 0,
                                         "avgMs": round(sum(all_ms) / len(all_ms)) if all_ms else None, "series": series, "commands": commands},
            "users": users, "maintenance": runtime.maintenance_get(bot_id)}


def admin_maintenance_set(uid: str, bot_id: str, body: dict) -> dict:
    own_bot(uid, bot_id)
    on = bool(body.get("on"))
    msg = security.clean_text(body.get("message"), 500) or "🛠 This bot is under maintenance. Please try again soon."
    prev = runtime.maintenance_get(bot_id)
    since = prev["since"] if (on and prev["on"]) else (appdb.now_iso() if on else "")
    with appdb.db() as c:
        c.execute("INSERT OR REPLACE INTO platform_settings (key,value) VALUES (?,?)", (f"maint:{bot_id}", json.dumps({"on": on, "message": msg, "since": since})))
    return runtime.maintenance_get(bot_id)


def admin_action(uid: str, bot_id: str, action: str) -> dict:
    b = own_bot(uid, bot_id)
    action = str(action or "")
    if action == "restart":
        if not b["token"]:
            raise ApiError("Add the bot token first.", 400)
        runtime.set_running(bot_id, False)
        res = runtime.set_running(bot_id, True)
        if not res.get("ok"):
            raise ApiError(res.get("error") or "Couldn't restart the bot.", 400)
        return {"ok": True, "message": "Bot restarted."}
    if action == "clear-errors":
        clear_errors(uid, bot_id)
        return {"ok": True, "message": "Error log cleared."}
    if action == "reset-stats":
        with appdb.db() as c:
            n = c.execute("DELETE FROM events WHERE bot_id=?", (bot_id,)).rowcount
        return {"ok": True, "message": f"Execution statistics reset ({n} records)."}
    if action == "remove-left-users":
        with appdb.db() as c:
            n = c.execute("DELETE FROM chats WHERE bot_id=? AND bot_blocked=1", (bot_id,)).rowcount
        return {"ok": True, "message": f"Removed {n} users who left the bot."}
    if action == "stop-broadcasts":
        from backend import broadcast_service as _bc
        n = 0
        for r in _bc.list_for(uid):
            if r.get("status") in ("Active", "Paused") and bot_id in (r.get("targetBotIds") or []):
                try:
                    _bc.act(uid, r["id"], "cancel")
                    n += 1
                except Exception:
                    pass
        return {"ok": True, "message": f"Stopped {n} running broadcast(s)."}
    if action == "clear-schedules":
        from backend.database import SessionLocal
        from backend import models as em
        db = SessionLocal()
        try:
            eb = db.query(em.Bot).filter_by(public_id=bot_id, deleted_at=None).first()
            n = 0
            if eb:
                from backend.scheduler.scheduler import list_pending_tasks, cancel_task
                for t in list_pending_tasks(db, eb.id, limit=100000):
                    if cancel_task(db, t["id"], eb.id).get("ok"):
                        n += 1
            return {"ok": True, "message": f"Cancelled {n} scheduled command(s)."}
        finally:
            db.close()
    raise ApiError("Unknown action.", 400)
