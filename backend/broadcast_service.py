"""Broadcast Manager engine."""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from typing import Dict, List, Optional

from backend import appdb, plans, security, tg
from backend.errors import ApiError

log = logging.getLogger("broadcast")
FREE_RATE = 5
SENDERS = 8
_cl = threading.Lock()
_ctl: Dict[str, "Control"] = {}

MEDIA_METHOD = {
    "Photo": ("sendPhoto", "photo"),
    "Video": ("sendVideo", "video"),
    "Audio": ("sendAudio", "audio"),
    "Document": ("sendDocument", "document"),
    "Animation": ("sendAnimation", "animation"),
    "Voice": ("sendVoice", "voice"),
    "VideoNote": ("sendVideoNote", "video_note"),
    "Sticker": ("sendSticker", "sticker"),
}
NO_CAPTION = {"Sticker", "VideoNote"}


class Control:
    def __init__(self):
        self.paused = threading.Event()
        self.cancelled = threading.Event()
        self.cap = FREE_RATE
        self.rate = FREE_RATE
        self.bot_state: Dict[str, str] = {}


class _Limiter:
    def __init__(self, ctl: Control):
        self.ctl = ctl
        self._t: List[float] = []
        self.rate = 0.0
        self._lock = threading.Lock()

    def acquire(self):
        while True:
            if self.ctl.cancelled.is_set():
                return
            with self._lock:
                now = time.time()
                self._t = [t for t in self._t if t > now - 1.0]
                cap = max(1.0, float(self.ctl.rate or self.ctl.cap or FREE_RATE))
                if len(self._t) < cap:
                    self._t.append(now)
                    self.rate = float(len(self._t))
                    return
            time.sleep(0.05)

    def ok(self):
        pass

    def penalize(self, sec: float):
        time.sleep(max(0.1, min(float(sec), 30)))


def plan_speed(uid: str) -> int:
    try:
        return int(plans.limit(uid, "broadcastSpeed") or FREE_RATE)
    except Exception:
        return FREE_RATE


def resolve_speed(uid: str, want) -> tuple:
    cap = plan_speed(uid)
    try:
        w = int(str(want).split()[0]) if want and str(want)[0].isdigit() else cap
    except Exception:
        w = cap
    rate = max(1, min(cap, w if w > 0 else cap))
    return rate, f"{rate}/s"


def min_users(user_id: str) -> int:
    return 1


def _aud_where(bot_id: str, lang: str):
    q = "bot_id=? AND is_blocked=0 AND bot_blocked=0"
    args: list = [bot_id]
    if lang and lang.lower() not in ("all", ""):
        codes = ["" if x.strip().lower() == "unknown" else x.strip().lower() for x in re.split(r"[,\s]+", lang) if x.strip()]
        if codes:
            q += " AND lower(COALESCE(language_code,'')) IN (%s)" % ",".join("?" * len(codes))
            args += codes
    return q, args


def audience_count(c, bot_id: str, lang: str) -> int:
    q, args = _aud_where(bot_id, lang)
    return int(c.execute(f"SELECT COUNT(*) n FROM chats WHERE {q}", args).fetchone()["n"] or 0)


def audience_iter(bot_id: str, lang: str, take: int, chunk: int = 2000):
    q, args = _aud_where(bot_id, lang)
    with appdb.read() as c:
        n = int(c.execute(f"SELECT COUNT(*) n FROM chats WHERE {q}", args).fetchone()["n"] or 0)
        ids = None
        if take < n:
            ids = [r[0] for r in c.execute(f"SELECT rowid FROM chats WHERE {q} ORDER BY last_active DESC LIMIT ?", (*args, take))]
    if ids is not None:
        for i in range(0, len(ids), chunk):
            part = ids[i:i + chunk]
            with appdb.read() as c:
                rows = c.execute(
                    f"SELECT telegram_id,name,username,language_code FROM chats WHERE rowid IN ({','.join('?' * len(part))})",
                    part,
                ).fetchall()
            for r in rows:
                yield r
        return
    last = 0
    sent = 0
    while sent < take:
        with appdb.read() as c:
            rows = c.execute(
                f"SELECT rowid AS rid,telegram_id,name,username,language_code FROM chats WHERE {q} AND rowid>? ORDER BY rowid LIMIT ?",
                (*args, last, min(chunk, take - sent)),
            ).fetchall()
        if not rows:
            return
        for r in rows:
            yield r
        sent += len(rows)
        last = rows[-1]["rid"]


def languages(uid: str, bot_ids: list) -> list:
    out: Dict[str, int] = {}
    with appdb.read() as c:
        for i in bot_ids:
            if not appdb.one(c, "SELECT id FROM bots WHERE id=? AND user_id=?", (i, uid)):
                continue
            for r in c.execute(
                "SELECT lower(COALESCE(NULLIF(language_code,''),'unknown')) l, COUNT(*) n FROM chats "
                "WHERE bot_id=? AND is_blocked=0 AND bot_blocked=0 GROUP BY l",
                (i,),
            ):
                out[r["l"]] = out.get(r["l"], 0) + int(r["n"] or 0)
    return [{"code": k, "count": v} for k, v in sorted(out.items(), key=lambda kv: -kv[1])]


def serialize(r) -> dict:
    stats = appdb.jload(r["bot_stats_json"], [])
    return {
        "id": r["id"], "title": r["title"], "status": r["status"],
        "messageType": r["message_type"], "messageText": r["message_text"],
        "sentCount": int(r["sent_count"] or 0), "failedCount": int(r["failed_count"] or 0),
        "blockedCount": int(r["blocked_count"] or 0),
        "totalTargetUsers": int(r["total_target_users"] or 0),
        "deliverySpeed": r["delivery_speed"],
        "botStats": stats,
        "createdAt": r["created_at"], "startedAt": r["started_at"],
        "finishedAt": r["finished_at"] if "finished_at" in r.keys() else None,
        "failedRecipients": appdb.jload(r["failed_recipients_json"], []),
    }


def list_for(user_id: str) -> list:
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT * FROM broadcasts WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user_id,))
    return [serialize(r) for r in rows]


def get_for(user_id: str, bc_id: str) -> dict:
    with appdb.read() as c:
        r = appdb.one(c, "SELECT * FROM broadcasts WHERE id=? AND user_id=?", (bc_id, user_id))
    if not r:
        raise ApiError("Broadcast not found.", 404)
    return serialize(r)


def _keyboard(buttons):
    if not buttons:
        return None
    rows = []
    for b in buttons:
        if not isinstance(b, dict):
            continue
        btn = {"text": str(b.get("text") or "Button")[:64]}
        if b.get("url"):
            btn["url"] = str(b["url"])[:512]
        elif b.get("callback_data"):
            btn["callback_data"] = str(b["callback_data"])[:64]
        else:
            continue
        rows.append([btn])
    return {"inline_keyboard": rows} if rows else None


def _payload(r, a, kb, media_value=None):
    mt = r["message_type"] or "Text"
    data = {"chat_id": int(a["telegram_id"]) if str(a["telegram_id"]).lstrip("-").isdigit() else a["telegram_id"]}
    text = r["message_text"] or ""
    if kb:
        data["reply_markup"] = kb
    if mt == "Text" or mt not in MEDIA_METHOD:
        data["text"] = text
        if r["parse_mode"] in ("HTML", "Markdown", "MarkdownV2"):
            data["parse_mode"] = r["parse_mode"]
        return "sendMessage", data
    method, field = MEDIA_METHOD[mt]
    if media_value:
        data[field] = media_value
    elif r["media_ref"]:
        data[field] = r["media_ref"]
    if text and mt not in NO_CAPTION:
        data["caption"] = text
        if r["parse_mode"] in ("HTML", "Markdown", "MarkdownV2"):
            data["parse_mode"] = r["parse_mode"]
    return method, data


def create(user: dict, body: dict) -> dict:
    uid = user["id"]
    text = security.clean_text(body.get("messageText"), 4096)
    msrc = body.get("mediaSource") if body.get("mediaSource") in ("upload", "url") else ""
    mref = security.clean_text(body.get("mediaRef"), 1500) if msrc else ""
    mname = ""
    ids = [str(x) for x in (body.get("targetBotIds") or [])][:200]
    if not ids:
        raise ApiError("Select at least one bot.", 400)
    mtype = body.get("messageType") if body.get("messageType") in ("Text", *MEDIA_METHOD) else "Text"
    if mtype == "Text" and not text:
        raise ApiError("Write a message first.", 400)
    pmode = body.get("parseMode") if body.get("parseMode") in ("None", "HTML", "Markdown", "MarkdownV2") else "HTML"
    lang = security.clean_text(body.get("languageFilter") or "All", 100) or "All"
    try:
        limit = max(1, int(body.get("targetUserLimit") or 1))
    except Exception:
        limit = 1
    buttons = body.get("inlineButtons") or []
    if not isinstance(buttons, list):
        buttons = []
    pin = 1 if body.get("pinMessage") else 0
    cap = plan_speed(uid)
    rate, speed_txt = resolve_speed(uid, body.get("deliverySpeed") or f"{cap}")
    minu = min_users(uid)
    with appdb.db() as c:
        running = appdb.one(c, "SELECT id FROM broadcasts WHERE user_id=? AND status IN ('Active','Paused')", (uid,))
        if running:
            raise ApiError("A broadcast is already running. Wait until it finishes or cancel it first.", 409)
        bots = []
        for i in ids:
            b = appdb.one(c, "SELECT id,name,username,token,status FROM bots WHERE id=? AND user_id=?", (i, uid))
            if not b:
                raise ApiError("One of the selected bots was not found.", 404)
            n_aud = audience_count(c, i, lang)
            if not b["token"]:
                raise ApiError(f"{b['name']} has no bot token yet — add one in its Settings first.", 400)
            if n_aud < minu:
                raise ApiError(f"{b['name']} needs at least {minu} users for a broadcast (it has {n_aud}).", 400)
            bots.append((b, n_aud))
        remaining = limit
        stats, total = [], 0
        for b, n in bots:
            take = min(n, max(0, remaining))
            remaining -= take
            total += take
            stats.append({
                "botId": b["id"], "botName": b["name"], "botUsername": b["username"], "targetCount": take,
                "sentCount": 0, "failedCount": 0, "blockedCount": 0,
                "status": "Delivering" if take else "Done", "speed": speed_txt,
            })
        if total <= 0:
            raise ApiError("There is nobody to send this to yet.", 400)
        plans.check_broadcast(uid, total)
        bid = appdb.new_id("bc_", 8)
        now = appdb.now_iso()
        c.execute(
            "INSERT INTO broadcasts (id,user_id,title,target_bot_ids,target_bot_usernames,message_type,message_text,parse_mode,"
            "inline_buttons,language_filter,status,target_user_limit,total_target_users,sent_count,in_progress_count,failed_count,"
            "cleaned_failed,delivery_speed,bot_stats_json,failed_recipients_json,created_at,updated_at,started_at,blocked_count,paused_seconds,"
            "media_source,media_ref,media_name,pin_message)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'Active',?,?,0,?,0,0,?,?,'[]',?,?,?,0,0,?,?,?,?)",
            (bid, uid, (security.clean_text(body.get("title"), 80) or text[:32] or (mtype + " broadcast")), json.dumps(ids),
             json.dumps([b["username"] for b, _ in bots]), mtype, text, pmode, json.dumps(buttons), lang, limit, total, total, speed_txt,
             json.dumps(stats), now, now, now, msrc, mref, mname, pin),
        )
    ctl = Control()
    ctl.cap, ctl.rate = cap, rate
    with _cl:
        _ctl[bid] = ctl
    threading.Thread(target=_run, args=(bid, uid), daemon=True, name=f"bc-{bid}").start()
    try:
        from backend import connect_bot
        connect_bot.alert(uid, "broadcastStarted", f"\U0001f4e3 Broadcast “{connect_bot._h(str(body.get('title') or text[:32] or mtype))}” started for {total} users.")
    except Exception:
        pass
    return {"id": bid, "total": total, "status": "Active"}


def _run(bc_id: str, uid: str, resume: bool = False):
    with _cl:
        ctl = _ctl.get(bc_id) or Control()
        _ctl[bc_id] = ctl
    try:
        with appdb.read() as c:
            r = appdb.one(c, "SELECT * FROM broadcasts WHERE id=?", (bc_id,))
            if not r:
                return
            stats = appdb.jload(r["bot_stats_json"], [])
            bot_rows = {s["botId"]: appdb.one(c, "SELECT id,name,token FROM bots WHERE id=?", (s["botId"],)) for s in stats}
        kb = _keyboard(appdb.jload(r["inline_buttons"], []))
        lock = threading.Lock()
        counters = {"sent": 0, "failed": 0, "blocked": 0, "unreachable": 0}
        per = {s["botId"]: dict(s) for s in stats}
        total = int(r["total_target_users"] or 0)
        fail_buf: List[tuple] = []
        done_buf: List[tuple] = []
        failed_list: List[dict] = []
        reasons: Dict[str, dict] = {}
        last_flush = [0.0]

        def flush(force=False):
            now = time.time()
            if not force and now - last_flush[0] < 0.4:
                return
            last_flush[0] = now
            rows, dones = fail_buf[:], done_buf[:]
            fail_buf.clear()
            done_buf.clear()
            top = sorted(reasons.values(), key=lambda x: -x["count"])[:6]
            with appdb.db() as c:
                if rows:
                    c.executemany("INSERT INTO broadcast_failures (bc_id,bot_id,telegram_id,kind,reason,failed_at) VALUES (?,?,?,?,?,?)", rows)
                if dones:
                    c.executemany("INSERT OR IGNORE INTO broadcast_done (bc_id,bot_id,telegram_id) VALUES (?,?,?)", dones)
                c.execute(
                    "UPDATE broadcasts SET sent_count=?,failed_count=?,blocked_count=?,unreachable_count=?,in_progress_count=?,bot_stats_json=?,"
                    "failed_recipients_json=?,reasons_json=?,updated_at=? WHERE id=?",
                    (counters["sent"], counters["failed"], counters["blocked"], counters["unreachable"],
                     max(0, total - counters["sent"] - counters["failed"]),
                     json.dumps(list(per.values())), json.dumps(failed_list[-300:]), json.dumps(top), appdb.now_iso(), bc_id),
                )

        def worker(bot_id: str):
            st = per[bot_id]
            brow = bot_rows.get(bot_id)
            if not brow:
                st["status"] = "Failed"
                st["fatal"] = "Bot was removed before the broadcast finished."
                return
            token = security.decrypt(brow["token"] or "")
            if not token:
                st["status"] = "Failed"
                st["fatal"] = "Could not read this bot's token. Re-save the token in bot Settings and set a stable SECRET_KEY."
                log.error("broadcast %s bot %s: empty token after decrypt", bc_id, bot_id)
                return
            lim = _Limiter(ctl)
            nsend = 16 if ctl.cap > FREE_RATE else SENDERS
            q: queue.Queue = queue.Queue(maxsize=nsend * 3)

            def send_one(a):
                method, data = _payload(r, a, kb, r["media_ref"] if r["media_source"] == "url" else None)
                attempt = 0
                limited = 0
                while True:
                    attempt += 1
                    if ctl.cancelled.is_set():
                        return
                    lim.acquire()
                    try:
                        res = tg.call(token, method, data, timeout=20)
                        if r["pin_message"] and isinstance(res, dict) and res.get("message_id"):
                            try:
                                tg.call(token, "pinChatMessage", {"chat_id": data["chat_id"], "message_id": res["message_id"], "disable_notification": True}, timeout=15)
                            except tg.TgError:
                                pass
                        lim.ok()
                        with lock:
                            counters["sent"] += 1
                            st["sentCount"] = st.get("sentCount", 0) + 1
                            done_buf.append((bc_id, bot_id, str(a["telegram_id"])))
                        return
                    except tg.TgError as e:
                        if (getattr(e, "retry_after", None) or e.code == 429) and limited < 50:
                            limited += 1
                            attempt -= 1
                            lim.penalize(min(float(e.retry_after or 1), 60))
                            continue
                        if (e.code == 0 or e.code >= 500) and attempt < 4:
                            time.sleep(min(1.5 * attempt, 6))
                            continue
                        kind = "unreachable" if getattr(e, "unreachable", False) else "error"
                        reason = (e.description or "error")[:160]
                        with lock:
                            counters["failed"] += 1
                            st["failedCount"] = st.get("failedCount", 0) + 1
                            if kind == "unreachable":
                                counters["unreachable"] += 1
                                counters["blocked"] += 1
                            rk = f"{kind}:{reason}"
                            rr = reasons.setdefault(rk, {"reason": reason, "kind": kind, "count": 0})
                            rr["count"] += 1
                            fail_buf.append((bc_id, bot_id, str(a["telegram_id"]), kind, reason, appdb.now_iso()))
                            failed_list.append({"telegramId": str(a["telegram_id"]), "kind": kind, "reason": reason})
                        if e.code == 401:
                            st["fatal"] = "Telegram rejected this bot's token."
                        return

            def sender():
                while True:
                    a = q.get()
                    if a is None:
                        return
                    try:
                        send_one(a)
                    except Exception as ex:
                        log.exception("send")
                        with lock:
                            counters["failed"] += 1
                            st["failedCount"] = st.get("failedCount", 0) + 1
                            fail_buf.append((bc_id, bot_id, str(a["telegram_id"]), "error", str(ex)[:160], appdb.now_iso()))
                    with lock:
                        flush()

            pool = [threading.Thread(target=sender, daemon=True) for _ in range(nsend)]
            for th in pool:
                th.start()
            for a in audience_iter(bot_id, r["language_filter"], int(st["targetCount"])):
                if ctl.cancelled.is_set() or st.get("fatal"):
                    break
                while ctl.paused.is_set() and not ctl.cancelled.is_set():
                    time.sleep(0.2)
                st["status"] = "Delivering"
                q.put(a)
            for _ in pool:
                q.put(None)
            for th in pool:
                th.join()
            if st["status"] != "Cancelled":
                st["status"] = "Failed" if st.get("sentCount", 0) == 0 and st.get("failedCount", 0) > 0 else "Done"

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in list(per.keys())]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with lock:
            flush(True)
        why = ""
        with appdb.db() as c:
            cur = appdb.one(c, "SELECT status,user_id,title FROM broadcasts WHERE id=?", (bc_id,))
            if cur and cur["status"] == "Cancelled":
                final = "Cancelled"
            elif counters["sent"] == 0 and counters["failed"] > 0:
                final = "Failed"
            else:
                final = "Done"
            fatals = [s.get("fatal") for s in per.values() if s.get("fatal")]
            if counters["sent"] == 0 and counters["failed"] == 0 and fatals:
                why = " " + fatals[0]
                final = "Failed"
            elif counters["sent"] == 0 and counters["failed"] == 0:
                why = " No recipients delivered (empty audience or token decrypt failed). Re-save bot token + set SECRET_KEY."
                final = "Failed"
            c.execute("UPDATE broadcasts SET status=?, in_progress_count=0, finished_at=?, updated_at=? WHERE id=?",
                      (final, appdb.now_iso(), appdb.now_iso(), bc_id))
            c.execute("DELETE FROM broadcast_done WHERE bc_id=?", (bc_id,))
        title = (cur["title"] if cur else bc_id)
        msg = f"Broadcast \u201c{title}\u201d {final.lower()}: {counters['sent']} sent, {counters['failed']} failed.{why}"
        appdb.notify(uid, "Broadcast " + final.lower(), msg, "success" if final == "Done" else "warning", "tab:Broadcast Manager")
        try:
            from backend import connect_bot
            connect_bot.alert(uid, "broadcastReports", "\U0001f4e3 " + connect_bot._h(msg))
        except Exception:
            pass
    except Exception:
        log.exception("broadcast %s crashed", bc_id)
        with appdb.db() as c:
            c.execute("UPDATE broadcasts SET status='Failed', finished_at=?, in_progress_count=0 WHERE id=? AND status IN ('Active','Paused')",
                      (appdb.now_iso(), bc_id))
    finally:
        with _cl:
            _ctl.pop(bc_id, None)


def act(user_id: str, bc_id: str, action: str) -> dict:
    action = (action or "").lower()
    with appdb.read() as c:
        r = appdb.one(c, "SELECT id,status FROM broadcasts WHERE id=? AND user_id=?", (bc_id, user_id))
    if not r:
        raise ApiError("Broadcast not found.", 404)
    with _cl:
        ctl = _ctl.get(bc_id)
    if action == "cancel":
        if ctl:
            ctl.cancelled.set()
        with appdb.db() as c:
            c.execute("UPDATE broadcasts SET status='Cancelled', updated_at=? WHERE id=?", (appdb.now_iso(), bc_id))
        return {"ok": True, "status": "Cancelled"}
    if action == "pause":
        if ctl:
            ctl.paused.set()
        with appdb.db() as c:
            c.execute("UPDATE broadcasts SET status='Paused', updated_at=? WHERE id=?", (appdb.now_iso(), bc_id))
        return {"ok": True, "status": "Paused"}
    if action == "resume":
        if ctl:
            ctl.paused.clear()
        with appdb.db() as c:
            c.execute("UPDATE broadcasts SET status='Active', updated_at=? WHERE id=?", (appdb.now_iso(), bc_id))
        return {"ok": True, "status": "Active"}
    raise ApiError("Unknown action.", 400)


def set_speed(user_id: str, bc_id: str, speed: str) -> dict:
    rate, label = resolve_speed(user_id, speed)
    with _cl:
        ctl = _ctl.get(bc_id)
        if ctl:
            ctl.rate = rate
    with appdb.db() as c:
        r = appdb.one(c, "SELECT id FROM broadcasts WHERE id=? AND user_id=?", (bc_id, user_id))
        if not r:
            raise ApiError("Broadcast not found.", 404)
        c.execute("UPDATE broadcasts SET delivery_speed=?, updated_at=? WHERE id=?", (label, appdb.now_iso(), bc_id))
    return {"ok": True, "speed": label}


def bot_status(user_id: str, bc_id: str, bot_id: str, status: str) -> dict:
    status = (status or "").title()
    with _cl:
        ctl = _ctl.get(bc_id)
        if ctl:
            ctl.bot_state[bot_id] = status
    return {"ok": True}


def delete(user_id: str, bc_id: str) -> dict:
    with appdb.db() as c:
        r = appdb.one(c, "SELECT id,status FROM broadcasts WHERE id=? AND user_id=?", (bc_id, user_id))
        if not r:
            raise ApiError("Broadcast not found.", 404)
        if r["status"] in ("Active", "Paused"):
            raise ApiError("Cancel the broadcast before deleting it.", 400)
        c.execute("DELETE FROM broadcasts WHERE id=?", (bc_id,))
        c.execute("DELETE FROM broadcast_failures WHERE bc_id=?", (bc_id,))
        c.execute("DELETE FROM broadcast_done WHERE bc_id=?", (bc_id,))
    return {"ok": True}


def recover_on_start() -> None:
    with appdb.db() as c:
        rows = appdb.rows(c, "SELECT id FROM broadcasts WHERE status IN ('Active','Paused')")
        for r in rows:
            c.execute("UPDATE broadcasts SET status='Failed', finished_at=?, updated_at=? WHERE id=?",
                      (appdb.now_iso(), appdb.now_iso(), r["id"]))
            log.warning("marked interrupted broadcast %s as Failed", r["id"])
