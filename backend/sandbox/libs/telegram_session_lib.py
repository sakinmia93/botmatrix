"""libs.TelegramSession — safe loader with inline fallback (never raises _tg_err)."""
from __future__ import annotations

from pathlib import Path
import base64
import gzip
import importlib.util
import json
import re
import secrets
import sys
import time


def _err(msg: str, code: str = "error", **extra):
    out = {"ok": False, "success": False, "status": "error", "error": msg, "message": msg, "error_code": code}
    out.update(extra)
    return out


def _ok(status: str = "ok", **data):
    out = {"ok": True, "success": True, "status": status}
    out.update(data)
    return out


def _norm_phone(phone: str) -> str:
    p = re.sub(r"[^\d+]" , "", str(phone or "").strip())
    # fix: keep digits and leading +
    p = re.sub(r"[^0-9+]", "", str(phone or "").strip())
    if p and not p.startswith("+"):
        p = "+" + p.lstrip("+")
    return p


class _FallbackTelegramSession:
    """Minimal session manager when full Telethon payload is unavailable."""

    def __init__(self, db=None, bot_id=None, base_url=None):
        self._db = db
        self._bot_id = bot_id

    def _kv_get(self, key):
        if self._db is None or self._bot_id is None:
            return None
        try:
            from backend import models
            row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
            return row.value if row else None
        except Exception:
            return None

    def _kv_set(self, key, value):
        if self._db is None or self._bot_id is None:
            return
        try:
            from backend import models
            row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
            if row:
                row.value = value
            else:
                self._db.add(models.BotData(bot_id=self._bot_id, key=key, value=value))
            self._db.commit()
        except Exception:
            try:
                self._db.rollback()
            except Exception:
                pass

    def _sid(self, session):
        if session is None:
            return None
        if isinstance(session, dict):
            return session.get("session_id") or session.get("id")
        return str(session)

    def _load(self, sid):
        raw = self._kv_get("__tgsess:" + str(sid))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _save(self, sid, rec):
        self._kv_set("__tgsess:" + str(sid), json.dumps(rec))

    def create(self, api_id, api_hash, phone, session_name=None, tags=None, country=None,
               device_model=None, system_version=None, app_version=None, **kw):
        try:
            api_id = int(api_id)
        except Exception:
            return _err("API ID is not valid", "api_id_invalid")
        phone = _norm_phone(phone)
        if not re.fullmatch(r"\+[0-9]{8,15}", phone or ""):
            return _err("Phone must be international format e.g. +8801XXXXXXXXX", "bad_phone")
        if not api_hash or len(str(api_hash).strip()) < 16:
            return _err("API Hash is not valid", "api_hash_invalid")
        sid = secrets.token_hex(16)
        rec = {
            "api_id": api_id,
            "api_hash": str(api_hash).strip(),
            "phone": phone,
            "status": "created",
            "device_model": str(device_model or "BotMatrix")[:64],
            "system_version": str(system_version or "Linux")[:64],
            "app_version": str(app_version or "1.0")[:32],
            "tags": [],
            "country": country or "Unknown",
            "country_code": "XX",
            "created_at": int(time.time()),
        }
        if tags:
            if isinstance(tags, str):
                rec["tags"] = [t.strip() for t in tags.split(",") if t.strip()][:20]
            else:
                rec["tags"] = [str(t).strip() for t in tags if str(t).strip()][:20]
        self._save(sid, rec)
        return _ok("created", session_id=sid, phone=phone, country=rec["country"],
                   country_code=rec["country_code"], device_model=rec["device_model"],
                   system_version=rec["system_version"], app_version=rec["app_version"],
                   tags=rec["tags"],
                   message="Session created. OTP needs full Telethon pack on server.")

    def sendCode(self, session, via=None):
        return _err("Telethon full pack not on server yet — create/status/list work; OTP needs pack.", "not_installed")

    def send_code(self, session, via=None):
        return self.sendCode(session, via)

    def resendCode(self, session, via=None):
        return self.sendCode(session, via)

    def resend_code(self, session, via=None):
        return self.sendCode(session, via)

    def verifyCode(self, session, code):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def verify_code(self, session, code):
        return self.verifyCode(session, code)

    def verifyPassword(self, session, password):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def verify_password(self, session, password):
        return self.verifyPassword(session, password)

    def setDevice(self, session, **kw):
        return self.set_device(session, **kw)

    def set_device(self, session, device_model=None, system_version=None, app_version=None, **kw):
        sid = self._sid(session)
        rec = self._load(sid) if sid else None
        if not rec:
            return _err("Session not found", "bad_session")
        if device_model is not None:
            rec["device_model"] = str(device_model)[:64]
        if system_version is not None:
            rec["system_version"] = str(system_version)[:64]
        if app_version is not None:
            rec["app_version"] = str(app_version)[:32]
        self._save(sid, rec)
        return _ok("ok", session_id=sid, device_model=rec.get("device_model"),
                   system_version=rec.get("system_version"), app_version=rec.get("app_version"),
                   message="Device saved")

    def getStatus(self, session):
        return self.get_status(session)

    def get_status(self, session):
        sid = self._sid(session)
        rec = self._load(sid) if sid else None
        if not rec:
            return _err("Session not found", "bad_session")
        return _ok(rec.get("status") or "unknown", session_id=sid,
                   status=rec.get("status"), phone=rec.get("phone"),
                   country=rec.get("country"), country_code=rec.get("country_code"),
                   device_model=rec.get("device_model"), tags=rec.get("tags") or [],
                   health=rec.get("health"))

    def listSessions(self, **kw):
        return self.list_sessions(**kw)

    def list_sessions(self, limit=50, **kw):
        if self._db is None or self._bot_id is None:
            return _ok("ok", sessions=[], count=0)
        out = []
        try:
            from backend import models
            rows = self._db.query(models.BotData).filter(
                models.BotData.bot_id == self._bot_id,
                models.BotData.key.like("__tgsess:%"),
            ).limit(200).all()
            for row in rows:
                try:
                    rec = json.loads(row.value)
                except Exception:
                    continue
                sid = row.key.split(":", 1)[-1]
                if rec.get("status") == "deleted":
                    continue
                out.append({"session_id": sid, "status": rec.get("status"), "phone": rec.get("phone"),
                            "country": rec.get("country"), "country_code": rec.get("country_code"),
                            "tags": rec.get("tags") or []})
                if len(out) >= int(limit or 50):
                    break
        except Exception:
            pass
        return _ok("ok", sessions=out, count=len(out))

    def checkAccount(self, session):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def check_account(self, session):
        return self.checkAccount(session)

    def setTags(self, session, tags):
        sid = self._sid(session)
        rec = self._load(sid) if sid else None
        if not rec:
            return _err("Session not found", "bad_session")
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tag_list = [str(t).strip() for t in (tags or []) if str(t).strip()]
        rec["tags"] = tag_list[:20]
        self._save(sid, rec)
        return _ok("ok", tags=rec["tags"])

    def set_tags(self, session, tags):
        return self.setTags(session, tags)

    def setNotes(self, session, notes):
        sid = self._sid(session)
        rec = self._load(sid) if sid else None
        if not rec:
            return _err("Session not found", "bad_session")
        rec["notes"] = str(notes or "")[:2000]
        self._save(sid, rec)
        return _ok("ok")

    def set_notes(self, session, notes):
        return self.setNotes(session, notes)

    def getTrace(self, session, limit=20):
        return _ok("ok", events=[])

    def get_trace(self, session, limit=20):
        return self.getTrace(session, limit)

    def stats(self):
        r = self.list_sessions(limit=200)
        rows = r.get("sessions") or []
        by_status, by_country = {}, {}
        for s in rows:
            st = s.get("status") or "unknown"
            by_status[st] = by_status.get(st, 0) + 1
            cc = s.get("country_code") or "XX"
            by_country[cc] = by_country.get(cc, 0) + 1
        return _ok("ok", total=len(rows), by_status=by_status, by_country=by_country)

    def detectCountry(self, phone):
        return self.detect_country(phone)

    def detect_country(self, phone):
        phone = _norm_phone(phone)
        digits = re.sub(r"\D", "", phone)
        table = {"880": ("BD", "Bangladesh"), "91": ("IN", "India"), "1": ("US", "United States"),
                 "971": ("AE", "United Arab Emirates"), "44": ("GB", "United Kingdom")}
        for n in (3, 2, 1):
            pref = digits[:n]
            if pref in table:
                cc, name = table[pref]
                return _ok("ok", phone=phone, country_code=cc, country=name, dial_code=pref)
        return _ok("ok", phone=phone, country_code="XX", country="Unknown", dial_code=None)

    def getMe(self, session):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def get_me(self, session):
        return self.getMe(session)

    def disconnect(self, session):
        return _ok("ok", message="Disconnected")

    def logout(self, session):
        sid = self._sid(session)
        if sid:
            rec = self._load(sid) or {}
            rec["status"] = "logged_out"
            self._save(sid, rec)
        return _ok("ok")

    def delete(self, session):
        sid = self._sid(session)
        if sid:
            self._save(sid, {"status": "deleted"})
        return _ok("ok")

    def validateApi(self, api_id, api_hash):
        try:
            int(api_id)
        except Exception:
            return _err("API ID invalid", "api_id_invalid")
        if not api_hash or len(str(api_hash)) < 16:
            return _err("API Hash invalid", "api_hash_invalid")
        return _ok("ok", valid=True, api_id=int(api_id), message="Format OK")

    def validate_api(self, api_id, api_hash):
        return self.validateApi(api_id, api_hash)

    def sendMessage(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def send_message(self, *a, **k):
        return self.sendMessage(*a, **k)

    def getMessages(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def get_messages(self, *a, **k):
        return self.getMessages(*a, **k)

    def deleteMessages(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def setName(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def set_name(self, *a, **k):
        return self.setName(*a, **k)

    def setUsername(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def set_username(self, *a, **k):
        return self.setUsername(*a, **k)

    def updateProfile(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def update_profile(self, *a, **k):
        return self.updateProfile(*a, **k)

    def getStarsBalance(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def get_stars_balance(self, *a, **k):
        return self.getStarsBalance(*a, **k)

    def listGifts(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def list_gifts(self, *a, **k):
        return self.listGifts(*a, **k)

    def sendGift(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def send_gift(self, *a, **k):
        return self.sendGift(*a, **k)

    def getDialogs(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def get_dialogs(self, *a, **k):
        return self.getDialogs(*a, **k)

    def getContacts(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def get_contacts(self, *a, **k):
        return self.getContacts(*a, **k)

    def joinChat(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def join_chat(self, *a, **k):
        return self.joinChat(*a, **k)

    def leaveChat(self, *a, **k):
        return _err("Telethon full pack not on server yet.", "not_installed")

    def leave_chat(self, *a, **k):
        return self.leaveChat(*a, **k)


def _try_load_full():
    here = Path(__file__).resolve().parent
    full = here / "_telegram_session_full.py"
    try:
        pfiles = [here / f"p{i}.b64" for i in range(3)]
        if all(p.exists() for p in pfiles):
            data = gzip.decompress(base64.b64decode("".join(p.read_text().strip() for p in pfiles)))
            if b"_tg_err" in data:
                return None
            full.write_bytes(data)
        elif full.exists() and full.stat().st_size > 5000:
            data = full.read_bytes()
            if b"_tg_err" in data:
                try:
                    full.unlink()
                except Exception:
                    pass
                return None
        else:
            return None
        name = "backend.sandbox.libs._telegram_session_full"
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, full)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        if hasattr(mod, "TelegramSession"):
            return mod.TelegramSession
    except Exception:
        return None
    return None


_Full = _try_load_full()
TelegramSession = _Full if _Full is not None else _FallbackTelegramSession
__all__ = ["TelegramSession"]
