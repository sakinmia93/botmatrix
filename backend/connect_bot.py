"""The platform's own Telegram bot: links an account, sends alerts, remote control by buttons."""
from __future__ import annotations

import hashlib
import html
import logging
import os
import secrets
import threading
import time

from backend import appdb, security, tg
from backend.errors import ApiError

log = logging.getLogger("connect")
TOKEN = os.environ.get("CONNECT_BOT_TOKEN", "").strip()
_info = {"username": ""}
_stop = threading.Event()

KB = {"keyboard": [[{"text": "👤 My Account"}, {"text": "🤖 My Bots"}],
                   [{"text": "📣 Broadcast"}, {"text": "📊 Stats"}],
                   [{"text": "⭐ Points"}, {"text": "🧾 Errors"}],
                   [{"text": "▶️ Start all"}, {"text": "⏹ Stop all"}],
                   [{"text": "🔔 Alerts"}, {"text": "❓ Help"}],
                   [{"text": "🔌 Disconnect"}]], "resize_keyboard": True}
ALERT_LABELS = {
    "botStartStop": "Bot start / stop", "botTransfers": "Bot transfers", "criticalCrashes": "Crashes & problems",
    "broadcastReports": "Broadcast reports", "newSubscribers": "New subscribers",
    "securityAlerts": "Security & sign-in alerts", "dailyDigest": "Daily digest",
    "botErrors": "Bot error alerts", "lowPoints": "Low points warning", "broadcastStarted": "Broadcast started",
}


_h = html.escape


def enabled() -> bool:
    return bool(TOKEN)


def username() -> str:
    return _info["username"]


def _send(chat_id, text, markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup:
        data["reply_markup"] = markup
    try:
        return tg.call(TOKEN, "sendMessage", data, timeout=15)
    except tg.TgError as e:
        log.warning("send failed: %s", e.description)
        return None


def _user_by_chat(chat_id):
    with appdb.read() as c:
        return appdb.one(c, "SELECT * FROM users WHERE telegram_chat_id=? AND telegram_connected=1", (str(chat_id),))


# ------------------------------------------------------------------ link codes
def create_link(user_id: str) -> dict:
    if not enabled() or not _info["username"]:
        raise ApiError("Telegram connect is not available right now.", 503)
    code = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")
    with appdb.db() as c:
        c.execute("DELETE FROM connect_links WHERE user_id=? OR expires_at<?", (user_id, appdb.now_iso()))
        c.execute("INSERT INTO connect_links (code_hash,user_id,expires_at) VALUES (?,?,?)",
                  (hashlib.sha256(code.encode()).hexdigest(), user_id, appdb.iso_in(minutes=10)))
    return {"code": code, "url": f"https://t.me/{_info['username']}?start={code}", "expiresInSec": 600}


def _consume(code: str):
    h = hashlib.sha256(code.encode()).hexdigest()
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM connect_links WHERE code_hash=?", (h,))
        if not r:
            return None
        c.execute("DELETE FROM connect_links WHERE code_hash=?", (h,))
        if r["expires_at"] < appdb.now_iso():
            return None
        return r["user_id"]


# ------------------------------------------------------------------ alerts
def alerts_of(user_row) -> dict:
    a = dict(appdb.DEFAULT_ALERTS)
    a.update(appdb.jload(user_row["telegram_alerts_json"], {}))
    return a


def alert(user_id: str, kind: str, text: str) -> bool:
    """Push a Telegram message to the user's linked connect-bot chat.

    Requires CONNECT_BOT_TOKEN, telegram_connected=1, telegram_chat_id, and the
    alert kind enabled in Settings (or DEFAULT_ALERTS). Failures are logged so
    missing Telegram "signal" alerts are diagnosable.
    """
    if not enabled():
        log.warning("Telegram alert not sent (CONNECT_BOT_TOKEN not set). kind=%s", kind)
        return False
    with appdb.read() as c:
        u = appdb.one(c, "SELECT * FROM users WHERE id=? AND telegram_connected=1", (user_id,))
    if not u or not u["telegram_chat_id"]:
        log.info("Telegram alert skipped — account not linked. user=%s kind=%s", user_id, kind)
        return False
    if kind and not alerts_of(u).get(kind, False):
        log.info("Telegram alert skipped — kind disabled in user settings. user=%s kind=%s", user_id, kind)
        return False
    ok = _send(u["telegram_chat_id"], text) is not None
    if not ok:
        log.warning("Telegram alert send failed user=%s kind=%s chat=%s", user_id, kind, u.get("telegram_chat_id"))
    return ok


def account_text(u) -> str:
    with appdb.read() as c:
        total = appdb.one(c, "SELECT COUNT(*) n FROM bots WHERE user_id=?", (u["id"],))["n"]
        run = appdb.one(c, "SELECT COUNT(*) n FROM bots WHERE user_id=? AND status='working'", (u["id"],))["n"]
        bc = appdb.one(c, "SELECT title,status,sent_count,failed_count,total_target_users FROM broadcasts WHERE user_id=? AND status IN ('Active','Paused')", (u["id"],))
    t = (f"👤 <b>{html.escape(u['name'])}</b>\n✉️ {html.escape(u['email'])}\n"
         f"💳 Plan: {html.escape(u['plan'] or 'Free')}\n⭐ Points: <b>{int(u['points'] or 0):,}</b>\n"
         f"🤖 Bots: {total} ({run} running)")
    if bc:
        t += f"\n📣 Broadcast: {html.escape(bc['title'])} — {bc['status']} ({bc['sent_count'] + bc['failed_count']}/{bc['total_target_users']})"
    return t


def bots_markup(user_id: str):
    with appdb.read() as c:
        bots = appdb.rows(c, "SELECT id,name,username,status FROM bots WHERE user_id=? ORDER BY updated_at DESC LIMIT 25", (user_id,))
    if not bots:
        return "You don't have any bots yet.", None
    rows = [[{"text": f"{'🟢' if b['status'] == 'working' else '⚪️'} {b['name'][:24]} — {'Turn off' if b['status'] == 'working' else 'Turn on'}",
              "callback_data": f"tg:{b['id']}"}] for b in bots]
    return "🤖 <b>Your bots</b>\nTap a bot to turn it on or off.", {"inline_keyboard": rows}


def alerts_markup(u):
    a = alerts_of(u)
    rows = [[{"text": f"{'✅' if a[k] else '▫️'} {label}", "callback_data": f"al:{k}"}] for k, label in ALERT_LABELS.items()]
    return "🔔 <b>Alerts</b>\nChoose what you want to be told about.", {"inline_keyboard": rows}


def stats_text(u) -> str:
    since = appdb.iso_in(hours=-24)
    with appdb.read() as c:
        cmds = appdb.one(c, "SELECT COUNT(*) n FROM events WHERE owner_id=? AND kind='command' AND ts>=?", (u["id"], since))["n"]
        errs = appdb.one(c, "SELECT COUNT(*) n FROM events WHERE owner_id=? AND kind='error' AND ts>=?", (u["id"], since))["n"]
        users = appdb.one(c, "SELECT COUNT(DISTINCT tg_user) n FROM events WHERE owner_id=? AND ts>=?", (u["id"], since))["n"]
        aud = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id IN (SELECT id FROM bots WHERE user_id=?) AND bot_blocked=0", (u["id"],))["n"]
    return f"📊 <b>Last 24 hours</b>\n⚡ Commands: {cmds}\n🐞 Errors: {errs}\n👥 Active users: {users}\n🌐 Total audience: {aud}"


def errors_text(u) -> str:
    from backend import services
    out = []
    with appdb.read() as c:
        bots = appdb.rows(c, "SELECT id,name FROM bots WHERE user_id=?", (u["id"],))
    for b in bots[:20]:
        for e in services.bot_errors(b["id"])[:2]:
            out.append(f"• <b>{html.escape(b['name'])}</b> {html.escape(e['command'])}: <code>{html.escape(e['message'][:120])}</code>")
    return "🧾 <b>Recent errors</b>\n" + "\n".join(out[:8]) if out else "🧾 No recent errors. 🎉"


def digest_loop():
    """Once a day (09:00 UTC) send the daily digest to users who turned it on."""
    last = [""]
    while not _stop.wait(60):
        now = appdb.utcnow()
        day = now.strftime("%Y-%m-%d")
        if now.hour != 9 or last[0] == day:
            continue
        last[0] = day
        try:
            with appdb.read() as c:
                us = appdb.rows(c, "SELECT * FROM users WHERE telegram_connected=1")
            for u in us:
                if alerts_of(u).get("dailyDigest"):
                    _send(u["telegram_chat_id"], "🗓 <b>Daily digest</b>\n\n" + stats_text(u) + f"\n⭐ Points: {int(u['points'] or 0):,}")
        except Exception:
            log.exception("digest")


def broadcast_text(u) -> str:
    with appdb.read() as c:
        bc = appdb.rows(c, "SELECT * FROM broadcasts WHERE user_id=? ORDER BY created_at DESC LIMIT 3", (u["id"],))
    if not bc:
        return "📣 No broadcasts yet."
    out = ["📣 <b>Latest broadcasts</b>"]
    for b in bc:
        tot = b["total_target_users"] or 0
        out.append(f"\n<b>{html.escape(b['title'])}</b> — {b['status']}\n✅ {b['sent_count']}  ❌ {b['failed_count']}  👥 {tot}")
    return "\n".join(out)


# ------------------------------------------------------------------ updates
def _on_message(m):
    chat = m.get("chat") or {}
    if chat.get("type") != "private":
        return
    cid = chat["id"]
    frm = m.get("from") or {}
    text = (m.get("text") or "").strip()
    if security.rate_limit(f"cb:{cid}", 40, 60):
        return
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            uid = _consume(parts[1].strip())
            if not uid:
                _send(cid, "This link has expired. Open Settings → Telegram Connect on the website and tap Connect again.")
                return
            with appdb.db() as c:
                c.execute("UPDATE users SET telegram_connected=0, telegram_chat_id=NULL WHERE telegram_chat_id=? AND id!=?", (str(cid), uid))
                c.execute("UPDATE users SET telegram_connected=1, telegram_chat_id=?, telegram_first_name=?, telegram_username=?,"
                          " telegram_connected_at=? WHERE id=?",
                          (str(cid), frm.get("first_name") or "", ("@" + frm["username"]) if frm.get("username") else "",
                           appdb.now_iso(), uid))
                u = appdb.one(c, "SELECT * FROM users WHERE id=?", (uid,))
            _send(cid, "✅ <b>Connected!</b>\nYour account is now linked. Use the buttons below.\n\n" + account_text(u), KB)
            appdb.notify(uid, "Telegram connected", "Your Telegram account was linked.", "success")
            return
        u = _user_by_chat(cid)
        _send(cid, "Welcome! Open <b>Settings → Telegram Connect</b> on the website and tap Connect to link your account."
              if not u else "Welcome back!", KB if u else None)
        return
    u = _user_by_chat(cid)
    if not u:
        _send(cid, "Your account isn't linked yet. Open <b>Settings → Telegram Connect</b> on the website to connect.")
        return
    if text == "👤 My Account":
        _send(cid, account_text(u), KB)
    elif text == "🤖 My Bots":
        t, mk = bots_markup(u["id"])
        _send(cid, t, mk)
    elif text == "📣 Broadcast":
        _send(cid, broadcast_text(u), KB)
    elif text == "📊 Stats":
        _send(cid, stats_text(u), KB)
    elif text == "⭐ Points":
        _send(cid, f"⭐ You have <b>{int(u['points'] or 0):,}</b> points.\nPlan: {html.escape(u['plan'] or 'Free')}", KB)
    elif text == "🧾 Errors":
        _send(cid, errors_text(u), KB)
    elif text in ("▶️ Start all", "⏹ Stop all"):
        _send(cid, f"{'Start' if text.startswith('▶') else 'Stop'} every bot on your account?", {"inline_keyboard": [[
            {"text": "Yes", "callback_data": "all:" + ("on" if text.startswith("▶") else "off")}, {"text": "Cancel", "callback_data": "all:no"}]]})
    elif text == "❓ Help":
        _send(cid, "👤 My Account – your details\n🤖 My Bots – turn bots on/off\n📣 Broadcast – latest broadcasts\n📊 Stats – last 24 hours\n⭐ Points – balance\n🧾 Errors – recent bot errors\n▶️/⏹ – start or stop all bots\n🔔 Alerts – choose what I tell you", KB)
    elif text == "🔔 Alerts":
        t, mk = alerts_markup(u)
        _send(cid, t, mk)
    elif text == "🔌 Disconnect":
        _send(cid, "Disconnect this chat from your account?", {"inline_keyboard": [[
            {"text": "Yes, disconnect", "callback_data": "dc:yes"}, {"text": "Cancel", "callback_data": "dc:no"}]]})
    else:
        _send(cid, "Use the buttons below.", KB)


def _on_callback(cq):
    msg = cq.get("message") or {}
    cid = (msg.get("chat") or {}).get("id")
    data = cq.get("data") or ""
    u = _user_by_chat(cid) if cid else None

    def ans(t=""):
        try:
            tg.call(TOKEN, "answerCallbackQuery", {"callback_query_id": cq["id"], "text": t[:180]})
        except tg.TgError:
            pass
    if not u:
        return ans("Not linked")
    if data.startswith("tg:"):
        bid = data[3:]
        with appdb.read() as c:
            b = appdb.one(c, "SELECT * FROM bots WHERE id=? AND user_id=?", (bid, u["id"]))
        if not b:
            return ans("Bot not found")
        from backend import runtime
        res = runtime.set_running(bid, b["status"] != "working")
        if not res.get("ok"):
            return ans(res.get("error", "Failed"))
        ans("Done")
        t, mk = bots_markup(u["id"])
        try:
            tg.call(TOKEN, "editMessageText", {"chat_id": cid, "message_id": msg["message_id"], "text": t,
                                               "parse_mode": "HTML", "reply_markup": mk})
        except tg.TgError:
            pass
    elif data.startswith("al:"):
        k = data[3:]
        if k not in ALERT_LABELS:
            return ans()
        a = alerts_of(u)
        a[k] = not a[k]
        with appdb.db() as c:
            c.execute("UPDATE users SET telegram_alerts_json=? WHERE id=?", (appdb.json.dumps(a), u["id"]))
            u = appdb.one(c, "SELECT * FROM users WHERE id=?", (u["id"],))
        ans("Saved")
        t, mk = alerts_markup(u)
        try:
            tg.call(TOKEN, "editMessageReplyMarkup", {"chat_id": cid, "message_id": msg["message_id"], "reply_markup": mk})
        except tg.TgError:
            pass
    elif data.startswith("all:"):
        if data == "all:no":
            return ans("Cancelled")
        want = data == "all:on"
        from backend import runtime
        with appdb.read() as c:
            ids = [r["id"] for r in appdb.rows(c, "SELECT id,status FROM bots WHERE user_id=?", (u["id"],)) if (r["status"] == "working") != want]
        n = sum(1 for i in ids if runtime.set_running(i, want).get("ok"))
        ans("Done")
        _send(cid, f"{'🟢 Started' if want else '⚪️ Stopped'} {n} bot(s).", KB)
    elif data == "dc:yes":
        disconnect(u["id"])
        ans("Disconnected")
        _send(cid, "🔌 Disconnected. You can link again from the website any time.", {"remove_keyboard": True})
    else:
        ans()


def disconnect(user_id: str):
    with appdb.db() as c:
        c.execute("UPDATE users SET telegram_connected=0, telegram_chat_id=NULL, telegram_username=NULL, telegram_first_name=NULL,"
                  " telegram_connected_at=NULL WHERE id=?", (user_id,))


def _loop():
    offset = 0
    while not _stop.is_set():
        try:
            ups = tg.call(TOKEN, "getUpdates", {"offset": offset, "timeout": 20,
                                                "allowed_updates": ["message", "callback_query"]}, timeout=30)
            for up in ups or []:
                offset = max(offset, up["update_id"] + 1)
                try:
                    if up.get("message"):
                        _on_message(up["message"])
                    elif up.get("callback_query"):
                        _on_callback(up["callback_query"])
                except Exception:
                    log.exception("connect update")
        except tg.TgError as e:
            if e.code == 401:
                log.error("Connect bot token rejected.")
                return
            _stop.wait(4)
        except Exception:
            _stop.wait(4)


def start():
    global TOKEN
    TOKEN = os.environ.get("CONNECT_BOT_TOKEN", "").strip()      # may have been set from the admin panel
    if not enabled():
        log.warning("CONNECT_BOT_TOKEN not set — Telegram connect disabled.")
        return
    try:
        me = tg.get_me(TOKEN)
        _info["username"] = me.get("username", "")
        try:
            tg.call(TOKEN, "deleteWebhook", {})
            tg.call(TOKEN, "setMyCommands", {"commands": [{"command": "start", "description": "Open the menu"}]})
        except tg.TgError:
            pass
    except tg.TgError as e:
        log.error("Connect bot unavailable: %s", e.description)
        return
    threading.Thread(target=_loop, daemon=True, name="connect-bot").start()
    threading.Thread(target=digest_loop, daemon=True, name="connect-digest").start()
