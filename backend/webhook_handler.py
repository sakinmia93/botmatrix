"""Webhook endpoint logic (libs.Webhook.getUrlFor)."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs

from backend.errors import ApiError
from backend import security

# Bounded pool so mass broadcast / lakhs of webhook posts cannot exhaust the process.
_WH_WORKERS = 24
_WH_QUEUE_CAP = 10000
_wh_exec = ThreadPoolExecutor(max_workers=_WH_WORKERS, thread_name_prefix="wh")
_wh_inflight = threading.Semaphore(_WH_QUEUE_CAP)


def handle_webhook(x):
    import base64, hashlib, hmac as _hmac
    from backend import runtime, models as em
    from backend.database import SessionLocal
    from backend.sandbox.libs.webhook_lib import _stable_secret, _normalize_secret
    tok = (x.query.get("data") or [""])[0]
    if not tok:
        raise ApiError("Invalid webhook link.", 400)
    try:
        # Accept both standard and urlsafe base64; strip whitespace that browsers sometimes add
        tok = str(tok).strip().replace(" ", "+")
        blob = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4))
        if len(blob) < 34:
            raise ValueError("token too short")
        # Format: raw_json + b"." + 32-byte HMAC
        raw, sig = blob[:-33], blob[-32:]
        if not raw or raw[-1:] == b".":
            # defensive: if separator was included in raw slice, trim
            raw = raw.rstrip(b".")
        payload = json.loads(raw.decode())
        bot_pk = int(payload["bot_id"])
    except Exception:
        raise ApiError("Invalid webhook link.", 400)
    db = SessionLocal()
    try:
        # Resolve engine bot row by numeric id or public_id from payload
        pid = str(payload.get("pid") or "")
        b = db.query(em.Bot).filter_by(id=bot_pk).first()
        if b is None and pid:
            b = db.query(em.Bot).filter_by(public_id=pid).first()
            if b is not None:
                bot_pk = int(b.id)
        if b is not None and not pid:
            pid = str(b.public_id or b.id)

        row = db.query(em.BotData).filter_by(bot_id=bot_pk, key="__webhook_secret").first()
        db_secret = _normalize_secret(row.value) if row else ""

        # Candidates in priority order:
        # 1) sticky DB secret (survives SECRET_KEY rotation / process restart)
        # 2) current stable(pid)  — for links signed before sticky fix
        # 3) stable(bot_pk)       — older links without pid
        candidates = []
        if db_secret:
            candidates.append(db_secret)
        if pid:
            candidates.append(_stable_secret(pid))
        candidates.append(_stable_secret(str(bot_pk)))
        # de-dupe while preserving order
        seen = set()
        uniq = []
        for s in candidates:
            if s and s not in seen:
                seen.add(s)
                uniq.append(s)

        ok = False
        for secret in uniq:
            try:
                dig = _hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
                if len(dig) == len(sig) and _hmac.compare_digest(dig, sig):
                    ok = True
                    # Keep DB in sync with the secret that actually verified
                    # (only write if missing — never rotate an existing working secret)
                    if not db_secret and secret:
                        try:
                            if row:
                                row.value = secret
                            else:
                                db.add(em.BotData(bot_id=bot_pk, key="__webhook_secret", value=secret))
                            db.commit()
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass
                    break
            except Exception:
                continue
        if not ok:
            raise ApiError("Invalid webhook link.", 403)
    finally:
        db.close()
    if security.rate_limit(f"wh:{bot_pk}", 600, 60):
        raise ApiError("Too many requests.", 429)
    body = x.body.get("_raw") or b""
    text = body.decode("utf-8", "replace")
    ctype = (x.h.headers.get("Content-Type") or "").lower()
    parsed = None
    if text.strip():
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    hdrs = {k: v for k, v in x.h.headers.items() if k.lower() not in ("host", "cookie", "authorization", "x-dm-client-ip", "x-forwarded-host")}
    opts = dict(payload.get("options") or {})
    opts.update({"data": text, "json": parsed, "headers": hdrs, "ip": x.h.client_ip(), "method": x.h.command})
    if parsed is None and "application/x-www-form-urlencoded" in ctype:
        opts["form"] = {k: (v[0] if len(v) == 1 else v) for k, v in parse_qs(text).items()}
    qs = {k: (v[0] if len(v) == 1 else v) for k, v in x.query.items() if k != "data"}
    if qs:
        opts["query"] = qs
    uid = payload.get("user_id")
    chat = payload.get("chat_id") or uid
    try:
        uid_i = int(uid) if uid not in (None, "") else 0
        chat_i = int(chat) if chat not in (None, "") else uid_i
    except (TypeError, ValueError):
        uid_i = chat_i = 0
    update = {"message": {"message_id": 0, "date": int(time.time()), "text": str(payload.get("command") or ""),
                          "chat": {"id": chat_i, "type": "private"}, "from": {"id": uid_i, "is_bot": False, "first_name": "webhook"}},
              "_webhook": True, "webhook_payload": parsed if parsed is not None else text}

    # Fire-and-forget by default. Broadcast loops post many webhooks; blocking
    # 20s each caused ReadTimeout on the caller. Pass ?wait=1 to wait up to 15s.
    wait = False
    try:
        w = (x.query.get("wait") or [""])[0]
        wait = str(w).lower() in ("1", "true", "yes")
    except Exception:
        wait = False

    if not _wh_inflight.acquire(blocking=False):
        raise ApiError(
            "Too many webhook deliveries in progress. Retry shortly or use Broadcast Manager.",
            429,
        )

    box = {}

    def _run():
        try:
            box["r"] = runtime.run_external(bot_pk, str(payload.get("command") or ""), update, opts)
        except Exception as e:
            box["r"] = {"ok": False, "error": str(e), "webhook_result": None}
        finally:
            try:
                _wh_inflight.release()
            except Exception:
                pass

    fut = _wh_exec.submit(_run)
    if not wait:
        return {"ok": True, "accepted": True, "async": True}

    try:
        fut.result(timeout=15)
    except Exception:
        return {"ok": True, "accepted": True, "async": True}
    r = box.get("r") or {"ok": False, "error": "no result"}
    res = r.get("webhook_result") if isinstance(r, dict) else None
    if res is None:
        return {"ok": bool(r.get("ok")), **({"error": r.get("error")} if not r.get("ok") else {})}
    if isinstance(res, (bytes, bytearray)):
        return ("raw", "application/octet-stream", bytes(res))
    if isinstance(res, str):
        return ("raw", "text/plain; charset=utf-8", res.encode())
    return res


def install_webhook_route():
    """Rebind server /api/new-webhook to handle_webhook (stable secret verify)."""
    try:
        import backend.server as s
        def _wh(x):
            return handle_webhook(x)
        s._webhook = _wh
        for i, row in enumerate(list(getattr(s, "ROUTES", []) or [])):
            method, rx, fn, auth = row
            pat = getattr(rx, "pattern", "") or ""
            if "new-webhook" in pat:
                s.ROUTES[i] = (method, rx, _wh, auth)
        return True
    except Exception:
        return False
