"""libs.Referral — referral codes, tracking, rewards helpers."""
import hashlib
import secrets

class ReferralLib:
    def __init__(self, db=None, bot_id=None, telegram_user_id=None):
        self._db = db
        self._bot_id = bot_id
        self._uid = telegram_user_id

    def _ud(self, uid=None):
        from backend.sandbox.context_objects import UserObject
        return UserObject(self._db, self._bot_id, int(uid if uid is not None else self._uid))

    def code_for(self, user_id=None):
        """Stable short referral code for a user."""
        uid = int(user_id if user_id is not None else self._uid)
        h = hashlib.md5(f"{self._bot_id}:{uid}".encode()).hexdigest()[:8].upper()
        return h

    def link(self, bot_username, user_id=None):
        code = self.code_for(user_id)
        uname = str(bot_username).lstrip("@")
        return f"https://t.me/{uname}?start=ref_{code}"

    def register(self, ref_code, new_user_id=None):
        """Bind new user to referrer by code. Returns referrer user_id or None."""
        new_uid = int(new_user_id if new_user_id is not None else self._uid)
        # find referrer by scanning is expensive; store code->uid map
        from backend import models
        from backend.sandbox.context_objects import _decode, _encode
        key = f"__refcode_{str(ref_code).upper()}"
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        if not row:
            return None
        ref_uid = _decode(row.value)
        if not ref_uid or int(ref_uid) == new_uid:
            return None
        u = self._ud(new_uid)
        if u.getData("referred_by"):
            return None  # already set
        u.saveData("referred_by", int(ref_uid))
        # track list on referrer
        refu = self._ud(ref_uid)
        refs = refu.getData("referrals") or []
        if not isinstance(refs, list):
            refs = []
        if new_uid not in refs:
            refs.append(new_uid)
            refu.saveData("referrals", refs)
            refu.incr("referral_count", 1)
        return int(ref_uid)

    def ensure_code(self, user_id=None):
        """Publish this user's code into global map."""
        from backend import models
        from backend.sandbox.context_objects import _encode
        uid = int(user_id if user_id is not None else self._uid)
        code = self.code_for(uid)
        key = f"__refcode_{code}"
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        if not row:
            self._db.add(models.BotData(bot_id=self._bot_id, key=key, value=_encode(uid)))
            self._db.commit()
        return code

    def count(self, user_id=None):
        u = self._ud(user_id)
        return int(u.getData("referral_count") or 0)

    def list(self, user_id=None):
        u = self._ud(user_id)
        return u.getData("referrals") or []
