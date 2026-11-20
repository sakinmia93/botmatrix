import base64, hashlib, hmac, json, os, secrets as _secrets
import requests


def _stable_secret(public_id: str) -> str:
    """Deterministic webhook secret from platform SECRET_KEY + bot public_id.

    Survives engine bot row re-create (new numeric id) as long as public_id and
    SECRET_KEY stay the same. Random DB secrets alone break broayt lists after
    re-sync/import and cause 403 Invalid webhook link on broadcast.
    """
    from backend.config import SECRET_KEY
    dig = hmac.new(
        (SECRET_KEY or "bm").encode("utf-8"),
        f"bm.webhook.v1:{public_id}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(dig).decode().rstrip("=")


def _normalize_secret(value) -> str:
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        try:
            s2 = json.loads(s)
            if isinstance(s2, str):
                s = s2
        except Exception:
            s = s.strip("\"'")
    return s.strip()


class WebhookLib:
    def __init__(self, db=None, bot_id=None, base_url="http://127.0.0.1:8000"):
        self._db = db
        self._bot_id = bot_id
        self._base_url = (base_url or "http://127.0.0.1:8000").rstrip("/")

    def _bot_row(self, pk=None):
        from backend import models
        pk = int(pk or self._bot_id)
        return self._db.query(models.Bot).filter_by(id=pk).first()

    def _public_id(self, pk=None) -> str:
        b = self._bot_row(pk)
        if b is None:
            return str(pk or self._bot_id)
        return str(b.public_id or b.id)

    def _secret(self, bot_pk=None):
        """Sticky webhook secret: once stored in DB, never rotate it.

        SECRET_KEY can be ephemeral on Railway restarts. Overwriting the DB
        secret with a new stable value invalidates every previously signed
        getUrlFor link (broadcast lists, /onWebhook, etc.). Prefer the
        existing DB value for both signing and verification; only seed with
        stable(pid) when the row is missing.
        """
        from backend import models
        pk = int(bot_pk or self._bot_id)
        row = self._db.query(models.BotData).filter_by(bot_id=pk, key="__webhook_secret").first()
        if row:
            existing = _normalize_secret(row.value)
            if existing:
                return existing
        # Seed once from deterministic stable secret (or random if stable fails)
        pid = self._public_id(pk)
        stable = _stable_secret(pid) or _secrets.token_urlsafe(32)
        if not row:
            self._db.add(models.BotData(bot_id=pk, key="__webhook_secret", value=stable))
        else:
            row.value = stable
        try:
            self._db.commit()
        except Exception:
            try:
                self._db.rollback()
            except Exception:
                pass
        return stable

    def _legacy_secret(self, bot_pk=None) -> str:
        from backend import models
        pk = int(bot_pk or self._bot_id)
        row = self._db.query(models.BotData).filter_by(bot_id=pk, key="__webhook_secret").first()
        return _normalize_secret(row.value) if row else ""

    def _target_bot(self, bot_id, api_key):
        from backend import models
        from backend.routers.bots import _verify_account_key
        me = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
        acct = self._db.query(models.Account).filter_by(id=me.owner_id).first() if me else None
        if not api_key:
            raise ValueError("api_key is required when bot_id is given")
        if not acct or not _verify_account_key(self._db, acct, str(api_key)):
            raise PermissionError("invalid api_key")
        q = self._db.query(models.Bot).filter(models.Bot.owner_id == acct.id, models.Bot.deleted_at.is_(None))
        t = q.filter(models.Bot.public_id == str(bot_id)).first()
        if t is None and str(bot_id).isdigit():
            t = q.filter(models.Bot.id == int(bot_id)).first()
        if t is None:
            raise ValueError("bot not found on this account")
        return t.id

    def getUrlFor(self, command, user_id=None, chat_id=None, bot_id=None, api_key=None, **options):
        """Signed opaque URL that runs `command` when called."""
        pk = self._target_bot(bot_id, api_key) if bot_id else int(self._bot_id)
        pid = self._public_id(pk)

        def _id(v):
            if v is None or isinstance(v, bool):
                return v
            if hasattr(v, "_v"):
                v = v._v
            try:
                return int(v)
            except Exception:
                return v

        user_id = _id(user_id)
        chat_id = _id(chat_id) if chat_id is not None else user_id
        payload = {
            "bot_id": pk,
            "pid": pid,
            "command": str(command),
            "user_id": user_id,
            "chat_id": chat_id,
            "options": options or {},
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode()
        secret = self._secret(pk)
        sig = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(raw + b"." + sig).decode().rstrip("=")
        base = (os.environ.get("BASE_URL") or self._base_url).rstrip("/")
        if "127.0.0.1" in base or "localhost" in base:
            env_base = (
                (os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "")
                or (os.environ.get("RAILWAY_STATIC_URL") or "")
            ).strip()
            if env_base:
                if not env_base.startswith("http"):
                    env_base = "https://" + env_base
                base = env_base.rstrip("/")
        return f"{base}/api/new-webhook?data={token}"

    def genRandomId(self):
        return _secrets.token_urlsafe(24)

    def send(self, url, payload=None, headers=None, method="POST", timeout=15):
        fn = getattr(requests, method.upper().lower(), requests.post)
        r = fn(url, json=payload, headers=headers, timeout=timeout)
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return {"status_code": r.status_code, "ok": r.ok, "body": body}
