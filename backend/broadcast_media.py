"""Broadcast media: uploads live in memory only (never on disk); URLs are detected automatically."""
import ipaddress, re, secrets, socket, threading, time
from urllib.parse import urlparse

import requests

from backend.errors import ApiError

MAX_BYTES = 20 * 1024 * 1024
TTL = 3600
_items = {}
_lock = threading.Lock()

ACCEPT = {  # message type -> allowed mime prefixes
    "Photo": ("image/",), "Video": ("video/",), "Audio": ("audio/",), "Doc": ("",), "GIF": ("image/gif", "video/"),
    "Voice": ("audio/",), "VidNote": ("video/",), "Sticker": ("image/webp", "application/x-tgsticker", "video/webm"),
}


def _gc():
    now = time.time()
    for k in [k for k, v in _items.items() if v["exp"] < now]:
        _items.pop(k, None)


def put(user_id: str, name: str, mime: str, data: bytes, mtype: str) -> str:
    if mtype not in ACCEPT:
        raise ApiError("Choose a media type first.", 400)
    if not data:
        raise ApiError("The file is empty.", 400)
    if len(data) > MAX_BYTES:
        raise ApiError("That file is too large (max 20 MB).", 413)
    if not any((mime or "").startswith(p) for p in ACCEPT[mtype]):
        raise ApiError(f"That file does not match the {mtype} type.", 400)
    with _lock:
        _gc()
        mine = [v for v in _items.values() if v["uid"] == user_id]
        if len(mine) >= 5 or sum(len(v["data"]) for v in mine) + len(data) > 60 * 1024 * 1024:
            raise ApiError("Too many uploads waiting. Send or cancel your broadcast first.", 429)
        mid = "m_" + secrets.token_hex(10)
        _items[mid] = {"uid": user_id, "name": (name or "file")[:120], "mime": mime or "application/octet-stream", "data": data, "exp": time.time() + TTL}
    return mid


def get(mid: str, user_id: str):
    with _lock:
        v = _items.get(mid)
    if not v or v["uid"] != user_id or v["exp"] < time.time():
        return None
    return v


def drop(mid: str):
    with _lock:
        _items.pop(mid, None)


# ------------------------------------------------------------------ URL detection
def _public(host: str) -> bool:
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


def _ext_type(path: str, mime: str = ""):
    p = path.lower().split("?")[0]
    if mime.startswith("image/gif") or p.endswith(".gif"):
        return "GIF"
    if mime.startswith("image/webp") or p.endswith(".webp"):
        return "Sticker" if False else "Photo"
    if mime.startswith("image/") or p.endswith((".jpg", ".jpeg", ".png")):
        return "Photo"
    if mime.startswith("video/") or p.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "Video"
    if p.endswith((".ogg", ".oga", ".opus")) or mime in ("audio/ogg", "audio/opus"):
        return "Voice"
    if mime.startswith("audio/") or p.endswith((".mp3", ".m4a", ".wav", ".flac")):
        return "Audio"
    return "Doc"


_KEEP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "s": "s", "strike": "s", "del": "s", "code": "code", "pre": "pre", "tg-spoiler": "tg-spoiler", "blockquote": "blockquote"}


def _tg_html(h: str):
    """Embed-page HTML -> the small HTML subset Telegram accepts (bold, italic, links…). Returns (text, "HTML" | "")."""
    import html as _h
    def _emo(m):
        eid = re.search(r'data-(?:document-id|custom-emoji-id|emoji-id)="(\d+)"', m.group(1))
        inner = m.group(2) or "🙂"
        return '<tg-emoji emoji-id="%s">%s</tg-emoji>' % (eid.group(1), inner) if eid else inner
    h = re.sub(r'<(?:i|tg-emoji)\b([^>]*(?:class="emoji|tg-emoji|custom-emoji)[^>]*)>\s*(?:<b>)?(.*?)(?:</b>)?\s*</(?:i|tg-emoji)>', _emo, h, flags=re.S)
    h = re.sub(r"<br\s*/?>", "\n", h)
    out, stack, formatted = [], [], False
    for tok in re.split(r"(<[^>]+>)", h):
        if not tok:
            continue
        if tok.startswith("<"):
            m = re.match(r"<\s*(/?)\s*([a-zA-Z0-9-]+)([^>]*)>", tok)
            if not m:
                continue
            closing, name, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3)
            if name == "tg-emoji":
                if closing:
                    out.append("</tg-emoji>")
                else:
                    em = re.search(r'emoji-id="(\d+)"', attrs)
                    out.append('<tg-emoji emoji-id="%s">' % em.group(1) if em else "")
                    formatted = formatted or bool(em)
            elif name == "a":
                if closing:
                    if "a" in stack:
                        stack.remove("a")
                        out.append("</a>")
                else:
                    hm = re.search(r'href="([^"]+)"', attrs)
                    href = _h.unescape(hm.group(1)) if hm else ""
                    if href.startswith("/"):
                        href = "https://t.me" + href
                    if href.startswith(("http://", "https://", "tg://")):
                        out.append('<a href="%s">' % href.replace("&", "&amp;").replace('"', "&quot;"))
                        stack.append("a")
                        formatted = True
            elif name in _KEEP:
                t = _KEEP[name]
                if closing:
                    if t in stack:
                        stack.remove(t)
                        out.append(f"</{t}>")
                else:
                    out.append(f"<{t}>")
                    stack.append(t)
                    formatted = True
        else:
            out.append(_h.unescape(tok).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    for t in reversed(stack):
        out.append(f"</{t}>")
    text = "".join(out).strip()
    return text, ("HTML" if formatted or "&" in text else "") if text else ("", "")


def _buttons(h: str):
    """Inline buttons under an embedded post, keeping their rows. Only URL buttons are public on the embed page."""
    import html as _h
    rows = []
    for rm in re.finditer(r'<div class="tgme_widget_message_inline_row">(.*?)</div>\s*(?=<div class="tgme_widget_message_inline_row"|</div>)', h, re.S):
        row = []
        for bm in re.finditer(r'<a class="tgme_widget_message_inline_button[^"]*"([^>]*)>(.*?)</a>', rm.group(1), re.S):
            href = re.search(r'href="([^"]+)"', bm.group(1))
            label = re.sub(r"<[^>]+>", "", bm.group(2))
            label = _h.unescape(label).strip()
            url = _h.unescape(href.group(1)) if href else ""
            if url.startswith("/"):
                url = "https://t.me" + url
            if label and url.startswith(("http://", "https://", "tg://")):
                row.append({"text": label[:64], "type": "url", "url": url, "row": len(rows) + 1})
        if row:
            rows.append(row)
    return [b for r in rows for b in r]


def detect(url: str) -> dict:
    url = (url or "").strip()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ApiError("Paste a full link that starts with http:// or https://", 400)
    if not _public(u.hostname):
        raise ApiError("That link cannot be used.", 400)
    hdr = {"User-Agent": "Mozilla/5.0 (compatible; BotMatrix/1.0)"}
    host = u.hostname.lower()
    if host in ("t.me", "telegram.me", "www.t.me"):
        m = re.match(r"^/(?:s/)?([A-Za-z0-9_]{4,})/(\d+)", u.path)
        if not m:
            raise ApiError("Paste the link of a public Telegram post, like t.me/channel/123.", 400)
        try:
            r = requests.get(f"https://t.me/{m.group(1)}/{m.group(2)}?embed=1&mode=tme", headers=hdr, timeout=10)
        except requests.RequestException:
            raise ApiError("Could not open that Telegram post.", 502)
        h = r.text
        if r.status_code != 200 or "tgme_widget_message" not in h:
            raise ApiError("That Telegram post is not public (or it was deleted).", 400)
        vid = re.search(r'<video[^>]+src="([^"]+)"', h)
        aud = re.search(r'<audio[^>]+src="([^"]+)"', h)
        photo = re.search(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)", h)
        txt = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', h, re.S)
        caption, mode = _tg_html(txt.group(1)) if txt else ("", "")
        note = ""
        if len(caption) > 1024:
            caption, mode, note = "", "", "The post's text is longer than Telegram's 1024-character caption limit, so it was left out."
        base = {"caption": caption, "parseMode": mode or None, "note": note, "buttons": _buttons(h),
                "customEmojiIds": sorted(set(re.findall(r'emoji-id="(\d+)"', caption)))}
        if "tgme_widget_message_roundvideo" in h and vid:
            return {"type": "VidNote", "url": vid.group(1), **{**base, "caption": "", "parseMode": None}}
        if vid:
            return {"type": "GIF" if "tgme_widget_message_video_player" in h and "animated" in h else "Video", "url": vid.group(1), **base}
        if aud:
            return {"type": "Voice" if "tgme_widget_message_voice" in h else "Audio", "url": aud.group(1), **base}
        if photo:
            return {"type": "Photo", "url": photo.group(1), **base}
        if caption:
            return {"type": "Text", "url": "", **base}
        raise ApiError("That post has no photo, video or text I can use.", 400)
    mime = ""
    try:
        r = requests.head(url, headers=hdr, timeout=8, allow_redirects=False)
        mime = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    except requests.RequestException:
        pass
    return {"type": _ext_type(u.path, mime), "url": url, "caption": "", "parseMode": None, "note": "", "buttons": [], "customEmojiIds": []}
