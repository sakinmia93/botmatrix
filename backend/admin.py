"""Admin panel backend: platform overview, users, plans and configuration."""
import json
import os
from typing import Any, Dict, List

from backend import appdb, plans, security
from backend.errors import ApiError

SCHEMA: List[tuple] = [
    ("SMTP_HOST", "SMTP host", "E-mail (verification codes)", "text", False, "e.g. smtp.gmail.com"),
    ("SMTP_PORT", "SMTP port", "E-mail (verification codes)", "number", False, "587"),
    ("SMTP_USER", "SMTP user", "E-mail (verification codes)", "text", False, "your Gmail address"),
    ("SMTP_PASSWORD", "SMTP password / Gmail app password", "E-mail (verification codes)", "secret", False, "Google App passwords"),
    ("SMTP_FROM", "From address", "E-mail (verification codes)", "text", False, "BOT MATRIX <you@gmail.com>"),
    ("REQUIRE_EMAIL_OTP", "Require e-mail code on sign-up / sign-in", "Security", "bool", False, "Off = nobody is asked for a code"),
    ("TURNSTILE_ENABLED", "Cloudflare Turnstile", "Security", "bool", False, "Human check on auth"),
    ("TURNSTILE_SITE_KEY", "Turnstile site key", "Security", "text", False, ""),
    ("TURNSTILE_SECRET_KEY", "Turnstile secret key", "Security", "secret", False, ""),
    ("RATE_LIMITS", "Rate limits", "Security", "bool", False, "Off by default"),
    ("ADMIN_EMAILS", "Admin e-mails (comma separated)", "Platform", "text", False, "Who can open this panel"),
    ("ADMIN_CONTACT_URL", "Contact Admin link", "Platform", "text", False, "https://t.me/..."),
    ("DEFAULT_POINTS", "Points for new accounts", "Platform", "number", False, "Applies to new sign-ups"),
    ("PLAN_POINT_RATE", "Plan points per execution", "Platform", "number", False, "Default 1"),
    ("EXTRA_POINT_RATE", "Extra points per execution", "Platform", "number", False, "Default 1.5"),
    ("BASE_URL", "Public base URL", "Server", "text", False, "https://your-domain"),
    ("CONNECT_BOT_TOKEN", "Connect bot token", "Telegram", "secret", True, "Bot from @BotFather"),
    ("TELEGRAM_API_ROOT", "Telegram API root", "Telegram", "text", True, "https://api.telegram.org"),
    ("OPENAI_API_KEY", "OpenAI API key", "AI libraries for bots", "secret", False, ""),
    ("GEMINI_API_KEY", "Gemini API key", "AI libraries for bots", "secret", False, ""),
    ("API_PORT", "API port", "Server", "number", True, "5001"),
    ("DATABASE_URL", "Engine database URL", "Server", "text", True, "sqlite:///storage/engine.db"),
    ("APP_DB_PATH", "App database path", "Server", "text", True, ""),
]
KEYS = {s[0]: s for s in SCHEMA}
_PREFIX = "cfg:"


def apply_all() -> None:
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT key,value FROM platform_settings WHERE key LIKE 'cfg:%'")
    for r in rows:
        k = r["key"][len(_PREFIX):]
        if k not in KEYS:
            continue
        v = security.decrypt(r["value"]) if KEYS[k][3] == "secret" else r["value"]
        if v == "":
            continue
        os.environ[k] = v


def _stored(c) -> Dict[str, str]:
    return {r["key"][len(_PREFIX):]: r["value"] for r in appdb.rows(c, "SELECT key,value FROM platform_settings WHERE key LIKE 'cfg:%'")}


def get_config() -> List[dict]:
    with appdb.read() as c:
        rows = _stored(c)
    out = []
    for key, label, group, kind, restart, help_ in SCHEMA:
        stored = rows.get(key)
        env = os.environ.get(key, "")
        raw = stored if stored not in (None, "") else env
        source = "stored" if stored not in (None, "") else ("env" if env else "")
        if kind == "secret" and raw:
            val = security.decrypt(raw) if str(raw).startswith("enc:") else raw
            display = security.mask_token(val) if val else ""
            masked = display
        else:
            display = raw or ""
            masked = display
        out.append({
            "key": key,
            "label": label,
            "group": group,
            "kind": kind,
            "restart": restart,
            "help": help_,
            "value": display,
            "masked": masked,
            "hasValue": bool(raw),
            "set": bool(raw),
            "source": source or "not set",
        })
    return out


def save_config(admin_email: str, values: Dict[str, Any]) -> dict:
    if not isinstance(values, dict):
        values = {}
    with appdb.db() as c:
        for k, v in values.items():
            if k not in KEYS:
                continue
            kind = KEYS[k][3]
            s = "" if v is None else str(v)
            if kind == "secret" and (not s or set(s) <= set("\u2022*")):
                continue
            store = security.encrypt(s) if kind == "secret" else s
            c.execute("INSERT OR REPLACE INTO platform_settings (key,value) VALUES (?,?)", (_PREFIX + k, store))
            if kind != "secret":
                os.environ[k] = s
            elif s:
                os.environ[k] = s
    apply_all()
    return {"ok": True}


def overview() -> dict:
    with appdb.read() as c:
        one = lambda q, a=(): int((appdb.one(c, q, a) or {"n": 0})["n"] or 0)
        per = appdb.rows(c, "SELECT COALESCE(plan,'Matrix Free') p, COUNT(*) n FROM users GROUP BY p")
        return {
            "users": one("SELECT COUNT(*) n FROM users"),
            "bots": one("SELECT COUNT(*) n FROM bots"),
            "workingBots": one("SELECT COUNT(*) n FROM bots WHERE status='working'"),
            "newUsers7d": one("SELECT COUNT(*) n FROM users WHERE created_at >= ?", (appdb.iso_in(days=-7),)),
            "plans": {r["p"]: r["n"] for r in per},
            "broadcasts": one("SELECT COUNT(*) n FROM broadcasts") if True else 0,
            "activeBroadcasts": 0,
            "openTickets": one("SELECT COUNT(*) n FROM support_tickets WHERE lower(COALESCE(status,'')) IN ('open','pending','')"),
        }


def users(q: str, page: int) -> dict:
    q = (q or "").strip().lower()
    like = f"%{q.replace('%', '').replace('_', '')}%"
    page = max(1, int(page or 1))
    with appdb.read() as c:
        total = int(appdb.one(c, "SELECT COUNT(*) n FROM users WHERE lower(email) LIKE ? OR lower(COALESCE(name,'')) LIKE ?", (like, like))["n"] or 0)
        try:
            rows = appdb.rows(
                c,
                "SELECT u.id,u.email,u.name,u.plan,u.points,u.extra_points,u.created_at,u.plan_expires_at,u.suspended,"
                "(SELECT COUNT(*) FROM bots b WHERE b.user_id=u.id) bots "
                "FROM users u WHERE lower(u.email) LIKE ? OR lower(COALESCE(u.name,'')) LIKE ? "
                "ORDER BY u.created_at DESC LIMIT 25 OFFSET ?",
                (like, like, (page - 1) * 25),
            )
            has_exp = True
        except Exception:
            rows = appdb.rows(
                c,
                "SELECT u.id,u.email,u.name,u.plan,u.points,u.extra_points,u.created_at,u.suspended,"
                "(SELECT COUNT(*) FROM bots b WHERE b.user_id=u.id) bots "
                "FROM users u WHERE lower(u.email) LIKE ? OR lower(COALESCE(u.name,'')) LIKE ? "
                "ORDER BY u.created_at DESC LIMIT 25 OFFSET ?",
                (like, like, (page - 1) * 25),
            )
            has_exp = False
    return {
        "total": total,
        "users": [{
            "id": r["id"], "email": r["email"], "name": r["name"], "plan": r["plan"] or "Matrix Free",
            "points": int(r["points"] or 0), "extraPoints": int(r["extra_points"] or 0), "bots": r["bots"],
            "createdAt": r["created_at"],
            "planExpiresAt": (r["plan_expires_at"] if has_exp and "plan_expires_at" in r.keys() else None),
            "suspended": bool(r["suspended"]),
        } for r in rows],
    }


def update_user(uid: str, body: dict) -> dict:
    with appdb.db() as c:
        u = appdb.one(c, "SELECT id FROM users WHERE id=?", (uid,))
        if not u:
            raise ApiError("User not found.", 404)
        if body.get("plan"):
            p = appdb.one(c, "SELECT name,id,points FROM plans WHERE name=?", (str(body["plan"]),))
            if not p:
                raise ApiError("Unknown plan.", 404)
            months = body.get("planMonths")
            try:
                months_i = int(months) if months is not None else 0
            except Exception:
                months_i = 0
            c.execute("UPDATE users SET plan=? WHERE id=?", (p["name"], uid))
            try:
                if p["id"] != "free" and months_i > 0:
                    import datetime as _dt
                    exp = (appdb.utcnow() + _dt.timedelta(days=months_i * 30)).isoformat(timespec="seconds") + "Z"
                    c.execute("UPDATE users SET plan_expires_at=? WHERE id=?", (exp, uid))
                elif p["id"] == "free":
                    c.execute("UPDATE users SET plan_expires_at=NULL WHERE id=?", (uid,))
            except Exception:
                pass
            if body.get("setPlanPoints") is not None:
                c.execute("UPDATE users SET points=? WHERE id=?", (max(0, int(body["setPlanPoints"])), uid))
            elif body.get("grantPlanPoints"):
                c.execute("UPDATE users SET points=? WHERE id=?", (max(0, int(p["points"] or 0)), uid))
        if "suspended" in body:
            sus = 1 if body.get("suspended") else 0
            c.execute("UPDATE users SET suspended=?, suspended_reason=? WHERE id=?",
                      (sus, security.clean_text(body.get("reason"), 200) if sus else "", uid))
        if body.get("setPoints") is not None:
            c.execute("UPDATE users SET points=? WHERE id=?", (max(0, int(body["setPoints"])), uid))
        if body.get("addPoints") is not None:
            c.execute("UPDATE users SET points=MAX(0,COALESCE(points,0)+?) WHERE id=?", (int(body["addPoints"]), uid))
        if body.get("addExtraPoints") is not None:
            n = int(body["addExtraPoints"])
            c.execute("UPDATE users SET points=MAX(0,COALESCE(points,0)+?), extra_points=MAX(0,COALESCE(extra_points,0)+?) WHERE id=?", (n, n, uid))
    try:
        appdb.notify(uid, "Account updated", "An administrator updated your plan or points.", "info", "tab:Plans & Billing")
    except Exception:
        pass
    return {"ok": True}


def save_plan(pid: str, body: dict) -> dict:
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM plans WHERE id=?", (pid,))
        if not r:
            raise ApiError("Plan not found.", 404)
        name = security.clean_text(body.get("name") or r["name"], 40) or r["name"]
        price = float(body.get("priceUsd") if body.get("priceUsd") is not None else r["price_usd"] or 0)
        pts = int(body.get("points") if body.get("points") is not None else r["points"] or 0)
        lim = body.get("limits") if isinstance(body.get("limits"), dict) else appdb.jload(r["limits_json"], {})
        feats = body.get("features") if isinstance(body.get("features"), list) else appdb.jload(r["features_json"], [])
        c.execute("UPDATE plans SET name=?, price_usd=?, points=?, limits_json=?, features_json=? WHERE id=?",
                  (name, price, pts, json.dumps(lim), json.dumps(feats), pid))
    return {"ok": True}


def _rg(row, key, default=None):
    try:
        return row[key] if key in row.keys() else default
    except Exception:
        return default


def tickets() -> list:
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT * FROM support_tickets ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 200")
    return [{
        "id": r["id"], "subject": _rg(r, "subject") or (r["message"] or "")[:80], "status": r["status"] or "open",
        "email": r["email"], "name": r["name"], "userId": _rg(r, "user_id"),
        "createdAt": r["created_at"], "updatedAt": _rg(r, "updated_at"),
        "priority": _rg(r, "priority") or "Normal", "department": _rg(r, "department"),
    } for r in rows]


def ticket_detail(tid: str) -> dict:
    with appdb.read() as c:
        r = appdb.one(c, "SELECT * FROM support_tickets WHERE id=?", (tid,))
        if not r:
            raise ApiError("Ticket not found.", 404)
        try:
            msgs = appdb.rows(c, "SELECT * FROM support_messages WHERE ticket_id=? ORDER BY created_at ASC", (tid,))
        except Exception:
            msgs = []
    return {
        "ticket": {
            "id": r["id"], "subject": _rg(r, "subject") or "", "status": r["status"] or "open",
            "email": r["email"], "name": r["name"], "message": r["message"],
            "userId": _rg(r, "user_id"), "createdAt": r["created_at"],
        },
        "messages": [{
            "id": m["id"], "message": m["message"], "createdAt": m["created_at"],
            "authorName": _rg(m, "author_name") or "User",
        } for m in msgs],
    }


def set_ticket(tid: str, status: str) -> dict:
    status = (status or "open").lower()
    if status not in ("open", "pending", "closed", "resolved"):
        raise ApiError("Invalid status.", 400)
    with appdb.db() as c:
        r = appdb.one(c, "SELECT id FROM support_tickets WHERE id=?", (tid,))
        if not r:
            raise ApiError("Ticket not found.", 404)
        c.execute("UPDATE support_tickets SET status=?, updated_at=? WHERE id=?", (status, appdb.now_iso(), tid))
    return {"ok": True}


def reply_ticket(tid: str, message: str, staff_name: str = "Support Staff") -> dict:
    message = security.clean_text(message, 8000)
    if not message:
        raise ApiError("Message required.", 400)
    mid = appdb.new_id("sm_", 8)
    with appdb.db() as c:
        r = appdb.one(c, "SELECT id,user_id,status FROM support_tickets WHERE id=?", (tid,))
        if not r:
            raise ApiError("Ticket not found.", 404)
        if (r["status"] or "").lower() == "closed":
            raise ApiError("Ticket is closed.", 400)
        try:
            c.execute(
                "INSERT INTO support_messages (id,ticket_id,message,created_at,author_name) VALUES (?,?,?,?,?)",
                (mid, tid, message, appdb.now_iso(), staff_name),
            )
        except Exception:
            pass
        c.execute("UPDATE support_tickets SET updated_at=?, status=COALESCE(NULLIF(status,''),'open') WHERE id=?", (appdb.now_iso(), tid))
        uid = r["user_id"]
    if uid:
        try:
            appdb.notify(uid, "Support reply", message[:200], "info", "tab:Help")
        except Exception:
            pass
    return {"ok": True, "id": mid}


def search_bots(q: str) -> list:
    q = (q or "").strip().lower()
    like = f"%{q}%"
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT id,name,username,user_id,status FROM bots WHERE lower(name) LIKE ? OR lower(COALESCE(username,'')) LIKE ? ORDER BY updated_at DESC LIMIT 40", (like, like))
    return [{"id": r["id"], "name": r["name"], "username": r["username"], "userId": r["user_id"], "status": r["status"]} for r in rows]


def store_items() -> list:
    with appdb.read() as c:
        try:
            rows = appdb.rows(c, "SELECT * FROM bot_store ORDER BY created_at DESC LIMIT 100")
        except Exception:
            return []
    return [dict(r) for r in rows]


def store_add(body: dict) -> dict:
    return {"ok": True}


def store_remove(sid: str) -> dict:
    return {"ok": True}
