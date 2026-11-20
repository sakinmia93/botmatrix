"""Turns raw runtime errors into clean, safe, readable ones.

Bot owners must only ever see what is relevant to *their* command: the error type, a plain explanation, the line of their own
code — never server file paths, internal frames, tokens or keys.

Hints are aligned with go-telebot/telebot errors.go (Telegram API error catalog).
"""
import re

_TOKEN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_PATH = re.compile(r"(?:/[A-Za-z0-9_.\-]+){2,}(?:\.py)?(?:\", line \d+)?")
_KEYS = re.compile(r"\b(?:BMP|sk|pk|key)[-_][A-Za-z0-9_\-]{12,}\b")
_EMAIL = re.compile(r"\bu_[0-9a-f]{8,}@matrix\.local\b")


def redact(text) -> str:
    try:
        from backend.security import redact_secrets
        text = redact_secrets(text)
    except Exception:
        pass
    s = str(text or "")
    s = _TOKEN.sub("<bot token hidden>", s)
    s = _KEYS.sub("<key hidden>", s)
    s = _EMAIL.sub("<hidden>", s)
    s = re.sub(r'File "(?!<command>)[^"]*"', 'File "<hidden>"', s)
    s = _PATH.sub("<path hidden>", s)
    return s


# (regex on lower-cased message, user-facing hint) — telebot errors.go + platform
_HINTS = [
    (r"request entity too large|payload too large", "The request body is too large for Telegram."),
    (r"unauthorized|401", "Unauthorized — the bot token is invalid or revoked. Re-save the token."),
    (r"not found.*404|404.*not found", "Telegram returned Not Found for that resource."),
    (r"internal server error|500", "Telegram had an internal error. Retry in a moment."),
    (r"button_data_invalid|bad request: button", "Inline button callback_data is invalid (too long or bad characters). Max 64 bytes."),
    (r"user_id_invalid|bad request: user_id", "USER_ID_INVALID — pass a numeric Telegram user id."),
    (r"expected an array of string as options|poll options", "Poll options must be a list of non-empty strings."),
    (r"failed to get http url content|bad url content", "Telegram could not download that HTTP URL (blocked, private, or invalid)."),
    (r"message can't be edited|message to edit not found|cant.?edit.?message", "The message can't be edited (gone, too old, or identical text)."),
    (r"can't remove chat owner", "You can't remove the chat owner."),
    (r"can't upload file by url", "Telegram couldn't upload the file from that URL."),
    (r"can't use the media of the specified type in the album", "That media type can't be mixed in this album."),
    (r"chat description is not modified|chat about not modified", "Chat description is unchanged — nothing to update."),
    (r"chat not found", "Telegram can't find that chat/channel. Check the id or @username, and that the bot was added there."),
    (r"chat_id is empty|empty chat.?id", "chat_id is missing. Pass `u` or `message.chat.id`."),
    (r"message must be non-empty|message text is empty|text is empty|empty message|empty text", "The text to send is empty. Pass a non-empty string to sendMessage/editMessageText."),
    (r"image_process_failed|image process failed", "Telegram failed to process the image."),
    (r"group chat was upgraded|migrated to a supergroup|group.?migrated", "This group was upgraded to a supergroup — use the new chat id."),
    (r"message is not modified|same message content", "New content is identical to the current message — Telegram ignores no-op edits."),
    (r"message can't be deleted|no rights to delete", "The message can't be deleted (permissions or already gone)."),
    (r"not enough rights to restrict|no rights to restrict", "Bot lacks permission to restrict/unrestrict members."),
    (r"have no rights to send a message|no rights to send", "Bot has no rights to send messages in that chat."),
    (r"chat_send_gifs_forbidden|no rights to send gifs|sending gifs is not allowed", "Sending GIFs is not allowed in this chat."),
    (r"not enough rights to send photos|no rights to send photo", "Bot can't send photos in that chat."),
    (r"not enough rights to send stickers|no rights to send stickers", "Bot can't send stickers in that chat."),
    (r"message to delete not found|not found to delete", "Message to delete was not found (already deleted)."),
    (r"message to forward not found|not found to forward", "Message to forward was not found."),
    (r"reply message not found|not found to reply", "The message you tried to reply to was deleted."),
    (r"query is too old|query_id_invalid|query too old", "answerCallbackQuery failed — the button callback expired."),
    (r"invalid sticker emojis|sticker emojis invalid", "Sticker emoji list is invalid."),
    (r"stickerset_invalid|sticker set invalid", "Sticker set is invalid."),
    (r"invalid sticker set name|sticker set invalid name", "Invalid sticker set name."),
    (r"sticker set name is already occupied", "That sticker set name is already taken."),
    (r"reply markup is too long|too long markup", "Inline keyboard / reply markup is too large."),
    (r"message is too long|too long message", "The message is longer than 4096 characters. Split it."),
    (r"user is an administrator of the chat|user is admin", "That user is a chat admin — this action is not allowed on admins."),
    (r"wrong file identifier|wrong file id|wrong remote file id", "file_id / URL is wrong. Re-upload or use a fresh file_id."),
    (r"wrong type of the web page content|wrong type of content", "Wrong type of web page content for this method."),
    (r"wrong http url specified|wrong url", "The HTTP URL is invalid."),
    (r"restricted message forwarding|forward message", "Admins restricted message forwarding in that chat."),
    (r"user_already_participant|user is already a participant", "User is already a participant."),
    (r"hide_requester_missing", "HIDE_REQUESTER_MISSING — required field missing for this join request action."),
    (r"channels_too_much|user_channels_too_much", "Too many channels — Telegram limit reached."),
    (r"bot was blocked by the user|blocked by the user", "This user blocked the bot, so nothing can be sent to them."),
    (r"bot was kicked from the group", "Bot was kicked from that group."),
    (r"bot was kicked from the supergroup", "Bot was kicked from that supergroup."),
    (r"bot was kicked from the channel", "Bot was kicked from that channel."),
    (r"bot can't initiate conversation|not started by user", "The user has to press Start before the bot can message them."),
    (r"user is deactivated", "This Telegram account was deleted."),
    (r"bot is not a member of the channel|not channel member", "Bot is not a member of that channel."),
    (r"not enough rights|need administrator rights|chat_admin_required|have no rights", "The bot lacks admin rights in that chat. Make it an admin with the needed permission."),
    (r"not a member|member list is inaccessible|bot is not a member", "The bot isn't a member/admin of that channel or group."),
    (r"too many requests|retry after|flood", "Telegram rate limit hit — sending too fast. Slow down or add `time.sleep`."),
    (r"read timed out|connecttimeout|connectionpool|readtimeout", "The outbound HTTP request timed out. Prefer short timeouts; for own webhooks the platform runs them in-process."),
    (r"message caption is empty", "The caption is empty. Pass caption text or omit caption."),
    (r"there is no text in the message to edit", "That message has no text to edit (it may be media-only). Use editMessageCaption for captions."),
    (r"message identifier is not specified", "message_id is missing or invalid. Save it from sendMessage/editMessageText and pass it as an integer."),
    (r"invalid user_id|user_id is empty|needs the telegram user id", "The user id given to Telegram is empty or not a number. Pass the numeric id (for example `u`)."),
    (r"can't parse entities", "The formatting (HTML/Markdown) in the message is invalid. Escape special characters or remove parse_mode."),
    (r"attributeerror", "An object is missing that attribute. For media use `if message.photo:` (missing fields are None)."),
    (r"typeerror", "Wrong type passed to a function — check arguments."),
    (r"valueerror", "A value is invalid for this operation."),
    (r"jsondecodeerror|expecting value", "Failed to parse JSON — the response body is not valid JSON."),
    (r"ssrf|url target is blocked", "That URL is blocked by SSRF protection (private/localhost/metadata)."),
    (r"database is locked", "The bot database was briefly busy. Retry the action."),
    (r"too many webhook deliveries", "Webhook fan-out is at capacity. The platform queues deliveries; retry shortly or use Broadcast Manager for large audiences."),
    (r"command took too long|limit 160", "The command took too long (limit 160 seconds)."),
    (r"is not defined", "A name is used before it was created — check spelling and that it is defined above."),
    (r"division by zero", "A number was divided by zero."),
    (r"list index out of range|index out of range", "A list position doesn't exist — check the list length first."),
    (r"keyerror", "A dictionary key doesn't exist — use `.get('key')`."),
    (r"timed out|timeout", "The command took too long (limit 160 seconds)."),
    (r"syntax error", "The command code has a syntax mistake."),
    (r"nonetype", "A value is `None` (empty) where text/number/object was expected."),
    (r"not allowed|isn't allowed|permission", "This action isn't allowed in the sandbox."),
    (r"bad request", "Telegram rejected the request (Bad Request). Check the parameters you passed."),
    (r"forbidden", "Telegram forbade this action. The user may have blocked the bot, or the bot lacks rights."),
    (r"conflict", "Another getUpdates/webhook is already reading this bot. Stop the other instance."),
    (r"bad gateway|service unavailable", "Telegram had a temporary server error. Retry in a moment."),
]


def hint_for(exc_type: str, message: str) -> str:
    m = f"{exc_type} {message}".lower()
    for rx, h in _HINTS:
        if re.search(rx, m):
            return h
    # Fallback: go-telebot catalog in telegram/api_errors.py
    try:
        from backend.telegram.api_errors import lookup
        _code, _name, hint = lookup(message or "", 0)
        if hint and _name != "TelegramAPIError":
            return hint
    except Exception:
        pass
    return ""


def clean_message(exc_type: str, message: str) -> str:
    msg = redact(message).strip()
    msg = re.sub(r"^(TelegramAPIError|TgError|TelegramError):?\s*", "", msg)
    msg = re.sub(r"^\[(\d+)\]\s*", r"Telegram \1: ", msg)
    h = hint_for(exc_type, msg)
    first = f"{exc_type}: {msg}" if exc_type and exc_type not in msg[:40] else msg
    return (first + (f"\n→ {h}" if h else ""))[:1500]


def user_stack(tb: str, code: str = "", offset: int = 0) -> str:
    """Only frames that belong to the owner's command, as `line N: source`."""
    lines = (code or "").split("\n")
    out, seen = [], set()
    for m in re.finditer(r'File "<command>", line (\d+)', tb or ""):
        n = int(m.group(1))
        if n in seen:
            continue
        seen.add(n)
        shown = max(1, n - offset)
        src = lines[n - 1].strip() if 0 < n <= len(lines) else ""
        out.append(f"line {shown}: {redact(src)[:160]}" if src else f"line {shown}")
    return "\n".join(out)


def format_command_error(cmd_name: str, line_no: int, exc_type: str, message: str, tb: str = "", code: str = "") -> str:
    """TBC-style: Warning Error in /cmd (line N) Type: msg then hint."""
    name = cmd_name if str(cmd_name).startswith("/") else f"/{cmd_name}"
    head = f"\u26a0\ufe0f Error in {name}"
    if line_no:
        head += f" (line {line_no})"
    body = clean_message(exc_type, message)
    stack = user_stack(tb, code)
    parts = [head, body]
    if stack:
        parts.append(stack)
    return "\n".join(parts)[:2000]
