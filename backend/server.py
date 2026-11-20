"""BOT MATRIX API server (stdlib HTTP). Run: python -m backend.server"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import logging
import os
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import backend.config  # noqa: F401  (loads .env first)
from backend import appdb, security, tg
from backend.errors import ApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("server")

MAX_BODY = 2_000_000
COOKIE = "bm_session"

def _check_origin(handler) -> None:
    """Reject cross-site browser calls when Origin is present and does not match our host.

    DevTools/same-origin still work. Pure API clients without Origin are allowed
    (mobile apps / curl) but still need a valid session token.
    """
    origin = (handler.headers.get("Origin") or "").strip()
    if not origin:
        return
    host = (handler.headers.get("Host") or "").split(":")[0].lower()
    base = (os.environ.get("BASE_URL") or "").strip()
    allowed = set()
    if host:
        allowed.add(host)
    if base:
        try:
            from urllib.parse import urlparse
            h = urlparse(base).hostname
            if h:
                allowed.add(h.lower())
        except Exception:
            pass
    # parse origin host
    try:
        from urllib.parse import urlparse
        oh = urlparse(origin).hostname
        if oh and oh.lower() in allowed:
            return
        if oh and oh.lower() in ("localhost", "127.0.0.1") and host in ("localhost", "127.0.0.1"):
            return
    except Exception:
        pass
    raise ApiError("Cross-origin request blocked.", 403)

ROUTES = []  # (method, regex, fn, auth)


def route(method, pattern, auth=True):
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn, auth))
        return fn
    return deco


class Ctx:
    def __init__(self, h, body, query, params, user, sess):
        self.h, self.body, self.query, self.params, self.user, self.sess = h, body, query, params, user, sess
        self.uid = user["id"] if user else None

    def p(self, i=0):
        return self.params[i]


def user_public(u, with_points=True) -> dict:
    d = {"id": u["id"], "email": u["email"], "name": u["name"], "plan": u["plan"] or "Matrix Free",
         "avatar": u["avatar"] or f"/api/avatar/{u['id']}.svg",
         "telegramConnected": bool(u["telegram_connected"]), "telegramUsername": (u["telegram_username"] or "") if u["telegram_connected"] else ""}
    if with_points:
        d["points"] = int(u["points"] or 0)
        try:
            from backend import plans as _pl
            d["isAdmin"] = (u["email"] or "").lower() in _pl.admins()
        except Exception:
            d["isAdmin"] = False
    return d


# ====================================================================== WEBHOOKS (libs.Webhook.getUrlFor)
def _webhook(x: Ctx):
    import base64, hashlib, hmac as _hmac
    from backend import runtime, models as em
    from backend.database import SessionLocal
    tok = (x.query.get("data") or [""])[0]
    try:
        blob = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4))
        raw, sig = blob[:-33], blob[-32:]
        payload = json.loads(raw.decode())
        bot_pk = int(payload["bot_id"])
    except Exception:
        raise ApiError("Invalid webhook link.", 400)
    db = SessionLocal()
    try:
        row = db.query(em.BotData).filter_by(bot_id=bot_pk, key="__webhook_secret").first()
        secret = row.value if row else None
    finally:
        db.close()
    if not secret or not _hmac.compare_digest(_hmac.new(secret.encode(), raw, hashlib.sha256).digest(), sig):
        raise ApiError("Invalid webhook link.", 403)
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
    r = runtime.run_external(bot_pk, str(payload.get("command") or ""), update, opts)
    res = r.get("webhook_result")
    if res is None:
        return {"ok": bool(r.get("ok")), **({"error": r.get("error")} if not r.get("ok") else {})}
    if isinstance(res, (bytes, bytearray)):
        return ("raw", "application/octet-stream", bytes(res))
    if isinstance(res, str):
        return ("raw", "text/plain; charset=utf-8", res.encode())
    return res


for _m in ("GET", "POST", "PUT", "PATCH", "DELETE"):
    route(_m, "/api/new-webhook", auth=False)(_webhook)


# ====================================================================== TON CONNECT (libs.TonLib)
_TC_STYLE = ("<meta name='viewport' content='width=device-width,initial-scale=1'><style>body{font-family:system-ui,sans-serif;background:#0f1115;color:#e8e8ea;"
             "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}main{max-width:420px;padding:24px;text-align:center}"
             "h1{font-size:20px}p{color:#9aa0a6;line-height:1.5}#st{margin-top:16px;font-weight:600}</style>")


def _tc_load(db, em, key):
    row = db.query(em.BotData).filter(em.BotData.key == key).first()
    return row, (json.loads(row.value) if row else None)


def _tc_page(kind, ident):
    base_js = "https://unpkg.com/@tonconnect/ui@2.0.9/dist/tonconnect-ui.min.js"
    title = "Connect your TON wallet" if kind == "session" else "Confirm in your wallet"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>{_TC_STYLE}
<script src='{base_js}'></script></head><body><main><h1>{title}</h1><p id='p'>Use the button below.</p><div id='btn'></div><div id='st'></div></main>
<script>
const KIND='{kind}', ID={json.dumps(ident)}, API=location.origin+'/api/ton-connect/';
const st=t=>document.getElementById('st').textContent=t;
const ui=new TON_CONNECT_UI.TonConnectUI({{manifestUrl:location.origin+'/api/ton-connect/manifest.json',buttonRootId:'btn'}});
fetch(API+KIND+'/'+ID+'/info').then(r=>r.json()).then(info=>{{
  if(info.error){{st(info.error);return}}
  ui.setConnectRequestParameters({{state:'ready',value:{{tonProof:info.challenge}}}});
  ui.onStatusChange(async w=>{{
    if(!w)return;
    const proof=w.connectItems&&w.connectItems.tonProof&&w.connectItems.tonProof.proof;
    const r=await fetch(API+KIND+'/'+ID+'/connected',{{method:'POST',headers:{{'content-type':'application/json'}},
      body:JSON.stringify({{address:w.account.address,publicKey:w.account.publicKey,stateInit:w.account.walletStateInit,proof:proof,domain:location.host}})}}).then(r=>r.json());
    if(r.error){{st(r.error);return}}
    if(KIND==='session'){{st('Wallet connected. You can return to Telegram.');return}}
    try{{
      const b=await fetch(API+'request/'+ID+'/build?wallet='+encodeURIComponent(w.account.address)).then(r=>r.json());
      if(b.error){{st(b.error);return}}
      const res=await ui.sendTransaction(b.payload);
      await fetch(API+'request/'+ID+'/result',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{status:'sent',boc:res.boc,wallet:w.account.address}})}});
      st('Sent. You can return to Telegram.');
      if(info.return_url)setTimeout(()=>location.href=info.return_url,1200);
    }}catch(e){{
      await fetch(API+'request/'+ID+'/result',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{status:'rejected',wallet:w.account.address}})}});
      st('Cancelled.');
    }}
  }});
}});
</script></body></html>""".encode()


def _tc_row(kind, ident):
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    pre = "__tonc:" if kind == "session" else "__tonr:"
    row, rec = _tc_load(db, em, pre + ident)
    return db, em, row, rec


@route("GET", "/api/ton-connect/manifest.json", auth=False)
def _tc_manifest(x: Ctx):
    host = x.h.headers.get("X-Forwarded-Host") or x.h.headers.get("Host") or "localhost"
    proto = x.h.headers.get("X-Forwarded-Proto") or ("http" if host.startswith(("localhost", "127.")) else "https")
    return ("raw", "application/json", json.dumps({"url": f"{proto}://{host}", "name": "BOT MATRIX",
            "iconUrl": f"{proto}://{host}/favicon.ico"}).encode(), {"Access-Control-Allow-Origin": "*"})


@route("GET", r"/api/ton-connect/(session|request)/([A-Za-z0-9_\-]{10,64})", auth=False)
def _tc_view(x: Ctx):
    kind, ident = x.p(0), x.p(1)
    db, em, row, rec = _tc_row(kind, ident)
    db.close()
    if not rec:
        return ("raw", "text/html; charset=utf-8", b"<h3>Link not found or expired.</h3>")
    return ("raw", "text/html; charset=utf-8", _tc_page(kind, ident),
            {"Content-Security-Policy": "default-src 'self' https: data: blob:; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline' https:; connect-src *; frame-ancestors 'none'",
             "Cache-Control": "no-store"})


@route("GET", r"/api/ton-connect/(session|request)/([A-Za-z0-9_\-]{10,64})/info", auth=False)
def _tc_info(x: Ctx):
    kind, ident = x.p(0), x.p(1)
    db, em, row, rec = _tc_row(kind, ident)
    db.close()
    if not rec:
        raise ApiError("Link not found or expired.", 404)
    if kind == "session" and rec["expires"] < time.time():
        raise ApiError("This session has expired.", 410)
    if kind == "request" and rec.get("status") != "pending":
        raise ApiError("This request is already completed.", 410)
    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url", "")}


def _tc_verify_proof(rec_challenge, body):
    """TON Connect ton_proof verification (ed25519 over the spec'd message; the public key must belong to the address)."""
    import hashlib, struct
    from nacl.signing import VerifyKey
    from tonsdk.utils import Address
    from tonsdk.boc import Cell
    proof = body.get("proof") or {}
    pub = bytes.fromhex(str(body.get("publicKey") or ""))
    addr = Address(str(body.get("address")))
    si = base64.b64decode(str(body.get("stateInit") or ""))
    if hashlib.sha256 and bytes(Cell.one_from_boc(si).bytes_hash()) != bytes(addr.hash_part):
        raise ValueError("wallet state does not match the address")
    dom = proof.get("domain") or {}
    domain = str(dom.get("value") or "").encode()
    ts = int(proof.get("timestamp"))
    if abs(time.time() - ts) > 900:
        raise ValueError("proof expired")
    if str(proof.get("payload")) != str(rec_challenge):
        raise ValueError("wrong challenge")
    msg = (b"ton-proof-item-v2/" + struct.pack("<i", addr.wc) + bytes(addr.hash_part) + struct.pack("<I", len(domain)) + domain
           + struct.pack("<Q", ts) + str(proof.get("payload")).encode())
    full = b"\xff\xff" + b"ton-connect" + hashlib.sha256(msg).digest()
    VerifyKey(pub).verify(hashlib.sha256(full).digest(), base64.b64decode(str(proof.get("signature"))))
    return addr.to_string(True, True, True)


@route("POST", r"/api/ton-connect/(session|request)/([A-Za-z0-9_\-]{10,64})/connected", auth=False)
def _tc_connected(x: Ctx):
    import base64 as _b
    kind, ident = x.p(0), x.p(1)
    db, em, row, rec = _tc_row(kind, ident)
    try:
        if not rec:
            raise ApiError("Link not found or expired.", 404)
        if security.rate_limit(f"tonc:{x.h.client_ip()}", 60, 60):
            raise ApiError("Too many requests.", 429)
        try:
            addr = _tc_verify_proof(rec.get("challenge") or ident, x.body)
        except Exception:
            raise ApiError("Wallet ownership could not be verified. Please reconnect.", 400)
        if kind == "session":
            if rec["expires"] < time.time():
                raise ApiError("This session has expired.", 410)
            rec["wallet_address"] = addr
            rec["public_key"] = str((x.body or {}).get("publicKey") or "")[:64]
        else:
            if rec.get("status") != "pending":
                raise ApiError("This request is already completed.", 410)
            rec["wallet"] = addr
        row.value = json.dumps(rec)
        db.commit()
        return {"ok": True, "address": addr}
    finally:
        db.close()


@route("GET", r"/api/ton-connect/(request)/([A-Za-z0-9_\-]{10,64})/build", auth=False)
def _tc_build(x: Ctx):
    from tonsdk.utils import Address
    from tonsdk.boc import begin_cell
    import requests as _rq
    db, em, row, rec = _tc_row("request", x.p(1))
    db.close()
    if not rec or rec.get("status") != "pending":
        raise ApiError("Link not found or expired.", 404)
    wallet = (x.query.get("wallet") or [""])[0]
    if not rec.get("wallet") or Address(wallet).to_string(True, True, True) != rec["wallet"]:
        raise ApiError("Connect your wallet first.", 403)
    pl = dict(rec["payload"])
    pl["validUntil"] = int(time.time()) + 600
    j = rec.get("jetton")
    if j:
        base = "https://toncenter.com/api/v3"
        d = _rq.get(base + "/jetton/wallets", params={"owner_address": rec["wallet"], "jetton_address": j["master"], "limit": 1}, timeout=20).json()
        w = (d.get("jetton_wallets") or [None])[0]
        if not w:
            raise ApiError("Your wallet holds none of this jetton.", 400)
        m = _rq.get(base + "/jetton/masters", params={"address": j["master"], "limit": 1}, timeout=20).json()
        info = ((m.get("metadata") or {}).get((m.get("jetton_masters") or [{}])[0].get("address")) or {}).get("token_info") or [{}]
        dec = int((info[0].get("extra") or {}).get("decimals") or 9)
        units = int(round(float(j["amount"]) * 10 ** dec))
        b = begin_cell().store_uint(0xf8a7ea5, 32).store_uint(0, 64).store_coins(units).store_address(Address(j["to"])).store_address(Address(rec["wallet"])).store_uint(0, 1)
        if j.get("comment"):
            b.store_coins(1).store_uint(1, 1).store_ref(begin_cell().store_uint(0, 32).store_string(str(j["comment"])).end_cell())
        else:
            b.store_coins(0).store_uint(0, 1)
        pl["messages"] = [{"address": w["address"], "amount": "60000000", "payload": base64.b64encode(b.end_cell().to_boc(False)).decode()}]
    return {"payload": pl}


@route("POST", r"/api/ton-connect/(request)/([A-Za-z0-9_\-]{10,64})/result", auth=False)
def _tc_result(x: Ctx):
    db, em, row, rec = _tc_row("request", x.p(1))
    try:
        if not rec or rec.get("status") != "pending" or not rec.get("wallet"):
            raise ApiError("Link not found or expired.", 404)
        st = "sent" if x.body.get("status") == "sent" and x.body.get("boc") else "rejected"
        rec["status"], rec["boc"] = st, str(x.body.get("boc") or "")[:20000]
        row.value = json.dumps(rec)
        db.commit()
        cb = rec.get("callback_url") or ""
    finally:
        db.close()
    if cb:
        def _fire():
            try:
                import requests as _rq
                from backend.sandbox.libs.http_lib import _check_url
                _rq.post(_check_url(cb), json={"request_id": x.p(1), "status": st, "boc": rec["boc"], "wallet_address": rec["wallet"]}, timeout=10, allow_redirects=False)
            except Exception:
                log.warning("ton-connect callback failed")
        threading.Thread(target=_fire, daemon=True).start()
    return {"ok": True, "status": st}


# ====================================================================== AUTH
def _issue(handler, user_row, remember, meta) -> str:
    tok = security.new_session_token()
    ua = (handler.headers.get("User-Agent") or "")[:200]
    days = 30 if remember else 1
    with appdb.db() as c:
        c.execute("INSERT INTO sessions (token,token_hash,user_id,email,client_metadata,ip,user_agent,remember_me,is_active,created_at,expires_at)"
                  " VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                  (security.token_hash(tok)[:16], security.token_hash(tok), user_row["id"], user_row["email"],
                   json.dumps(meta if isinstance(meta, dict) else {})[:2000], handler.client_ip(), ua, 1 if remember else 0,
                   appdb.now_iso(), appdb.iso_in(days=days)))
    try:
        handler.cookie_max_age = days * 86400
    except Exception:
        pass
    try:
        from backend import security_center
        security_center.note_login(user_row["id"], handler.client_ip(), ua)
    except Exception:
        pass
    return tok


_otp_fails: dict = {}


def _turnstile_on() -> bool:
    return security.env_flag("TURNSTILE_ENABLED", False)


def _captcha(x: Ctx) -> None:
    """Cloudflare Turnstile: when TURNSTILE_ENABLED=1 the browser's token is verified with Cloudflare on the server."""
    if not _turnstile_on():
        return
    secret = os.environ.get("TURNSTILE_SECRET_KEY", "")
    if not secret:
        raise ApiError("Human verification is switched on but TURNSTILE_SECRET_KEY is not set on the server.", 503)
    token = security.clean_text(x.body.get("captchaToken"), 4096)
    if not token:
        raise ApiError("Please complete the human verification.", 400)
    import urllib.request
    data = json.dumps({"secret": secret, "response": token, "remoteip": x.h.client_ip()}).encode()
    url = os.environ.get("TURNSTILE_VERIFY_URL", "https://challenges.cloudflare.com/turnstile/v0/siteverify")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"}), timeout=8) as r:
            res = json.loads(r.read().decode() or "{}")
    except Exception:
        raise ApiError("Human verification could not be checked right now. Please try again.", 503)
    if not res.get("success"):
        raise ApiError("Human verification failed. Please try again.", 400)


@route("GET", "/api/config", auth=False)
def public_config(x: Ctx):
    return {"turnstile": {"enabled": _turnstile_on(), "siteKey": os.environ.get("TURNSTILE_SITE_KEY", "") if _turnstile_on() else ""},
            "otpRequired": _otp_required()}


def _otp_required() -> bool:
    return security.env_flag("REQUIRE_EMAIL_OTP", True)


def _otp_send(okey: str, email: str, subject: str, intro: str, minutes: int = 10):
    """Create + e-mail a fresh one-time code (stored hashed). Raises ApiError when it cannot be delivered."""
    if not _mail_configured():
        raise ApiError("Email sending is not set up on this server yet, so codes cannot be sent (set SMTP_HOST / SMTP_USER / SMTP_PASSWORD in .env). Sign-up and sign-in work without codes when REQUIRE_EMAIL_OTP=0; only password reset needs email.", 503)
    if security.rate_limit(f"otp:{okey}", 5, 3600):
        raise ApiError("Too many codes requested. Try again later.", 429)
    code = security.new_code(6)
    with appdb.db() as c:
        c.execute("UPDATE email_otps SET is_used=1 WHERE email=?", (okey,))
        c.execute("INSERT INTO email_otps (id,email,code,expires_at,is_used,created_at) VALUES (?,?,?,?,0,?)",
                  (appdb.new_id("otp_", 6), okey, security.token_hash(code), appdb.iso_in(minutes=minutes), appdb.now_iso()))
    if not _send_mail(email, subject, f"{intro}\n\nYour code: {code}\nIt expires in {minutes} minutes. If this wasn't you, ignore this email."):
        raise ApiError("We could not send the verification email. Please try again in a moment.", 503)


def _otp_check(okey: str, code: str):
    with appdb.db() as c:
        o = appdb.one(c, "SELECT * FROM email_otps WHERE email=? AND is_used=0 ORDER BY created_at DESC LIMIT 1", (okey,))
        if not code or not o or o["expires_at"] < appdb.now_iso() or o["code"] != security.token_hash(code):
            # a code can only be guessed a few times (stops brute-forcing 6 digits); then a new one must be requested
            if o:
                n = _otp_fails.get(o["id"], 0) + 1
                _otp_fails[o["id"]] = n
                if n >= 5:
                    c.execute("UPDATE email_otps SET is_used=1 WHERE id=?", (o["id"],))
                    _otp_fails.pop(o["id"], None)
                    raise ApiError("Too many wrong codes. Request a new code.", 400)
            raise ApiError("That code is wrong or has expired.", 400)
        c.execute("UPDATE email_otps SET is_used=1 WHERE id=?", (o["id"],))


@route("POST", "/api/auth/register", auth=False)
def register(x: Ctx):
    ip = x.h.client_ip()
    if security.rate_limit(f"reg:{ip}", 6, 3600):
        raise ApiError("Too many sign-ups from this network. Try again later.", 429)
    email = security.clean_text(x.body.get("email"), 200).lower()
    pw = x.body.get("password") or ""
    name = security.clean_text(x.body.get("name"), 60) or email.split("@")[0]
    if not security.valid_email(email):
        raise ApiError("Enter a valid email address.", 400)
    err = security.valid_password(pw)
    if err:
        raise ApiError(err, 400)
    with appdb.read() as c:
        if appdb.one(c, "SELECT id FROM users WHERE email=?", (email,)):
            raise ApiError("An account with this email already exists. Sign in instead.", 409)
    code = security.clean_text(x.body.get("code"), 12)
    if not code or not _otp_required():
        _captcha(x)
    if _otp_required():
        if not code:
            _otp_send("reg:" + email, email, "Your BOT MATRIX verification code", "Welcome to BOT MATRIX! Confirm your email to finish creating your account.")
            return {"success": True, "otpRequired": True, "email": email}
        _otp_check("reg:" + email, code)
    uid = appdb.new_id("u_", 8)
    with appdb.db() as c:
        if appdb.one(c, "SELECT id FROM users WHERE email=?", (email,)):
            raise ApiError("An account with this email already exists. Sign in instead.", 409)
        c.execute("INSERT INTO users (id,email,password_hash,name,plan,is_email_verified,created_at,updated_at,points,telegram_connected) VALUES (?,?,?,?, 'Matrix Free',1,?,?,?,0)",
                  (uid, email, security.hash_password(pw), name, appdb.now_iso(), appdb.now_iso(), int(os.environ.get("DEFAULT_POINTS") or appdb.DEFAULT_POINTS)))
        u = appdb.one(c, "SELECT * FROM users WHERE id=?", (uid,))
    tok = _issue(x.h, u, True, x.body.get("client_metadata"))
    x.h.set_cookie = tok
    return {"success": True, "token": tok, "user": user_public(u)}


@route("POST", "/api/auth/login", auth=False)
def login(x: Ctx):
    email = security.clean_text(x.body.get("email"), 200).lower()
    pw = x.body.get("password") or ""
    code = security.clean_text(x.body.get("code"), 12)
    if not code or not _otp_required():
        _captcha(x)
    key = f"login:{x.h.client_ip()}:{email}"
    wait = security.rate_limit(key, 8, 300)
    if wait:
        raise ApiError("Too many attempts. Please wait a few minutes and try again.", 429, {"retryAfter": int(wait)})
    with appdb.read() as c:
        u = appdb.one(c, "SELECT * FROM users WHERE email=?", (email,))
    if not u:
        security.dummy_verify(pw)
        raise ApiError("Incorrect email or password.", 401)
    if not security.verify_password(pw, u["password_hash"]):
        raise ApiError("Incorrect email or password.", 401)
    if u["suspended"]:
        raise ApiError("This account is suspended" + (": " + u["suspended_reason"] if u["suspended_reason"] else ".") + " Contact the administrator.", 403)
    if _otp_required():
        if not code:
            _otp_send("login:" + email, email, "Your BOT MATRIX sign-in code", "Someone (hopefully you) is signing in to BOT MATRIX.", 10)
            return {"success": True, "otpRequired": True, "email": email}
        _otp_check("login:" + email, code)
    security.clear_limit(key)
    if security.needs_rehash(u["password_hash"]):
        with appdb.db() as c:
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(pw), u["id"]))
    remember = bool(x.body.get("remember_me"))
    tok = _issue(x.h, u, remember, x.body.get("client_metadata"))
    try:
        ua = (x.h.headers.get("User-Agent") or "unknown device")[:80]
        appdb.notify(u["id"], "New login to your account", f"Signed in from {x.h.client_ip()} · {ua}. If this wasn't you, change your password and sign out other sessions.", "warning", "tab:Settings#security")
    except Exception:
        pass
    x.h.set_cookie = tok
    try:
        os_, br, _k = _device(x.h.headers.get("User-Agent") or "")
        from backend import connect_bot
        threading.Thread(target=connect_bot.alert, args=(u["id"], "securityAlerts",
                         f"🔐 New sign-in to your account\n{br} on {os_}\nIP: {x.h.client_ip()}\nNot you? Change your password in Settings."),
                         daemon=True).start()
    except Exception:
        pass
    return {"success": True, "token": tok, "user": user_public(u), "remember_me": remember}


@route("POST", "/api/auth/logout", auth=False)
def logout(x: Ctx):
    tok = x.h.session_token()
    if tok:
        with appdb.db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (security.token_hash(tok),))
    x.h.clear_cookie = True
    return {"success": True}


@route("GET", "/api/auth/me")
def me(x: Ctx):
    return {"success": True, "user": user_public(x.user), "remember_me": bool(x.sess["remember_me"])}


@route("POST", "/api/auth/forgot-password", auth=False)
def forgot(x: Ctx):
    email = security.clean_text(x.body.get("email"), 200).lower()
    if security.rate_limit(f"fp:{x.h.client_ip()}", 6, 3600) or security.rate_limit(f"fpe:{email}", 4, 3600):
        raise ApiError("Too many requests. Try again later.", 429)
    if not security.valid_email(email):
        raise ApiError("Enter a valid email address.", 400)
    _captcha(x)
    with appdb.read() as c:
        u = appdb.one(c, "SELECT id FROM users WHERE email=?", (email,))
    if u:
        _otp_send("fp:" + email, email, "Your BOT MATRIX password reset code", "We received a request to reset your BOT MATRIX password.", 15)
    elif not _mail_configured():
        raise ApiError("Email sending is not set up on this server yet, so a reset code cannot be sent. Set SMTP_HOST / SMTP_USER / SMTP_PASSWORD in .env.", 503)
    return {"success": True, "message": "If this email has an account, a 6-digit reset code has been sent to it.", "email": email, "delivery": "email"}


def _mail_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def _send_mail(to, subject, body) -> bool:
    """Real e-mail through SMTP (Gmail: smtp.gmail.com + an app password)."""
    if not _mail_configured():
        return False
    try:
        import smtplib
        from email.message import EmailMessage
        m = EmailMessage()
        m["From"] = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
        m["To"], m["Subject"] = to, subject
        m.set_content(body)
        host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                s.send_message(m)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if os.environ.get("SMTP_STARTTLS", "1") != "0":
                    s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                s.send_message(m)
        return True
    except Exception:
        logging.getLogger("mail").exception("send mail")
        return False


@route("POST", "/api/auth/reset-password", auth=False)
def reset_pw(x: Ctx):
    email = security.clean_text(x.body.get("email"), 200).lower()
    code = security.clean_text(x.body.get("code"), 12)
    new = x.body.get("new_password") or ""
    if security.rate_limit(f"rp:{email}", 8, 3600):
        raise ApiError("Too many attempts. Try again later.", 429)
    err = security.valid_password(new)
    if err:
        raise ApiError(err, 400)
    _otp_check("fp:" + email, code)
    with appdb.db() as c:
        u = appdb.one(c, "SELECT id FROM users WHERE email=?", (email,))
        if not u:
            raise ApiError("That code is wrong or has expired.", 400)
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(new), u["id"]))
        c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
    return {"success": True, "message": "Password updated. You can sign in now."}


@route("POST", "/api/auth/change-password")
def change_pw(x: Ctx):
    cur, new = x.body.get("currentPassword") or "", x.body.get("newPassword") or ""
    if security.rate_limit(f"cp:{x.uid}", 8, 600):
        raise ApiError("Too many attempts. Try again later.", 429)
    if not security.verify_password(cur, x.user["password_hash"]):
        raise ApiError("Your current password is incorrect.", 400)
    err = security.valid_password(new)
    if err:
        raise ApiError(err, 400)
    keep = security.token_hash(x.h.session_token() or "")
    with appdb.db() as c:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(new), x.uid))
        c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (x.uid, keep))
    return {"success": True}


@route("POST", "/api/account/delete")
def delete_account(x: Ctx):
    if not security.verify_password(x.body.get("password") or "", x.user["password_hash"]):
        raise ApiError("Password is incorrect.", 400)
    from backend import runtime
    with appdb.read() as c:
        ids = [r["id"] for r in appdb.rows(c, "SELECT id FROM bots WHERE user_id=?", (x.uid,))]
    for i in ids:
        runtime.stop_worker(i)
        runtime.drop_engine_bot(i)
    with appdb.db() as c:
        for i in ids:
            c.execute("DELETE FROM chats WHERE bot_id=?", (i,))
        for t in ("bots", "folders", "global_admins", "broadcasts", "notifications", "settings", "recycle_bin", "sessions", "support_tickets", "connect_links"):
            c.execute(f"DELETE FROM {t} WHERE user_id=?", (x.uid,))
        c.execute("DELETE FROM store_bots WHERE owner_id=?", (x.uid,))
        c.execute("DELETE FROM transfers WHERE from_user_id=? OR to_user_id=?", (x.uid, x.uid))
        c.execute("DELETE FROM users WHERE id=?", (x.uid,))
    x.h.clear_cookie = True
    return {"success": True}


# ====================================================================== USER
@route("GET", "/api/user/points")
def points(x: Ctx):
    p = appdb.get_points(x.uid)
    sp = appdb.split_points(x.uid)
    return {"points": p, "planPoints": sp["plan"], "extraPoints": sp["extra"], "plan": x.user["plan"] or "Free", "allBotsStopped": p <= 0}


@route("GET", "/api/settings/broadcast-limit")
def bl_get(x: Ctx):
    from backend import broadcast_service as bs
    return {"minBroadcastUsers": bs.min_users(x.uid)}


@route("POST", "/api/settings/broadcast-limit")
def bl_set(x: Ctx):
    try:
        v = max(1, min(100000, int(x.body.get("minBroadcastUsers"))))
    except Exception:
        raise ApiError("Enter a number.", 400)
    st = _load_settings(x.uid) or {}
    st["minBroadcastUsers"] = v
    _save_settings(x.uid, st)
    return {"success": True, "minBroadcastUsers": v}


def _load_settings(uid):
    with appdb.read() as c:
        r = appdb.one(c, "SELECT settings_json FROM settings WHERE user_id=?", (uid,))
    return appdb.jload(r["settings_json"], None) if r else None


def _save_settings(uid, st):
    with appdb.db() as c:
        c.execute("INSERT INTO settings (user_id,settings_json,updated_at) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=excluded.updated_at",
                  (uid, json.dumps(st), appdb.now_iso()))


def _device(ua: str):
    u = ua.lower()
    os_ = "Windows" if "windows" in u else "Android" if "android" in u else "iOS" if ("iphone" in u or "ipad" in u) else "macOS" if "mac os" in u else "Linux" if "linux" in u else "Unknown"
    br = "Edge" if "edg/" in u else "Chrome" if "chrome" in u else "Firefox" if "firefox" in u else "Safari" if "safari" in u else "Browser"
    kind = "mobile" if os_ in ("Android", "iOS") else "desktop"
    return os_, br, kind


@route("GET", "/api/settings")
def settings_get(x: Ctx):
    st = _load_settings(x.uid)
    cur = security.token_hash(x.h.session_token() or "")
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT * FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC LIMIT 20", (x.uid, appdb.now_iso()))
    sess = []
    for r in rows:
        os_, br, kind = _device(r["user_agent"] or "")
        sess.append({"id": r["token"], "device": f"{br} on {os_}", "browser": br, "os": os_, "ip": r["ip"] or "", "location": "",
                     "isCurrent": r["token_hash"] == cur, "status": "online" if r["token_hash"] == cur else "offline",
                     "lastActive": r["created_at"], "clientType": kind})
    st = dict(st or {})
    st["activeSessions"] = sess
    st["email"] = x.user["email"]
    ak = _api_key_info(x.uid) or {"apiKey": "", "apiKeyCreatedAt": ""}
    st.update(ak)
    from backend import plans as _pl
    st["plan"] = {"name": _pl.plan_of(x.uid)["name"], "remainingPoints": appdb.split_points(x.uid)["plan"],
                  "extraPoints": appdb.split_points(x.uid)["extra"], "totalPoints": appdb.get_points(x.uid), "resetsOn": "", "changePlanTg": _pl.contact_url(), "billingSupportTg": _pl.contact_url()}
    st["outgoingLimit"] = st.get("outgoingLimit") or 10
    return st


@route("PUT", "/api/settings")
def settings_put(x: Ctx):
    body = x.body if isinstance(x.body, dict) else {}
    for k in ("activeSessions", "email", "apiKey", "plan", "globalBotAdmins"):
        body.pop(k, None)
    if len(json.dumps(body)) > 65536:
        raise ApiError("Settings are too large.", 400)
    old = _load_settings(x.uid) or {}
    old.update(body)
    try:
        old["outgoingLimit"] = max(1, min(50, int(old.get("outgoingLimit") or 10)))
    except Exception:
        old["outgoingLimit"] = 10
    _save_settings(x.uid, old)
    return settings_get(x)


def _mask_prefix(prefix: str) -> str:
    return f"{prefix}{'•' * 24}" if prefix else ""


def _api_key_info(uid):
    """Security model: the platform API key is a bearer credential, so it is never stored or
    re-readable in full after creation (same principle as a password). Only a SHA-256 hash is kept
    (backend/routers/bots.py::_verify_account_key / api_v2.py auth check against it), plus a short,
    non-sensitive prefix for display. The raw key is returned to the caller ONLY once, by apikey_new,
    at the moment it is generated."""
    from backend import models as em
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        acc = db.query(em.Account).filter_by(email=f"{uid}@matrix.local").first()
        if not acc:
            return None
        row = db.query(em.AccountAPIKey).filter_by(account_id=acc.id, revoked_at=None).order_by(em.AccountAPIKey.created_at.desc()).first()
        if not row:
            return None
        created = row.created_at.strftime("%Y-%m-%d") if row.created_at else ""
        return {"apiKey": "", "apiKeyMasked": _mask_prefix(row.key_prefix), "apiKeyCreatedAt": created}
    finally:
        db.close()


@route("GET", "/api/settings/api-key")
def apikey_get(x: Ctx):
    return _api_key_info(x.uid) or {"apiKey": "", "apiKeyMasked": "", "apiKeyCreatedAt": ""}


@route("POST", "/api/settings/api-key")
def apikey_new(x: Ctx):
    import hashlib
    from backend import models as em
    from backend.database import SessionLocal
    from backend.routers.bots import _api_key_hash
    if security.rate_limit(f"ak:{x.uid}", 10, 3600):
        raise ApiError("Too many requests. Try again later.", 429)
    key = "BMP-" + security.secrets.token_hex(16)
    created = appdb.now_iso()[:10]
    # No reversible copy is ever written: only the hash + a short display prefix are persisted.
    db = SessionLocal()
    try:
        acc = db.query(em.Account).filter_by(email=f"{x.uid}@matrix.local").first()
        if not acc:
            acc = em.Account(email=f"{x.uid}@matrix.local", hashed_password="!", points=appdb.get_points(x.uid))
            db.add(acc)
            db.flush()
        db.query(em.AccountAPIKey).filter_by(account_id=acc.id, revoked_at=None).update({"revoked_at": appdb.utcnow()})
        db.add(em.AccountAPIKey(account_id=acc.id, key_hash=_api_key_hash(key), key_prefix=key[:8], name="default"))
        db.commit()
    finally:
        db.close()
    # Drop any legacy reversible-encrypted copy from a pre-hardening version of this account.
    with appdb.db() as c:
        c.execute("DELETE FROM platform_settings WHERE key=?", (f"apikey:{x.uid}",))
    return {"apiKey": key, "apiKeyMasked": _mask_prefix(key[:8]), "apiKeyCreatedAt": created,
            "warning": "Copy this key now — for your security it will not be shown again."}


@route("POST", "/api/sessions/revoke-others")
def sess_revoke_others(x: Ctx):
    keep = security.token_hash(x.h.session_token() or "")
    with appdb.db() as c:
        c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (x.uid, keep))
    return {"success": True}


@route("POST", "/api/sessions/revoke-all")
def sess_revoke_all(x: Ctx):
    """Sign out every device including this one."""
    with appdb.db() as c:
        c.execute("DELETE FROM sessions WHERE user_id=?", (x.uid,))
    x.h.clear_cookie = True
    return {"success": True, "force_logout": True}


@route("DELETE", "/api/sessions/([^/]+)")
def sess_revoke(x: Ctx):
    cur = security.token_hash(x.h.session_token() or "")
    with appdb.db() as c:
        r = appdb.one(c, "SELECT token_hash FROM sessions WHERE token=? AND user_id=?", (x.p(), x.uid))
        if not r:
            raise ApiError("Session not found", 404)
        if r["token_hash"] == cur:
            raise ApiError("Use Logout to end this session.", 400)
        c.execute("DELETE FROM sessions WHERE token=? AND user_id=?", (x.p(), x.uid))
    return {"success": True}


@route("GET", "/api/notifications")
def notifs(x: Ctx):
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT * FROM notifications WHERE user_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 100", (x.uid, appdb.iso_in(days=-30)))
    out = []
    for r in rows:
        t = appdb.parse_iso(r["created_at"])
        s = int((appdb.utcnow() - t).total_seconds()) if t else 0
        rel = "Just now" if s < 60 else f"{s // 60}m ago" if s < 3600 else f"{s // 3600}h ago" if s < 86400 else f"{s // 86400}d ago"
        out.append({"id": r["id"], "title": r["title"], "message": r["message"], "time": rel, "read": bool(r["is_read"]),
                    "type": r["type"] if r["type"] in ("info", "success", "warning", "alert") else "info", "link": r["link"] or ""})
    return out


@route("PUT", "/api/notifications/([^/]+)/read")
def notif_read(x: Ctx):
    with appdb.db() as c:
        c.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (x.p(), x.uid))
    return {"success": True}


@route("POST", "/api/notifications/read-all")
def notif_all(x: Ctx):
    with appdb.db() as c:
        c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (x.uid,))
    return {"success": True}


_TICKET_DEPTS = {
    "General", "Bot Studio & Editor", "Billing & Plans", "Broadcast",
    "Technical / Bug Report", "Account & Security",
}
_TICKET_PRIOS = {"Low", "Normal", "High", "Urgent"}
_TICKET_STATUSES = {"open", "answered", "customer-reply", "closed"}


def _rg(row, key, default=None):
    """Safe get for sqlite3.Row / dict / mapping."""
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        v = row[key]
        return default if v is None else v
    except Exception:
        return default


def _ticket_row(r) -> dict:
    return {
        "id": r["id"],
        "name": _rg(r, "name", "") or "",
        "email": _rg(r, "email", "") or "",
        "subject": _rg(r, "subject") or _rg(r, "category") or "Support request",
        "message": _rg(r, "message", "") or "",
        "category": _rg(r, "category") or "General",
        "department": _rg(r, "department") or _rg(r, "category") or "General",
        "priority": _rg(r, "priority") or "Normal",
        "status": (_rg(r, "status") or "open").lower(),
        "createdAt": _rg(r, "created_at"),
        "updatedAt": _rg(r, "updated_at") or _rg(r, "created_at"),
        "userId": _rg(r, "user_id"),
    }


def _ticket_replies(c, tid: str) -> list:
    rows = appdb.rows(
        c,
        "SELECT * FROM support_ticket_replies WHERE ticket_id=? ORDER BY created_at ASC",
        (tid,),
    )
    return [
        {
            "id": rr["id"],
            "message": rr["message"],
            "isStaff": bool(_rg(rr, "is_staff")),
            "authorName": _rg(rr, "author_name") or ("Support Staff" if _rg(rr, "is_staff") else "You"),
            "createdAt": _rg(rr, "created_at"),
        }
        for rr in rows
    ]


@route("POST", "/api/help-support/ticket")
def ticket(x: Ctx):
    msg = security.clean_text(x.body.get("message"), 4000)
    if not msg:
        raise ApiError("Please write your message.", 400)
    subject = security.clean_text(x.body.get("subject") or x.body.get("category") or "Support request", 120)
    if not subject:
        raise ApiError("Please add a subject.", 400)
    dept = security.clean_text(x.body.get("department") or x.body.get("category") or "General", 60)
    if dept not in _TICKET_DEPTS:
        dept = "General"
    priority = security.clean_text(x.body.get("priority") or "Normal", 20)
    if priority not in _TICKET_PRIOS:
        priority = "Normal"
    if security.rate_limit(f"tk:{x.uid}", 10, 3600):
        raise ApiError("Too many tickets. Try again later.", 429)
    tid = "TKT-" + security.new_code(6)
    now = appdb.now_iso()
    uname = _rg(x.user, "name", "") or ""
    uemail = _rg(x.user, "email", "") or ""
    with appdb.db() as c:
        c.execute(
            "INSERT INTO support_tickets (id,name,email,message,category,created_at,user_id,status,subject,department,priority,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                tid,
                uname,
                uemail,
                msg,
                dept,
                now,
                x.uid,
                "open",
                subject,
                dept,
                priority,
                now,
            ),
        )
    return {"success": True, "ticketId": tid}



# In-memory typing indicators for live support chat (TTL seconds)
_TICKET_TYPING = {}  # key: "{tid}:{side}" -> expire_ts


def _typing_set(tid: str, side: str, active: bool = True, ttl: float = 3.0):
    import time as _time
    key = f"{tid}:{side}"
    if active:
        _TICKET_TYPING[key] = _time.time() + ttl
    else:
        _TICKET_TYPING.pop(key, None)


def _typing_get(tid: str) -> dict:
    import time as _time
    now = _time.time()
    dead = [k for k, exp in list(_TICKET_TYPING.items()) if exp < now]
    for k in dead:
        _TICKET_TYPING.pop(k, None)
    return {
        "userTyping": _TICKET_TYPING.get(f"{tid}:user", 0) > now,
        "adminTyping": _TICKET_TYPING.get(f"{tid}:admin", 0) > now,
    }


@route("GET", "/api/help-support/tickets")
def tickets(x: Ctx):
    with appdb.read() as c:
        rows = appdb.rows(
            c,
            "SELECT * FROM support_tickets WHERE user_id=? ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 100",
            (x.uid,),
        )
    return [_ticket_row(r) for r in rows]


@route("GET", "/api/help-support/tickets/([^/]+)")
def ticket_detail(x: Ctx):
    tid = x.p()
    now = appdb.now_iso()
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM support_tickets WHERE id=? AND user_id=?", (tid, x.uid))
        if not r:
            raise ApiError("Ticket not found.", 404)
        # Mark staff messages as seen by the customer
        try:
            c.execute(
                "UPDATE support_ticket_replies SET seen_at=COALESCE(seen_at, ?) WHERE ticket_id=? AND COALESCE(is_staff,0)=1 AND seen_at IS NULL",
                (now, tid),
            )
        except Exception:
            pass
        replies = _ticket_replies(c, tid)
    data = _ticket_row(r)
    data["replies"] = replies
    data["message"] = r["message"] or ""
    data.update(_typing_get(tid))
    return data


@route("POST", "/api/help-support/tickets/([^/]+)/reply")
def ticket_reply(x: Ctx):
    tid = x.p()
    msg = security.clean_text(x.body.get("message"), 4000)
    if not msg:
        raise ApiError("Please write your reply.", 400)
    if security.rate_limit(f"tkr:{x.uid}", 30, 3600):
        raise ApiError("Too many replies. Try again later.", 429)
    now = appdb.now_iso()
    rid = "RPL-" + security.new_code(8)
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM support_tickets WHERE id=? AND user_id=?", (tid, x.uid))
        if not r:
            raise ApiError("Ticket not found.", 404)
        if (r["status"] or "open").lower() == "closed":
            raise ApiError("This ticket is closed. You cannot reply until it is reopened.", 400)
        new_status = "customer-reply"
        c.execute(
            "INSERT INTO support_ticket_replies (id,ticket_id,user_id,is_staff,message,created_at,author_name,delivered_at) VALUES (?,?,?,?,?,?,?,?)",
            (rid, tid, x.uid, 0, msg, now, _rg(x.user, "name") or "Customer", now),
        )
        c.execute(
            "UPDATE support_tickets SET status=?, updated_at=? WHERE id=?",
            (new_status, now, tid),
        )
    return {"success": True, "replyId": rid, "status": new_status, "createdAt": now, "deliveredAt": now}


@route("POST", "/api/help-support/tickets/([^/]+)/close")
def ticket_close(x: Ctx):
    tid = x.p()
    now = appdb.now_iso()
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM support_tickets WHERE id=? AND user_id=?", (tid, x.uid))
        if not r:
            raise ApiError("Ticket not found.", 404)
        c.execute("UPDATE support_tickets SET status=?, updated_at=? WHERE id=?", ("closed", now, tid))
    return {"success": True, "status": "closed"}


@route("POST", "/api/help-support/tickets/([^/]+)/reopen")
def ticket_reopen(x: Ctx):
    tid = x.p()
    now = appdb.now_iso()
    with appdb.db() as c:
        r = appdb.one(c, "SELECT * FROM support_tickets WHERE id=? AND user_id=?", (tid, x.uid))
        if not r:
            raise ApiError("Ticket not found.", 404)
        c.execute(
            "UPDATE support_tickets SET status=?, updated_at=? WHERE id=?",
            ("customer-reply", now, tid),
        )
    return {"success": True, "status": "customer-reply"}



@route("POST", "/api/help-support/tickets/([^/]+)/typing")
def ticket_typing(x: Ctx):
    tid = x.p()
    with appdb.read() as c:
        r = appdb.one(c, "SELECT id FROM support_tickets WHERE id=? AND user_id=?", (tid, x.uid))
    if not r:
        raise ApiError("Ticket not found.", 404)
    active = bool((x.body or {}).get("typing", True))
    _typing_set(tid, "user", active)
    return {"success": True, **_typing_get(tid)}


@route("POST", "/api/admin/tickets/([^/]+)/typing")
def admin_ticket_typing(x: Ctx):
    _admin(x)
    tid = x.p()
    with appdb.read() as c:
        r = appdb.one(c, "SELECT id FROM support_tickets WHERE id=?", (tid,))
    if not r:
        raise ApiError("Ticket not found.", 404)
    active = bool((x.body or {}).get("typing", True))
    _typing_set(tid, "admin", active)
    return {"success": True, **_typing_get(tid)}


# ====================================================================== PLANS
@route("GET", "/api/plans")
def plans_list(x: Ctx):
    from backend import plans
    cur = plans.plan_of(x.uid)
    return {"plans": plans.all_plans(), "current": cur["name"], "points": appdb.get_points(x.uid),
            "contactUrl": plans.contact_url()}


def _admin(x: Ctx):
    """Admin panel gate: session + email must be in ADMIN_EMAILS (server env). Not client-side flags."""
    from backend import plans
    email = (str(_rg(x.user, "email") or "")).lower()
    if not plans.admins():
        raise ApiError("Admin access is not configured on this server.", 403)
    if email not in plans.admins():
        # slow down probing
        security.rate_limit(f"adminfail:{x.h.client_ip()}", 20, 600)
        raise ApiError("Not allowed.", 403)
    if security.rate_limit(f"admin:{x.uid}", 120, 60):
        raise ApiError("Too many admin requests. Slow down.", 429)


@route("POST", "/api/admin/plan")
def admin_plan(x: Ctx):
    from backend import plans
    _admin(x)
    pts = x.body.get("addPoints")
    return plans.assign(str(x.body.get("email") or ""), str(x.body.get("plan") or ""), int(pts) if pts not in (None, "") else None)


@route("GET", "/api/admin/overview")
def admin_overview(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.overview()


@route("GET", "/api/admin/users")
def admin_users(x: Ctx):
    from backend import admin
    _admin(x)
    q = {k: v[0] for k, v in x.query.items()}
    return admin.users(q.get("q", ""), int(q.get("page") or 1))


@route("PUT", "/api/admin/users/([^/]+)")
def admin_user_upd(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.update_user(x.p(), x.body)


@route("PUT", "/api/admin/plans/([^/]+)")
def admin_plan_save(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.save_plan(x.p(), x.body)


@route("GET", "/api/admin/config")
def admin_cfg(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.get_config()


@route("PUT", "/api/admin/config")
def admin_cfg_save(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.save_config(x.user["email"], x.body.get("values") or {})


@route("GET", "/api/admin/tickets")
def admin_tickets(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.tickets()


@route("GET", "/api/admin/tickets/([^/]+)")
def admin_ticket_detail(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.ticket_detail(x.p())


@route("PUT", "/api/admin/tickets/([^/]+)")
def admin_ticket_set(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.set_ticket(x.p(), str(x.body.get("status") or ""))


@route("POST", "/api/admin/tickets/([^/]+)/reply")
def admin_ticket_reply(x: Ctx):
    from backend import admin
    _admin(x)
    staff = (_rg(x.user, "name") or _rg(x.user, "email") or "Support Staff")[:80]
    return admin.reply_ticket(x.p(), str(x.body.get("message") or ""), staff)


@route("GET", "/api/admin/bots")
def admin_bots(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.search_bots((x.query.get("q") or [""])[0])


@route("GET", "/api/admin/store")
def admin_store(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.store_items()


@route("POST", "/api/admin/store")
def admin_store_add(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.store_add(x.body)


@route("DELETE", "/api/admin/store/([^/]+)")
def admin_store_del(x: Ctx):
    from backend import admin
    _admin(x)
    return admin.store_remove(x.p())


@route("GET", "/api/admin/server")
def admin_server(x: Ctx):
    from backend import sysmon
    _admin(x)
    return sysmon.vitals()


@route("GET", "/api/admin/fleet")
def admin_fleet(x: Ctx):
    from backend import sysmon
    _admin(x)
    return sysmon.fleet(int((x.query.get("hours") or ["24"])[0]))


@route("GET", "/api/admin/fleet/([^/]+)/diagnose")
def admin_diag(x: Ctx):
    from backend import sysmon
    _admin(x)
    return sysmon.diagnose(x.p(), int((x.query.get("hours") or ["24"])[0]))


@route("POST", "/api/admin/fleet/([^/]+)/action")
def admin_fleet_act(x: Ctx):
    from backend import sysmon
    _admin(x)
    return sysmon.bot_action(x.p(), str(x.body.get("action") or ""))


@route("GET", "/api/admin/logs")
def admin_logs(x: Ctx):
    from backend import sysmon
    _admin(x)
    q = {k: v[0] for k, v in x.query.items()}
    return sysmon.logs(q.get("level", "ALL"), q.get("q", ""), int(q.get("after") or 0))


@route("GET", "/api/admin/database")
def admin_db(x: Ctx):
    from backend import sysmon
    _admin(x)
    return sysmon.db_info()


@route("POST", "/api/admin/database/action")
def admin_db_act(x: Ctx):
    from backend import sysmon
    _admin(x)
    r = sysmon.db_action(str(x.body.get("action") or ""), str(x.body.get("db") or "app"))
    appdb.log_event(x.uid, "", "admin", None, None, "db:" + str(x.body.get("action")))
    return r


@route("POST", "/api/admin/database/query")
def admin_db_q(x: Ctx):
    from backend import sysmon
    _admin(x)
    return sysmon.sql_readonly(str(x.body.get("sql") or ""), str(x.body.get("db") or "app"))


@route("GET", "/api/admin/audit")
def admin_audit(x: Ctx):
    from backend import audit
    _admin(x)
    return {"entries": audit.recent(int((x.query.get("limit") or ["100"])[0]))}


@route("GET", "/api/admin/security")
def admin_sec(x: Ctx):
    from backend import security_center
    _admin(x)
    return security_center.admin_status(scan=False)


@route("POST", "/api/admin/security/scan")
def admin_sec_scan(x: Ctx):
    from backend import security_center
    _admin(x)
    return security_center.admin_status(scan=True, fix=(x.body.get("fix") or None))


@route("PUT", "/api/admin/security/events/([^/]+)/resolve")
def admin_sec_res(x: Ctx):
    from backend import security_center
    _admin(x)
    return security_center.resolve(None, x.p())


@route("GET", "/api/security")
def user_sec(x: Ctx):
    from backend import security_center
    return security_center.user_status(x.uid, scan=False)


@route("POST", "/api/security/scan")
def user_sec_scan(x: Ctx):
    from backend import security_center
    if security.rate_limit(f"secscan:{x.uid}", 6, 300):
        raise ApiError("Please wait a moment before scanning again.", 429)
    return security_center.user_status(x.uid, scan=True)


@route("PUT", "/api/security/events/([^/]+)/resolve")
def user_sec_res(x: Ctx):
    from backend import security_center
    return security_center.resolve(x.uid, x.p())


@route("PUT", "/api/admin/contact")
def admin_contact(x: Ctx):
    _admin(x)
    url = security.clean_text(x.body.get("url"), 300)
    if url and not re.match(r"^(https?://|tg://)", url):
        raise ApiError("The contact link must start with https:// or tg://", 400)
    with appdb.db() as c:
        c.execute("INSERT OR REPLACE INTO platform_settings (key,value) VALUES ('contact_admin_url',?)", (url,))
    return {"success": True, "contactUrl": url}


# ====================================================================== TRANSFER RECEIPTS
def _mask(e: str) -> str:
    n, _, d = (e or "").partition("@")
    return (n[:1] + "***@" + d) if d else "***"


def _receipt_sig(r) -> str:
    return security.sign("receipt|%s|%s|%s|%s|%s" % (r["id"], r["bot_numeric_id"], r["from_email"], r["to_email"], r["created_at"]))[:32]


@route("GET", "/api/transfers/([^/]+)/receipt")
def transfer_receipt_link(x: Ctx):
    with appdb.read() as c:
        r = appdb.one(c, "SELECT * FROM transfers WHERE id=? AND (from_user_id=? OR to_user_id=?)", (x.p(), x.uid, x.uid))
    if not r:
        raise ApiError("Transfer not found", 404)
    return {"code": f"{r['id']}.{_receipt_sig(r)}"}


@route("GET", "/api/public/receipt/([^/]+)", auth=False)
def public_receipt(x: Ctx):
    if security.rate_limit(f"rcpt:{x.h.client_ip()}", 60, 60):
        raise ApiError("Too many requests.", 429)
    tid, _, sig = x.p().partition(".")
    with appdb.read() as c:
        r = appdb.one(c, "SELECT * FROM transfers WHERE id=?", (tid,))
    import hmac as _h
    if not r or not sig or not _h.compare_digest(sig, _receipt_sig(r)):
        return {"valid": False}
    return {"valid": True, "id": r["id"], "botName": r["bot_name"], "botNumericId": r["bot_numeric_id"],
            "from": _mask(r["from_email"]), "to": _mask(r["to_email"]), "status": r["status"],
            "createdAt": r["created_at"], "respondedAt": r["responded_at"],
            "signature": sig, "algorithm": "HMAC-SHA256 (server-signed)"}


_STARTED = __import__("time").time()


@route("GET", "/api/status")
def platform_status(x: Ctx):
    import time as _t
    from backend import runtime
    t0 = _t.perf_counter()
    with appdb.read() as c:
        mine = appdb.one(c, "SELECT COUNT(*) n, SUM(CASE WHEN status='working' THEN 1 ELSE 0 END) r FROM bots WHERE user_id=?", (x.uid,))
        bc = appdb.one(c, "SELECT COUNT(*) n FROM broadcasts WHERE user_id=? AND status IN ('Active','Paused')", (x.uid,))
        err = appdb.one(c, "SELECT COUNT(*) n FROM events WHERE owner_id=? AND kind='error' AND ts>=?", (x.uid, appdb.iso_in(hours=-24)))
    db_ms = round((_t.perf_counter() - t0) * 1000, 1)
    with appdb.read() as c:
        ids = [r["id"] for r in appdb.rows(c, "SELECT id FROM bots WHERE user_id=? AND status='working'", (x.uid,))]
    live = sum(1 for i in ids if runtime.is_running(i))
    return {"api": {"ok": True, "uptimeSec": int(_t.time() - _STARTED)}, "database": {"ok": True, "latencyMs": db_ms},
            "bots": {"total": mine["n"] or 0, "running": mine["r"] or 0, "liveWorkers": live},
            "broadcasts": {"active": bc["n"]}, "errors24h": err["n"] if err else 0}


@route("GET", "/api/dashboard/stats")
def dash(x: Ctx):
    from backend import services
    return services.dashboard(x.uid)


# ====================================================================== BOTS
def S():
    from backend import services
    return services


from backend import api_v2 as _api_v2
_api_v2.register(route, Ctx)


@route("GET", "/api/bots")
def bots_list(x: Ctx):
    return S().list_bots(x.uid)


@route("POST", "/api/bots")
def bots_create(x: Ctx):
    if security.rate_limit(f"mk:{x.uid}", 20, 3600):
        raise ApiError("Too many bots created. Try again later.", 429)
    return S().create_bot(x.uid, x.body)


@route("GET", "/api/bots/([^/]+)/admin/overview")
def bots_admin_overview(x: Ctx):
    try:
        d = int((x.query.get("days") or ["7"])[0])
    except ValueError:
        d = 7
    return S().admin_overview(x.uid, x.p(), d)


@route("PUT", "/api/bots/([^/]+)/admin/maintenance")
def bots_admin_maint(x: Ctx):
    return S().admin_maintenance_set(x.uid, x.p(), x.body)


@route("POST", "/api/bots/([^/]+)/admin/action")
def bots_admin_action(x: Ctx):
    return S().admin_action(x.uid, x.p(), x.body.get("action"))


@route("GET", "/api/bots/([^/]+)/intro")
def bots_intro(x: Ctx):
    try:
        tz = int((x.query.get("tz") or ["0"])[0])
    except ValueError:
        tz = 0
    return S().intro(x.uid, x.p(), max(-840, min(840, tz)))


@route("GET", "/api/bots/([^/]+)/errors")
def bots_errors(x: Ctx):
    S().own_bot(x.uid, x.p())
    return S().bot_errors(x.p())


@route("DELETE", "/api/bots/([^/]+)/errors")
def bots_errors_clear(x: Ctx):
    return S().clear_errors(x.uid, x.p())


@route("GET", "/api/bots/([^/]+)")
def bots_get(x: Ctx):
    return S().bot_dict(S().own_bot(x.uid, x.p()))


@route("PUT", "/api/bots/([^/]+)")
def bots_put(x: Ctx):
    return S().update_bot(x.uid, x.p(), x.body)


@route("DELETE", "/api/bots/([^/]+)")
def bots_del(x: Ctx):
    return S().delete_bot(x.uid, x.p())


@route("POST", "/api/bots/([^/]+)/toggle-status")
def bots_toggle(x: Ctx):
    return S().toggle_bot(x.uid, x.p())


@route("POST", "/api/bots/([^/]+)/(sync-telegram|refresh-photo)")
def bots_sync(x: Ctx):
    return S().sync_telegram(x.uid, x.p())


@route("POST", "/api/bots/([^/]+)/test-command")
def bots_test(x: Ctx):
    from backend import tpy_tools
    if security.rate_limit(f"tc:{x.uid}", 60, 60):
        raise ApiError("Slow down a little.", 429)
    return tpy_tools.test_command(x.uid, x.p(), x.body)


@route("POST", "/api/bots/([^/]+)/transfer")
def bots_transfer(x: Ctx):
    return S().start_transfer(x.uid, x.p(), x.body.get("email"), options=x.body.get("options"))


@route("POST", "/api/bots/([^/]+)/chats/([^/]+)/send")
def bots_send(x: Ctx):
    return S().chat_send(x.uid, x.p(0), x.p(1), x.body.get("text"))


@route("POST", "/api/bots/([^/]+)/users/import")
def users_import(x: Ctx):
    from backend import user_io, plans
    plans.require(x.uid, "userImport", "Importing users")
    if security.rate_limit(f"uimp:{x.uid}", 20, 3600):
        raise ApiError("Too many imports. Try again later.", 429)
    raw = x.body.get("_raw") if isinstance(x.body, dict) else None
    name = urllib.parse.unquote(x.h.headers.get("x-file-name") or "users.txt")
    return user_io.start_import(x.uid, x.p(), raw or b"", name)


@route("POST", "/api/bots/([^/]+)/users/export")
def users_export(x: Ctx):
    from backend import user_io
    if security.rate_limit(f"uexp:{x.uid}", 30, 3600):
        raise ApiError("Too many exports. Try again later.", 429)
    return user_io.start_export(x.uid, x.p(), x.body.get("format"), x.body.get("fields"), str(x.body.get("filter") or "all"), bool(x.body.get("includeDates")))


@route("GET", "/api/bots/([^/]+)/users/jobs")
def users_jobs(x: Ctx):
    from backend import user_io
    return user_io.active(x.uid, x.p())


@route("GET", "/api/bots/([^/]+)/users/jobs/([^/]+)")
def users_job(x: Ctx):
    from backend import user_io
    return user_io.status(x.uid, x.p(0), x.p(1))


@route("POST", "/api/bots/([^/]+)/users/jobs/([^/]+)/cancel")
def users_job_cancel(x: Ctx):
    from backend import user_io
    return user_io.cancel(x.uid, x.p(0), x.p(1))


@route("GET", "/api/bots/([^/]+)/users/export/([^/]+)/download")
def users_download(x: Ctx):
    from backend import user_io
    return user_io.download(x.uid, x.p(0), x.p(1))


@route("GET", "/api/bots/([^/]+)/export")
def bot_export(x: Ctx):
    from backend import bot_package
    if security.rate_limit(f"bexp:{x.uid}", 60, 3600):
        raise ApiError("Too many exports. Try again later.", 429)
    q = {k: v[0] for k, v in x.query.items()}
    return bot_package.export(x.uid, x.p(), q.get("format", "json"), q.get("parts", "commands"), q.get("envValues", "1") != "0")


@route("POST", "/api/bots/([^/]+)/import")
def bot_import(x: Ctx):
    from backend import bot_package
    if security.rate_limit(f"bimp:{x.uid}", 40, 3600):
        raise ApiError("Too many imports. Try again later.", 429)
    q = {k: v[0] for k, v in x.query.items()}
    if (q.get("parts") or "").find("users") >= 0 and q.get("dryRun") != "1":
        from backend import plans
        plans.require(x.uid, "userImport", "Importing users")
    raw = x.body.get("_raw") if isinstance(x.body, dict) else None
    name = urllib.parse.unquote(x.h.headers.get("x-file-name") or "bot.json")
    return bot_package.preview_and_apply(x.uid, x.p(), raw or b"", name, q.get("parts") or None, q.get("replace") == "1", q.get("dryRun") == "1")


@route("GET", "/api/bots/([^/]+)/token")
@route("POST", "/api/bots/([^/]+)/token")
def bot_token_reveal(x: Ctx):
    """Owner-only: shows the bot's own token (Settings eye icon). Never in normal bot payloads.

    Hardened: strict rate limit, owner check, optional password re-check, audit log.
    DevTools can call this only with a valid session of the *owner* — not other users.
    """
    if security.rate_limit(f"tokrv:{x.uid}", 5, 600):
        raise ApiError("Too many token reveals. Wait a few minutes.", 429)
    if security.rate_limit(f"tokrvip:{x.h.client_ip()}", 15, 600):
        raise ApiError("Too many requests from this network.", 429)
    b = S().own_bot(x.uid, x.p())
    if not b["token"]:
        raise ApiError("This bot has no token yet — add your own token to start it.", 404)
    # Optional step-up: if client sends password, verify it (UI can require this)
    pw = (x.body or {}).get("password") if isinstance(x.body, dict) else None
    if pw is not None and str(pw) != "":
        if not security.verify_password(str(pw), x.user.get("password_hash") or ""):
            raise ApiError("Incorrect password.", 403)
    try:
        from backend import audit
        audit.log_action(x.uid, "bot.token_reveal", target_id=x.p(), body={}, ip=x.h.client_ip())
    except Exception:
        pass
    return {"token": security.decrypt(b["token"])}


@route("GET", "/api/folders")
def folders(x: Ctx):
    return S().folders(x.uid)


@route("POST", "/api/folders")
def folders_add(x: Ctx):
    return S().add_folder(x.uid, x.body.get("name"))


@route("GET", "/api/global-admins")
def ga_list(x: Ctx):
    return S().admins(x.uid)


@route("POST", "/api/global-admins")
def ga_add(x: Ctx):
    return S().add_admin(x.uid, x.body.get("telegramId"))


@route("DELETE", "/api/global-admins/([^/]+)")
def ga_del(x: Ctx):
    return S().remove_admin(x.uid, x.p())


@route("GET", "/api/chats/([^/]+)")
def chats(x: Ctx):
    return S().chat_list(x.uid, x.p(), {k: v[0] for k, v in x.query.items()})


@route("PUT", "/api/chats/([^/]+)/users/([^/]+)/block")
def chat_block(x: Ctx):
    return S().chat_block(x.uid, x.p(0), x.p(1))


@route("POST", "/api/chats/([^/]+)/users/([^/]+)/reply")
def chat_reply(x: Ctx):
    return S().chat_send(x.uid, x.p(0), x.p(1), x.body.get("message"))


@route("GET", "/api/database/([^/]+)")
def kv(x: Ctx):
    return S().kv_data(x.uid, x.p(), {k: v[0] for k, v in x.query.items()})


@route("PUT", "/api/database/([^/]+)")
def kv_put(x: Ctx):
    return S().kv_set(x.uid, x.p(), x.body)


@route("DELETE", "/api/database/([^/]+)")
def kv_del(x: Ctx):
    return S().kv_delete(x.uid, x.p(), {k: v[0] for k, v in x.query.items()})


@route("GET", "/api/recycle-bin")
def rb(x: Ctx):
    return S().recycle_list(x.uid)


@route("POST", "/api/recycle-bin/([^/]+)/restore")
def rb_restore(x: Ctx):
    return S().recycle_restore(x.uid, x.p())


@route("DELETE", "/api/recycle-bin/([^/]+)")
def rb_del(x: Ctx):
    return S().recycle_purge(x.uid, x.p())


@route("GET", "/api/store/bots")
def store(x: Ctx):
    return S().store_list()


@route("POST", "/api/store/bots/([^/]+)/clone")
def store_clone(x: Ctx):
    return S().store_clone(x.uid, x.p())


@route("POST", "/api/store/publish")
def store_pub(x: Ctx):
    return S().store_publish(x.uid, x.body)


# ====================================================================== BROADCASTS
def B():
    from backend import broadcast_service
    return broadcast_service


@route("GET", "/api/broadcasts")
def bc_list(x: Ctx):
    return B().list_for(x.uid)


@route("GET", "/api/broadcasts/languages")
def bc_languages(x: Ctx):
    ids = [i for i in str((x.query.get("botIds") or [""])[0]).split(",") if i][:200]
    return B().languages(x.uid, ids)


@route("POST", "/api/broadcasts/media")
def bc_media(x: Ctx):
    from backend import broadcast_media
    if security.rate_limit(f"bcm:{x.uid}", 30, 3600):
        raise ApiError("Too many uploads. Try again later.", 429)
    raw = x.body.get("_raw") if isinstance(x.body, dict) else None
    name = urllib.parse.unquote(x.h.headers.get("x-file-name") or "file")
    mime = (x.h.headers.get("content-type") or "").split(";")[0].strip().lower()
    mid = broadcast_media.put(x.uid, name, mime, raw or b"", x.h.headers.get("x-media-type") or "")
    return {"mediaId": mid, "name": name[:120]}


@route("POST", "/api/broadcasts/detect-url")
def bc_detect(x: Ctx):
    from backend import broadcast_media
    if security.rate_limit(f"bcd:{x.uid}", 60, 600):
        raise ApiError("Too many requests. Try again shortly.", 429)
    return broadcast_media.detect(str(x.body.get("url") or ""))


@route("POST", "/api/broadcasts")
def bc_create(x: Ctx):
    if security.rate_limit(f"bc:{x.uid}", 20, 3600):
        raise ApiError("Too many broadcasts. Try again later.", 429)
    return B().create(x.user, x.body)


@route("GET", "/api/broadcasts/([^/]+)")
def bc_get(x: Ctx):
    return B().get_for(x.uid, x.p())


@route("POST", "/api/broadcasts/([^/]+)/(pause|resume|cancel|clean-failed)")
def bc_act(x: Ctx):
    return B().act(x.uid, x.p(0), x.p(1))


@route("POST", "/api/broadcasts/([^/]+)/speed")
def bc_speed(x: Ctx):
    return B().set_speed(x.uid, x.p(), str(x.body.get("speed") or ""))


@route("POST", "/api/broadcasts/([^/]+)/bots/([^/]+)/status")
def bc_bot(x: Ctx):
    return B().bot_status(x.uid, x.p(0), x.p(1), str(x.body.get("status") or ""))


@route("DELETE", "/api/broadcasts/([^/]+)")
def bc_del(x: Ctx):
    return B().delete(x.uid, x.p())


# ====================================================================== TELEGRAM CONNECT
@route("GET", "/api/telegram/status")
def tg_status(x: Ctx):
    return S().telegram_status(x.uid)


@route("POST", "/api/telegram/link-code")
def tg_link(x: Ctx):
    from backend import connect_bot
    if security.rate_limit(f"lk:{x.uid}", 10, 600):
        raise ApiError("Too many attempts. Try again in a few minutes.", 429)
    return connect_bot.create_link(x.uid)


@route("POST", "/api/telegram/alerts")
def tg_alerts(x: Ctx):
    from backend import connect_bot
    a = dict(connect_bot.alerts_of(x.user))
    for k, v in (x.body.get("alerts") or {}).items():
        if k in a:
            a[k] = bool(v)
    with appdb.db() as c:
        c.execute("UPDATE users SET telegram_alerts_json=? WHERE id=?", (json.dumps(a), x.uid))
    return {"success": True, "alerts": a}


@route("POST", "/api/telegram/disconnect")
def tg_disc(x: Ctx):
    from backend import connect_bot
    chat = x.user["telegram_chat_id"]
    if x.user["telegram_connected"] and chat:
        connect_bot._send(chat, "🔌 This chat was disconnected from your account.", {"remove_keyboard": True})
    connect_bot.disconnect(x.uid)
    return {"success": True, "connected": False}


@route("POST", "/api/telegram/test-alert")
def tg_test(x: Ctx):
    from backend import connect_bot
    if not x.user["telegram_connected"]:
        raise ApiError("Connect Telegram first.", 400)
    if security.rate_limit(f"ta:{x.uid}", 6, 600):
        raise ApiError("Too many test alerts. Try again later.", 429)
    ok = connect_bot._send(x.user["telegram_chat_id"], "✅ Test alert from BOT MATRIX. Alerts are working.") is not None
    if not ok:
        raise ApiError("Couldn't deliver the alert. Reconnect Telegram and try again.", 400)
    return {"success": True, "message": "Test alert sent"}


# ====================================================================== TRANSFERS
@route("GET", "/api/transfers")
def tr_list(x: Ctx):
    return S().transfers_overview(x.uid)


@route("POST", "/api/transfers/([^/]+)/accept")
def tr_acc(x: Ctx):
    return {"success": True, "transfer": S().accept_transfer(x.uid, x.p())}


@route("POST", "/api/transfers/([^/]+)/reject")
def tr_rej(x: Ctx):
    return {"success": True, "transfer": S().reject_transfer(x.uid, x.p())}


@route("POST", "/api/transfers/([^/]+)/cancel")
def tr_can(x: Ctx):
    return {"success": True, "transfer": S().cancel_transfer(x.uid, x.p())}


# ====================================================================== EDITOR
@route("GET", "/api/editor/catalog")
def ed_cat(x: Ctx):
    from backend import tpy_tools
    return tpy_tools.catalog()


@route("POST", "/api/editor/format")
def ed_fmt(x: Ctx):
    from backend import tpy_tools
    code = str(x.body.get("code") or "")
    if len(code) > 300_000:
        raise ApiError("This command is too large to format.", 400)
    return tpy_tools.format_code(code)


@route("POST", "/api/editor/validate")
def ed_val(x: Ctx):
    from backend import tpy_tools
    return tpy_tools.validate(str(x.body.get("code") or ""), str(x.body.get("name") or ""))


# ====================================================================== MEDIA
_COLORS = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#059669", "#0891b2", "#4f46e5", "#be123c"]


@route("GET", "/api/avatar/([^/]+)\\.svg", auth=False)
def avatar(x: Ctx):
    seed = x.p()
    n = sum(ord(ch) for ch in seed)
    col = _COLORS[n % len(_COLORS)]
    letter = "B"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><rect width="96" height="96" rx="24" fill="{col}"/>'
           f'<text x="48" y="62" font-family="Arial,sans-serif" font-size="44" font-weight="700" text-anchor="middle" fill="#fff">{letter}</text></svg>')
    return ("raw", "image/svg+xml", svg.encode(), {"Cache-Control": "public, max-age=86400"})


@route("GET", "/api/media/bot/([^/]+)")
def media_bot(x: Ctx):
    with appdb.read() as c:
        b = appdb.one(c, "SELECT token,photo_url FROM bots WHERE id=? AND user_id=?", (x.p(), x.uid))
    if not b or not (b["photo_url"] or "").startswith("tgfile:"):
        raise ApiError("Not found", 404)
    data = tg.download_file(security.decrypt(b["token"]), b["photo_url"][7:])
    if not data:
        raise ApiError("Not found", 404)
    return ("raw", "image/jpeg", data, {"Cache-Control": "private, max-age=3600"})


_photo_cache: dict = {}


@route("GET", "/api/media/chat/([^/]+)/(\\d+)")
def media_chat(x: Ctx):
    """Profile photo of a person who talks to the bot (fetched with the bot's own token, cached for an hour)."""
    with appdb.read() as c:
        b = appdb.one(c, "SELECT token FROM bots WHERE id=? AND user_id=?", (x.p(0), x.uid))
        ch = appdb.one(c, "SELECT 1 x FROM chats WHERE bot_id=? AND telegram_id=?", (x.p(0), x.p(1)))
    if not b or not ch or not b["token"]:
        raise ApiError("Not found", 404)
    key = (x.p(0), x.p(1))
    hit = _photo_cache.get(key)
    if hit and time.time() - hit[0] < 3600:
        data = hit[1]
    else:
        token = security.decrypt(b["token"])
        path = tg.profile_photo_url(token, int(x.p(1)))
        data = tg.download_file(token, path) if path else None
        if len(_photo_cache) > 3000:
            _photo_cache.clear()
        _photo_cache[key] = (time.time(), data)
    if not data:
        raise ApiError("Not found", 404)
    return ("raw", "image/jpeg", data, {"Cache-Control": "private, max-age=3600"})


@route("GET", "/api/health", auth=False)
def health(x: Ctx):
    return {"status": "OK"}


# ====================================================================== HTTP
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "BotMatrix"
    sys_version = ""
    set_cookie = None
    clear_cookie = False

    def log_message(self, *a):
        pass

    def client_ip(self) -> str:
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1"):
            v = (self.headers.get("x-dm-client-ip") or "").replace("::ffff:", "").strip()
            if v:
                return v[:64]
        return peer

    def session_token(self):
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer ") and len(auth) > 10:
            return auth[7:].strip()
        ck = self.headers.get("Cookie") or ""
        m = re.search(COOKIE + r"=([^;]+)", ck)
        return m.group(1) if m else None

    def _auth(self):
        tok = self.session_token()
        if not tok:
            return None, None
        th = security.token_hash(tok)
        with appdb.read() as c:
            s = appdb.one(c, "SELECT * FROM sessions WHERE token_hash=? AND is_active=1", (th,))
            if not s or s["expires_at"] < appdb.now_iso():
                return None, None
            u = appdb.one(c, "SELECT * FROM users WHERE id=?", (s["user_id"],))
        if not u:
            return None, None
        if u["suspended"]:
            try:
                with appdb.db() as c:
                    c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
            except Exception:
                pass
            self._auth_fail_reason = "suspended"
            return None, None
        return (u, s)

    def _send(self, status, payload, ctype="application/json", extra=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if self.headers.get("X-Forwarded-Proto") == "https" or os.environ.get("BASE_URL", "").startswith("https://"):
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if ctype == "application/json":
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if self.set_cookie:
            sec = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https" or os.environ.get("BASE_URL", "").startswith("https://")) else ""
            max_age = int(getattr(self, "cookie_max_age", None) or 86400)
            self.send_header("Set-Cookie", f"{COOKIE}={self.set_cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{sec}")
        if self.clear_cookie:
            self.send_header("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        self.set_cookie, self.clear_cookie = None, False
        try:
            body = {}
            length = int(self.headers.get("Content-Length") or 0)
            _p = urlparse(self.path).path.rstrip("/")
            is_media = self.command == "POST" and (_p == "/api/broadcasts/media" or re.fullmatch(r"/api/bots/[^/]+/(users/)?import", _p) is not None)
            if is_media:
                user_, _s = self._auth()
                if not user_ or length > 21 * 1024 * 1024:
                    try:
                        self.rfile.read(min(length, 1024))
                    except Exception:
                        pass
                    self.close_connection = True
                    return self._send(401 if not user_ else 413, {"error": "Please sign in again." if not user_ else "That file is too large (max 20 MB)."})
            if length > MAX_BODY and not is_media:
                self.rfile.read(min(length, MAX_BODY))
                return self._send(413, {"error": "That request is too large."})
            raw = self.rfile.read(length) if length else b""  # always consume the body first
            if is_media:
                body = {"_raw": raw}
                raw = b""
            if _p == "/api/new-webhook":
                body, raw = {"_raw": raw}, b""         # webhooks: any content type, kept verbatim
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    return self._send(400, {"error": "Invalid request."})
            if not isinstance(body, dict):
                body = {}
            u = urlparse(self.path)
            path = u.path.rstrip("/") or "/"
            query = parse_qs(u.query)
            matched = False
            for m, rx, fn, auth in ROUTES:
                mt = rx.match(path)
                if not mt:
                    continue
                matched = True
                if m != method:
                    continue
                user = sess = None
                if auth:
                    user, sess = self._auth()
                    if not user:
                        reason = getattr(self, "_auth_fail_reason", None)
                        self._auth_fail_reason = None
                        if reason == "suspended":
                            return self._send(401, {
                                "error": "This account has been suspended. Contact the administrator.",
                                "force_logout": True,
                                "suspended": True,
                            })
                        return self._send(401, {"error": "Please sign in again.", "force_logout": True})
                    if method != "GET":
                        try:
                            _check_origin(self)
                        except ApiError as oe:
                            return self._send(oe.status, {"error": oe.message})
                    if method != "GET" and security.rate_limit(f"api:{user['id']}", 600, 60):
                        return self._send(429, {"error": "Too many requests. Slow down a little."})
                elif method == "POST" and security.rate_limit(f"anon:{self.client_ip()}", 120, 60):
                    return self._send(429, {"error": "Too many requests. Try again shortly."})
                res = fn(Ctx(self, body, query, mt.groups(), user, sess))
                if user and method != "GET" and (path.startswith("/api/admin/") or path == "/api/settings/api-key"):
                    try:
                        from backend import audit
                        audit.log_action(user["id"], f"{method} {path}", target_id=(mt.groups() or [""])[0] or "", body=body, ip=self.client_ip())
                    except Exception:
                        pass
                if isinstance(res, tuple) and res and res[0] == "raw":
                    return self._send(200, res[2], res[1], res[3] if len(res) > 3 else None)
                return self._send(200, res if res is not None else {"success": True})
            return self._send(405 if matched else 404, {"error": "Not found."})
        except ApiError as e:
            if urlparse(self.path).path.startswith("/v2/"):
                extra = dict(e.extra)
                return self._send(e.status, {"ok": False, "result": e.message}, extra=extra.get("_headers"))
            payload = {"error": e.message, **e.extra}
            if e.force_logout:
                payload["force_logout"] = True
            return self._send(e.status, payload)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            log.error("unhandled %s %s\n%s", method, self.path, traceback.format_exc())
            try:
                self._send(500, {"error": "Something went wrong on our side. Please try again."})
            except Exception:
                pass

    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PUT(self): self._handle("PUT")
    def do_DELETE(self): self._handle("DELETE")
    def do_PATCH(self): self._handle("PATCH")
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 256


def _apply_process_rlimits():
    """Last-resort circuit breaker: sandboxed TPY code runs as a thread INSIDE this process
    (needed to share the exec() globals cheaply), so a per-run memory/CPU cap would require a
    separate process per execution -- a larger architecture change, tracked as a follow-up.
    Until then, a generous process-wide address-space ceiling stops one runaway/malicious bot
    command (e.g. an unbounded allocation loop) from OOM-killing the whole server for every
    tenant: it turns into a catchable MemoryError in that one command instead of a hard crash.
    Best-effort and silent on platforms without `resource` (e.g. Windows / non-Linux dev machines)."""
    if sys.platform == "win32":
        # `resource` is Unix-only; nothing to do on Windows.
        return
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        cap_mb = int(os.environ.get("PROCESS_MEMORY_LIMIT_MB", "3072"))
        cap_bytes = cap_mb * 1024 * 1024
        if soft == resource.RLIM_INFINITY or soft > cap_bytes:
            resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard if hard != resource.RLIM_INFINITY else cap_bytes))
        soft_fd, hard_fd = resource.getrlimit(resource.RLIMIT_NOFILE)
        want_fd = min(hard_fd, 8192) if hard_fd != resource.RLIM_INFINITY else 8192
        if soft_fd < want_fd:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want_fd, hard_fd))
    except Exception as e:
        log.warning("process rlimits skipped (non-fatal): %s", e)


def main():
    _apply_process_rlimits()
    from backend import runtime, services, connect_bot, broadcast_service
    appdb.init_db()
    from backend import plans
    plans.seed()
    from backend import admin as _admin_mod
    _admin_mod.apply_all()
    runtime.init_engine()
    services.register_hooks()
    try:
        from backend import sysmon, security_center
        sysmon.install_log_buffer(); sysmon.start_sampler(); security_center.encrypt_legacy_env(); security_center.start_watcher()
    except Exception:
        log.exception("monitors")
    broadcast_service.recover_on_start()
    try:
        from backend.scheduler import scheduler as _sch
        _sch.start_scheduler()
    except Exception:
        log.exception("scheduler")
    port = int(os.environ.get("API_PORT", "5001"))
    srv = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=connect_bot.start, daemon=True).start()
    threading.Thread(target=runtime.resume_all, daemon=True).start()
    log.info("Email codes: %s | REQUIRE_EMAIL_OTP=%s | Turnstile=%s | rate limits=%s",
             "SMTP configured" if _mail_configured() else "SMTP NOT configured",
             "on" if _otp_required() else "off", "on" if _turnstile_on() else "off",
             "on" if security.env_flag("RATE_LIMITS", False) else "off")
    log.info("BOT MATRIX API listening on 127.0.0.1:%s", port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
