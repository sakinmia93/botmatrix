"""TBC libs.TonLib — V5R1 + TON Connect URL/verify/user-wallet helpers."""
from __future__ import annotations
import pathlib, zlib, base64
_p = pathlib.Path(__file__).with_name
_blob = "".join(_p(f"f{i}.b64").read_text().strip() for i in range(7))
_code = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
# Force correct public URLs
_code = _code.replace(
    'f"{self._base_url}/tonconnect/{sid}"',
    'f"{self._base_url}/api/ton-connect/session/{sid}"',
)
_code = _code.replace(
    'f"{self._base_url}/tonconnect/req/{rid}"',
    'f"{self._base_url}/api/ton-connect/request/{rid}"',
)
# verify: wallet_address => connected
_code = _code.replace(
    '        return {"status": rec.get("status", "pending"), "wallet_address": rec.get("wallet_address")}',
    '        st = rec.get("status", "pending")\n'
    '        wa = rec.get("wallet_address")\n'
    '        if wa and st == "pending":\n'
    '            st = "connected"\n'
    '        return {"status": st, "wallet_address": wa, "public_key": rec.get("public_key")}',
)
# create session: accept bot_username / bot_link kwargs
_code = _code.replace(
    '    def create_ton_connect_session(self, user_id, expiry_seconds=86400):\n'
    '        sid = _secrets.token_hex(16)\n'
    '        self._kv_set(SESSION_PREFIX + sid, json.dumps({"user_id": user_id, "exp": int(time.time()) + expiry_seconds, "status": "pending"}))\n'
    '        return {"session_id": sid, "connect_url": f"{self._base_url}/api/ton-connect/session/{sid}"}',
    '    def create_ton_connect_session(self, user_id, expiry_seconds=86400, bot_username=None, bot_link=None, **kw):\n'
    '        sid = _secrets.token_hex(16)\n'
    '        rec = {"user_id": user_id, "exp": int(time.time()) + expiry_seconds, "status": "pending", "challenge": sid}\n'
    '        if bot_username: rec["bot_username"] = str(bot_username).lstrip("@")\n'
    '        if bot_link: rec["bot_link"] = str(bot_link)\n'
    '        elif bot_username: rec["bot_link"] = "https://t.me/" + str(bot_username).lstrip("@") + "?start=wallet_ok"\n'
    '        self._kv_set(SESSION_PREFIX + sid, json.dumps(rec))\n'
    '        return {"session_id": sid, "connect_url": f"{self._base_url}/api/ton-connect/session/{sid}"}',
)
# helpers: get wallet by telegram user_id (auto-detect without session id)
_code += '''

def _bm_get_user_wallet(self, user_id):
    raw = self._kv_get("__tonc_user:%s" % user_id)
    if not raw:
        return {"status": "pending", "wallet_address": None}
    try:
        import json as _j
        rec = _j.loads(raw)
    except Exception:
        return {"status": "error", "message": "Invalid record"}
    return {"status": rec.get("status") or ("connected" if rec.get("wallet_address") else "pending"),
            "wallet_address": rec.get("wallet_address"), "session_id": rec.get("session_id")}

def _bm_check_wallet(self, user_id=None, session_id=None):
    if session_id:
        return self.verify_ton_connect_session(session_id)
    if user_id is not None:
        return _bm_get_user_wallet(self, user_id)
    return {"status": "error", "message": "user_id or session_id required"}

TonLib.get_user_wallet = _bm_get_user_wallet
TonLib.check_wallet = _bm_check_wallet
'''
exec(compile(_code, str(pathlib.Path(__file__)), "exec"), globals())
