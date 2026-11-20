"""libs.Resources — counters/balances (user, account, global).

Documented surface (TBC libraries):
  userRes / accountRes / globalRes / anotherRes / adminRes
  add, cut, set, reset, value, getAllData, fetchAllResources,
  fetchAllResourcesOfUser, deleteSingleUserData, deleteAllUsersData,
  clearAllUserOrAccountData

Consistency: every mutating path runs inside a SQLAlchemy transaction and
rolls back automatically on any exception (no partial writes).
"""
from sqlalchemy.orm import Session
from backend import models


def _safe_int(value, default=None):
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


_ACCT = "__acct:"


def _fmt_check(fmt):
    f = str(fmt or "json").lower()
    if f not in ("csv", "json"):
        raise ValueError('output_format must be "csv" or "json"')
    return f


def _as_file(rows, fmt, filename):
    """rows: list of dicts -> BytesIO (csv or json)."""
    import csv as _csv
    import io
    import json as _json
    if fmt == "json":
        data = _json.dumps(rows, indent=2, default=str).encode("utf-8")
    else:
        sio = io.StringIO()
        cols = list(rows[0].keys()) if rows else ["name", "user", "value"]
        w = _csv.DictWriter(sio, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
        data = sio.getvalue().encode("utf-8")
    f = io.BytesIO(data)
    f.name = f"{filename}.{fmt}"
    return f


class ResourceHandle:
    """One named resource. kind: user | another | global | admin | account."""

    def __init__(self, db, bot_id, name, uid=None, kind="user", owner_id=None):
        self._db = db
        self._bot_id = bot_id
        self._name = str(name)
        self._uid = uid
        self._kind = kind
        self._owner = owner_id
        self.name = self._name

    # ---- storage ----
    def _store_name(self, name=None):
        n = str(name if name is not None else self._name)
        return f"{_ACCT}{self._owner}:{n}" if self._kind == "account" else n

    def _q(self, name=None):
        q = self._db.query(models.Resource).filter(models.Resource.name == self._store_name(name))
        if self._kind == "account":
            return q.filter(models.Resource.telegram_user_id == -1)       # shared by every bot of the account
        return q.filter(models.Resource.bot_id == self._bot_id, models.Resource.telegram_user_id == self._uid)

    def _row(self, create=True):
        row = self._q().first()
        if not row and create:
            row = models.Resource(bot_id=self._bot_id, name=self._store_name(),
                                  telegram_user_id=-1 if self._kind == "account" else self._uid, amount=0)
            self._db.add(row)
            self._db.flush()
        return row

    def _commit(self):
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    @staticmethod
    def _num(v):
        if isinstance(v, bool) or v is None:
            raise ValueError("value must be a number")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("value must be a number")
        if f != f or f in (float("inf"), float("-inf")):
            raise ValueError("value must be a finite number")
        return f

    # ---- value methods (every kind) ----
    def value(self):
        row = self._row(create=False)
        return float(row.amount or 0) if row else 0.0

    def get(self):
        return self.value()

    def add(self, value):
        v = self._num(value)
        try:
            r = self._row(create=True)
            r.amount = float(r.amount or 0) + v
            self._commit()
            return float(r.amount)
        except Exception:
            self._db.rollback()
            raise

    def cut(self, value):
        return self.add(-self._num(value))

    def set(self, value):
        v = self._num(value)
        try:
            r = self._row(create=True)
            r.amount = v
            self._commit()
            return float(r.amount)
        except Exception:
            self._db.rollback()
            raise

    def reset(self):
        return self.set(0)

    def clearAllData(self):
        return self.reset()

    # ---- admin-only methods ----
    def _need_admin(self, account_ok=False):
        if self._kind == "admin" or (account_ok and self._kind == "account"):
            return
        raise PermissionError("This method requires libs.Resources.adminRes" + (" or accountRes" if account_ok else "") + ".")

    def _bot_rows(self):
        """Every record of this bot (never the account-level ones)."""
        return self._db.query(models.Resource).filter(models.Resource.bot_id == self._bot_id,
                                                      ~models.Resource.name.like(_ACCT.replace("_", "\\_") + "%", escape="\\"))

    def getAllData(self, length=10):
        """Top entries of this resource sorted by value (descending): [{"user": "<id>", "value": <float>}].

        TBC parity: works on userRes / anotherRes / globalRes / adminRes / accountRes.
        Official TBC examples use libs.Resources.userRes("points").getAllData(5) for leaderboards.
        length may be an int, or any value coercible to int (e.g. Bot.info().userstat).
        """
        # NOTE: do NOT require adminRes — TBC allows getAllData on userRes for leaderboards
        try:
            n = max(0, int(float(length))) if length is not None else 10
        except Exception:
            n = 10
        if self._kind == "account":
            rows = (self._db.query(models.Resource).filter(models.Resource.telegram_user_id == -1,
                    models.Resource.name.like(f"{_ACCT}{self._owner}:%")).order_by(models.Resource.amount.desc()).limit(n).all())
            return [{"name": r.name.split(":", 2)[2], "value": float(r.amount or 0)} for r in rows]
        q = self._bot_rows().filter(models.Resource.name == self._name, models.Resource.telegram_user_id > 0)
        if self._uid is not None and getattr(self, "_scoped", False):
            q = q.filter(models.Resource.telegram_user_id == self._uid)
        rows = q.order_by(models.Resource.amount.desc()).limit(n).all()
        return [{"user": str(r.telegram_user_id), "value": float(r.amount or 0)} for r in rows]

    def fetchAllResources(self, output_format):
        """All resource records of the bot (or of the whole account for accountRes) as a downloadable BytesIO file."""
        self._need_admin(account_ok=True)
        fmt = _fmt_check(output_format)
        if self._kind == "account":
            rows = self._db.query(models.Resource).filter(models.Resource.telegram_user_id == -1,
                    models.Resource.name.like(f"{_ACCT}{self._owner}:%")).all()
            data = [{"name": r.name.split(":", 2)[2], "user": "", "value": float(r.amount or 0)} for r in rows]
        else:
            rows = self._bot_rows().order_by(models.Resource.name, models.Resource.telegram_user_id).all()
            data = [{"name": r.name, "user": str(r.telegram_user_id), "value": float(r.amount or 0)} for r in rows]
        return _as_file(data, fmt, "resources")

    def fetchAllResourcesOfUser(self, user, output_format):
        self._need_admin()
        fmt = _fmt_check(output_format)
        uid = _safe_int(user, default=None)
        rows = self._bot_rows().filter(models.Resource.telegram_user_id == uid).order_by(models.Resource.name).all()
        data = [{"name": r.name, "user": str(uid), "value": float(r.amount or 0)} for r in rows]
        return _as_file(data, fmt, f"resources_{uid}")

    def deleteSingleUserData(self, user, data=None, all_data=False):
        self._need_admin()
        try:
            uid = _safe_int(user, default=None)
            q = self._bot_rows().filter(models.Resource.telegram_user_id == uid)
            if not all_data:
                q = q.filter(models.Resource.name == str(data if data else self._name))
            n = 0
            for r in q.all():
                self._db.delete(r)
                n += 1
            self._commit()
            return {"ok": True, "deleted": n}
        except Exception:
            self._db.rollback()
            raise

    def deleteAllUsersData(self, data=None, all_data=False):
        self._need_admin()
        try:
            q = self._bot_rows().filter(models.Resource.telegram_user_id > 0)
            if not all_data:
                q = q.filter(models.Resource.name == str(data if data else self._name))
            n = 0
            for r in q.all():
                self._db.delete(r)
                n += 1
            self._commit()
            return {"ok": True, "deleted": n}
        except Exception:
            self._db.rollback()
            raise

    def clearAllUserOrAccountData(self, data=None):
        """adminRes: clears every record of the named resource for the bot. accountRes: clears all account-level records."""
        self._need_admin(account_ok=True)
        try:
            if self._kind == "account":
                q = self._db.query(models.Resource).filter(models.Resource.telegram_user_id == -1,
                        models.Resource.name.like(f"{_ACCT}{self._owner}:%"))
            else:
                q = self._bot_rows().filter(models.Resource.name == str(data if data else self._name))
            n = 0
            for r in q.all():
                self._db.delete(r)
                n += 1
            self._commit()
            return {"ok": True, "deleted": n}
        except Exception:
            self._db.rollback()
            raise


class ResourcesLib:
    def __init__(self, db, bot_id, telegram_user_id):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    def _owner_id(self):
        if self._db is None:
            return None
        b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        return b.owner_id if b else None

    def _target(self, bot_id, api_key):
        """Own bot, or another bot of the same account when bot_id + api_key are given (key validated)."""
        if bot_id is None:
            return self._bot_id
        from backend.sandbox.libs.webhook_lib import WebhookLib
        return WebhookLib(db=self._db, bot_id=self._bot_id)._target_bot(bot_id, api_key)

    def _user(self, user):
        return self._uid if user is None else _safe_int(user, default=self._uid)

    def userRes(self, name, user=None, bot_id=None, api_key=None):
        return ResourceHandle(self._db, self._target(bot_id, api_key), name, self._user(user), "user")

    def anotherRes(self, name, user, bot_id=None, api_key=None):
        if user is None:
            raise ValueError("user is required")
        return ResourceHandle(self._db, self._target(bot_id, api_key), name, _safe_int(user), "another")

    def globalRes(self, name, bot_id=None, api_key=None):
        return ResourceHandle(self._db, self._target(bot_id, api_key), name, 0, "global")

    def adminRes(self, name, user=None, bot_id=None, api_key=None):
        h = ResourceHandle(self._db, self._target(bot_id, api_key), name, self._user(user), "admin")
        h._scoped = user is not None
        return h

    def accountRes(self, name):
        return ResourceHandle(self._db, self._bot_id, name, -1, "account", owner_id=self._owner_id())

    # legacy shortcuts
    def get(self, name, user=None):
        return self.userRes(name, user).value()

    def add(self, name, amount, user=None):
        return self.userRes(name, user).add(amount)

    def set(self, name, amount, user=None):
        return self.userRes(name, user).set(amount)

    def leaderboard(self, name, top=10):
        # TBC parity: leaderboard is a top-N of the named resource across all users
        return self.userRes(name).getAllData(top)
