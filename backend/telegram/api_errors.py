"""Telegram Bot API error catalog (aligned with go-telebot/telebot errors.go).

Maps Telegram description strings to stable codes + short owner-facing hints.
Used by BotWrapper and error_clean so every failure is understandable.
"""
from __future__ import annotations

from typing import Tuple

# description substring (lower) -> (code, short_name, hint)
_CATALOG: list[tuple[str, int, str, str]] = [
    ("request entity too large", 400, "ErrTooLarge", "The request body is too large for Telegram."),
    ("unauthorized", 401, "ErrUnauthorized", "Unauthorized — bot token invalid or revoked. Re-save the token."),
    ("not found", 404, "ErrNotFound", "Telegram returned Not Found for that resource."),
    ("internal server error", 500, "ErrInternal", "Telegram had an internal error. Retry in a moment."),
    ("button_data_invalid", 400, "ErrBadButtonData", "Inline button callback_data is invalid (max 64 bytes)."),
    ("user_id_invalid", 400, "ErrBadUserID", "USER_ID_INVALID — pass a numeric Telegram user id."),
    ("expected an array of string as options", 400, "ErrBadPollOptions", "Poll options must be a list of non-empty strings."),
    ("failed to get http url content", 400, "ErrBadURLContent", "Telegram could not download that HTTP URL."),
    ("message can't be edited", 400, "ErrCantEditMessage", "The message can't be edited (gone, too old, or identical text)."),
    ("message to edit not found", 400, "ErrCantEditMessage", "The message can't be edited (gone, too old, or identical text)."),
    ("can't remove chat owner", 400, "ErrCantRemoveOwner", "You can't remove the chat owner."),
    ("can't upload file by url", 400, "ErrCantUploadFile", "Telegram couldn't upload the file from that URL."),
    ("can't use the media of the specified type in the album", 400, "ErrCantUseMediaInAlbum", "That media type can't be mixed in this album."),
    ("chat description is not modified", 400, "ErrChatAboutNotModified", "Chat description is unchanged."),
    ("chat not found", 400, "ErrChatNotFound", "Chat/channel not found. Check id/@username and that the bot was added."),
    ("chat_id is empty", 400, "ErrEmptyChatID", "chat_id is missing. Pass u or message.chat.id."),
    ("message must be non-empty", 400, "ErrEmptyMessage", "The text to send is empty."),
    ("text is empty", 400, "ErrEmptyText", "The text to send is empty."),
    ("message text is empty", 400, "ErrEmptyText", "The text to send is empty."),
    ("image_process_failed", 400, "ErrFailedImageProcess", "Telegram failed to process the image."),
    ("group chat was upgraded to a supergroup", 400, "ErrGroupMigrated", "Group upgraded to supergroup — use the new chat id."),
    ("message is not modified", 400, "ErrMessageNotModified", "New content is identical — Telegram ignores no-op edits."),
    ("message can't be deleted", 400, "ErrNoRightsToDelete", "The message can't be deleted (permissions or already gone)."),
    ("not enough rights to restrict", 400, "ErrNoRightsToRestrict", "Bot lacks permission to restrict/unrestrict members."),
    ("have no rights to send a message", 400, "ErrNoRightsToSend", "Bot has no rights to send messages in that chat."),
    ("chat_send_gifs_forbidden", 400, "ErrNoRightsToSendGifs", "Sending GIFs is not allowed in this chat."),
    ("not enough rights to send photos", 400, "ErrNoRightsToSendPhoto", "Bot can't send photos in that chat."),
    ("not enough rights to send stickers", 400, "ErrNoRightsToSendStickers", "Bot can't send stickers in that chat."),
    ("message to delete not found", 400, "ErrNotFoundToDelete", "Message to delete was not found."),
    ("message to forward not found", 400, "ErrNotFoundToForward", "Message to forward was not found."),
    ("reply message not found", 400, "ErrNotFoundToReply", "The message you tried to reply to was deleted."),
    ("query is too old", 400, "ErrQueryTooOld", "Callback query expired — answerCallbackQuery too late."),
    ("query_id_invalid", 400, "ErrQueryTooOld", "Callback query id is invalid or expired."),
    ("invalid sticker emojis", 400, "ErrStickerEmojisInvalid", "Sticker emoji list is invalid."),
    ("stickerset_invalid", 400, "ErrStickerSetInvalid", "Sticker set is invalid."),
    ("invalid sticker set name", 400, "ErrStickerSetInvalidName", "Invalid sticker set name."),
    ("sticker set name is already occupied", 400, "ErrStickerSetNameOccupied", "That sticker set name is already taken."),
    ("reply markup is too long", 400, "ErrTooLongMarkup", "Inline keyboard / reply markup is too large."),
    ("message is too long", 400, "ErrTooLongMessage", "Message longer than 4096 characters. Split it."),
    ("user is an administrator of the chat", 400, "ErrUserIsAdmin", "That user is a chat admin — action not allowed."),
    ("wrong file identifier", 400, "ErrWrongFileID", "file_id / URL is wrong. Re-upload or use a fresh file_id."),
    ("wrong remote file id", 400, "ErrWrongFileID", "file_id is wrong. Re-upload or use a fresh file_id."),
    ("wrong type of the web page content", 400, "ErrWrongTypeOfContent", "Wrong type of web page content for this method."),
    ("wrong http url specified", 400, "ErrWrongURL", "The HTTP URL is invalid."),
    ("restricted message forwarding", 400, "ErrForwardMessage", "Admins restricted message forwarding in that chat."),
    ("user_already_participant", 400, "ErrUserAlreadyParticipant", "User is already a participant."),
    ("hide_requester_missing", 400, "ErrHideRequesterMissing", "Required field missing for this join-request action."),
    ("channels_too_much", 400, "ErrChannelsTooMuch", "Too many channels — Telegram limit reached."),
    ("user_channels_too_much", 400, "ErrChannelsTooMuchUser", "User is in too many channels."),
    ("can't parse entities", 400, "ErrCantParseEntities", "HTML/Markdown formatting is invalid. Escape special characters or remove parse_mode."),
    ("message caption is empty", 400, "ErrEmptyCaption", "The caption is empty. Pass caption text or omit caption."),
    ("there is no text in the message to edit", 400, "ErrNoTextToEdit", "That message has no text to edit. Use editMessageCaption for captions."),
    ("bot was blocked by the user", 403, "ErrBlockedByUser", "This user blocked the bot."),
    ("bot was kicked from the group", 403, "ErrKickedFromGroup", "Bot was kicked from that group."),
    ("bot was kicked from the supergroup", 403, "ErrKickedFromSuperGroup", "Bot was kicked from that supergroup."),
    ("bot was kicked from the channel", 403, "ErrKickedFromChannel", "Bot was kicked from that channel."),
    ("bot can't initiate conversation", 403, "ErrNotStartedByUser", "User must press Start before the bot can message them."),
    ("user is deactivated", 403, "ErrUserIsDeactivated", "This Telegram account was deleted."),
    ("bot is not a member of the channel", 403, "ErrNotChannelMember", "Bot is not a member of that channel."),
    ("too many requests", 429, "ErrFlood", "Telegram rate limit — slow down or add time.sleep."),
    ("retry after", 429, "ErrFlood", "Telegram rate limit — wait and retry."),
]


def lookup(description: str, error_code: int = 0) -> Tuple[int, str, str]:
    """Return (code, short_name, hint) for a Telegram description."""
    d = (description or "").lower()
    for needle, code, name, hint in _CATALOG:
        if needle in d:
            return (error_code or code, name, hint)
    if error_code == 401:
        return (401, "ErrUnauthorized", "Unauthorized — bot token invalid or revoked.")
    if error_code == 403:
        return (403, "ErrForbidden", "Telegram forbade this action (blocked, kicked, or no rights).")
    if error_code == 429:
        return (429, "ErrFlood", "Telegram rate limit — slow down.")
    if error_code and error_code >= 500:
        return (error_code, "ErrInternal", "Telegram had a temporary server error. Retry.")
    return (error_code or 400, "TelegramAPIError", "Telegram rejected the request. Check the parameters.")


def enrich(description: str, error_code: int = 0) -> str:
    """One-line message: [code] description then hint."""
    code, name, hint = lookup(description, error_code)
    desc = (description or "Unknown Telegram API error").strip()
    return f"[{code}] {desc}\n→ {hint}"
