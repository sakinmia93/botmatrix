# BOT MATRIX

Full-stack Telegram bot builder platform.

- **Frontend:** React + Vite + TypeScript (UI unchanged)
- **Backend:** Python multi-threaded REST API
- **Database:** SQLite by default (zero setup). Optional PostgreSQL via Docker.

All user account data (bots, commands, broadcasts, settings, notifications, recycle bin, points, etc.) is stored in the database and loaded per authenticated user. No hardcoded demo user bots.

## One-command start (Frontend + Backend)

```bash
chmod +x start.sh
./start.sh
```

Open: **http://localhost:3000**

1. Optionally starts PostgreSQL if `USE_POSTGRES=1` and Docker exists
2. Installs Python deps
3. Installs Node deps
4. Runs Express (port 3000) + Vite + Python API (port 5001)

## Manual start

```bash
cd backend && python3 -m pip install -r requirements.txt && python3 server.py
# other terminal:
npm install && npm run dev
```

## PostgreSQL (optional)

```bash
docker compose up -d postgres
export USE_POSTGRES=1
export DATABASE_URL=postgresql://telebot:telebot_secret@127.0.0.1:5432/telebot_db
./start.sh
```

Default mode is SQLite so the project runs without Docker.

## Data rules

- Register/Login create real users and session tokens
- Bots, broadcasts, notifications, recycle bin, points are user-scoped
- Store catalog is platform-level only
- Chats and bot KV start empty (real data only, no fake samples)

## API

Frontend uses `/api/*` → proxy → `http://127.0.0.1:5001/api/*`  
Auth header: `Authorization: Bearer <token>`


## Configuration (`.env`)

| Variable | Purpose |
| --- | --- |
| `CONNECT_BOT_TOKEN` | Token of the platform's connect bot. Users press *Connect Telegram* in Settings, open the link and press START; the bot then offers keyboard buttons (My Account, My Bots, Broadcast, Alerts, Disconnect) and sends alerts. |
| `SECRET_KEY` | Encrypts bot tokens and API keys at rest. Bot tokens are never sent back to the browser. |

Rotate any token that was ever pasted into a chat or committed to a repository (BotFather → `/revoke`).

## Admin panel

Put your e-mail in `ADMIN_EMAILS` (in `.env`, or later in the panel). Admins get an **Admin** item in the sidebar: overview, users (change plan / add points), plan editor (price, points, limits, features), **Settings** (every `.env` value: SMTP, Turnstile, OTP, rate limits, connect bot token, API keys…) and support tickets. Values saved in the panel are stored in the database (secrets encrypted, never shown again) and win over `.env`; items marked *restart* need a server restart. `SECRET_KEY` stays in `.env` only.

## Bot code ↔ panel parity

`Bot.broadcast(function='send_message'|'send_photo'|…, text=…, reply_markup=…, speed=…, pin=True, language='en')` runs on the same engine as the Broadcast Manager page (same limits, personalisation, buttons, plan speed, pin, resume) and returns a `bc_…` id that `Bot.getBroadcastStatus / pauseBroadcast / resumeBroadcast / stopBroadcast / setBroadcastSpeed` accept. Command names are used exactly as typed (no automatic `/`), and a duplicate name is refused.

## Broadcast notes

- Speed is capped by the plan (Free 5/s, Pro 15/s, Growth 30/s, Ultra Unlimited). Above 30 messages/second Telegram's *paid broadcast* is used (billed by Telegram in Stars, up to 1000/s; the bot needs a Stars balance).
- Pasting a public Telegram post link detects text, media, formatting, premium emoji ids and the post's URL buttons. Premium (custom) emoji in bot messages only render if Telegram allows the bot to use them; otherwise the fallback emoji is shown.
- Buttons accept a Row number (same row = side by side), a colour and a premium emoji id. *Pin broadcast* pins the message in each chat (best effort).

## How it works

- Bots run on the built-in command engine; each bot is polled by its own worker. *Faster Response* uses long polling (20s) instead of 3s polling.
- Points: 1 point per matched command, 50 per bot creation; bots stop when points reach 0.
- Broadcasts: one active/paused per account; *Done* and *Cancelled* are final.
- Transfers are two-step (recipient accepts); the outgoing limit is shared by the Transfer settings and the bot-code functions.
- The code editor completes and checks against the real engine (`/api/editor/catalog`, `/api/editor/validate`).

## Tests

```bash
python3 tests/e2e.py        # backend end-to-end against a mock Telegram (66 checks)
bash tests/ui_env.sh &      # throw-away stack for browser tests
python3 tests/ui_walk.py    # Playwright walkthrough (needs playwright + chromium)
```


## Added in this version

- **Editor safety:** unsaved code is kept as a draft (survives refresh, crash, power or network loss). Leaving with unsaved changes asks for confirmation; reopening the command asks "Continue where you left off?".
- **Editor language service:** suggestions and syntax checks follow the audited v15 surface (`backend/v15_surface.json`, `tests/audit_conformance.py` checks every audit item against the real engine).
- **Transfers:** choose what goes along with the commands — bot database, chats, error log, ENV. Bot code: `Account.Transfer(..., include_data=, include_chats=, include_errors=, include_env=)`.
- **Broadcasts:** media from the device (kept in memory only, uploaded once per bot, then reused by file_id) or a link (Telegram post / direct media link, type detected automatically).
- **Captcha:** `Bot.genCaptcha()` images exist only in memory and go straight to Telegram; nothing is written to disk.
- **E-mail codes:** set `SMTP_*` (Gmail app password) to e-mail real sign-up and reset codes (`tests/otp_check.py`).
- **Telegram connect bot:** account, bots on/off, broadcasts, 24h stats, points, errors, start/stop all, alerts (bot errors, low points, sign-in, broadcast started/finished, daily digest).

## Added in the latest update
- **Transfer = copy.** The sender keeps the bot; the recipient gets a copy of what was ticked (database, chats, error log, ENV). The bot token is never sent — the recipient adds their own token in Settings.
- **Token eye icon** in Bot → Settings (owner only, auto-hides after 30 s).
- **Mandatory Gmail OTP** for sign-in, sign-up and password reset (`REQUIRE_EMAIL_OTP`, SMTP_* required; no demo mode).
- **Users — Import & Export** (Bot → Manage): import Telegram IDs from JSON/CSV/TXT (verified through Telegram, ~10/s, existing data untouched); export JSON/CSV with live progress, optional registration dates (1,000,000 users ≈ 3–5 s).
- Intro Start/Stop fixed; notification pop-ups appear only once.


## Plans, notifications, editor (latest)
- **Plans & Billing** (sidebar): Matrix Free $0 / Pro $5 / Growth $15 / Ultra $39 with points and limits (bots, commands per bot,
  broadcast audience, user import, bot transfer, store publish). Limits are enforced on the server. The **Contact Admin** link is read
  from the database (`platform_settings.contact_admin_url`, seeded from `ADMIN_CONTACT_URL`; admins change it with `PUT /api/admin/contact`).
- Assign a plan (adds that plan's points): `POST /api/admin/plan {"email","plan"}` - only emails listed in `ADMIN_EMAILS`.
- **Notifications**: clicking one opens the page it came from; Settings -> Preferences has on/off switches (all, browser pop-ups, per type).
- **Transfer receipt**: Transfers -> Audit Proof gives a public, signed link (`/receipt/<code>`) anyone can open to verify.
- **Editor**: Run (real dry run, nothing is sent) and Format (server-side, program checked to stay identical).
- **Broadcast**: parallel senders at Telegram's 30/s limit; after a crash/restart unfinished campaigns continue where they stopped.
- `server.ts` restarts the API automatically if it crashes or stops answering.
- Tests: `tests/e2e.py` (137 checks), `tests/resume_check.py`, UI: `tests/ui_plans.py`, `tests/ui_new.py`.

## Production switches (.env)
- `TURNSTILE_ENABLED=1` + `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY`: Cloudflare Turnstile on sign-up, sign-in and forgot-password; the server verifies every token with Cloudflare. Off by default.
- `REQUIRE_EMAIL_OTP=0`: no e-mail code is asked anywhere (1 = required).
- `RATE_LIMITS=0` (default): request rate limits are off. A wrong e-mail code can still only be guessed 5 times, then a new code is needed.
- `ADMIN_EMAILS`, `ADMIN_CONTACT_URL`: plan admins and the Contact Admin link.
- Tests: `tests/turnstile_check.py`.

## Latest changes

### Round 4 — TBC docs parity
- `libs.Webhook.getUrlFor` links now work: `/api/new-webhook?data=…` (signed, any HTTP method). The command gets `options.data / json / headers / ip / query / form`; `Api.setWebhookResult(...)` is the HTTP response. `bot_id` + `api_key` target another bot of the same account (key is verified).
- `Bot.runCommandAfter` now really fires: the scheduler is started with the server and runs through the normal engine (points, `~` preface, `!` error handler).
- `~` command is a preface: its code is prepended to every command (shared names, line numbers shifted back in errors). `!` gets `options` as the error text.
- `libs.customHTTP` rewritten (SSRF/DNS guard, `.gov` blocked, 120 s timeout, 50 MB cap, `fallback_command`).
- `libs.TonLib` is real: tonsdk v4r2 wallets, balance/send/transactions (toncenter), jettons (v3), persistent TON Connect sessions with verified `ton_proof`, transaction and jetton-transfer request pages with callback.
- `libs.openai_lib.chat(key, msg, model=, system=, provider="openai|gemini|openrouter")` and `.models(key)`; deprecated `libs.Polygon/ARB/TTcoin/Tomochain` have `send(...)` and `sendPolygon`-style helpers.
- Admin → Settings → "Public base URL" (`BASE_URL`) must be set to your public domain so webhook / TON Connect links are reachable from outside.
- Not included on purpose: TBC Ads and MD Exchange.

- **Broadcast speed (free):** no Telegram paid broadcast (Stars) any more. Plan speed is a ceiling; an adaptive (AIMD) limiter starts at the free 30 msg/s per bot token, probes upward while Telegram accepts, backs off on 429 and honours `retry_after`; rate limits and network/5xx errors are retried and never fail a user. Several bots send in parallel.
- **Points:** plan points and extra points are tracked separately (`users.extra_points`). Plan points cost `PLAN_POINT_RATE` (default 1) per user execution, extra points `EXTRA_POINT_RATE` (default 1.5). Admin → Users can add extra points.
- **TPY/TBC parity:** `libs.web3lib` (31 EVM chains: sendNativeCoin, sendETHER/ERC-20, getBalance, getTokenBalance), `Bot.setAutoTranslate/getAutoTranslate`, `Account.parse_import_data`, positional signatures for all newer Bot API methods, `libs.customHTTP()` callable, `callback_data` global.
- **Errors:** the original error is shown in the chat when there is no `!` handler; `!` handler runs first when present; everything is in the Errors log.

### Round 4 (later additions)
- Broadcast V2 parity (function/command/code modes, test run, status keys, 3 running per bot), scheduling limits (runCommandAfter 1s–366d, 60/min, 50,000 outstanding), fast-command limiter, `time.sleep` cap 10 s, new safe builtins.
- Payments: positional signatures for `answerPreCheckoutQuery`, `answerShippingQuery`, `refundStarPayment`, `createInvoiceLink`.
- Special commands `~ @ ! *` and reply/inline keyboard behaviours covered by `tests/e2e.py` (316 checks).
- Vite/Express watchers ignore `storage/`, DB and backend files (no more reload loop).
- Set `BASE_URL` in Admin → Settings so webhook and TON Connect links are public.

### Round 5 – TeleBot Studio (TBS) docs parity
Everything in help.telebotstudio.com that the project did not have is now there (TBC names keep working):
- `Account.storeData/fetchData/removeData/exportData/exportAllData/stats/botStats/botsStats/botUsage/cloneBot/banUser/unbanUser/bannedUsers/exportBannedUsersFile/res`, `Admin.res(...).exportAllData/removeAllData/fetchAllResourcesOfUser`, `Api.<any Bot API method>` and `Api.setWebhookResponse`.
- Globals `JSON`, `URL`, `Hash`, `dir()`, `CheckMembership` (list = all channels, bad channel / non-admin bot raises, both argument orders).
- `Lib.Random` (hex, bytes, password, sample, boolean, range, gaussian…), `Lib.Security` (hashSHA256/512/MD5, verifyEd25519, verifyPaymentGatewayWebhook), `Lib.TeleGifts` (ById, ByCategory, search, stats, settings), `Lib.EVM` (sendCoin/sendToken in both argument orders, fetchBalance/fetchTokenBalance, generateKey), `Lib.TON` (positional signatures, register_ton_connect_wallet result, public_key), `Lib.DateTime.utcnow()` string, `Lib.AI.client(provider, apiKey, baseUrl)` + `Lib.AI.Assistant(...)`, `Lib.RefLib` (track callbacks, getTopList dict, getStats…), `Lib.PIL` / `Lib.CV` with exact TBS signatures (tbs_media.py).
- `Bot.scheduleCommand(delay, command, user_id, chat_id, params)` (both argument orders, returns object with `.id`), `cancelScheduledCommand` → bool, `resetScheduledCommands(user_id=)`, `cancelBroadcast()` (all), `sendCloneBroadcast(id)`, TBS captcha signatures, 8-char `randomID`.
- `Request`: Response object, SSRF guard (also on redirects), 50 MB cap (`max_data_size`), timeouts, `fallback_command` background mode (>120 s).
- **REST API v2** (`/v2/...`, API-key auth, 60/min per IP + 1000/h per key, `X-RateLimit-*` headers, `{ok:false,result:msg}` errors).
- Data entries are limited to 10 MB.
Tests: `python3 tests/e2e.py` (377 checks), `python3 tests/unit_request.py` (12 checks).

## Round 6 — Admin tab, maintenance mode, language analytics

- **Edit bot → Admin** with sub-tabs: *Executions* (range 24h/7d/30d, chart, totals/errors/avg runtime, every command with run count, share and progress bar), *Users* (Total, Active 24h/7d/30d, New 24h/7d/30d, Blocked, new-vs-active chart, language/country analysis), *Broadcasts* (pause/resume/cancel), *Bot Data* / *User Data* (full editor), *Permissions* (bot admins), *Maintenance* (maintenance mode + message, restart, clear errors, reset stats, remove users who left, stop broadcasts, clear scheduled commands, shortcuts to every other tab).
- **Chats** now show each user's Telegram `language_code` badge (e.g. `en`).
- Backend: `GET /api/bots/:id/admin/overview?days=`, `PUT …/admin/maintenance`, `POST …/admin/action`; events now record the command name. While maintenance is on, only global bot admins can run commands; everyone else gets the notice and no points are used.
- Tests: `tests/e2e.py` ROUND 6 (397 checks total), `tests/ui_botadmin.py`.

### Round 6b
- Admin tab: *Bot Data* / *User Data* sub-tabs removed (use the Database tab); every operation (restart, clear, reset, broadcasts, admins, maintenance) asks for confirmation.
- Docs-parity fixes: bare `handleNextCommand("name")` (as in the TBC docs), `handleNextCommand` target names resolve with or without leading `/`, `Lib.Crypto.sha256/md5/sha1/sha512/hmac_*` (TBS), `Bot.sendBroadcast()` result also carries TBS keys `ok`, `estimated_users`, `error`.
- Verified: every Telegram Bot API method referenced in the TBC docs is callable (camelCase and snake_case); all 470 doc code samples were run through the validator (only the intentionally-wrong anti-pattern samples are rejected).

### Round 6c
- Admin tab redesigned (gradient hero, per-section colours, coloured stat cards, ranked command bars, language cards, broadcast cards with *View details*, colourful operation tiles).
- Broadcast details: real bot photo with the bot icon as fallback (`BotAvatar`, also used in My Bots / Studio / Admin); *Open bot →* jumps to the bot and shows a highlighted "opened from broadcast" banner; opening details from a bot's Admin tab marks that bot with a *This bot* badge. Fixed: details page wasn't restored when navigating to Broadcast Manager.
- Errors are clean and safe: `backend/error_clean.py` — type + plain explanation + only the owner's own line numbers; no server paths, internal frames, tokens, e-mails or source code in the Errors tab or the chat notice (old rows are cleaned on read).
- `CheckMembership` tolerates empty/odd user ids and quoted channel names (`invalid user_id` fixed, clear message otherwise).
- `Bot.info()` returns the same real numbers as the web app (real owner e-mail, points, users, times); status compares case-insensitively; `Bot.Transfer()` result carries `ok/bot_id/new_owner/transfer_id/status`.
- Dashboard Growth % no longer "—" when yesterday had no new users; Error rate / Response time verified against real events.

## Round 6d — docs-parity fixes
- `bot.getFileUrl(file_id)` returns a real download URL.
- `message.photo[-1].file_id` (list/attribute access) works.
- Safe imports whitelist (datetime, math, random, json, re, hashlib, base64, …); dangerous modules stay refused.
- Special updates (`edited_message`, `my_chat_member`, `chat_join_request`, `poll_answer`, `message_reaction`, `chat_boost`, …) are requested from Telegram (`ALL_UPDATE_TYPES`) and routed to `/handler_<type>` or `/handler_special_updates`. They never change the audience or un-block users.
- `Lib.Crypto.sha256`-style aliases added.

## Round 7 — automatic updates, methods, broadcast kinds
- **Any Telegram update type** reaches the bot with no code change: the type is read from the update itself (`update_type_of`). `/handler_<type>` runs if it exists, otherwise `/handler_special_updates`. Unknown/new types never touch the audience list. Polling requests every known type; when Telegram invents a brand-new one, add its name to Admin → Settings → "Extra Telegram update types" (no redeploy).
- **Any Bot API method** works as `bot.<method>(...)` (camelCase or snake_case) — methods are forwarded generically, so methods Telegram adds later work automatically.
- Broadcast Manager now also sends **Location, Venue, Contact, Poll, Dice and Forward** (same engine, speed, buttons, pin, resume as the other kinds).
- `Bot.isAdmin()/getAdmins()` read the Admin-tab list live; env vars (text / raw number / raw list) are tested inside commands; admin-only commands are tested for admins and non-admins.
- Tests: `tests/e2e.py` (443 checks), `tests/ui_bc_types.py`.

## Round 8 — server panel + Security Center
**Admin → Server / Bot fleet / Database / Live logs / Security** (EN/বাংলা toggle), all real data from this machine:
- Server: CPU (total + per core), RAM/swap/cache, disk, network rx/tx, load average, uptime, process RSS/threads/open files, history charts.
- Fleet: per-bot runs, avg/p95 ms, error rate, share of total execution time, speed class (<50 / 50-500 / 500-1500 / >1500 ms), "Damage radar" flags (heavy load, many errors, critical slow, flooding), **Why?** diagnosis (slow commands, `time.sleep`, HTTP/AI/blockchain calls, running broadcasts, server CPU/RAM) and Stop/Restart/Start with confirmation (owner is notified). Note: per-bot "load" is execution time, not OS CPU (all bots share one Python process).
- Database: sizes, WAL, fragmentation, table row counts, integrity check, WAL flush, optimize, VACUUM, snapshot backup (10 kept), read-only SQL console (SQLite authorizer: no writes/attach; secret columns masked).
- Logs: live ring buffer with level / text filter, secrets redacted.
- Users: Suspend / Unsuspend (signs out, stops bots, blocks login).
**Security Center** (admin page + each user's Settings → Security): secrets-in-code scanner (bot tokens, API keys, private keys, wallet keys, seed phrases), bot-token health monitor (revoked / token now belongs to another bot / unknown webhook / 409 conflict), bulk token-replacement and token-change-after-new-network-login detection, new-network sign-in alert, sandbox jail self-test (20 escape patterns, validated *and* executed), data-at-rest checks (tokens encrypted, key file/DB permissions, integrity), configuration and vulnerable-library checks. Findings are de-duplicated, shown in-app first, then sent through the Connect bot (Security alerts switch); serious ones also notify admins.
Tests: `tests/e2e.py` (484), `tests/ui_admin.py` (15).

## Round 9 — security hardening
- Bot-code HTTP (`HTTP.get/post`, `customHTTP`): redirects are followed manually and **every hop is re-checked** (no SSRF to localhost / private / cloud-metadata through a redirect). Test: `tests/unit_ssrf.py`.
- Environment variable values are **encrypted in the database** (existing plain ones are encrypted at start-up); Security Center has an `env-encrypted` check. SQL console masks `env_vars` and `commands_json`.
- Session cookie gets `Secure` over https; new headers `X-Frame-Options`, `Permissions-Policy`, `Strict-Transport-Security` (https only).
- User-list export folder is private (0700 / files 0600). Broadcast link detection no longer follows redirects.

## Round 10 — lessons from a real-world TBC incident report
Prompted by a published TBC security-notice post-mortem (database leak via sandbox introspection, readable platform API keys, mass data extraction). Lessons applied here:

- **Editor data-loss bug fixed**: saving a command with a syntax/sandbox error used to silently reject the *entire* save server-side while the editor still showed "Saved" from its optimistic UI update. Now the web editor **always persists exactly what you typed**, any problems are reported back per-command (`codeErrors`) and shown as a warning toast, and the flagged command simply won't run until fixed — sibling commands keep working. The old hard-reject behavior is kept **only** for the documented external `/v2` API, which must still refuse code that won't compile. Test: `tests/e2e.py` ("code with errors is STILL saved").
- **Sandbox escape hardening** (the incident's own description of attackers abusing "Python's dynamic introspection and object relationships"): closed four concrete escape classes that could reach `__class__`/`__globals__`/frame internals *without* tripping the existing dunder-attribute check — format-string field specs (`'{0.__class__}'.format(x)`, `format_map`, builtin `format()`), `operator.attrgetter`/`methodcaller` (string-based reflection), non-dunder frame/code/traceback attribute names (`gi_frame`, `f_globals`, `mro`, …), and 3-argument dynamic `type()` class creation. Enforced at both the real security boundary (`backend/sandbox/executor.py` AST check + `backend/sandbox/safe_builtins.py` runtime wrappers) and mirrored in the editor's inline linter. Security Center's self-test list (`_JAIL_TESTS`) grew from 20 → 30 patterns and is exercised continuously by the background watcher.
- **Platform API key: readable-forever → hash-and-show-once.** The incident report's root cause for the database leak was storing readable credentials; this project's own dashboard API key had the same shape (reversibly encrypted, decrypted and returned on every Settings page load). It's now stored the same way passwords are: only a SHA-256 hash + a short display prefix are kept at rest (`account_api_keys` table), the raw key is returned to you **exactly once**, at generation time, and the `/v2` REST API and Settings page were both migrated to the hash-only check. There is no code path left that can read an existing key back out.
- **Admin audit log**: every admin-panel mutation (and API-key regeneration) is now recorded — who, what, which target, when — in a log nothing in the API can edit or delete. Visible under Admin → Security. Secret-shaped fields (passwords, tokens, codes) are redacted before they're ever written to it.
- **Bulk-export alarm**: mirrors the incident's "mass extraction" pattern — an account pulling an unusually high volume of data through the `/v2` API in a short window (300+ calls / 5 min) now raises a critical Security Center alert (in-app + Telegram) suggesting an immediate key rotation, the same way a sudden burst of bot-token replacements already does.
- **Process-wide memory ceiling**: sandboxed commands run as threads inside the one server process (needed to share state cheaply), so a true per-run memory/CPU cap would need a separate-process sandbox — a larger change, noted below as a roadmap item. In the meantime a generous `RLIMIT_AS` ceiling is applied at startup so a runaway allocation in one bad command raises a catchable `MemoryError` in that command instead of being able to take the whole server down for every tenant.
- Full regression: `tests/e2e.py` 498/498, `tests/unit_request.py` 12/12, `tests/unit_ssrf.py` 4/4 — all passing, no behavior regressions.

**Not done yet (flagged honestly rather than rushed/half-built):**
- TOTP-based 2FA login (Google Authenticator style) — the backend already has the login/session plumbing to hang this off; next round.
- True per-execution CPU/memory isolation would need sandboxed code to run in its own short-lived OS process instead of a thread — a bigger architectural change than a config tweak, tracked for later.
