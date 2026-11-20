"""
Broadcast V2 engine.

A self-hosted, thread-based (no Redis dependency required) implementation
of a configurable-speed, pausable/resumable, multi-bot broadcast system.

Each BroadcastJob row in the DB is the source of truth for status/position/
speed, so the engine survives process restarts (crash recovery): on
startup, any job left in "running" state is simply picked back up from its
last saved `position`.

Concurrency model: one background worker thread per active broadcast job,
managed by a process-wide singleton `broadcast_manager`. Pause/stop/speed
changes are communicated to the worker thread via a small in-memory control
object (per job id) that the loop checks between sends, so a live
`setBroadcastSpeed()` call takes effect within ~1 second, as specified.
"""
import datetime
import threading
import time
import requests as _requests

from backend.database import SessionLocal
from backend import models
from backend.telegram.bot_wrapper import BotWrapper, TelegramAPIError

MIN_SPEED = 1
MAX_SPEED = 25
DEFAULT_SPEED = 8
MAX_RUNNING_GLOBAL = 5000
COMMIT_EVERY = 25       # persist progress every N sends (scale-safe)
MAX_RUNNING_PER_BOT = 3
GLOBAL_MAX_RUNNING = 5000

ALLOWED_BROADCAST_FUNCTIONS = {
    "send_message", "send_photo", "send_video", "send_animation",
    "send_audio", "send_document", "forward_message", "send_paid_media",
    "send_sticker", "send_video_note", "send_voice", "send_location",
    "send_venue", "send_contact", "send_poll", "send_dice", "send_invoice",
    "send_game", "send_media_group", "pin_chat_message",
}

# Map function names to BotWrapper methods (camelCase Telegram API)
_FUNCTION_TO_METHOD = {
    "send_message": "sendMessage", "send_photo": "sendPhoto",
    "send_video": "sendVideo", "send_animation": "sendAnimation",
    "send_audio": "sendAudio", "send_document": "sendDocument",
    "forward_message": "forwardMessage", "send_paid_media": "sendPaidMedia",
    "send_sticker": "sendSticker", "send_video_note": "sendVideoNote",
    "send_voice": "sendVoice", "send_location": "sendLocation",
    "send_venue": "sendVenue", "send_contact": "sendContact",
    "send_poll": "sendPoll", "send_dice": "sendDice",
    "send_invoice": "sendInvoice", "send_game": "sendGame",
    "send_media_group": "sendMediaGroup", "pin_chat_message": "pinChatMessage",
    "edit_message_live_location": "editMessageLiveLocation",
    "edit_chat_invite_link": "editChatInviteLink",
    "edit_chat_subscription_invite_link": "editChatSubscriptionInviteLink",
    "edit_message_text": "editMessageText",
    "edit_message_media": "editMessageMedia",
    "edit_message_caption": "editMessageCaption",
    "edit_message_reply_markup": "editMessageReplyMarkup",
    "edit_forum_topic": "editForumTopic",
    "edit_general_forum_topic": "editGeneralForumTopic",
}

_PLACEHOLDERS = ("{user_name}", "{first_name}", "{username}", "{user_id}", "{chat_id}")


def _apply_placeholders(value, chat_id, profile=None):
    """Replace TBC-style tokens in text/caption/button labels."""
    if value is None:
        return value
    profile = profile or {}
    name = (
        profile.get("first_name")
        or profile.get("name")
        or profile.get("username")
        or "there"
    )
    last = profile.get("last_name") or ""
    username = profile.get("username") or ""
    full = (name + (" " + last if last else "")).strip() or name
    mapping = {
        "{user_name}": full,
        "{first_name}": name,
        "{last_name}": last,
        "{username}": ("@" + username) if username else "",
        "{user_id}": str(chat_id),
        "{chat_id}": str(chat_id),
    }
    if isinstance(value, str):
        out = value
        for k, v in mapping.items():
            out = out.replace(k, str(v))
        return out
    if isinstance(value, dict):
        return {k: _apply_placeholders(v, chat_id, profile) for k, v in value.items()}
    if isinstance(value, list):
        return [_apply_placeholders(v, chat_id, profile) for v in value]
    return value


def _prepare_kwargs(kwargs, chat_id, profile=None):
    """Apply placeholders + JSON-encode complex Telegram fields."""
    import json as _json
    out = {}
    for k, v in (kwargs or {}).items():
        if k in ("code", "sent_messages", "function", "command",
                 "sent_messages_deleted", "deleted_count"):
            continue
        if k in ("text", "caption", "question", "title", "address", "first_name",
                 "last_name", "phone_number", "description"):
            out[k] = _apply_placeholders(v, chat_id, profile)
        elif k == "reply_markup":
            # deep-copy personalize button text; keep callback_data/url intact
            markup = _apply_placeholders(v, chat_id, profile) if isinstance(v, (dict, list)) else v
            if not isinstance(markup, str):
                try:
                    markup = _json.dumps(markup)
                except Exception:
                    pass
            out[k] = markup
        elif k in ("options", "media", "results", "prices", "provider_data",
                   "suggested_tip_amounts", "entities", "caption_entities"):
            if isinstance(v, (list, dict)):
                try:
                    out[k] = _json.dumps(v)
                except Exception:
                    out[k] = v
            else:
                out[k] = v
        else:
            out[k] = v
    out["chat_id"] = chat_id
    return out

MIN_MEMBERS_FOR_ALL_MODE = 20


class _JobControl:
    """Thread-safe live control channel for one running broadcast job."""

    def __init__(self, speed: int):
        self.speed = speed
        self.pause_event = threading.Event()  # set() == PAUSED
        self.stop_flag = threading.Event()     # set() == STOP requested


class BroadcastManager:
    def __init__(self):
        self._controls = {}  # job_id -> _JobControl
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- API
    def start(self, db, bot: models.Bot, owner: models.Account, *, mode="single",
              bot_ids=None, speed=DEFAULT_SPEED, text=None, config=None, callback_url=None) -> models.BroadcastJob:
        speed = max(MIN_SPEED, min(MAX_SPEED, int(speed or DEFAULT_SPEED)))
        bot_ids = bot_ids or []
        # TBC limit: 3 running broadcasts per bot
        running = db.query(models.BroadcastJob).filter_by(bot_id=bot.id, status="running").count()
        running += db.query(models.BroadcastJob).filter_by(bot_id=bot.id, status="paused").count()
        if running >= MAX_RUNNING_PER_BOT:
            raise ValueError("You already have 3 running broadcasts.")

        total_running = db.query(models.BroadcastJob).filter(models.BroadcastJob.status.in_(("running", "paused"))).count()
        if total_running >= MAX_RUNNING_GLOBAL:
            raise ValueError("Server currently at max capacity (5000). Please try again later.")

        def _resolve(ids):
            out = []
            for x in ids:
                sx = str(x)
                row = db.query(models.Bot).filter(models.Bot.owner_id == owner.id, models.Bot.deleted_at.is_(None),
                                                  models.Bot.public_id == sx).first()
                if row is None and sx.isdigit():
                    row = db.query(models.Bot).filter(models.Bot.owner_id == owner.id, models.Bot.deleted_at.is_(None),
                                                      models.Bot.id == int(sx)).first()
                if row is None:
                    raise ValueError("You can only broadcast to bots you own")
                out.append(row)
            return out

        if mode == "multi":
            if not bot_ids:
                raise ValueError("bot_ids is required when mode='multi'")
            if not isinstance(bot_ids, (list, tuple)):
                raise ValueError("bot_ids must be a list")
            if len(bot_ids) > 500:
                raise ValueError("Maximum 500 bots allowed per multi-bot broadcast")
            target_bots = _resolve(bot_ids)
        elif mode == "all":
            # bots below the minimum audience are simply left out
            target_bots = [b for b in db.query(models.Bot).filter_by(owner_id=owner.id, deleted_at=None).all()
                           if db.query(models.BotMember).filter_by(bot_id=b.id).count() >= MIN_MEMBERS_FOR_ALL_MODE]
            if not target_bots:
                raise ValueError(f"No bot has the minimum of {MIN_MEMBERS_FOR_ALL_MODE} members required for mode='all'")
        elif mode in ("single", None, ""):
            target_bots = [bot]
        else:
            raise ValueError("mode must be 'single', 'multi' or 'all'")

        recipients = []
        for b in target_bots:
            member_ids = [m.chat_id for m in db.query(models.BotMember).filter_by(bot_id=b.id).all()]
            recipients.extend([(b.id, chat_id) for chat_id in member_ids])

        job = models.BroadcastJob(
            bot_id=bot.id,
            owner_id=owner.id,
            mode=mode,
            target_bot_ids=[b.id for b in target_bots],
            speed=speed,
            status="running",
            text=text,
            config=config or {},
            total=len(recipients),
            sent=0,
            failed=0,
            position=0,
            callback_url=callback_url,
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        self._spawn_worker(job.id, recipients)
        return job

    def test_run(self, db, bot, chat_id, config):
        """Run the broadcast once against the triggering user. Returns None when fine, else an error text."""
        cfg = dict(config or {})
        token = bot.token
        try:
            if cfg.get("code"):
                self._run_custom_code_for_recipient(db, bot.id, token, chat_id, cfg["code"])
            elif cfg.get("command"):
                self._run_command_for_recipient(db, bot.id, token, chat_id, cfg["command"])
            else:
                self._call_function_for_recipient(token, chat_id, cfg.get("function"), cfg.get("text"), cfg, db, bot.id)
        except Exception as e:  # noqa
            msg = getattr(e, "description", None) or str(e)
            if "chat not found" in msg.lower():
                return None
            return msg
        return None

    def _spawn_worker(self, job_id: int, recipients):
        control = _JobControl(speed=DEFAULT_SPEED)
        with self._lock:
            self._controls[job_id] = control
        t = threading.Thread(target=self._run_job, args=(job_id, recipients, control), daemon=True)
        t.start()

    def _run_job(self, job_id: int, recipients, control: _JobControl):
        db = SessionLocal()
        try:
            job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
            if not job:
                return
            control.speed = job.speed
            token_cache = {}

            i = job.position
            while i < len(recipients):
                if control.stop_flag.is_set():
                    job.status = "stopped"
                    db.commit()
                    return

                while control.pause_event.is_set():
                    job.status = "paused"
                    db.commit()
                    time.sleep(0.5)
                    if control.stop_flag.is_set():
                        job.status = "stopped"
                        db.commit()
                        return

                if job.status == "paused":
                    job.status = "running"
                    db.commit()

                bot_id, chat_id = recipients[i]
                if bot_id not in token_cache:
                    b = db.query(models.Bot).filter_by(id=bot_id).first()
                    token_cache[bot_id] = b.token if b else None
                token = token_cache.get(bot_id)

                custom_code = (job.config or {}).get("code")
                function = (job.config or {}).get("function")
                command = (job.config or {}).get("command")

                # Track delivered message ids for later bulk-delete
                cfg = job.config if isinstance(job.config, dict) else {}
                if not isinstance(job.config, dict):
                    job.config = {}
                    cfg = job.config
                sent_log = cfg.setdefault("sent_messages", [])

                if token and custom_code:
                    try:
                        mid = self._run_custom_code_for_recipient(db, bot_id, token, chat_id, custom_code)
                        job.sent += 1
                        if mid:
                            sent_log.append({"chat_id": chat_id, "message_id": int(mid), "bot_id": bot_id})
                    except Exception:
                        job.failed += 1
                elif token and command:
                    try:
                        mid = self._run_command_for_recipient(db, bot_id, token, chat_id, command)
                        job.sent += 1
                        if mid:
                            sent_log.append({"chat_id": chat_id, "message_id": int(mid), "bot_id": bot_id})
                    except Exception:
                        job.failed += 1
                elif token and function:
                    try:
                        mid = self._call_function_for_recipient(
                            token, chat_id, function, job.text, cfg, db, bot_id
                        )
                        job.sent += 1
                        if mid:
                            sent_log.append({"chat_id": chat_id, "message_id": int(mid), "bot_id": bot_id})
                    except TelegramAPIError:
                        job.failed += 1
                    except Exception:
                        job.failed += 1
                elif token:
                    try:
                        bw = BotWrapper(token)
                        kwargs = {k: v for k, v in (job.config or {}).items()
                                  if k not in ("code", "sent_messages", "function", "command")}
                        kwargs["chat_id"] = chat_id
                        if job.text and "text" not in kwargs:
                            kwargs["text"] = job.text
                        # placeholders
                        if "text" in kwargs:
                            kwargs["text"] = _apply_placeholders(kwargs["text"], chat_id)
                        if "caption" in kwargs:
                            kwargs["caption"] = _apply_placeholders(kwargs["caption"], chat_id)
                        result = bw.sendMessage(**kwargs)
                        job.sent += 1
                        mid = getattr(result, "message_id", None)
                        if mid is None and isinstance(result, dict):
                            mid = result.get("message_id")
                        if mid:
                            sent_log.append({"chat_id": chat_id, "message_id": int(mid), "bot_id": bot_id})
                    except TelegramAPIError:
                        job.failed += 1
                    except Exception:
                        job.failed += 1
                else:
                    job.failed += 1

                # persist sent_messages log (force JSON column dirty)
                job.config = dict(cfg)
                try:
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(job, "config")
                except Exception:
                    pass

                i += 1
                job.position = i
                if job.callback_url and len(recipients) >= 5 and i % max(1, len(recipients) // 5) == 0 and i < len(recipients):
                    self._fire_callback(job)
                if i % COMMIT_EVERY == 0 or i == len(recipients):
                    db.commit()

                # rate limit: speed msgs/sec → sleep between sends
                sleep_time = 1.0 / (max(1, float(control.speed)) * max(1, len(job.target_bot_ids or [1])))
                if sleep_time > 0.001:
                    time.sleep(sleep_time)

            job.status = "completed"
            job.finished_at = datetime.datetime.utcnow()
            db.commit()

            if job.callback_url:
                self._fire_callback(job)
        finally:
            with self._lock:
                self._controls.pop(job_id, None)
            db.close()

    def _call_function_for_recipient(self, token, chat_id, function, text, cfg, db, bot_id):
        """Dispatch one allowed Telegram send function for a recipient."""
        method_name = _FUNCTION_TO_METHOD.get(function) or _FUNCTION_TO_METHOD.get(str(function).lower())
        if not method_name:
            for k, v in _FUNCTION_TO_METHOD.items():
                if k.replace("_", "") == str(function).lower().replace("_", ""):
                    method_name = v
                    break
        if not method_name:
            method_name = str(function)

        # Load profile for placeholders (best-effort, no crash)
        profile = {}
        try:
            m = db.query(models.BotMember).filter_by(bot_id=bot_id, chat_id=chat_id).first()
            if m is None:
                m = db.query(models.BotMember).filter_by(bot_id=bot_id, telegram_user_id=chat_id).first()
            if m is not None:
                profile = {
                    "first_name": getattr(m, "first_name", None) or "",
                    "last_name": getattr(m, "last_name", None) or "",
                    "username": getattr(m, "username", None) or "",
                }
        except Exception:
            profile = {}

        bw = BotWrapper(token, default_chat_id=chat_id)
        raw = {k: v for k, v in (cfg or {}).items()
               if k not in ("code", "sent_messages", "function", "command",
                            "sent_messages_deleted", "deleted_count")}
        if text and "text" not in raw and function in ("send_message",):
            raw["text"] = text
        kwargs = _prepare_kwargs(raw, chat_id, profile)

        try:
            fn = getattr(bw, method_name, None)
            if callable(fn):
                result = fn(**kwargs)
            else:
                result = bw.call(method_name, **kwargs)
        except TelegramAPIError as e:
            # Flood control: brief pause then re-raise so job.failed increments
            desc = (e.description or "").lower()
            if "flood" in desc or "retry after" in desc or e.error_code == 429:
                import re as _re
                m = _re.search(r"retry after (\d+)", desc)
                wait = int(m.group(1)) if m else 2
                time.sleep(min(wait, 10))
            raise

        mid = getattr(result, "message_id", None)
        if mid is None and isinstance(result, dict):
            mid = result.get("message_id")
        if mid is None and isinstance(result, list) and result:
            first = result[0]
            mid = getattr(first, "message_id", None) or (first.get("message_id") if isinstance(first, dict) else None)
        return mid

    def _run_command_for_recipient(self, db, bot_id, token, chat_id, command):
        """Run an existing bot command once for recipient (command-mode broadcast)."""
        bot_row = db.query(models.Bot).filter_by(id=bot_id).first()
        owner = db.query(models.Account).filter_by(id=bot_row.owner_id).first()
        trigger = str(command)
        cmd = db.query(models.Command).filter_by(bot_id=bot_id, trigger=trigger).first()
        if not cmd and not trigger.startswith("/"):
            cmd = db.query(models.Command).filter_by(bot_id=bot_id, trigger="/" + trigger).first()
            if cmd:
                trigger = "/" + trigger
        if not cmd:
            raise ValueError("command doesn't exist")
        from backend.sandbox.runner import run_command
        update = {
            "update_id": 0,
            "message": {
                "message_id": 1,
                "date": 0,
                "text": trigger,
                "chat": {"id": chat_id, "type": "private"},
                "from": {"id": chat_id, "is_bot": False, "first_name": "User"},
            },
        }
        run_command(db, bot_row, owner, trigger, update, options=None, params="")
        return None

    def _run_custom_code_for_recipient(self, db, bot_id, token, chat_id, code):
        """Runs `code` sandboxed once per recipient, exactly like a normal
        command, with `bot` pre-bound to send to this recipient by default."""
        from backend.sandbox.executor import run_sandboxed
        from backend.sandbox.context_objects import UserObject, BotDataObject, AccountObject, MessageObject
        from backend.sandbox.libs_namespace import LibsNamespace
        from backend.sandbox.safe_builtins import build_preimported_modules
        from backend.config import STORAGE_DIR, MAX_EXEC_SECONDS

        bot_wrapper = BotWrapper(token, default_chat_id=chat_id)
        # docs: broadcast code sees only `bot` and `u` (the recipient's user id)
        injected = {"bot": bot_wrapper, "u": chat_id}
        run_sandboxed(code, injected, timeout_seconds=MAX_EXEC_SECONDS)
        # Best-effort: last Telegram response message_id
        try:
            lr = getattr(bot_wrapper, "last_response", None) or {}
            if isinstance(lr, dict):
                res = lr.get("result") or {}
                if isinstance(res, dict) and res.get("message_id"):
                    return int(res["message_id"])
        except Exception:
            pass
        return None

    def delete_sent_messages(self, db, job_id: int) -> dict:
        """Delete every message that this broadcast job delivered (best-effort)."""
        job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError("Broadcast not found")
        cfg = job.config if isinstance(job.config, dict) else {}
        sent_log = list(cfg.get("sent_messages") or [])
        if not sent_log:
            return {"ok": True, "deleted": 0, "failed": 0, "total": 0, "hint": "No tracked message ids"}

        token_cache = {}
        deleted, failed = 0, 0
        for item in sent_log:
            try:
                bid = int(item.get("bot_id") or job.bot_id)
                chat_id = item.get("chat_id")
                message_id = item.get("message_id")
                if not chat_id or not message_id:
                    failed += 1
                    continue
                if bid not in token_cache:
                    b = db.query(models.Bot).filter_by(id=bid).first()
                    token_cache[bid] = b.token if b else None
                token = token_cache.get(bid)
                if not token:
                    failed += 1
                    continue
                bw = BotWrapper(token)
                bw.call("deleteMessage", chat_id=chat_id, message_id=message_id)
                deleted += 1
            except Exception:
                failed += 1
        cfg["sent_messages_deleted"] = True
        cfg["deleted_count"] = deleted
        job.config = dict(cfg)
        db.commit()
        return {"ok": True, "deleted": deleted, "failed": failed, "total": len(sent_log)}

    def _fire_callback(self, job: models.BroadcastJob):
        try:
            from backend.sandbox.libs.http_lib import _check_url
            _requests.post(_check_url(job.callback_url), json={
                "broadcast_id": job.id,
                "status": job.status,
                "total": job.total,
                "sent": job.sent,
                "failed": job.failed,
            }, timeout=15)
        except Exception:
            pass

    # ---------------------------------------------------------------- controls
    def set_speed(self, job_id: int, speed: int):
        speed = max(MIN_SPEED, min(MAX_SPEED, int(speed)))
        with self._lock:
            control = self._controls.get(job_id)
        db = SessionLocal()
        try:
            job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
            if not job:
                raise ValueError("Broadcast not found")
            job.speed = speed
            db.commit()
        finally:
            db.close()
        if control:
            control.speed = speed  # takes effect within ~1s (next loop iteration)
        return True

    def pause(self, job_id: int):
        with self._lock:
            control = self._controls.get(job_id)
        # Always mark paused in DB immediately so status API reflects it
        db = SessionLocal()
        try:
            job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
            if job and job.status in ("running", "paused"):
                job.status = "paused"
                db.commit()
        finally:
            db.close()
        if control:
            control.pause_event.set()
            return True
        return False

    def resume(self, job_id: int, speed=None):
        with self._lock:
            control = self._controls.get(job_id)
        if not control:
            # Worker thread not alive (e.g. after a restart) — respawn it from saved position
            db = SessionLocal()
            try:
                job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
                if not job or job.status not in ("paused", "stopped"):
                    return False
                if speed:
                    job.speed = max(MIN_SPEED, min(MAX_SPEED, int(speed)))
                job.status = "running"
                db.commit()
                recipients = self._rebuild_recipients(db, job)
            finally:
                db.close()
            self._spawn_worker(job_id, recipients)
            return True

        if speed:
            self.set_speed(job_id, speed)
        control.pause_event.clear()
        db = SessionLocal()
        try:
            job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
            if job:
                job.status = "running"
                db.commit()
        finally:
            db.close()
        return True

    def stop(self, job_id: int):
        with self._lock:
            control = self._controls.get(job_id)
        db = SessionLocal()
        try:
            job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
            if job:
                job.status = "stopped"
                job.finished_at = datetime.datetime.utcnow()
                db.commit()
        finally:
            db.close()
        if control:
            control.stop_flag.set()
        return True

    def rerun(self, db, job_id: int, speed=None) -> models.BroadcastJob:
        old = db.query(models.BroadcastJob).filter_by(id=job_id).first()
        if not old:
            raise ValueError("Broadcast not found")
        bot = db.query(models.Bot).filter_by(id=old.bot_id).first()
        owner = db.query(models.Account).filter_by(id=old.owner_id).first()
        return self.start(
            db, bot, owner,
            mode=old.mode, bot_ids=old.target_bot_ids, speed=speed or old.speed,
            text=old.text, config=old.config, callback_url=old.callback_url,
        )

    def clear(self, db, bot_id: int, job_id=None):
        q = db.query(models.BroadcastJob).filter_by(bot_id=bot_id)
        if job_id:
            q = q.filter_by(id=job_id)
        q.delete(synchronize_session=False)
        db.commit()
        return True

    def _rebuild_recipients(self, db, job: models.BroadcastJob):
        recipients = []
        for bid in (job.target_bot_ids or [job.bot_id]):
            members = db.query(models.BotMember).filter_by(bot_id=bid).all()
            recipients.extend([(bid, m.chat_id) for m in members])
        return recipients

    # ---------------------------------------------------------------- status
    def status(self, db, job_id: int) -> dict:
        job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError("Broadcast not found")
        cfg = job.config if isinstance(job.config, dict) else {}
        sent_log = cfg.get("sent_messages") or []
        return {
            "broadcast_id": job.id,
            "status": job.status,
            "mode": job.mode,
            "speed": job.speed,
            "total": job.total,
            "sent": job.sent,
            "failed": job.failed,
            "position": job.position,
            "total_users": job.total,
            "total_success": job.sent,
            "total_errors": job.failed,
            "total_bots": len(job.target_bot_ids or [job.bot_id]),
            "done_bots": len(job.target_bot_ids or [job.bot_id]) if job.status == "completed" else 0,
            "processed": job.position,
            "remaining": max(0, job.total - job.position),
            "tracked_messages": len(sent_log),
            "messages_deleted": bool(cfg.get("sent_messages_deleted")),
        }

    def progress(self, db, job_id: int) -> dict:
        job = db.query(models.BroadcastJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError("Broadcast not found")
        remaining = max(0, job.total - job.position)
        eta_seconds = int(remaining / max(1, job.speed)) if job.status == "running" else None
        pct = round((job.position / job.total) * 100, 1) if job.total else 100.0
        return {
            "broadcast_id": job.id,
            "status": job.status,
            "progress_pct": pct,
            "sent": job.sent,
            "failed": job.failed,
            "total": job.total,
            "processed": job.position,
            "remaining": remaining,
            "speed": job.speed,
            "eta_seconds": eta_seconds,
        }

    def list_jobs(self, db, bot_id: int, status=None, limit=20):
        q = db.query(models.BroadcastJob).filter_by(bot_id=bot_id)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(models.BroadcastJob.created_at.desc()).limit(limit).all()
        return [self.status(db, r.id) for r in rows]


broadcast_manager = BroadcastManager()
