# libs.TelegramSession

MTProto user-client (Telethon) for BotMatrix sandbox.

## Deploy note
On import, `telegram_session_lib.py` expands `tg_gz_0.b64` … `tg_gz_9.b64` (gzip+base64) into `_telegram_session_full.py`.
Requires server package: `telethon`.

## Auth
- create / sendCode / verifyCode / verifyPassword
- getStatus / listSessions / disconnect / logout / delete

## Business management
- listSessions(status, country_code, tag)
- listByCountry / listByStatus / stats
- setTags / setNotes / setName / getByPhone
- checkAccount (health: good | normal | restricted | bad)
- detectCountry / validateApi
- addTrace / getTrace / clearTrace

## Features
messages, media, chats, admin, contacts, profile, Stars/Gifts, reactions, search, call()

Session strings are encrypted at rest. Only opaque `session_id` is returned to bot code.
