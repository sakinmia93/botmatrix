"""TBC libs.TonLib — real TON integration (tonsdk wallets v4r2, toncenter v2/v3, persistent TON Connect sessions).

Return shapes follow the TBC "TON Library Documentation":
  generateWallet() -> {"address", "mnemonics"}          getWalletAddress() -> "EQ..."
  getBalance() -> float (TON)                            checkTONTransaction() -> [{"type": "incoming", "from", "amount", ...}]
  create_ton_connect_session() -> {"session_id", "connect_url"}
  verify_ton_connect_session() -> {"status": "connected" | "pending" | "expired" | "error", "wallet_address"}
  register_ton_connect_wallet() -> {"status": "success" | "error", "message", "wallet_address"}
  create_ton_connect_payload / request_ton_transaction / request_jetton_transfer -> {"request_id", "connect_url", "payload"}
Errors are raised (wrap calls in try/except as the docs advise).
"""
from __future__ import annotations

import base64
import json
import os
import secrets as _secrets
import time
from typing import Optional

import requests

MAINNET = "https://toncenter.com/api/v2"
TESTNET = "https://testnet.toncenter.com/api/v2"
SESSION_PREFIX = "__tonc:"
REQUEST_PREFIX = "__tonr:"
KEYS_KEY = "__ton_keys"


def _split(url):
    return url.rstrip("/")


def _v3(base):
    return base.replace("/api/v2", "/api/v3")


def _norm_mnemonics(m):
    if m is None:
        return None
    if isinstance(m, (list, tuple)):
        return [str(w).strip() for w in m if str(w).strip()]
    return [w for w in str(m).replace(",", " ").split() if w]


def _nano(amount):
    from decimal import Decimal
    a = Decimal(str(amount))
    if a <= 0:
        raise ValueError("amount must be greater than 0")
    return int(a * Decimal(10) ** 9)


class TonLib:
    def __init__(self, mnemonics=None, api_key=None, endpoint=None, db=None, bot_id=None, base_url=None):
        self._mnemonics = _norm_mnemonics(mnemonics)
        self._api_key = api_key
        self._endpoint = _split(endpoint or MAINNET)
        self._db = db
        self._bot_id = bot_id
        self._base_url = (base_url or "http://127.0.0.1:8000").rstrip("/")

    # ------------------------------------------------------------------ storage helpers
    def _kv_get(self, key):
        if self._db is None or self._bot_id is None:
            return None
        from backend import models
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        return row.value if row else None

    def _kv_set(self, key, value):
        if self._db is None or self._bot_id is None:
            return
        from backend import models
        row = self._db.query(models.BotData).filter_by(bot_id=self._bot_id, key=key).first()
        if row:
            row.value = value
        else:
            self._db.add(models.BotData(bot_id=self._bot_id, key=key, value=value))
        self._db.commit()

    def _http(self, api_key=None, endpoint=None, testnet=False):
        base = _split(endpoint) if endpoint else (TESTNET if testnet else self._endpoint)
        key = api_key or self._api_key
        return base, ({"X-API-Key": key} if key else {})

    def _get(self, url, params=None, headers=None):
        r = requests.get(url, params=params, headers=headers, timeout=30)
        try:
            data = r.json()
        except Exception:
            raise RuntimeError(f"TON API error {r.status_code}")
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("ok") is False):
            msg = data.get("error") if isinstance(data, dict) else str(data)
            raise RuntimeError(f"TON API error: {msg}")
        return data

    # ------------------------------------------------------------------ wallet management
    def generateWallet(self):
        """New v4r2 wallet: {"address", "mnemonics" (list of 24 words)}; also stored as the active keys of this run."""
        from tonsdk.contract.wallet import Wallets, WalletVersionEnum
        mnemonics, _pub, _priv, wallet = Wallets.create(WalletVersionEnum.v4r2, workchain=0)
        self._mnemonics = list(mnemonics)
        from backend.sandbox.tbs_compat import Phrase
        return {"address": wallet.address.to_string(True, True, True), "mnemonics": Phrase(mnemonics),
                "version": "v4r2", "mnemonic": " ".join(mnemonics)}

    def setKeys(self, mnemonics):
        words = _norm_mnemonics(mnemonics)
        if not words or len(words) not in (12, 18, 24):
            raise ValueError("mnemonics must be a 12/18/24 word phrase")
        self._mnemonics = words
        try:
            from backend import security
            self._kv_set(KEYS_KEY, security.encrypt(" ".join(words)))   # kept encrypted for later commands
        except Exception:
            pass
        return True

    def _keys(self, mnemonics=None):
        m = _norm_mnemonics(mnemonics) or self._mnemonics
        if not m:
            stored = self._kv_get(KEYS_KEY)
            if stored:
                from backend import security
                m = _norm_mnemonics(security.decrypt(stored))
        if not m:
            raise ValueError("No mnemonics: call libs.TonLib.setKeys(...) or pass mnemonics=")
        return m

    def _wallet(self, mnemonics=None):
        from tonsdk.contract.wallet import Wallets, WalletVersionEnum
        _m, _pub, _priv, wallet = Wallets.from_mnemonics(self._keys(mnemonics), WalletVersionEnum.v4r2, workchain=0)
        return wallet

    def getWalletAddress(self, mnemonics=None):
        return self._wallet(mnemonics).address.to_string(True, True, True)

    # ------------------------------------------------------------------ TON operations
    def getBalance(self, address, api_key=None, endpoint=None, is_testnet=False):
        base, h = self._http(api_key, endpoint, is_testnet)
        data = self._get(f"{base}/getAddressBalance", {"address": address}, h)
        return int(data.get("result") or 0) / 1e9

    def sendTON(self, to_address, amount, comment=None, mnemonics=None, api_key=None, endpoint=None, is_testnet=False):
        """Send TON from the wallet of `mnemonics` (or the stored keys). Returns {"ok", "hash", "from", "to", "amount"}."""
        from tonsdk.utils import Address
        wallet = self._wallet(mnemonics)
        Address(to_address)  # validates
        nano = _nano(amount)
        base, h = self._http(api_key, endpoint, is_testnet)
        src = wallet.address.to_string(True, True, True)
        bal = int(self._get(f"{base}/getAddressBalance", {"address": src}, h).get("result") or 0)
        if bal < nano + 10_000_000:
            raise ValueError(f"insufficient balance: {bal / 1e9} TON")
        seqno = 0
        try:
            r = requests.post(f"{base}/runGetMethod", json={"address": src, "method": "seqno", "stack": []}, headers=h, timeout=30).json()
            if r.get("ok") and r["result"].get("exit_code") == 0:
                seqno = int(r["result"]["stack"][0][1], 16)
        except Exception:
            seqno = 0
        q = wallet.create_transfer_message(to_address, nano, seqno, payload=(str(comment) if comment else None))
        boc = base64.b64encode(q["message"].to_boc(False)).decode()
        r = requests.post(f"{base}/sendBoc", json={"boc": boc}, headers=h, timeout=30).json()
        if not r.get("ok"):
            raise RuntimeError(f"TON send failed: {r.get('error')}")
        return {"ok": True, "hash": (r.get("result") or {}).get("hash"), "from": src, "to": to_address,
                "amount": float(amount), "comment": comment, "seqno": seqno}

    def checkTONTransaction(self, address, api_key=None, endpoint=None, limit=10, is_testnet=False):
        """Recent transactions as [{"type": "incoming"|"outgoing", "from", "to", "amount", "comment", "hash", "time"}]."""
        base, h = self._http(api_key, endpoint, is_testnet)
        data = self._get(f"{base}/getTransactions", {"address": address, "limit": int(limit)}, h)
        out = []
        for tx in data.get("result") or []:
            inm = tx.get("in_msg") or {}
            outs = tx.get("out_msgs") or []
            src = inm.get("source") or ""
            if src:
                out.append({"type": "incoming", "from": src, "to": inm.get("destination"), "amount": int(inm.get("value") or 0) / 1e9,
                            "comment": inm.get("message") or "", "hash": (tx.get("transaction_id") or {}).get("hash"), "time": tx.get("utime")})
            for m in outs:
                out.append({"type": "outgoing", "from": m.get("source"), "to": m.get("destination"), "amount": int(m.get("value") or 0) / 1e9,
                            "comment": m.get("message") or "", "hash": (tx.get("transaction_id") or {}).get("hash"), "time": tx.get("utime")})
        return out

    # ------------------------------------------------------------------ TON Connect
    def _page(self, kind, ident):
        return f"{os.environ.get('BASE_URL') or self._base_url}/api/ton-connect/{kind}/{ident}"

    def create_ton_connect_session(self, user_id, expiry_seconds=86400):
        sid = _secrets.token_urlsafe(18)
        rec = {"user_id": str(user_id), "created": time.time(), "expires": time.time() + max(60.0, float(expiry_seconds)),
               "wallet_address": None, "challenge": _secrets.token_hex(16)}
        self._kv_set(SESSION_PREFIX + sid, json.dumps(rec))
        return {"session_id": sid, "connect_url": self._page("session", sid), "expires_at": rec["expires"]}

    def _session(self, session_id):
        raw = self._kv_get(SESSION_PREFIX + str(session_id))
        return json.loads(raw) if raw else None

    def verify_ton_connect_session(self, session_id):
        s = self._session(session_id)
        if not s:
            return {"status": "error", "message": "session not found"}
        if s["expires"] < time.time():
            return {"status": "expired", "message": "session expired"}
        if s.get("wallet_address"):
            return {"status": "connected", "wallet_address": s["wallet_address"], "public_key": s.get("public_key"), "user_id": s["user_id"]}
        return {"status": "pending", "message": "wallet not connected yet"}

    def register_ton_connect_wallet(self, session_id, wallet_address):
        s = self._session(session_id)
        if not s:
            return {"ok": False, "status": "error", "session_id": session_id, "error": "session not found", "message": "session not found"}
        if s["expires"] < time.time():
            return {"ok": False, "status": "error", "session_id": session_id, "error": "session expired", "message": "session expired"}
        try:
            from tonsdk.utils import Address
            Address(str(wallet_address))
        except Exception:
            return {"ok": False, "status": "error", "session_id": session_id, "error": "invalid wallet address", "message": "invalid wallet address"}
        s["wallet_address"] = str(wallet_address)
        self._kv_set(SESSION_PREFIX + str(session_id), json.dumps(s))
        return {"ok": True, "status": "success", "session_id": session_id, "message": "wallet connected", "wallet_address": s["wallet_address"]}

    def create_ton_connect_payload(self, callback_url, items=None, return_url=None):
        """Raw request: a TON Connect page with `items` (messages [{address, amount(nano), payload?}]) to be signed.
        When the wallet answers, the result is POSTed to `callback_url` (JSON: request_id, status, boc, wallet_address)."""
        rid = _secrets.token_urlsafe(18)
        payload = {"validUntil": int(time.time()) + 600, "messages": list(items or [])}
        rec = {"payload": payload, "callback_url": callback_url or "", "return_url": return_url or "",
               "status": "pending", "created": time.time()}
        self._kv_set(REQUEST_PREFIX + rid, json.dumps(rec))
        return {"request_id": rid, "connect_url": self._page("request", rid), "payload": payload}

    def request_ton_transaction(self, to_address, amount, comment=None, callback_url="", return_url=None):
        from tonsdk.utils import Address
        Address(to_address)
        msg = {"address": to_address, "amount": str(_nano(amount))}
        if comment:
            from tonsdk.boc import begin_cell
            cell = begin_cell().store_uint(0, 32).store_string(str(comment)).end_cell()
            msg["payload"] = base64.b64encode(cell.to_boc(False)).decode()
        out = self.create_ton_connect_payload(callback_url, [msg], return_url)
        out.update({"to": to_address, "amount": float(amount), "comment": comment})
        return out

    # ------------------------------------------------------------------ jettons
    def get_jetton_metadata(self, jetton_master_address, api_key=None, endpoint=None, is_testnet=False):
        base, h = self._http(api_key, endpoint, is_testnet)
        d = self._get(f"{_v3(base)}/jetton/masters", {"address": jetton_master_address, "limit": 1}, h)
        masters = d.get("jetton_masters") or []
        if not masters:
            raise ValueError("jetton master not found")
        m = masters[0]
        meta = ((d.get("metadata") or {}).get(m.get("address")) or {}).get("token_info", [{}])
        meta = (meta[0] if meta else {}) or {}
        content = m.get("jetton_content") or {}
        dec = int(meta.get("extra", {}).get("decimals") or content.get("decimals") or 9)
        return {"address": m.get("address"), "name": meta.get("name") or content.get("name"),
                "symbol": meta.get("symbol") or content.get("symbol"), "decimals": dec,
                "description": meta.get("description") or content.get("description"), "image": meta.get("image") or content.get("image"),
                "total_supply": int(m.get("total_supply") or 0) / (10 ** dec), "mintable": m.get("mintable"), "admin": m.get("admin_address")}

    def get_jetton_wallet_address(self, owner_address, jetton_master_address, api_key=None, endpoint=None, is_testnet=False):
        base, h = self._http(api_key, endpoint, is_testnet)
        d = self._get(f"{_v3(base)}/jetton/wallets", {"owner_address": owner_address, "jetton_address": jetton_master_address, "limit": 1}, h)
        w = d.get("jetton_wallets") or []
        if not w:
            raise ValueError("owner has no wallet for this jetton")
        return w[0].get("address")

    def get_jetton_balance(self, owner_address, jetton_master_address, api_key=None, endpoint=None, is_testnet=False):
        base, h = self._http(api_key, endpoint, is_testnet)
        d = self._get(f"{_v3(base)}/jetton/wallets", {"owner_address": owner_address, "jetton_address": jetton_master_address, "limit": 1}, h)
        w = d.get("jetton_wallets") or []
        if not w:
            return 0.0
        try:
            dec = int(self.get_jetton_metadata(jetton_master_address, api_key, endpoint, is_testnet).get("decimals") or 9)
        except Exception:
            dec = 9
        return int(w[0].get("balance") or 0) / (10 ** dec)

    def request_jetton_transfer(self, to_address, jetton_master_address, amount, comment=None, callback_url="", return_url=None):
        """The user signs a standard jetton `transfer` message from their own jetton wallet (resolved when they connect)."""
        from tonsdk.utils import Address
        Address(to_address)
        Address(jetton_master_address)
        a = float(amount)
        if a <= 0:
            raise ValueError("amount must be greater than 0")
        out = self.create_ton_connect_payload(callback_url, [], return_url)
        rid = out["request_id"]
        rec = json.loads(self._kv_get(REQUEST_PREFIX + rid))
        rec["jetton"] = {"master": jetton_master_address, "to": to_address, "amount": a, "comment": comment or ""}
        self._kv_set(REQUEST_PREFIX + rid, json.dumps(rec))
        out.update({"to": to_address, "jetton": jetton_master_address, "amount": a, "comment": comment})
        return out

    # ------------------------------------------------------------------ TBS aliases
    def createWallet(self): return self.generateWallet()
    def getAddress(self, mnemonics=None): return self.getWalletAddress(mnemonics)
    def storeKey(self, mnemonics): return self.setKeys(mnemonics)
    def balance(self, address, api_key=None, endpoint=None, is_testnet=False): return self.getBalance(address, api_key=api_key, endpoint=endpoint, is_testnet=is_testnet)
    def send(self, to_address, amount, comment=None, mnemonics=None, api_key=None, endpoint=None, is_testnet=False): return self.sendTON(to_address, amount, comment=comment, mnemonics=mnemonics, api_key=api_key, endpoint=endpoint, is_testnet=is_testnet)
    def transactions(self, address, limit=10, api_key=None, endpoint=None, is_testnet=False): return self.checkTONTransaction(address, api_key=api_key, endpoint=endpoint, limit=limit, is_testnet=is_testnet)
    def connectSession(self, user_id, expiry_seconds=86400): return self.create_ton_connect_session(user_id, expiry_seconds)
    def verifySession(self, session_id): return self.verify_ton_connect_session(session_id)
    def register(self, session_id, wallet_address): return self.register_ton_connect_wallet(session_id, wallet_address)
    def requestPayment(self, *a, **kw): return self.request_ton_transaction(*a, **kw)
    def requestToken(self, *a, **kw): return self.request_jetton_transfer(*a, **kw)
    def tokenBalance(self, *a, **kw): return self.get_jetton_balance(*a, **kw)
    def tokenInfo(self, *a, **kw): return self.get_jetton_metadata(*a, **kw)
    def getJettonWallet(self, *a, **kw): return self.get_jetton_wallet_address(*a, **kw)
    def getJettonBalance(self, *a, **kw): return self.get_jetton_balance(*a, **kw)
