"""
TPY-compatible runtime objects.
The important compatibility rule is: `u` is the current Telegram user ID;
`User` is the per-user storage object. Nested Telegram objects expose both
mapping-style and attribute-style access.
"""
from sqlalchemy.orm import Session
from backend import models
import json


def _json_default(o):
    """Make TBC wrapper types JSON-serializable (HTTP.post json=, saveData, etc.)."""
    if isinstance(o, _TBCOptionalStr):
        return None if not o else str(o)
    if isinstance(o, _TBCNum):
        return o._v
    if isinstance(o, (bytes, bytearray)):
        return o.decode("utf-8", errors="replace")
    if hasattr(o, "to_dict") and callable(o.to_dict):
        return o.to_dict()
    if hasattr(o, "_v"):
        return o._v
    return str(o)


MAX_DATA_ENTRY_BYTES = 10 * 1024 * 1024        # docs: each data entry can hold up to 10 MB


def _encode(value):
    out = _encode_raw(value)
    if len(out) > MAX_DATA_ENTRY_BYTES:
        raise ValueError("Data entry is too large (max 10 MB per entry)")
    return out


def _encode_raw(value):
    # OptionalStr / Msg-like → plain str first
    if isinstance(value, _TBCOptionalStr):
        value = None if not value else str(value)
    if isinstance(value, _TBCNum):
        value = value._v
    if isinstance(value, str):
        # JSON-string so "1.0" stays a STRING after decode (not float)
        return json.dumps(value, ensure_ascii=False)
    try:
        return json.dumps(value, ensure_ascii=False, default=_json_default)
    except Exception:
        return json.dumps(str(value), ensure_ascii=False)


def _decode(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _safe_int(value, default=None):
    """Coerce to int; empty string / None / invalid → default (never raises)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s or s in ("None", "null", "undefined"):
        return default
    try:
        return int(float(s)) if "." in s else int(s)
    except Exception:
        return default




class _TBCOptionalStr:
    """`params` / optional text: when nothing was sent it is the text `None` (docs), falsy, and still == None."""
    __slots__ = ("_v",)
    def __init__(self, value):
        if value is None or value == "":
            self._v = None
        else:
            self._v = str(value)
    @property
    def _t(self):
        return "None" if self._v is None else self._v
    def __bool__(self):
        return self._v is not None
    def __eq__(self, other):
        if other is None or other == "":
            return self._v is None
        if isinstance(other, _TBCOptionalStr):
            return self._v == other._v
        return self._t == other
    def __ne__(self, other):
        return not self.__eq__(other)
    def __contains__(self, item):
        return item in self._t
    def __str__(self):
        return self._t
    def __repr__(self):
        return repr(self._v)
    def __add__(self, other):
        return self._t + str(other)
    def __radd__(self, other):
        return str(other) + self._t
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._t, name)
    def __iter__(self):
        return iter(self._t)
    def __len__(self):
        return len(self._t)
    def __hash__(self):
        return hash(self._v)
    def __int__(self):
        return int(self._v or "0")
    def __float__(self):
        return float(self._v or "0")
    def __index__(self):
        return int(self._v or "0")
    def __format__(self, spec):
        return format(self._t, spec)


class _TBCNum:
    """Number that also accepts string methods (TBC bots often call .replace on amounts).

    amount.replace("+", "") works even when amount is 1000.
    float(amount), int(amount), amount + 1 all work.
    """
    __slots__ = ("_v",)
    def __init__(self, value):
        self._v = value
    def __repr__(self):
        return repr(self._v)
    def __str__(self):
        return str(self._v)
    def __bool__(self):
        return bool(self._v)
    def __hash__(self):
        return hash(self._v)
    def __int__(self):
        return int(self._v)
    def __float__(self):
        return float(self._v)
    def __index__(self):
        return int(self._v)
    def __format__(self, spec):
        return format(self._v, spec)
    def __eq__(self, other):
        if isinstance(other, _TBCNum):
            return self._v == other._v
        return self._v == other
    def __lt__(self, other):
        return self._v < (other._v if isinstance(other, _TBCNum) else other)
    def __le__(self, other):
        return self._v <= (other._v if isinstance(other, _TBCNum) else other)
    def __gt__(self, other):
        return self._v > (other._v if isinstance(other, _TBCNum) else other)
    def __ge__(self, other):
        return self._v >= (other._v if isinstance(other, _TBCNum) else other)
    def __add__(self, other):
        return self._v + (other._v if isinstance(other, _TBCNum) else other)
    def __radd__(self, other):
        return other + self._v
    def __sub__(self, other):
        return self._v - (other._v if isinstance(other, _TBCNum) else other)
    def __rsub__(self, other):
        return other - self._v
    def __mul__(self, other):
        return self._v * (other._v if isinstance(other, _TBCNum) else other)
    def __rmul__(self, other):
        return other * self._v
    def __truediv__(self, other):
        return self._v / (other._v if isinstance(other, _TBCNum) else other)
    def __rtruediv__(self, other):
        return other / self._v
    def __getattr__(self, name):
        # .replace .strip .split .lower … on the string form
        return getattr(str(self._v), name)


def _wrap_user_value(val):
    """After decode: ints/floats become _TBCNum so .replace works."""
    if isinstance(val, bool) or val is None:
        return val
    if isinstance(val, (int, float)):
        return _TBCNum(val)
    return val

class _CIStr(str):
    """'working' == 'Working' (docs show both spellings)."""
    def __eq__(self, o): return isinstance(o, str) and str.lower(self) == o.lower()
    def __ne__(self, o): return not self.__eq__(o)
    __hash__ = str.__hash__


class _AttrDict(dict):
    def __getattr__(self, item):
        value = self.get(item)
        if isinstance(value, dict) and not isinstance(value, _AttrDict):
            value = _AttrDict(value)
            self[item] = value
        elif isinstance(value, list):
            value = [_AttrDict(x) if isinstance(x, dict) else x for x in value]
            self[item] = value
        return value


class _ErrOptions(str):
    """`options` inside the `!` error handler: it is the error text, and also exposes the details
    (options.error, options.command, options.line, options.traceback, options.get("type") ...)."""
    def __new__(cls, text, details=None):
        o = str.__new__(cls, text)
        o._d = dict(details or {})
        return o

    def __getattr__(self, k):
        if k.startswith("_"):
            raise AttributeError(k)
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError(k)

    def __getitem__(self, k):
        if isinstance(k, str):
            return self._d[k]
        return str.__getitem__(self, k)

    def get(self, k, default=None):
        return self._d.get(k, default)


class _Captcha(dict):
    """genCaptcha result: attribute + key access; str() is plain text (never a <repr>)."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __str__(self):
        return str(self.get("captcha_url") or "")


class UserObject:
    def __init__(self, db: Session, bot_id: int, telegram_user_id: int):
        self._db = db
        self._bot_id = bot_id
        self.id = telegram_user_id

    def _row(self, key):
        return self._db.query(models.UserData).filter_by(
            bot_id=self._bot_id, telegram_user_id=self.id, key=str(key)
        ).first()

    def get(self, key, default=None, user=None):
        uid = _safe_int(user, default=None) if user is not None else None
        if uid is None or uid == _safe_int(self.id):
            row = self._row(key)
        else:
            row = self._db.query(models.UserData).filter_by(
                bot_id=self._bot_id, telegram_user_id=uid, key=str(key)
            ).first()
        if not row:
            return default
        val = _decode(row.value)
        # Telegram user ids stored as int → str (avoids "prefix" + id TypeError)
        if isinstance(val, int) and not isinstance(val, bool) and abs(val) >= 100000:
            return str(val)
        return _wrap_user_value(val)

    def set(self, key, value, user=None):
        uid = self.id if user is None else (_safe_int(user, default=self.id) or self.id)
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 100000:
            value = str(value)
        row = self._db.query(models.UserData).filter_by(bot_id=self._bot_id, telegram_user_id=uid, key=str(key)).first()
        if row:
            row.value = _encode(value)
        else:
            row = models.UserData(bot_id=self._bot_id, telegram_user_id=uid, key=str(key), value=_encode(value))
            self._db.add(row)
        self._db.commit()
        return True

    # TBC-compatible aliases
    def saveData(self, name, data, user=None):
        return self.set(name, data, user=user)

    def getData(self, name, user=None):
        return self.get(name, None, user=user)

    def delete(self, key, user=None):
        uid = self.id if user is None else (_safe_int(user, default=self.id) or self.id)
        row = self._db.query(models.UserData).filter_by(bot_id=self._bot_id, telegram_user_id=uid, key=str(key)).first()
        if row:
            self._db.delete(row)
            self._db.commit()
            return True
        return False

    def deleteData(self, name, user=None):
        return self.delete(name, user=user)

    def all(self):
        rows = self._db.query(models.UserData).filter_by(bot_id=self._bot_id, telegram_user_id=self.id).all()
        return {r.key: r.value for r in rows}

    def set_state(self, state, context=None):
        row = self._db.query(models.UserState).filter_by(bot_id=self._bot_id, telegram_user_id=self.id).first()
        if not row:
            row = models.UserState(bot_id=self._bot_id, telegram_user_id=self.id)
            self._db.add(row)
        row.state = state
        row.context = context or {}
        self._db.commit()

    def get_state(self):
        row = self._db.query(models.UserState).filter_by(bot_id=self._bot_id, telegram_user_id=self.id).first()
        return row.state if row else None

    def get_state_context(self):
        row = self._db.query(models.UserState).filter_by(bot_id=self._bot_id, telegram_user_id=self.id).first()
        return (row.context or {}) if row else {}

    def clear_state(self):
        self.set_state(None, {})


    def storeData(self, name, data, user=None):
        if user is not None and int(user) != int(self.id):
            return UserObject(self._db, self._bot_id, int(user)).saveData(name, data)
        return self.saveData(name, data)

    def fetchData(self, name, user=None):
        if user is not None and int(user) != int(self.id):
            return UserObject(self._db, self._bot_id, int(user)).getData(name)
        return self.getData(name)

    def removeData(self, name, user=None):
        if user is not None and int(user) != int(self.id):
            return UserObject(self._db, self._bot_id, int(user)).deleteData(name)
        return self.deleteData(name)

    def res(self, resource_name):
        from backend.sandbox.libs.resources_lib import ResourcesLib
        return ResourcesLib(self._db, self._bot_id, int(self.id)).userRes(resource_name)

    def resOf(self, resource_name, user):
        from backend.sandbox.libs.resources_lib import ResourcesLib
        return ResourcesLib(self._db, self._bot_id, int(user)).userRes(resource_name, user=int(user))

    def exportData(self, name, user=None, output_format="txt"):
        if user is not None and int(user) != int(self.id):
            return UserObject(self._db, self._bot_id, int(user)).getDataFile(name, output_format=output_format)
        return self.getDataFile(name, output_format=output_format)

    def incr(self, name, amount=1):
        """Increment a numeric user data value; returns new value."""
        try:
            cur = float(self.getData(name) or 0)
        except Exception:
            cur = 0.0
        cur = cur + float(amount)
        # store as int when whole
        val = int(cur) if cur == int(cur) else cur
        self.saveData(name, val)
        return val

    def decr(self, name, amount=1):
        return self.incr(name, -float(amount))

    def append_list(self, name, item, unique=False, max_len=None):
        data = self.getData(name) or []
        if not isinstance(data, list):
            data = [data]
        if unique and item in data:
            return data
        data.append(item)
        if max_len is not None:
            data = data[-int(max_len):]
        self.saveData(name, data)
        return data

    def get_list(self, name):
        data = self.getData(name) or []
        return data if isinstance(data, list) else [data]


    def getAllData(self, name=None, output_format="json", old_data=False):
        """User.getAllData — export this user's data.

        TBC signature: getAllData(name=None, output_format="json", old_data=False)
        - name: if set, only that key; else all keys for this user
        - output_format: "json" | "txt" | "csv"
        - old_data: reserved (accepted for parity; ignored)
        """
        q = self._db.query(models.UserData).filter_by(
            bot_id=self._bot_id, telegram_user_id=self.id
        )
        if name is not None:
            q = q.filter_by(key=str(name))
        rows = q.all()
        data = {r.key: _decode(r.value) for r in rows}
        if output_format == "txt":
            return "\n".join(f"{k}={v}" for k, v in data.items())
        if output_format == "csv":
            lines = ["key,value"]
            for k, v in data.items():
                lines.append(f"{k},{v}")
            return "\n".join(lines)
        return data


    def getAllDataOfUser(self, user, output_format="json"):
        uid = _safe_int(user, default=None)
        if uid is None:
            return {} if output_format != "txt" else ""
        rows = self._db.query(models.UserData).filter_by(
            bot_id=self._bot_id, telegram_user_id=uid
        ).all()
        data = {r.key: _decode(r.value) for r in rows}
        if output_format == "txt":
            return "\n".join(f"{k}={v}" for k, v in data.items())
        return data

    def getDataFile(self, name, output_format="txt"):
        """Return a file-like object suitable for bot.sendDocument(...)."""
        import io, json as _json
        val = self.getData(name)
        if output_format == "json":
            content = _json.dumps(val, ensure_ascii=False, indent=2)
            ext = "json"
        else:
            content = "" if val is None else str(val)
            ext = "txt"
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = f"{name}.{ext}"
        buf.seek(0)
        return buf



    def deleteAllData(self, name=None, old_data=False, except_data=None):
        """User.deleteAllData — wipe this user's stored keys (optionally only matching name prefix)."""
        q = self._db.query(models.UserData).filter_by(bot_id=self._bot_id, telegram_user_id=self.id)
        if name:
            q = q.filter(models.UserData.key == str(name))
        except_data = except_data or []
        if except_data:
            q = q.filter(~models.UserData.key.in_([str(x) for x in except_data]))
        n = q.delete(synchronize_session=False)
        self._db.commit()
        return {"ok": True, "deleted": n}

    def deleteAllDataOfUser(self, user):
        """User.deleteAllDataOfUser — wipe all keys for another telegram user id on this bot."""
        uid = int(user) if str(user).lstrip("-").isdigit() else user
        n = self._db.query(models.UserData).filter_by(bot_id=self._bot_id, telegram_user_id=uid).delete(synchronize_session=False)
        self._db.commit()
        return {"ok": True, "deleted": n}


class BotDataObject:
    def __init__(self, db: Session, bot_id: int, owner_account=None, runtime=None):
        self._db = db
        self._bot_id = bot_id
        self._owner_account = owner_account
        self._runtime = runtime or {}

    def _row(self, key):
        return self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=str(key)).first()

    def get(self, key, default=None):
        row = self._row(key)
        if not row:
            return default
        return _wrap_user_value(_decode(row.value))

    def getData(self, name=None):
        return self.get(name, None) if name is not None else self.all()

    def set(self, key, value):
        row = self._row(key)
        if row:
            row.value = _encode(value)
        else:
            row = models.BotData(bot_id=self._bot_id, key=str(key), value=_encode(value))
            self._db.add(row)
        self._db.commit()
        return True

    def saveData(self, name, data):
        return self.set(name, data)

    def deleteData(self, name=None):
        if name is None:
            return False
        row = self._row(name)
        if row:
            self._db.delete(row)
            self._db.commit()
            return True
        return False

    def all(self):
        rows = self._db.query(models.BotData).filter_by(bot_id=self._bot_id).all()
        return {r.key: r.value for r in rows}

    def info(self, bot_id=None, api_key=None):
        """TBC Bot.info(): the same real numbers the web app shows (owner e-mail, points, users, times)."""
        import json as _json
        from backend import appdb as _adb
        b = self._db.query(models.Bot).filter_by(id=bot_id or self._bot_id).first()
        if not b:
            b = self._db.query(models.Bot).filter_by(public_id=str(bot_id)).first() if bot_id else None
        if not b:
            return {}
        pub = str(b.public_id or b.id)
        if bot_id and str(bot_id) not in (str(b.id), pub):
            return {}
        with _adb.read() as _c:
            ab = _adb.one(_c, "SELECT * FROM bots WHERE id=?", (pub,))
            uid = ab["user_id"] if ab else None
            usr = _adb.one(_c, "SELECT email, points FROM users WHERE id=?", (uid,)) if uid else None
            tot = _adb.one(_c, "SELECT COUNT(*) n, MAX(last_active) la, MIN(first_seen) fs FROM chats WHERE bot_id=?", (pub,))
            act = _adb.one(_c, "SELECT COUNT(*) n FROM chats WHERE bot_id=? AND bot_blocked=0 AND is_blocked=0", (pub,))
            trf = _adb.one(_c, "SELECT COALESCE(responded_at, created_at) created_at FROM transfers WHERE bot_numeric_id=(SELECT bot_numeric_id FROM bots WHERE id=?) AND status IN ('accepted','completed','approved') ORDER BY created_at DESC LIMIT 1", (pub,))
        def _fmt(v):
            v = str(v or "")
            return v.replace("T", " ").replace("Z", "").split(".")[0] if v else ""
        running = bool(ab and ab["status"] == "working") if ab else bool(b.is_running)
        status = _CIStr("working" if running else "stopped")
        users_total = int((tot or {})["n"] or 0) if tot else 0
        info = {
            "bot_name": (ab["name"] if ab else b.name) or "",
            "bot_username": ((ab["username"] if ab else b.username) or "").lstrip("@"),
            "transferred_at": _fmt(trf["created_at"]) if trf else "",
            "all_time_users": users_total,
            "last_active_at": _fmt(tot["la"]) if tot and tot["la"] else "",
            "start_time": _fmt(ab["created_at"] if ab else getattr(b, "created_at", "")),
            "token": b.token or "",
            "bot_id": pub,
            "owner_email": (usr["email"] if usr else "") or "",
            "status": status,
            "userstat": int(act["n"] or 0) if act else 0,
            "username": ((ab["username"] if ab else b.username) or "").lstrip("@"),
            "first_name": (ab["name"] if ab else b.name) or "",
            "account_points": str(int(usr["points"] or 0)) if usr else "0",
            "id": pub,
            "name": (ab["name"] if ab else b.name) or "",
        }
        info["details"] = _json.dumps({k: v for k, v in info.items() if k not in ("details", "id", "name", "transferred_at")}, indent=4, ensure_ascii=False, default=str)
        return _AttrDict(info)

    def genId(self):
        import secrets
        return secrets.randbelow(900000000) + 100000000

    def genRandomId(self):
        return self.genId()

    def storageInfo(self):
        """Return bot storage quota/usage without exposing filesystem paths."""
        import os
        root = os.path.join(self._runtime.get("storage_root", ""), "bot_files", str(self._bot_id))
        used = 0
        if root and os.path.isdir(root):
            for base, _, files in os.walk(root):
                for name in files:
                    try:
                        used += os.path.getsize(os.path.join(base, name))
                    except OSError:
                        pass
        bot = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        limit = int(getattr(bot, "storage_limit_mb", 100) or 100)
        return {"used_bytes": used, "used_mb": round(used / 1048576, 3), "limit_mb": limit,
                "remaining_mb": max(0, limit - used / 1048576)}

    def setStorageLimit(self, limit_mb):
        bot = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if not bot or self._owner_account is None or bot.owner_id != self._owner_account.id:
            return False
        limit_mb = int(limit_mb)
        if limit_mb < 1 or limit_mb > 1024 * 1024:
            raise ValueError("storage limit must be between 1 MB and 1 TB")
        bot.storage_limit_mb = limit_mb
        self._db.commit()
        return True

    def Transfer(self, email: str, bot_id: str, bot_token: str = None,
                 run_now: bool = False, target_api_key: str = None,
                 include_data: bool = True, include_chats: bool = True,
                 include_errors: bool = True, include_env: bool = True,
                 data=None, chats=None, errors=None, env=None, options=None, **kwargs):
        """Transfer one of this account's bots (same as dashboard Send copy).

        Frontend parity options (all optional bools, default True unless explicitly False):
          include_data / data     — user & bot stored data
          include_chats / chats   — chat/user list
          include_errors / errors — error logs
          include_env / env       — .env / environment command values
        Or pass options={"data": True, "chats": False, ...} like the UI transferParts object.
        Without the other account's API key the transfer is a request they must accept.
        """
        from backend import platform_hooks
        if self._owner_account is None:
            raise PermissionError("Not allowed")
        # Merge options dict (UI shape) + short aliases + include_* flags
        opt = dict(options or {}) if isinstance(options, dict) else {}
        if data is not None: opt["data"] = data
        if chats is not None: opt["chats"] = chats
        if errors is not None: opt["errors"] = errors
        if env is not None: opt["env"] = env
        if "data" in opt: include_data = bool(opt["data"])
        if "chats" in opt: include_chats = bool(opt["chats"])
        if "errors" in opt: include_errors = bool(opt["errors"])
        if "env" in opt: include_env = bool(opt["env"])
        if "data" in kwargs: include_data = bool(kwargs["data"])
        if "chats" in kwargs: include_chats = bool(kwargs["chats"])
        if "errors" in kwargs: include_errors = bool(kwargs["errors"])
        if "env" in kwargs: include_env = bool(kwargs["env"])
        res = platform_hooks.call("transfer_bot", self._db, self._owner_account, str(bot_id), email,
                                  target_api_key=target_api_key, bot_token=bot_token, run_now=run_now,
                                  include_data=include_data, include_chats=include_chats,
                                  include_errors=include_errors, include_env=include_env)
        if isinstance(res, dict) and res.get("error"):
            raise ValueError(res["error"])
        return res

    def setAutoTranslate(self, enabled=True):
        """Turn Auto-Translate on/off for this bot (persists in the app database)."""
        enabled = bool(enabled)
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if b is None:
            raise ValueError("bot not found")
        b.auto_translate = enabled
        self._db.commit()
        try:
            from backend import appdb
            with appdb.db() as c:
                c.execute("UPDATE bots SET auto_translate=? WHERE id=?", (1 if enabled else 0, str(b.public_id or b.id)))
        except Exception:
            pass
        return enabled

    def getAutoTranslate(self):
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        return bool(getattr(b, "auto_translate", False)) if b else False

    def gen_random_id(self):
        import secrets
        return str(secrets.randbelow(900000000) + 100000000)

    def genRandomErrorId(self):
        import secrets
        return "err_" + secrets.token_hex(8)

    def genCaptcha(self, mode="auto", captcha=None):
        """genCaptcha — auto (5 chars) or manual (2-8 chars).

        Returns an object with captcha_url, captcha_text, length, captcha_id (manual).
        The image is kept in memory only and is uploaded straight to Telegram when
        captcha_url is passed to sendPhoto — nothing is written to disk.
        """
        import hashlib, random, string, time
        from backend import captcha_store
        mode = (mode or "auto").lower()
        if mode == "manual":
            text = str(captcha or "").strip()
            if not (2 <= len(text) <= 8):
                raise ValueError("manual captcha length must be 2-8")
            captcha_id = hashlib.md5(f"{text}-{time.time()}".encode()).hexdigest()[:12]
        else:
            alphabet = (string.ascii_uppercase + string.digits).translate(str.maketrans("", "", "0O1I"))
            text = "".join(random.choice(alphabet) for _ in range(5))
            captcha_id = None
        try:
            url = captcha_store.put(captcha_store.render(text))
        except Exception:
            from urllib.parse import quote
            url = f"https://dummyimage.com/280x100/1a1a2e/e94560.png&text={quote(text)}"

        return _Captcha({"captcha_url": url, "captcha_text": text, "length": len(text), "captcha_id": captcha_id})

    def getIpnUrl(self, command, user_id=None, url=None, chat_id=None):
        """IPN/webhook URL for payments & callbacks (alias of Webhook.getUrlFor)."""
        from backend.sandbox.libs.webhook_lib import WebhookLib
        from backend.config import BASE_URL
        lib = WebhookLib(db=self._db, bot_id=self._bot_id, base_url=BASE_URL)
        return lib.getUrlFor(command=command, user_id=user_id, chat_id=chat_id or user_id)

    def getIpnUrlForCoinbase(self, command):
        return self.getIpnUrl(command=command)

    def start(self, bot_id=None, api_key=None):
        """Start this bot (or another bot of the same account)."""
        return self._set_running(bot_id, True)

    def stop(self, bot_id=None, api_key=None):
        """Stop this bot (or another bot of the same account)."""
        return self._set_running(bot_id, False)

    def _set_running(self, bot_id, running):
        from backend import platform_hooks
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if bot_id is not None:
            owner = self._owner_account or self._db.query(models.Account).filter_by(id=b.owner_id).first()
            other = None
            if owner:
                other = self._db.query(models.Bot).filter_by(owner_id=owner.id, public_id=str(bot_id)).first()
            if not other:
                return {"ok": False, "error": "bot not found"}
            b = other
        res = platform_hooks.call("set_running", self._db, b, bool(running))
        if isinstance(res, dict) and res.get("ok"):
            res = dict(res)
            res["status"] = "working" if running else "stopped"
        return res

    def status(self, bot_id=None, api_key=None):
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if bot_id is not None:
            owner = self._owner_account or self._db.query(models.Account).filter_by(id=b.owner_id).first()
            other = None
            if owner:
                other = self._db.query(models.Bot).filter_by(owner_id=owner.id, public_id=str(bot_id)).first()
            if not other:
                return {"ok": False, "error": "bot not found"}
            b = other
        return {
            "ok": True,
            "status": "working" if b.is_running else "stopped",
            "username": b.username,
            "webhook_set": bool(b.webhook_set),
        }


    def cancelScheduledTask(self, job_id):
        from backend.scheduler.scheduler import cancel_task
        return cancel_task(self._db, job_id, bot_id=self._bot_id)

    def getAllData(self, name=None, output_format="json"):
        rows = self._db.query(models.BotData).filter_by(bot_id=self._bot_id).all()
        data = {r.key: _decode(r.value) for r in rows}
        if name is not None:
            data = {name: data.get(name)}
        if output_format == "txt":
            return "\n".join(f"{k}={v}" for k, v in data.items())
        return data

    def deleteAllData(self, except_data=None):
        except_set = set(except_data or [])
        rows = self._db.query(models.BotData).filter_by(bot_id=self._bot_id).all()
        n = 0
        for r in rows:
            if r.key in except_set or r.key.startswith("__"):
                continue
            self._db.delete(r)
            n += 1
        self._db.commit()
        return {"ok": True, "deleted": n}

    def getDataFile(self, name, output_format="txt"):
        """File-like for bot.sendDocument; content is the stored Bot data value."""
        import io, json as _json
        val = self.getData(name)
        if output_format == "json":
            content = _json.dumps(val, ensure_ascii=False, indent=2)
            ext = "json"
        else:
            content = "" if val is None else str(val)
            ext = "txt"
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = f"{name}.{ext}"
        buf.seek(0)
        return buf

    def getBotUsersFile(self, output_format="csv", include_creation_date=True):
        """Export known bot members as a file-like object (csv/json/txt)."""
        import io, json as _json, csv
        rows = []
        try:
            members = self._db.query(models.BotMember).filter_by(bot_id=self._bot_id).all()
        except Exception:
            members = []
        for m in members:
            rec = {
                "telegram_user_id": m.telegram_user_id,
                "chat_id": getattr(m, "chat_id", None),
            }
            if include_creation_date:
                rec["first_seen"] = str(getattr(m, "first_seen", "") or "")
                rec["last_seen"] = str(getattr(m, "last_seen", "") or "")
            rows.append(rec)
        if output_format == "json":
            content = _json.dumps(rows, ensure_ascii=False, indent=2)
            name = "bot_users.json"
            buf = io.BytesIO(content.encode("utf-8"))
        elif output_format == "txt":
            lines = []
            for r in rows:
                lines.append("\t".join(str(r.get(k, "")) for k in r.keys()))
            buf = io.BytesIO(("\n".join(lines)).encode("utf-8"))
            name = "bot_users.txt"
        else:
            # csv
            sio = io.StringIO()
            fields = ["telegram_user_id", "chat_id"]
            if include_creation_date:
                fields += ["first_seen", "last_seen"]
            w = csv.DictWriter(sio, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
            buf = io.BytesIO(sio.getvalue().encode("utf-8"))
            name = "bot_users.csv"
        buf.name = name
        buf.seek(0)
        return buf

    def getStats(self, time_frames=None, bot_id=None, api_key=None):
        """Bot.getStats — active users per time frame (via BotMember.last_seen)."""
        import datetime
        bid = self._bot_id
        if bot_id is not None:
            other = self._db.query(models.Bot).filter_by(public_id=str(bot_id)).first()
            if other:
                bid = other.id
        time_frames = time_frames or ["24h"]
        now = datetime.datetime.utcnow()
        out = {}
        for tf in time_frames:
            tf = str(tf).lower().strip()
            hours = 24
            if tf.endswith("h"):
                try: hours = int(tf[:-1])
                except: hours = 24
            elif tf.endswith("d"):
                try: hours = int(tf[:-1]) * 24
                except: hours = 24
            since = now - datetime.timedelta(hours=hours)
            try:
                cnt = self._db.query(models.BotMember).filter(
                    models.BotMember.bot_id == bid,
                    models.BotMember.last_seen >= since,
                ).count()
            except Exception:
                cnt = self._db.query(models.BotMember).filter_by(bot_id=bid).count()
            out[tf] = cnt
        try:
            out["total"] = self._db.query(models.BotMember).filter_by(bot_id=bid).count()
        except Exception:
            out["total"] = 0
        out["bot_id"] = str(bid)
        return out

    def blockUser(self, user_id):
        self.saveData(f"__blocked_{user_id}", True)
        return {"ok": True}

    def unblockUser(self, user_id):
        self.deleteData(f"__blocked_{user_id}")
        return {"ok": True}

    def getBlockedUsers(self):
        rows = self._db.query(models.BotData).filter(
            models.BotData.bot_id == self._bot_id,
            models.BotData.key.like("__blocked_%"),
        ).all()
        return [int(r.key.replace("__blocked_", "")) for r in rows if r.key.replace("__blocked_", "").isdigit()]

    def getBlockedUsersCount(self):
        return len(self.getBlockedUsers())

    def getBlockedUsersFile(self, output_format="csv"):
        """Return a BytesIO export of the bot-level blocked users."""
        import io, json as _json
        blocked = self.getBlockedUsers()
        if output_format == "json":
            content = _json.dumps({"blocked": blocked}, ensure_ascii=False, indent=2)
            name = "blocked_users.json"
        else:
            content = "user_id\n" + "\n".join(str(x) for x in blocked)
            name = "blocked_users.csv"
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = name
        buf.seek(0)
        return buf

    def handleNextCommand(self, command, options=None, params=None, cancel_at_command=None, **kwargs):
        """Wait for the user's next message and route it to `command`.

        Bot.handleNextCommand("/x", options=True)
        Bot.handleNextCommand("/x", params="abc")
        options/params may be any scalar — preserved as-is. Missing → None.
        Real slash commands, exact keyboard triggers, and callbacks cancel this wait.
        """
        uid = self._runtime.get("user_id")
        if uid is None:
            return False
        if options is None and "option" in kwargs:
            options = kwargs.get("option")
        user = UserObject(self._db, self._bot_id, int(uid))
        ctx = {
            "options": options,   # True / str / dict / None
            "params": params,     # optional override for next run
            "cancel_at_command": cancel_at_command,
        }
        user.set_state(command, ctx)
        return True

    def runCommand(self, command, options=None, params=None, **kwargs):
        """Bot.runCommand("/start", params="123") or options=...

        Injects params into a shallow copy of the current update text when possible.
        Disabled inside the `!` error handler (TBC: prevents infinite error loops).
        TBC hard limit: max 3 chained runCommand calls per user message.
        The 4th hop is refused silently (returns ok=False) — same as TBC.
        """
        if isinstance(options, str):  # docs also show Bot.runCommand(bot_id, "command")
            command, options = options, None
        if self._runtime.get("in_error_handler") or self._runtime.get("current_trigger") == "!":
            return {"ok": False, "error": "runCommand is disabled inside the ! error handler"}
        # --- TBC 3-command chain limit (shared across nested runCommand calls) ---
        from backend.sandbox.runner import run_named_command, _chain_enter
        if not _chain_enter():
            return {"ok": False, "error": "runCommand chain limit (3) exceeded", "refused": True}
        update = dict(self._runtime.get("update") or {})
        # If params provided, synthesize message text so extract_params works
        if params is not None:
            trig = str(command)
            body = f"{trig} {params}".strip() if not str(params) == "" else trig
            if "message" in update and isinstance(update["message"], dict):
                msg = dict(update["message"])
                msg["text"] = body
                update["message"] = msg
            elif "callback_query" in update and isinstance(update["callback_query"], dict):
                cq = dict(update["callback_query"])
                cq["data"] = body
                update["callback_query"] = cq
            else:
                update["message"] = {
                    "message_id": 0,
                    "text": body,
                    "chat": {"id": self._runtime.get("user_id"), "type": "private"},
                    "from": {"id": self._runtime.get("user_id"), "is_bot": False},
                }
        return run_named_command(
            self._db,
            self._runtime.get("bot"),
            self._owner_account,
            command,
            update,
            options=options,
        )

    def runCommandAfter(self, timeout, command, options=None, id=None, params=None, **kwargs):
        """Schedule a command to run after `timeout` seconds (TBC-compatible).

        Bot.runCommandAfter(10, "/hello")
        Bot.runCommandAfter(60, "reminder", options={"note": "x"})

        Returns: {"id": job_id, "command": "...", "timeout": N}
        Survives server restart (stored in DB). Cancel with Bot.cancelScheduledTask(job_id).
        """
        from backend.scheduler.scheduler import schedule_task
        import datetime
        uid = self._runtime.get("user_id")
        # docs: timeout is a number of seconds or a datetime; 1 second .. 366 days
        if isinstance(timeout, datetime.datetime):
            secs = (timeout - (datetime.datetime.now(timeout.tzinfo) if timeout.tzinfo else datetime.datetime.now())).total_seconds()
        else:
            try:
                secs = float(timeout)
            except (TypeError, ValueError):
                raise ValueError("timeout must be a number of seconds or a datetime")
        if secs < 1:
            raise ValueError("timeout must be at least 1 second")
        if secs > 366 * 24 * 3600:
            raise ValueError("timeout can be at most 366 days")
        target = self._bot_id
        if kwargs.get("bot_id") is not None:        # cross-bot: needs the account API key
            from backend.sandbox.libs.webhook_lib import WebhookLib
            target = WebhookLib(db=self._db, bot_id=self._bot_id)._target_bot(kwargs.get("bot_id"), kwargs.get("api_key"))
        _b = self._db.query(models.Bot).filter_by(id=target).first()
        if not _b or not _b.is_running:
            raise ValueError("The bot must be in the working state to schedule a command")
        _cmd = str(command or "")
        if not self._db.query(models.Command).filter(models.Command.bot_id == target, models.Command.trigger.in_([_cmd, _cmd.lstrip("/"), "/" + _cmd.lstrip("/")])).first():
            raise ValueError(f"Command not found: {command}")
        from backend.scheduler.scheduler import check_schedule_limits
        check_schedule_limits(self._db, target, int(uid) if uid is not None else None)
        run_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=secs)
        if options is None and "option" in kwargs:
            options = kwargs.get("option")
        if params is None:
            params = kwargs.get("params")
        return schedule_task(
            self._db,
            target,
            int(uid) if uid is not None else None,
            run_at,
            command,
            options=options,
            params=params,
            job_id=id,
        )

    def listScheduledTasks(self, limit=50):
        from backend.scheduler.scheduler import list_pending_tasks
        return list_pending_tasks(self._db, self._bot_id, limit=int(limit or 50))

    def broadcast(self, function=None, code=None, command=None, mode="single", bot_ids=None,
                  speed=8, callback_url=None, bot_id=None, api_key=None, warnings=None, **kwargs):
        """TBC Broadcast V2 — function / command / code modes.

        Exactly one of function, command, or code must be provided.
        Allowed functions (TBC docs): send_message, send_photo, send_video, send_animation,
        send_audio, send_document, forward_message, send_paid_media, send_sticker,
        send_video_note, send_voice, send_location, send_venue, send_contact, send_poll,
        send_dice, send_invoice, send_game, send_media_group, pin_chat_message,
        plus sendMessage/sendPhoto camelCase aliases.
        """
        from backend.broadcast.manager import broadcast_manager, ALLOWED_BROADCAST_FUNCTIONS
        # Plain message / media broadcasts run on the same engine as the Broadcast Manager page (shared limits, buttons, pin, speed)
        if function and not code and not command and bot_id is None and not callback_url and (mode or "single") in ("single", "multi", None):
            from backend import broadcast_bridge
            _b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
            # Frontend Broadcast Manager parity — same field names as createBroadcast payload
            _kw = dict(kwargs or {})
            if bot_ids:
                _kw.setdefault("targetBotIds", list(bot_ids))
            if mode == "multi" and bot_ids:
                _kw.setdefault("targetBotIds", list(bot_ids))
            # normalize common aliases once
            if "languageFilter" not in _kw and "language_filter" in _kw:
                _kw["languageFilter"] = _kw.pop("language_filter")
            if "targetUserLimit" not in _kw and "target_user_limit" in _kw:
                _kw["targetUserLimit"] = _kw.pop("target_user_limit")
            if "pinMessage" not in _kw and "pin_message" in _kw:
                _kw["pinMessage"] = _kw.pop("pin_message")
            if "inlineButtons" not in _kw and "inline_buttons" in _kw:
                _kw["inlineButtons"] = _kw.pop("inline_buttons")
            if "parseMode" not in _kw and "parse_mode" in _kw:
                _kw["parseMode"] = _kw["parse_mode"]
            _r = broadcast_bridge.start(str(_b.public_id or _b.id), str(function), speed if speed != 8 else None, _kw) if _b else None
            if _r is not None:
                return _r
        provided = sum(1 for x in (function, code, command) if x)
        if provided != 1:
            return {"status": "error", "message": "Either 'code' or 'function' must be provided."}
        if function:
            fn = str(function).strip()
            # normalize snake/camel
            key = fn.replace("-", "_")
            aliases = {
                "sendmessage": "send_message", "sendphoto": "send_photo", "sendvideo": "send_video",
                "sendanimation": "send_animation", "sendaudio": "send_audio", "senddocument": "send_document",
                "forwardmessage": "forward_message", "sendpaidmedia": "send_paid_media",
                "sendsticker": "send_sticker", "sendvideonote": "send_video_note", "sendvoice": "send_voice",
                "sendlocation": "send_location", "sendvenue": "send_venue", "sendcontact": "send_contact",
                "sendpoll": "send_poll", "senddice": "send_dice", "sendinvoice": "send_invoice",
                "sendgame": "send_game", "sendmediagroup": "send_media_group", "pinchatmessage": "pin_chat_message",
            }
            norm = aliases.get(key.lower().replace("_", ""), key.lower() if key.lower() in ALLOWED_BROADCAST_FUNCTIONS else key)
            if norm not in ALLOWED_BROADCAST_FUNCTIONS and key.lower() not in ALLOWED_BROADCAST_FUNCTIONS:
                # also accept exact camelCase telegram method names
                camel_map = {f.replace("_", ""): f for f in ALLOWED_BROADCAST_FUNCTIONS}
                norm = camel_map.get(key.lower().replace("_", ""), None)
                if not norm:
                    return {"status": "error", "message": f"Function '{function}' not allowed for broadcasting."}
            function = norm if norm in ALLOWED_BROADCAST_FUNCTIONS else key.lower()
        if command:
            exists = self._db.query(models.Command).filter_by(bot_id=self._bot_id, trigger=str(command)).first()
            if not exists and not str(command).startswith("/"):
                exists = self._db.query(models.Command).filter_by(bot_id=self._bot_id, trigger="/" + str(command)).first()
            if not exists:
                # try exact
                exists = self._db.query(models.Command).filter_by(bot_id=self._bot_id, trigger=str(command)).first()
            if not exists:
                return {"status": "error", "message": "command doesn't exist"}

        bot = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        owner = self._owner_account or self._db.query(models.Account).filter_by(id=bot.owner_id).first()

        # optional cross-bot
        if bot_id is not None:
            if not api_key:
                return {"status": "error", "message": "API key not valid"}
            # resolve by public_id or internal id
            other = self._db.query(models.Bot).filter(
                (models.Bot.public_id == str(bot_id)) | (models.Bot.id == int(bot_id) if str(bot_id).isdigit() else False)
            ).first()
            if not other or other.owner_id != owner.id:
                return {"status": "error", "message": "API key not valid"}
            bot = other

        config = dict(kwargs)
        if function:
            config["function"] = function
        if code:
            config["code"] = code
        if command:
            config["command"] = str(command)
        # Frontend parity fields for engines that read them from config
        for src, dst in (
            ("languageFilter", "languageFilter"), ("language_filter", "languageFilter"),
            ("language", "languageFilter"), ("targetUserLimit", "targetUserLimit"),
            ("target_user_limit", "targetUserLimit"), ("limit", "targetUserLimit"),
            ("pinMessage", "pinMessage"), ("pin_message", "pinMessage"), ("pin", "pinMessage"),
            ("inlineButtons", "inlineButtons"), ("parseMode", "parseMode"), ("parse_mode", "parseMode"),
        ):
            if src in kwargs and dst not in config:
                config[dst] = kwargs[src]

        if code:
            from backend import tpy_tools
            _v = tpy_tools.validate(str(code))
            _bad = [e for e in _v.get("errors", []) if e.get("severity") != "warning"]
            if _bad:
                return {"status": "error", "message": "Code did not pass the safety check: " + str(_bad[0].get("message"))}
        _uid = (self._runtime or {}).get("user_id")
        if _uid is not None and not (code is None and function is None and command is None):
            _err = broadcast_manager.test_run(self._db, bot, int(_uid), config)
            if _err:
                return {"status": "error", "message": "Test run failed: " + str(_err)}
        try:
            job = broadcast_manager.start(
                self._db, bot, owner,
                mode=mode or "single",
                bot_ids=bot_ids or [],
                speed=speed if speed is not None else 8,
                text=kwargs.get("text"),
                config=config,
                callback_url=callback_url,
            )
        except ValueError as e:
            return {"status": "error", "message": str(e)}
        return {"status": "success", "message": "Task added Successfully", "broadcast_id": job.id, "mode": mode or "single",
                "speed": job.speed}

    def _pub_id(self):
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        return str(b.public_id or b.id) if b else ""

    def getBroadcastStatus(self, broadcast_id):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        if _bb.is_code_id(broadcast_id):
            return _bb.status(self._pub_id(), str(broadcast_id))
        return broadcast_manager.status(self._db, int(broadcast_id))

    def getBroadcastProgress(self, broadcast_id):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        if _bb.is_code_id(broadcast_id):
            return _bb.progress(self._pub_id(), str(broadcast_id))
        return broadcast_manager.progress(self._db, int(broadcast_id))

    def listBroadcasts(self, status=None, limit=20):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        return _bb.list_jobs(self._pub_id(), limit) + broadcast_manager.list_jobs(self._db, self._bot_id, status=status, limit=limit)

    def getAllBroadcasts(self):
        return self.listBroadcasts(limit=1000)

    def setBroadcastSpeed(self, broadcast_id, speed):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        if _bb.is_code_id(broadcast_id):
            return _bb.control(self._pub_id(), str(broadcast_id), "speed", speed)
        return broadcast_manager.set_speed(int(broadcast_id), int(speed))

    def pauseBroadcast(self, broadcast_id):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        if _bb.is_code_id(broadcast_id):
            return _bb.control(self._pub_id(), str(broadcast_id), "pause")
        return broadcast_manager.pause(int(broadcast_id))

    def resumeBroadcast(self, broadcast_id, speed=None):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        if _bb.is_code_id(broadcast_id):
            r = _bb.control(self._pub_id(), str(broadcast_id), "resume")
            if speed:
                _bb.control(self._pub_id(), str(broadcast_id), "speed", speed)
            return r
        return broadcast_manager.resume(int(broadcast_id), speed=speed)

    def stopBroadcast(self, broadcast_id):
        from backend.broadcast.manager import broadcast_manager
        from backend import broadcast_bridge as _bb
        if _bb.is_code_id(broadcast_id):
            return _bb.control(self._pub_id(), str(broadcast_id), "stop")
        return broadcast_manager.stop(int(broadcast_id))

    def rerunBroadcast(self, broadcast_id, speed=None):
        from backend.broadcast.manager import broadcast_manager
        job = broadcast_manager.rerun(self._db, int(broadcast_id), speed=speed)
        return {"broadcast_id": job.id, "status": job.status, "total": job.total}

    def clearBroadcast(self, broadcast_id=None):
        from backend.broadcast.manager import broadcast_manager
        return broadcast_manager.clear(self._db, self._bot_id, job_id=int(broadcast_id) if broadcast_id is not None else None)

    def deleteBroadcastMessages(self, broadcast_id):
        """Delete all Telegram messages delivered by this broadcast job."""
        from backend.broadcast.manager import broadcast_manager
        return broadcast_manager.delete_sent_messages(self._db, int(broadcast_id))


    def setAdmins(self, user_ids):
        """Store admin telegram user ids for this bot."""
        ids = [str(x) for x in (user_ids or [])]
        self.saveData("__admins", ids)
        return {"ok": True, "admins": ids}

    def getAdmins(self):
        own = self.getData("__admins") or []
        glob = self.getData("__global_admins") or []
        try:   # live: admins added/removed in the Admin tab apply at once, with no bot restart
            from backend import appdb
            b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
            with appdb.read() as c:
                o = appdb.one(c, "SELECT user_id FROM bots WHERE id=?", (b.public_id,)) if b and b.public_id else None
                if o:
                    glob = [r["telegram_id"] for r in appdb.rows(c, "SELECT telegram_id FROM global_admins WHERE user_id=?", (o["user_id"],))]
        except Exception:
            pass
        return list(own) + [x for x in glob if x not in own]

    def isAdmin(self, user_id=None):
        uid = user_id if user_id is not None else (self._runtime or {}).get("user_id")
        return str(uid) in [str(x) for x in (self.getAdmins() or [])]

    def sendTo(self, chat_id, text, **kwargs):
        """Convenience: send a message to any chat_id."""
        from backend.telegram.bot_wrapper import BotWrapper
        token = None
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if b:
            token = b.token
        if not token:
            return {"ok": False, "error": "no token"}
        bw = BotWrapper(token, default_chat_id=chat_id)
        return bw.sendMessage(chat_id=chat_id, text=text, **kwargs)

    def notifyOwner(self, text, **kwargs):
        """Send a message to the bot owner (account-linked first member or stored owner id)."""
        owner_id = self.getData("__owner_telegram_id")
        if not owner_id:
            # fallback: first BotMember
            try:
                m = self._db.query(models.BotMember).filter_by(bot_id=self._bot_id).first()
                owner_id = m.telegram_user_id if m else None
            except Exception:
                owner_id = None
        if not owner_id:
            return {"ok": False, "error": "owner not set; Bot.saveData('__owner_telegram_id', your_id)"}
        return self.sendTo(int(owner_id), text, **kwargs)

    def setOwner(self, telegram_user_id):
        self.saveData("__owner_telegram_id", int(telegram_user_id))
        return {"ok": True}


    # --- TeleBot Studio (TBS) compatibility aliases ---


    def _live_bot(self):
        from backend.telegram.bot_wrapper import BotWrapper
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if not b or not b.token:
            return None
        uid = (self._runtime or {}).get("user_id")
        return BotWrapper(b.token, default_chat_id=uid)

    def sendMessage(self, text=None, chat_id=None, **kwargs):
        if text is not None:
            # MessageObject / dict / list → readable string (never empty for objects)
            if not isinstance(text, (str, int, float, bool)):
                try:
                    import json
                    from backend.sandbox.context_objects import MessageObject, _TBCOptionalStr
                    if isinstance(text, MessageObject):
                        text = str(text)
                    elif isinstance(text, _TBCOptionalStr):
                        text = str(text)  # "None" when missing
                    elif isinstance(text, (dict, list)):
                        text = json.dumps(text, ensure_ascii=False, default=str)
                    else:
                        text = str(text)
                except Exception:
                    text = str(text)
            kwargs["text"] = text if text is not None else "None"
        if chat_id is not None:
            kwargs["chat_id"] = chat_id
        bw = self._live_bot()
        if not bw:
            return {"ok": False, "error": "no bot token"}
        return bw.sendMessage(**kwargs)

    def sendPhoto(self, photo=None, chat_id=None, **kwargs):
        if photo is not None:
            kwargs["photo"] = photo
        if chat_id is not None:
            kwargs["chat_id"] = chat_id
        bw = self._live_bot()
        if not bw:
            return {"ok": False, "error": "no bot token"}
        return bw.sendPhoto(**kwargs)

    def sendLivePhoto(self, video=None, photo=None, chat_id=None, **kwargs):
        """Telegram sendVideo note / live photo style — uses sendVideo if available."""
        bw = self._live_bot()
        if not bw:
            return {"ok": False, "error": "no bot token"}
        if chat_id is not None:
            kwargs["chat_id"] = chat_id
        if video is not None:
            kwargs["video"] = video
            return bw.sendVideo(**kwargs)
        if photo is not None:
            kwargs["photo"] = photo
            return bw.sendPhoto(**kwargs)
        return {"ok": False, "error": "video or photo required"}

    def banUser(self, user_id, reason=""):
        from backend.sandbox.libs.moderation_lib import ModerationLib
        return ModerationLib(self._db, self._bot_id).ban(user_id, reason=reason)

    def bannedUsers(self):
        # scan BotData keys __mod_ban_
        from backend import models
        from backend.sandbox.context_objects import _decode
        rows = self._db.query(models.BotData).filter(
            models.BotData.bot_id == self._bot_id,
            models.BotData.key.like("__mod_ban_%"),
        ).all()
        out = []
        for r in rows:
            uid = r.key.replace("__mod_ban_", "")
            out.append({"user_id": uid, "info": _decode(r.value)})
        return out

    def botStats(self):
        from backend.sandbox.libs.stats_lib import StatsLib
        s = StatsLib(self._db, self._bot_id)
        members = 0
        try:
            members = self._db.query(models.BotMember).filter_by(bot_id=self._bot_id).count()
        except Exception:
            pass
        return {"ok": True, "members": members, "messages": s.get("messages"), "commands": s.get("commands")}

    def botUsage(self):
        return self.botStats()

    def createCaptcha(self, mode="auto", captcha=None):
        return self.genCaptcha(mode=mode, captcha=captcha)

    def sendCaptcha(self, mode="auto", captcha=None, caption="Enter the code:"):
        c = self.genCaptcha(mode=mode, captcha=captcha)
        from backend.telegram.bot_wrapper import BotWrapper
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        uid = (self._runtime or {}).get("user_id")
        if not b or not uid:
            return {"ok": False, "error": "no context", "captcha": c}
        try:
            bw = BotWrapper(b.token, default_chat_id=uid)
            bw.sendPhoto(chat_id=uid, photo=c.captcha_url, caption=caption)
        except Exception as e:
            return {"ok": False, "error": str(e), "captcha": c}
        # store answer for verify
        self.saveData(f"__captcha_{uid}", c.captcha_text)
        return {"ok": True, "captcha": c}

    def verifyCaptcha(self, answer, user_id=None):
        uid = user_id if user_id is not None else (self._runtime or {}).get("user_id")
        expected = self.getData(f"__captcha_{uid}")
        ok = str(answer or "").strip() == str(expected or "").strip()
        if ok:
            self.deleteData(f"__captcha_{uid}")
        return ok

    def uniqueID(self):
        return self.genId()

    def randomID(self):
        return self.genRandomId()

    def errorID(self):
        return self.genRandomErrorId()

    def getInfo(self, bot_id=None, api_key=None):
        return self.info(bot_id=bot_id, api_key=api_key)

    def transfer(self, *a, **k):
        return self.Transfer(*a, **k)

    def encryptAES(self, key, plaintext):
        from backend.sandbox.libs.security_lib import SecurityLib
        return SecurityLib().aes_encrypt(key, plaintext)

    def decryptAES(self, key, token):
        from backend.sandbox.libs.security_lib import SecurityLib
        return SecurityLib().aes_decrypt(key, token)

    def exportAllData(self, output_format="json"):
        return self.getAllData(output_format=output_format)

    def exportUserData(self, user, output_format="json"):
        from backend.sandbox.context_objects import UserObject
        return UserObject(self._db, self._bot_id, int(user)).getAllData(output_format=output_format)

    def broadcastStatus(self, broadcast_id):
        return self.getBroadcastStatus(broadcast_id)

    def cancelBroadcast(self, broadcast_id):
        return self.stopBroadcast(broadcast_id)

    def resetScheduledCommands(self):
        """Cancel all pending scheduled tasks for this bot."""
        from backend.scheduler.scheduler import list_pending_tasks, cancel_task
        tasks = list_pending_tasks(self._db, self._bot_id, limit=500)
        n = 0
        for tsk in tasks:
            r = cancel_task(self._db, tsk.get("id"))
            if r.get("ok"):
                n += 1
        return {"ok": True, "cancelled": n}

    def tokenInfo(self):
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        if not b:
            return {"ok": False}
        tok = b.token or ""
        parts = tok.split(":")
        return {
            "ok": True,
            "bot_id": str(b.public_id or b.id),
            "username": b.username,
            "token_prefix": parts[0] if parts else "",
            "token_masked": (parts[0] + ":***") if parts else "",
        }

    def setWebhookResponse(self, data):
        """TBS alias — sets custom webhook HTTP response body."""
        # stored via runtime result container if present
        rc = (self._runtime or {}).get("result_container")
        if rc is not None:
            rc["result"] = data
            return True
        return False

    def sendCloneBroadcast(self, **kwargs):
        """Broadcast to this bot only (alias of sendBroadcast/broadcast)."""
        kwargs.setdefault("mode", "single")
        return self.broadcast(**kwargs)

    def waitForInput(self, command, options=None, **kwargs):
        return self.handleNextCommand(command, options=options, **kwargs)

    def scheduleCommand(self, command, seconds, options=None, **kwargs):
        return self.runCommandAfter(seconds, command, options=options, **kwargs)

    def run(self, command, options=None, **kwargs):
        return self.runCommand(command, options=options, **kwargs)

    def sendBroadcast(self, **kwargs):
        r = self.broadcast(**kwargs)
        # TBS result shape: ok / broadcast_id / estimated_users (TBC keys kept alongside)
        if isinstance(r, dict):
            good = r.get("status") == "success" or r.get("ok") is True
            r.setdefault("ok", bool(good))
            if good:
                try:
                    from backend import appdb as _adb
                    with _adb.read() as _c:
                        n = _adb.one(_c, "SELECT COUNT(*) n FROM chats WHERE bot_id=? AND is_blocked=0 AND bot_blocked=0", (self._bot_id,))["n"]
                    r.setdefault("estimated_users", n)
                except Exception:
                    r.setdefault("estimated_users", 0)
            else:
                r.setdefault("error", r.get("message"))
        return r

    def storeData(self, name, data, user=None):
        if user is not None:
            from backend.sandbox.context_objects import UserObject
            return UserObject(self._db, self._bot_id, int(user)).saveData(name, data)
        return self.saveData(name, data)

    def fetchData(self, name, user=None):
        if user is not None:
            from backend.sandbox.context_objects import UserObject
            return UserObject(self._db, self._bot_id, int(user)).getData(name)
        return self.getData(name)

    def removeData(self, name, user=None):
        if user is not None:
            from backend.sandbox.context_objects import UserObject
            return UserObject(self._db, self._bot_id, int(user)).deleteData(name)
        return self.deleteData(name)

    def exportData(self, name, user=None, output_format="txt"):
        if user is not None:
            from backend.sandbox.context_objects import UserObject
            return UserObject(self._db, self._bot_id, int(user)).getDataFile(name, output_format=output_format)
        return self.getDataFile(name, output_format=output_format)

    def exportBotUsersFile(self, output_format="csv", include_creation_date=True):
        return self.getBotUsersFile(output_format=output_format, include_creation_date=include_creation_date)

    def getStatus(self, bot_id=None, api_key=None):
        return self.status(bot_id=bot_id, api_key=api_key)

    def cancelScheduledCommand(self, job_id):
        return self.cancelScheduledTask(job_id)

    def updateBroadcastSpeed(self, broadcast_id, speed):
        return self.setBroadcastSpeed(broadcast_id, speed)

    def broadcastProgress(self, broadcast_id):
        return self.getBroadcastProgress(broadcast_id)

    def webhookURL(self, command, user_id=None, **kwargs):
        return self.getIpnUrl(command, user_id=user_id, **kwargs)

    def paymentURL(self, command, user_id=None, **kwargs):
        return self.getIpnUrl(command, user_id=user_id, **kwargs)

    def res(self, resource_name, user=None):
        """TBS Bot.res — resource shortcut via libs.Resources."""
        from backend.sandbox.libs.resources_lib import ResourcesLib
        uid = user if user is not None else (self._runtime or {}).get("user_id")
        lib = ResourcesLib(self._db, self._bot_id, uid)
        return lib.userRes(resource_name, user=uid)

    def __getattr__(self, name):
        """Proxy unknown attrs to the live bot Telegram wrapper when available.

        Many TBC exports call Bot.sendMessage / Bot.editMessageText (capital B).
        """
        if name.startswith("_"):
            raise AttributeError(name)
        runtime = self._runtime or {}
        wrapper = getattr(self, "_tg_bot", None)
        if wrapper is None:
            bot_model = runtime.get("bot")
            if bot_model is not None and getattr(bot_model, "token", None):
                from backend.telegram.bot_wrapper import BotWrapper
                uid = runtime.get("user_id")
                wrapper = BotWrapper(bot_model.token, default_chat_id=uid)
                self._tg_bot = wrapper
        if wrapper is not None:
            return getattr(wrapper, name)
        raise AttributeError(name)


class ApiObject:
    def __init__(self, result_container: dict):
        self._container = result_container
    def setWebhookResult(self, data):
        self._container["result"] = data
        return True

    def setWebhookResponse(self, data):
        return self.setWebhookResult(data)

    def __getattr__(self, name):
        """TBS `Api.sendMessage(...)`: every Telegram Bot API method of the running bot."""
        if name.startswith("_"):
            raise AttributeError(name)
        tg = self.__dict__.get("_tg")
        if tg is None:
            raise AttributeError(name)
        return getattr(tg, name)


class AccountObject:
    def __init__(self, db: Session, account: models.Account):
        self._db = db
        self._account = account
        self.id = account.id
        self.email = account.email
        self.points = account.points

    def bots(self):
        rows = self._db.query(models.Bot).filter_by(owner_id=self.id, deleted_at=None).all()
        return [{"id": b.id, "name": b.name, "username": b.username} for b in rows]

    def info(self):
        a = self._account
        bots = self._db.query(models.Bot).filter_by(owner_id=a.id, deleted_at=None).count()
        return {"email": a.email, "points": a.points, "bots": bots, "id": a.id}

    def get_bots_list(self):
        bots = self._db.query(models.Bot).filter_by(owner_id=self._account.id, deleted_at=None).all()
        return {"ok": True, "result": [
            {"id": str(b.public_id or b.id), "name": b.name, "username": b.username, "running": bool(b.is_running)}
            for b in bots
        ]}

    def get_bot_info(self, botid):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        return {"ok": True, "id": str(b.public_id or b.id), "name": b.name, "username": b.username, "running": bool(b.is_running)}

    def get_bot_status(self, botid):
        info = self.get_bot_info(botid)
        if not info.get("ok"):
            return info
        return {"ok": True, "status": "working" if info["running"] else "stopped"}

    def start_bot(self, botid):
        from backend import platform_hooks
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        return platform_hooks.call("set_running", self._db, b, True)

    def stop_bot(self, botid):
        from backend import platform_hooks
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        return platform_hooks.call("set_running", self._db, b, False)

    def restart_bot(self, botid):
        self.stop_bot(botid)
        return self.start_bot(botid)

    def _owned_bot(self, botid):
        if botid is None: return None
        q = self._db.query(models.Bot).filter_by(owner_id=self._account.id)
        b = q.filter_by(public_id=str(botid)).first()
        if b: return b
        if str(botid).isdigit(): return q.filter_by(id=int(botid)).first()
        return None
    def _account_storage_bot_id(self):
        b = self._db.query(models.Bot).filter_by(owner_id=self._account.id).first()
        return b.id if b else None

    def gen_random_id(self):
        import secrets
        return str(secrets.randbelow(900000000) + 100000000)

    def saveData(self, name, data):
        key = f"__account__{name}"
        row = self._db.query(models.BotData).filter_by(bot_id=self._account_storage_bot_id() or -1, key=key).first()
        # store on a virtual bot_id 0 row scoped by encoding account id in key
        bid = self._account_storage_bot_id()
        if bid is None:
            return {"ok": False, "error": "no bot to store account data"}
        key = f"__account_{self._account.id}__{name}"
        row = self._db.query(models.BotData).filter_by(bot_id=bid, key=key).first()
        val = _encode(data)
        if row:
            row.value = val
        else:
            self._db.add(models.BotData(bot_id=bid, key=key, value=val))
        self._db.commit()
        return {"ok": True}

    def getData(self, name):
        key = f"__account_{self._account.id}__{name}"
        row = self._db.query(models.BotData).filter_by(bot_id=self._account_storage_bot_id() or -1, key=key).first()
        return _decode(row.value) if row else None

    def deleteData(self, name):
        key = f"__account_{self._account.id}__{name}"
        row = self._db.query(models.BotData).filter_by(bot_id=self._account_storage_bot_id() or -1, key=key).first()
        if row:
            self._db.delete(row)
            self._db.commit()
            return True
        return False

    def getAllData(self, name=None, output_format="json"):
        prefix = f"__account_{self._account.id}__"
        rows = self._db.query(models.BotData).filter(models.BotData.bot_id == (self._account_storage_bot_id() or -1), models.BotData.key.like(prefix + "%")).all()
        data = {r.key[len(prefix):]: _decode(r.value) for r in rows}
        if name is not None:
            data = {name: data.get(name)}
        if output_format == "txt":
            return "\n".join(f"{k}={v}" for k, v in data.items())
        return data

    def deleteAllData(self, except_data=None, include_bot_data=False):
        prefix = f"__account_{self._account.id}__"
        rows = self._db.query(models.BotData).filter(models.BotData.bot_id == (self._account_storage_bot_id() or -1), models.BotData.key.like(prefix + "%")).all()
        except_set = set(except_data or [])
        n = 0
        for r in rows:
            short = r.key[len(prefix):]
            if short in except_set:
                continue
            self._db.delete(r)
            n += 1
        self._db.commit()
        return {"ok": True, "deleted": n}


    def getStats(self, time_frames=None, bot_ids=None):
        """Account.getStats — user activity counts per time frame (approx via BotMember last_seen)."""
        import datetime
        time_frames = time_frames or ["24h"]
        bots = self._db.query(models.Bot).filter_by(owner_id=self.id, deleted_at=None).all()
        if bot_ids:
            wanted = {str(x) for x in bot_ids}
            bots = [b for b in bots if str(b.public_id or b.id) in wanted or str(b.id) in wanted]
        now = datetime.datetime.utcnow()
        windows = {}
        for tf in time_frames:
            tf = str(tf).lower().strip()
            hours = 24
            if tf.endswith("h"):
                try: hours = int(tf[:-1])
                except: hours = 24
            elif tf.endswith("d"):
                try: hours = int(tf[:-1]) * 24
                except: hours = 24
            windows[tf] = now - datetime.timedelta(hours=hours)
        out = {}
        for tf, since in windows.items():
            total = 0
            for b in bots:
                total += self._db.query(models.BotMember).filter(
                    models.BotMember.bot_id == b.id,
                    models.BotMember.last_seen >= since,
                ).count()
            out[tf] = total
        return out

    def blockUser(self, user_id, botid=None):
        """Block a Telegram user (account-level list, max 500)."""
        key = "blocked_users"
        row = self._db.query(models.AccountData).filter_by(account_id=self.id, key=key).first() if hasattr(models, 'AccountData') else None
        # store on first bot global as fallback via Account.saveData
        blocked = self.getData(key) or []
        if not isinstance(blocked, list):
            blocked = []
        uid = str(user_id)
        if uid not in blocked:
            if len(blocked) >= 500:
                return {"ok": False, "error": "max 500 blocked users"}
            blocked.append(uid)
            self.saveData(key, blocked)
        return {"ok": True, "blocked": len(blocked)}

    def unblockUser(self, user_id):
        blocked = self.getData("blocked_users") or []
        if not isinstance(blocked, list):
            blocked = []
        uid = str(user_id)
        blocked = [x for x in blocked if str(x) != uid]
        self.saveData("blocked_users", blocked)
        return {"ok": True}

    def getBlockedUsers(self, botid=None):
        blocked = self.getData("blocked_users") or []
        return blocked if isinstance(blocked, list) else []

    def get_blocked_users_count(self, botid=None):
        return self.getBlockedUsersCount(botid)

    def getBlockedUsersCount(self, botid=None):
        """Return the number of account-level blocked users."""
        return len(self.getBlockedUsers(botid))

    def getBlockedUsersFile(self, botid=None, output_format="csv"):
        """Return a BytesIO export of the account-level blocked users."""
        import io, json as _json
        blocked = self.getBlockedUsers(botid)
        if output_format == "json":
            content = _json.dumps({"blocked": blocked}, ensure_ascii=False, indent=2)
            name = "blocked_users.json"
        else:
            content = "user_id\n" + "\n".join(str(x) for x in blocked)
            name = "blocked_users.csv"
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = name
        buf.seek(0)
        return buf

    def create_command(self, botid, command, code):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        trigger = str(command)
        existing = self._db.query(models.Command).filter_by(bot_id=b.id, trigger=trigger).first()
        if existing:
            existing.code = str(code)
        else:
            self._db.add(models.Command(bot_id=b.id, trigger=trigger, code=str(code), trigger_type="command"))
        self._db.commit()
        return {"ok": True, "command": trigger}

    def edit_command(self, botid, command, code):
        return self.create_command(botid, command, code)

    def delete_command(self, botid, command):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        q = self._db.query(models.Command).filter_by(bot_id=b.id, trigger=str(command))
        n = q.delete()
        self._db.commit()
        return {"ok": True, "deleted": n}

    def get_command_list(self, botid):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        rows = self._db.query(models.Command).filter_by(bot_id=b.id).all()
        return {"ok": True, "result": [
            {"command": r.trigger, "code_length": len(r.code or ""), "has_code": bool(r.code)}
            for r in rows
        ]}

    def export_bot(self, botid, format="json", include_bot_data=False):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        cmds = self._db.query(models.Command).filter_by(bot_id=b.id).all()
        payload = {
            "bot": {"name": b.name, "username": b.username, "id": str(b.public_id or b.id)},
            "commands": [{"command": c.trigger, "code": c.code, "trigger_type": getattr(c, "trigger_type", "command")} for c in cmds],
            "export_info": {"format": format},
        }
        if include_bot_data:
            data_rows = self._db.query(models.BotData).filter_by(bot_id=b.id).all() if hasattr(models, 'BotData') else []
            payload["global_data"] = {r.key: r.value for r in data_rows}
        if format == "txt":
            lines = []
            for c in cmds:
                lines.append(f"Command: {c.trigger}\n---\n{c.code or ''}\n---\n")
            return {"ok": True, "result": "\n".join(lines)}
        return {"ok": True, "result": payload}

    def import_commands(self, import_data, botid, format="json"):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        data = import_data
        if isinstance(data, str):
            import json as _json
            data = _json.loads(data)
        cmds = data.get("commands") if isinstance(data, dict) else data
        n = 0
        for c in cmds or []:
            trigger = c.get("command") or c.get("trigger")
            code = c.get("code") or ""
            if not trigger:
                continue
            self.create_command(str(b.public_id or b.id), trigger, code)
            n += 1
        return {"ok": True, "imported": n}

    def parse_import_data(self, import_file, file_format="json"):
        """Parse an exported bot/commands file (str/bytes/dict) into Python data."""
        import json as _json
        data = import_file
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8", "replace")
        if isinstance(data, str):
            if file_format and str(file_format).lower() not in ("json",):
                raise ValueError("only json import files are supported")
            data = _json.loads(data)
        return data

    def delete_bot(self, botid):
        """Soft-delete bot (sets deleted_at)."""
        import datetime
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        b.deleted_at = datetime.datetime.utcnow()
        b.is_running = False
        self._db.commit()
        return {"ok": True}

    def get_deleted_bots(self):
        import datetime
        rows = self._db.query(models.Bot).filter(
            models.Bot.owner_id == self.id,
            models.Bot.deleted_at != None,
        ).all()
        now = datetime.datetime.utcnow()
        out = []
        for b in rows:
            days = 90
            if b.deleted_at:
                days = max(0, 90 - (now - b.deleted_at).days)
            out.append({"id": str(b.public_id or b.id), "name": b.name, "days_remaining": days})
        return out

    def recover_bot(self, botid):
        # include deleted bots
        b = self._db.query(models.Bot).filter(
            (models.Bot.public_id == str(botid)) | (models.Bot.id == int(botid) if str(botid).isdigit() else False),
            models.Bot.owner_id == self.id,
        ).first()
        if not b:
            return {"ok": False, "error": "bot not found"}
        b.deleted_at = None
        self._db.commit()
        return {"ok": True}

    def permanent_delete_bot(self, botid):
        b = self._db.query(models.Bot).filter(
            (models.Bot.public_id == str(botid)) | (models.Bot.id == int(botid) if str(botid).isdigit() else False),
            models.Bot.owner_id == self.id,
        ).first()
        if not b:
            return {"ok": False, "error": "bot not found"}
        self._db.query(models.Command).filter_by(bot_id=b.id).delete()
        self._db.delete(b)
        self._db.commit()
        return {"ok": True}

    def clone_bot(self, botid, new_token=None):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        if not new_token:
            return {"ok": False, "error": "new_token required"}
        exp = self.export_bot(botid, format="json")
        if not exp.get("ok"):
            return exp
        clone = models.Bot(
            owner_id=self.id,
            name=(b.name or "bot") + " (clone)",
            token=str(new_token),
            public_id=str(int(b.public_id or b.id) + 10**9)[:16] if False else None,
            username=None,
        )
        # generate public_id
        import random
        clone.public_id = str(random.randint(10**8, 10**9 - 1))
        self._db.add(clone)
        self._db.commit()
        self._db.refresh(clone)
        self.import_commands(exp["result"], str(clone.public_id))
        return {"ok": True, "id": str(clone.public_id), "name": clone.name}

    def create_bot(self, token, name=None):
        import random
        from backend.telegram.bot_wrapper import BotWrapper
        try:
            me = BotWrapper(token).getMe()
            uname = getattr(me, "username", None) or (me.get("username") if isinstance(me, dict) else None)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        b = models.Bot(
            owner_id=self.id,
            name=name or uname or "bot",
            token=token,
            username=uname,
            public_id=str(random.randint(10**8, 10**9 - 1)),
        )
        self._db.add(b)
        self._db.commit()
        self._db.refresh(b)
        return {"ok": True, "id": str(b.public_id), "username": uname}


    def transfer_data(self, *a, **k):
        return self.TransferData(*a, **k)

    def TransferData(self, from_bot=None, to_bot=None, data_name=None, user_id=None, to_user_id=None):
        """Copy bot/user data between bots or users under this account."""
        src = self._owned_bot(from_bot) if from_bot else None
        dst = self._owned_bot(to_bot) if to_bot else src
        if not src or not dst:
            return {"ok": False, "error": "bot not found"}
        n = 0
        if user_id is not None:
            q = self._db.query(models.UserData).filter_by(bot_id=src.id, telegram_user_id=int(user_id))
            if data_name:
                q = q.filter_by(key=str(data_name))
            target_uid = int(to_user_id) if to_user_id is not None else int(user_id)
            for row in q.all():
                existing = self._db.query(models.UserData).filter_by(
                    bot_id=dst.id, telegram_user_id=target_uid, key=row.key
                ).first()
                if existing:
                    existing.value = row.value
                else:
                    self._db.add(models.UserData(bot_id=dst.id, telegram_user_id=target_uid, key=row.key, value=row.value))
                n += 1
        else:
            q = self._db.query(models.BotData).filter_by(bot_id=src.id)
            if data_name:
                q = q.filter_by(key=str(data_name))
            for row in q.all():
                if str(row.key).startswith("__account_"):
                    continue
                existing = self._db.query(models.BotData).filter_by(bot_id=dst.id, key=row.key).first()
                if existing:
                    existing.value = row.value
                else:
                    self._db.add(models.BotData(bot_id=dst.id, key=row.key, value=row.value))
                n += 1
        self._db.commit()
        return {"ok": True, "transferred": n}

    def import_bot(self, import_data, new_token=None):
        """Create a new bot from export payload."""
        import json as _json, random
        data = import_data
        if isinstance(data, str):
            data = _json.loads(data)
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid import data"}
        if not new_token:
            return {"ok": False, "error": "new_token required"}
        meta = data.get("bot") or {}
        name = meta.get("name") or "imported"
        b = models.Bot(
            owner_id=self._account.id,
            name=name,
            token=str(new_token),
            public_id=str(random.randint(10**8, 10**9 - 1)),
            username=meta.get("username"),
        )
        self._db.add(b)
        self._db.commit()
        self._db.refresh(b)
        self.import_commands(data, str(b.public_id))
        return {"ok": True, "botid": str(b.public_id), "id": str(b.public_id)}

    def getBlockedUsersFile(self, botid=None, output_format="csv"):
        """Return BytesIO file of blocked user ids (TBC contract)."""
        import io, json as _json
        blocked = self.getBlockedUsers(botid)
        if output_format == "json":
            content = _json.dumps({"blocked": blocked}, ensure_ascii=False, indent=2)
            name = "blocked_users.json"
        else:
            content = "user_id\n" + "\n".join(str(x) for x in blocked)
            name = "blocked_users.csv"
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = name
        buf.seek(0)
        return buf


    def getDataFile(self, name, output_format="txt"):
        """Return BytesIO suitable for bot.sendDocument (TBC contract)."""
        import io, json as _json
        val = self.getData(name)
        if val is None:
            raise ValueError(f"data '{name}' not found")
        if output_format == "json":
            content = _json.dumps(val, ensure_ascii=False, indent=2) if not isinstance(val, str) else val
            ext = "json"
        else:
            content = str(val)
            ext = "txt"
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = f"{name}.{ext}"
        buf.seek(0)
        return buf

    def clear_expired_bots(self):
        import datetime
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=90)
        rows = self._db.query(models.Bot).filter(
            models.Bot.owner_id == self._account.id,
            models.Bot.deleted_at != None,
            models.Bot.deleted_at < cutoff,
        ).all()
        n = 0
        for b in rows:
            self._db.query(models.Command).filter_by(bot_id=b.id).delete()
            self._db.delete(b)
            n += 1
        self._db.commit()
        return {"ok": True, "result": f"Cleared {n} expired bots"}

    def get_bot_data(self, botid, name):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        row = self._db.query(models.BotData).filter_by(bot_id=b.id, key=str(name)).first()
        if not row:
            return {"ok": True, "result": None}
        return {"ok": True, "result": _decode(row.value)}

    def set_bot_data(self, botid, name, data):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        row = self._db.query(models.BotData).filter_by(bot_id=b.id, key=str(name)).first()
        val = _encode(data)
        if row:
            row.value = val
        else:
            self._db.add(models.BotData(bot_id=b.id, key=str(name), value=val))
        self._db.commit()
        return {"ok": True}

    def get_bot_usage(self, botid, period="all"):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        members = self._db.query(models.BotMember).filter_by(bot_id=b.id).count() if hasattr(models, "BotMember") else 0
        cmds = self._db.query(models.Command).filter_by(bot_id=b.id).count()
        return {"ok": True, "result": {"users": members, "commands": cmds, "period": period}}

    def get_command_usage(self, botid, command, period="all"):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        row = self._db.query(models.Command).filter_by(bot_id=b.id, trigger=str(command)).first()
        return {"ok": True, "result": {"command": command, "exists": bool(row), "code_length": len(row.code) if row else 0, "period": period}}

    def get_command_info(self, botid, command):
        return self.get_command_usage(botid, command)

    def get_stats(self):
        bots = self._db.query(models.Bot).filter_by(owner_id=self._account.id, deleted_at=None).all()
        deleted = self._db.query(models.Bot).filter(
            models.Bot.owner_id == self._account.id,
            models.Bot.deleted_at != None,
        ).count()
        users = 0
        for b in bots:
            if hasattr(models, "BotMember"):
                users += self._db.query(models.BotMember).filter_by(bot_id=b.id).count()
        return {
            "ok": True,
            "result": {
                "email": self._account.email,
                "points_left": self._account.points,
                "bots": {"total": len(bots), "running": sum(1 for b in bots if b.is_running), "deleted": deleted},
                "users": {"total": users},
            },
        }

    def get_bot_stats(self, botid):
        b = self._owned_bot(botid)
        if not b:
            return {"ok": False, "error": "bot not found"}
        users = self._db.query(models.BotMember).filter_by(bot_id=b.id).count() if hasattr(models, "BotMember") else 0
        cmds = self._db.query(models.Command).filter_by(bot_id=b.id).count()
        return {"ok": True, "result": {"id": str(b.public_id or b.id), "name": b.name, "users": users, "commands": cmds, "running": bool(b.is_running)}}

    def get_bots_stats(self):
        bots = self._db.query(models.Bot).filter_by(owner_id=self._account.id, deleted_at=None).all()
        out = []
        for b in bots:
            st = self.get_bot_stats(str(b.public_id or b.id))
            if st.get("ok"):
                out.append(st["result"])
        return {"ok": True, "result": out}

    def get_deleted_bots_stats(self):
        rows = self.get_deleted_bots()
        return {"ok": True, "result": {"count": len(rows), "bots": rows}}

    def revoke_api(self):
        """TBC: revoke existing API keys and return a newly generated key."""
        import hashlib, secrets
        # revoke/delete old keys
        keys = self._db.query(models.AccountAPIKey).filter_by(account_id=self._account.id).all()
        for k in keys:
            self._db.delete(k)
        # generate new key (same format as dashboard create_api_key)
        raw = "tbc_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        row = models.AccountAPIKey(
            account_id=self._account.id,
            key_hash=digest,
            key_prefix=raw[:12],
            name="default",
        )
        self._db.add(row)
        self._db.commit()
        return {"ok": True, "api_key": raw, "prefix": row.key_prefix,
                "warning": "Store this key securely; it will not be shown again."}



def _deep_attr(val):
    """dicts -> attribute-style dicts, also inside lists: message.photo[-1].file_id, message.entities[0].type"""
    if isinstance(val, dict):
        return _AttrDict(val)
    if isinstance(val, list):
        return [_deep_attr(v) for v in val]
    return val


class MessageObject:
    def __init__(self, raw_message: dict):
        self._raw = raw_message or {}
        self.message_id = self._raw.get("message_id")
        # TBC: missing text/caption behave as None (falsy) but `"x" in message.text` is safe.
        self.text = _TBCOptionalStr(self._raw.get("text"))
        self.caption = _TBCOptionalStr(self._raw.get("caption"))
        self.chat = _AttrDict(self._raw.get("chat", {}) or {})
        _cid = self.chat.get("id")
        if _cid is None:
            _cid = self._raw.get("chat_id")
        try:
            if _cid is None or (isinstance(_cid, str) and not str(_cid).strip()):
                self.chat_id = None
            else:
                self.chat_id = int(_cid)
        except Exception:
            self.chat_id = _cid if _cid not in ("", None) else None
        self.from_user = _AttrDict(self._raw.get("from", {}) or {})
        try:
            if "id" in self.from_user and self.from_user["id"] is not None:
                self.from_user["id"] = int(self.from_user["id"])
        except Exception:
            pass
        # TBC / python-telegram-bot style alias
        self.from_user = self.from_user
        self.date = self._raw.get("date")
        self.photo = _deep_attr(self._raw.get("photo"))
        self.document = _AttrDict(self._raw.get("document", {}) or {}) if self._raw.get("document") else None
        self.voice = _AttrDict(self._raw.get("voice", {}) or {}) if self._raw.get("voice") else None
        self.video = _AttrDict(self._raw.get("video", {}) or {}) if self._raw.get("video") else None
        self.sticker = _AttrDict(self._raw.get("sticker", {}) or {}) if self._raw.get("sticker") else None
        self.location = _AttrDict(self._raw.get("location", {}) or {}) if self._raw.get("location") else None
        self.contact = _AttrDict(self._raw.get("contact", {}) or {}) if self._raw.get("contact") else None
        self.reply_to_message = _AttrDict(self._raw.get("reply_to_message", {}) or {}) if self._raw.get("reply_to_message") else None
        self.forward_from_chat = _AttrDict(self._raw.get("forward_from_chat", {}) or {}) if self._raw.get("forward_from_chat") else None
        self.forward_from = _AttrDict(self._raw.get("forward_from", {}) or {}) if self._raw.get("forward_from") else None
        self.reply_markup = self._raw.get("reply_markup")
        self.data = self._raw.get("_callback_data") or self._raw.get("data")
        self.id = self._raw.get("_callback_query_id") or self._raw.get("id") or self.message_id
        self.raw_update_message = self._raw
        # Extra convenience attributes used in many bots
        self.content_type = self._guess_content_type()
        # TBC: every message object carries update_type (message, pre_checkout_query, ...)
        self.update_type = self._raw.get("update_type") or "message"

    def _guess_content_type(self):
        for k in ("text", "photo", "document", "video", "voice", "audio", "sticker",
                  "animation", "video_note", "contact", "location", "venue", "poll"):
            if self._raw.get(k):
                return k
        return "unknown"

    def raw(self):
        """Underlying Telegram dict (always a real dict). Use for isinstance(..., dict)."""
        return self._raw

    # Dict-like access so message["id"] / message.get("currency") work like TBC
    def get(self, key, default=None):
        if key == "update_type":
            return getattr(self, "update_type", default)
        if key == "id":
            return self.id
        if key in self._raw:
            return self._raw.get(key, default)
        return getattr(self, key, default) if not key.startswith("_") else default

    def __getitem__(self, key):
        if key == "update_type":
            return self.update_type
        if key == "id":
            return self.id
        if key in self._raw:
            return self._raw[key]
        raise KeyError(key)

    def __contains__(self, key):
        if key in ("update_type", "id"):
            return True
        return key in self._raw

    def keys(self):
        ks = set(self._raw.keys()) | {"update_type", "id"}
        return ks

    def items(self):
        for k in self.keys():
            try:
                yield k, self.get(k)
            except Exception:
                pass

    # String helpers so `msg.strip()` works even if msg is MessageObject
    def strip(self, *a, **k):
        return (str(self.text) if self.text is not None else "").strip(*a, **k)

    def split(self, *a, **k):
        return (str(self.text) if self.text is not None else "").split(*a, **k)

    def replace(self, *a, **k):
        return (str(self.text) if self.text is not None else "").replace(*a, **k)

    def startswith(self, *a, **k):
        return (str(self.text) if self.text is not None else "").startswith(*a, **k)

    def endswith(self, *a, **k):
        return (str(self.text) if self.text is not None else "").endswith(*a, **k)

    def lower(self, *a, **k):
        return (str(self.text) if self.text is not None else "").lower(*a, **k)

    def upper(self, *a, **k):
        return (str(self.text) if self.text is not None else "").upper(*a, **k)

    def __str__(self):
        # TBC parity: printing / sending `message` shows the full update payload
        # (so bot.sendMessage(message) never hits "message text is empty" and
        # users can inspect update_type / from_user / etc.). Prefer full dump
        # always — this matches Telebot Creator's observed behaviour.
        try:
            import json
            raw = dict(self._raw or {})
            # Ensure update_type is visible on the printed object
            if "update_type" not in raw and getattr(self, "update_type", None):
                raw["update_type"] = self.update_type
            return json.dumps(raw, ensure_ascii=False, default=str)
        except Exception:
            t = self.text
            if t is None or (hasattr(t, "_v") and t._v is None):
                return "None"
            return str(t)

    def __repr__(self):
        return self.__str__()

    def __int__(self):
        return int(str(self.text).strip())

    def get(self, key, default=None):
        """message.get("contact") — any raw Telegram field; nested objects support attribute access."""
        return _deep_attr(self._raw.get(key, default))

    def __getitem__(self, key):
        return self.get(key)

    def __contains__(self, key):
        return key in self._raw

    def __getattr__(self, item):
        # fallback to raw dict for any missing Telegram field.
        # MUST raise AttributeError for missing keys so hasattr()/getattr() work
        # correctly (otherwise MessageObject is mistaken for an HTTP response
        # because hasattr(obj, "status_code") would return True via a silent None).
        if item.startswith("_"):
            raise AttributeError(item)
        if item not in self._raw:
            raise AttributeError(item)
        return _deep_attr(self._raw.get(item))


class CallbackQueryObject:
    def __init__(self, raw_callback: dict):
        self._raw = raw_callback or {}
        self.id = self._raw.get("id")
        self.data = self._raw.get("data")
        self.from_user = _AttrDict(self._raw.get("from", {}) or {})
        self.message = MessageObject(self._raw.get("message", {}) or {}) if self._raw.get("message") else None
        self.chat_instance = self._raw.get("chat_instance")
        self.inline_message_id = self._raw.get("inline_message_id")
        # aliases used by some bots
        self.from_user = self.from_user
        self.query = self.data

    def __getattr__(self, item):
        if item.startswith("_"):
            raise AttributeError(item)
        val = self._raw.get(item)
        if isinstance(val, dict):
            return _AttrDict(val)
        return val


class ReturnCommand(Exception):
    pass


from backend.sandbox import tbs_compat as _tbs_compat
_tbs_compat.install()
