"""Bot-code broadcasts (Bot.broadcast(...)) use the very same engine as the Broadcast Manager page, so a broadcast started from code
shows up there with live progress and gets personalisation, buttons, premium emoji, pinning, language filter, plan speed and crash-resume."""
import re
from typing import Optional

from backend import appdb, broadcast_service as svc
from backend.errors import ApiError

_TYPES = {"send_message": "Text", "send_photo": "Photo", "send_video": "Video", "send_animation": "GIF", "send_audio": "Audio",
          "send_document": "Doc", "send_voice": "Voice", "send_video_note": "VidNote", "send_sticker": "Sticker"}
_FIELD = {"Photo": "photo", "Video": "video", "GIF": "animation", "Audio": "audio", "Doc": "document", "Voice": "voice",
          "VidNote": "video_note", "Sticker": "sticker"}


def is_code_id(x) -> bool:
    return str(x).startswith("bc_")


def _buttons(markup) -> list:
    out = []
    if not isinstance(markup, dict):
        return out
    for r, row in enumerate(markup.get("inline_keyboard") or [], 1):
        for b in row or []:
            if not isinstance(b, dict) or not b.get("text"):
                continue
            item = {"text": str(b["text"]), "row": r}
            if b.get("url"):
                item.update(type="url", url=b["url"])
            elif b.get("callback_data") is not None:
                item.update(type="callback_data", callbackData=b["callback_data"])
            elif isinstance(b.get("web_app"), dict):
                item.update(type="web_app", webAppUrl=b["web_app"].get("url", ""))
            elif b.get("switch_inline_query") is not None:
                item.update(type="switch_inline_query", switchInlineQuery=b["switch_inline_query"])
            elif b.get("switch_inline_query_current_chat") is not None:
                item.update(type="switch_inline_query_current_chat", switchInlineQuery=b["switch_inline_query_current_chat"])
            elif isinstance(b.get("copy_text"), dict):
                item.update(type="copy_text", copyText=b["copy_text"].get("text", ""))
            else:
                continue
            if b.get("style"):
                item["style"] = b["style"]
            if b.get("icon_custom_emoji_id"):
                item["iconEmojiId"] = str(b["icon_custom_emoji_id"])
            out.append(item)
    return out


def _owner(public_id: str) -> Optional[str]:
    with appdb.read() as c:
        b = appdb.one(c, "SELECT user_id FROM bots WHERE id=?", (public_id,))
    return b["user_id"] if b else None


def start(public_bot_id: str, function: str, speed, kwargs: dict) -> Optional[dict]:
    """Returns the result dict, or None when this call cannot be expressed in the shared engine (legacy path is used then)."""
    key = re.sub(r"[^a-z]", "", str(function or "").lower())
    fn = next((k for k in _TYPES if k.replace("_", "") == key), None)
    if not fn:
        return None
    mtype = _TYPES[fn]
    text = kwargs.get("text") if mtype == "Text" else kwargs.get("caption")
    media = ""
    if mtype != "Text":
        media = str(kwargs.get(_FIELD[mtype]) or "")
        if not re.match(r"^https?://", media):
            return None               # a Telegram file_id: only the legacy engine can reuse it
    uid = _owner(public_bot_id)
    if not uid:
        return {"status": "error", "message": "Bot not found."}
    with appdb.read() as c:
        user = appdb.one(c, "SELECT * FROM users WHERE id=?", (uid,))
        n = appdb.one(c, "SELECT COUNT(*) n FROM chats WHERE bot_id=? AND is_blocked=0 AND bot_blocked=0", (public_bot_id,))["n"]
    pm = kwargs.get("parse_mode") or kwargs.get("parseMode") or "None"
    # Frontend parity aliases: languageFilter, targetUserLimit, pinMessage, inlineButtons, targetBotIds
    lang = (kwargs.get("languageFilter") or kwargs.get("language_filter")
            or kwargs.get("language") or kwargs.get("languages") or "All")
    try:
        lim_raw = kwargs.get("targetUserLimit", kwargs.get("target_user_limit", kwargs.get("limit", None)))
        if lim_raw is None or str(lim_raw).strip().lower() in ("", "all"):
            lim = max(1, int(n or 1))
        else:
            lim = max(1, int(lim_raw))
    except Exception:
        lim = max(1, int(n or 1))
    pin = bool(kwargs.get("pinMessage") or kwargs.get("pin_message") or kwargs.get("pin") or False)
    buttons = kwargs.get("inlineButtons") or kwargs.get("inline_buttons")
    if buttons is None:
        buttons = _buttons(kwargs.get("reply_markup") or kwargs.get("buttons") or {})
    elif isinstance(buttons, dict):
        buttons = _buttons(buttons)
    bot_ids = kwargs.get("targetBotIds") or kwargs.get("target_bot_ids") or kwargs.get("bot_ids")
    if isinstance(bot_ids, (list, tuple)) and bot_ids:
        target_ids = [str(x) for x in bot_ids][:200]
    else:
        target_ids = [public_bot_id]
    body = {"title": (str(text or "") or mtype)[:32], "targetBotIds": target_ids, "messageType": mtype, "messageText": str(text or ""),
            "parseMode": pm if pm in ("HTML", "Markdown", "MarkdownV2") else "None",
            "inlineButtons": buttons if isinstance(buttons, list) else [],
            "languageFilter": str(lang) if str(lang).strip() else "All",
            "pinMessage": pin, "targetUserLimit": lim}
    if mtype != "Text":
        body.update(mediaSource="url", mediaRef=media)
    if speed:
        try:
            want = max(1, min(25, int(speed)))                       # docs: 1-25 msgs/sec per bot
            want = min(want, svc.plan_speed(uid))                    # never above what the plan allows
            body["deliverySpeed"] = f"{want} msgs/sec"
        except (TypeError, ValueError):
            body["deliverySpeed"] = str(speed)
    try:
        r = svc.create(dict(user), body)
    except ApiError as e:
        msg = e.message if hasattr(e, "message") else str(e)
        if "needs at least" in msg:
            return None                # docs have no audience minimum for single-bot function broadcasts: legacy engine handles it
        return {"status": "error", "message": msg}
    return {"status": "success", "message": "Task added Successfully", "broadcast_id": r["id"], "mode": "single",
            "speed": int(re.sub(r"\D", "", str(r.get("deliverySpeed") or "8")) or 8), "total": r["totalTargetUsers"]}


def _uid(public_bot_id: str) -> str:
    u = _owner(public_bot_id)
    if not u:
        raise ApiError("Bot not found.", 404)
    return u


def status(public_bot_id: str, bc_id: str) -> dict:
    d = svc.get_for(_uid(public_bot_id), bc_id)
    return {"broadcast_id": d["id"], "status": d["status"], "mode": "single", "speed": d["deliverySpeed"], "total": d["totalTargetUsers"],
            "sent": d["sentCount"], "failed": d["failedCount"], "blocked": d["blockedCount"], "position": d["sentCount"] + d["failedCount"],
            "pinned": d["pinMessage"], "percent": d["percent"], "total_users": d["totalTargetUsers"], "total_success": d["sentCount"],
            "total_errors": d["failedCount"], "total_bots": 1, "done_bots": 1 if d["status"] == "Done" else 0,
            "processed": d["sentCount"] + d["failedCount"], "remaining": max(0, d["totalTargetUsers"] - d["sentCount"] - d["failedCount"])}


def progress(public_bot_id: str, bc_id: str) -> dict:
    s = status(public_bot_id, bc_id)
    return {"broadcast_id": bc_id, "status": s["status"], "progress_pct": s["percent"], "sent": s["sent"], "failed": s["failed"], "total": s["total"],
            "processed": s["processed"], "remaining": s["remaining"], "speed": s["speed"], "eta_seconds": None}


def control(public_bot_id: str, bc_id: str, action: str, speed=None) -> dict:
    uid = _uid(public_bot_id)
    try:
        if action == "speed":
            return svc.set_speed(uid, bc_id, str(speed))
        return svc.act(uid, bc_id, {"stop": "cancel"}.get(action, action))
    except ApiError as e:
        return {"status": "error", "message": e.message if hasattr(e, "message") else str(e)}


def list_jobs(public_bot_id: str, limit: int = 20) -> list:
    uid = _uid(public_bot_id)
    out = []
    for d in svc.list_for(uid):
        if public_bot_id in d["targetBotIds"]:
            out.append({"broadcast_id": d["id"], "status": d["status"], "speed": d["deliverySpeed"], "total": d["totalTargetUsers"],
                        "sent": d["sentCount"], "failed": d["failedCount"]})
        if len(out) >= limit:
            break
    return out
