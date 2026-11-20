"""Small helper module used by the bot runtime (no web framework needed)."""
import hashlib
import secrets

from backend import models


def _api_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _verify_account_key(db, account, raw_key: str) -> bool:
    if not raw_key:
        return False
    row = db.query(models.AccountAPIKey).filter_by(
        account_id=account.id, key_hash=_api_key_hash(raw_key), revoked_at=None
    ).first()
    return row is not None


def _ensure_webhook_secret(db, bot):
    """Return sticky webhook secret. Never rotate an existing value."""
    key = "__webhook_secret"
    row = db.query(models.BotData).filter_by(bot_id=bot.id, key=key).first()
    if row and row.value:
        return row.value
    # Prefer deterministic stable secret so getUrlFor + handle_webhook stay in sync
    try:
        from backend.sandbox.libs.webhook_lib import _stable_secret
        pid = str(getattr(bot, "public_id", None) or bot.id)
        secret = _stable_secret(pid) or secrets.token_urlsafe(32)
    except Exception:
        secret = secrets.token_urlsafe(32)
    if not row:
        db.add(models.BotData(bot_id=bot.id, key=key, value=secret))
    else:
        row.value = secret
    db.commit()
    return secret
