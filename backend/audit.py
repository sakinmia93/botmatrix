"""Admin action audit trail.

Every mutating call under /api/admin/* (and a short list of other sensitive, non-admin-prefixed
actions such as regenerating the platform API key) is recorded here: who did it, what, on which
target, and when. This is read-only history -- nothing here can be edited or deleted through the
API -- so it keeps a trustworthy record even if an account is later compromised.

Bodies are redacted before storage: anything that looks like a secret (code, password, token,
key, secret) is dropped, and the stored metadata is capped in size, so the audit log itself never
becomes a second place secrets leak from.
"""
import datetime
import json

_REDACT_KEYS = {"password", "currentpassword", "newpassword", "token", "code", "secret",
                "apikey", "api_key", "botToken", "value", "enc"}


def _redact(body):
    if not isinstance(body, dict):
        return {}
    out = {}
    for k, v in body.items():
        if str(k).lower() in _REDACT_KEYS:
            out[k] = "<redacted>"
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v if not isinstance(v, str) or len(v) <= 200 else v[:200] + "…"
        else:
            out[k] = f"<{type(v).__name__}>"
    return out


def log_action(user_id: str, action: str, target_type: str = "", target_id: str = "", body=None, ip: str = ""):
    """Best-effort: a failure here must never break the admin action itself."""
    try:
        from backend import models as em
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            acc = db.query(em.Account).filter_by(email=f"{user_id}@matrix.local").first()
            if not acc:
                acc = em.Account(email=f"{user_id}@matrix.local", hashed_password="!", points=0)
                db.add(acc)
                db.flush()
            meta = _redact(body)
            meta["ip"] = str(ip or "")[:64]
            db.add(em.AuditLog(account_id=acc.id, action=str(action)[:100], target_type=str(target_type)[:50],
                                target_id=str(target_id)[:100], metadata_json=meta))
            db.commit()
        finally:
            db.close()
    except Exception:
        import logging
        logging.getLogger("audit").exception("audit log write failed")


def recent(limit: int = 100):
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        rows = db.query(em.AuditLog).order_by(em.AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)).all()
        accs = {a.id: a.email for a in db.query(em.Account).filter(em.Account.id.in_({r.account_id for r in rows})).all()} if rows else {}
        out = []
        for r in rows:
            email = accs.get(r.account_id, "")
            uid = email.rsplit("@matrix.local", 1)[0] if email.endswith("@matrix.local") else email
            out.append({"id": r.id, "uid": uid, "action": r.action, "targetType": r.target_type or "",
                        "targetId": r.target_id or "", "meta": r.metadata_json or {},
                        "at": r.created_at.isoformat() if r.created_at else ""})
        return out
    finally:
        db.close()
