"""TBC payment gateway integrations: Oxapay, Coinbase, CoinPayments.

These expose the documented call surface and make REAL signed HTTP calls to each
provider. Live charges require real API keys passed by the bot author; without
keys, methods return structured errors instead of silent failures.

NOTE: libs.MDxchange was intentionally removed from this build (not needed for
this project) — it is no longer registered in libs_namespace.py.
"""
from __future__ import annotations
from typing import Optional
import hashlib
import hmac
import time
import requests
from urllib.parse import urlencode


class OxapayLib:
    def __init__(self, merchant_api_key=None):
        self._key = merchant_api_key

    def post(self, merchant_api_key=None):
        key = merchant_api_key or self._key
        self._key = key
        return OxapayClient(key)

    def client(self, merchant_api_key=None):
        return self.post(merchant_api_key)


class OxapayClient:
    def __init__(self, key):
        self.key = key

    def createInvoice(self, amount, currency="USD", callback_url=None, **kwargs):
        return self.create_invoice(amount, currency=currency, callback_url=callback_url, **kwargs)

    def createAddress(self, currency="USDT", callback_url=None, **kwargs):
        if not self.key:
            return {"ok": False, "error": "merchant_api_key required"}
        try:
            r = requests.post(
                "https://api.oxapay.com/merchants/request/staticaddress",
                json={"merchant": self.key, "currency": currency, "callback_url": callback_url, **kwargs},
                timeout=30,
            )
            return {"ok": r.ok, "status_code": r.status_code, "data": r.json() if r.content else {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def invoice(self, *a, **k):
        return self.create_invoice(*a, **k)

    def payout(self, amount, address, currency="USDT", **kwargs):
        if not self.key:
            return {"ok": False, "error": "merchant_api_key required"}
        try:
            r = requests.post(
                "https://api.oxapay.com/api/send",
                json={"key": self.key, "amount": amount, "currency": currency, "address": address, **kwargs},
                timeout=30,
            )
            return {"ok": r.ok, "status_code": r.status_code, "data": r.json() if r.content else {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def allowance(self):
        if not self.key:
            return {"ok": False, "error": "merchant_api_key required"}
        try:
            r = requests.post("https://api.oxapay.com/api/balance", json={"key": self.key}, timeout=30)
            return {"ok": r.ok, "data": r.json() if r.content else {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_invoice(self, amount, currency="USD", callback_url=None, **kwargs):
        if not self.key:
            return {"ok": False, "error": "merchant_api_key required"}
        payload = {"amount": amount, "currency": currency, "callback_url": callback_url, **kwargs}
        try:
            r = requests.post(
                "https://api.oxapay.com/merchants/request",
                json={**payload, "merchant": self.key},
                timeout=30,
            )
            return {"ok": r.ok, "status_code": r.status_code, "data": r.json() if r.content else {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class CoinbaseLib:
    def __init__(self):
        self.ApiKey = None
        self.Secret = None

    def setKeys(self, ApiKey, Secret):
        self.ApiKey = ApiKey
        self.Secret = Secret
        return True

    def post(self, ApiKey=None, Secret=None):
        return CoinbaseClient(ApiKey or self.ApiKey, Secret or self.Secret)


class CoinbaseClient:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret

    def create_charge(self, name, amount, currency="USD", **kwargs):
        if not self.key:
            return {"ok": False, "error": "ApiKey required"}
        headers = {"X-CC-Api-Key": self.key, "X-CC-Version": "2018-03-22", "Content-Type": "application/json"}
        body = {"name": name, "local_price": {"amount": str(amount), "currency": currency}, "pricing_type": "fixed_price", **kwargs}
        try:
            r = requests.post("https://api.commerce.coinbase.com/charges", json=body, headers=headers, timeout=30)
            return {"ok": r.ok, "status_code": r.status_code, "data": r.json() if r.content else {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class CoinpaymentsLib:
    def __init__(self):
        self.public_key = None
        self.private_key = None

    def setKeys(self, public_key, private_key):
        self.public_key = public_key
        self.private_key = private_key
        return {"ok": "success"}

    def post(self, public_key=None, private_key=None):
        return CoinpaymentsClient(public_key or self.public_key, private_key or self.private_key)


class CoinpaymentsClient:
    def __init__(self, public_key, private_key):
        self.public_key = public_key
        self.private_key = private_key

    _API_URL = "https://www.coinpayments.net/api.php"

    def _call(self, cmd, **params):
        if not self.public_key or not self.private_key:
            return {"ok": False, "error": "public_key and private_key required"}
        payload = {"version": 1, "cmd": cmd, "key": self.public_key, "format": "json"}
        payload.update({k: v for k, v in params.items() if v is not None})
        encoded = urlencode(payload)
        hmac_sig = hmac.new(
            self.private_key.encode(), encoded.encode(), hashlib.sha512
        ).hexdigest()
        try:
            r = requests.post(
                self._API_URL,
                data=payload,
                headers={"HMAC": hmac_sig, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            data = r.json() if r.content else {}
            ok = r.ok and str(data.get("error", "")).lower() == "ok"
            return {"ok": ok, "status_code": r.status_code, "data": data.get("result", data)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_transaction(self, amount, currency1, currency2, buyer_email=None, **kwargs):
        """Real call to CoinPayments' create_transaction API (HMAC-SHA512 signed)."""
        return self._call(
            "create_transaction",
            amount=amount,
            currency1=currency1,
            currency2=currency2,
            buyer_email=buyer_email,
            **kwargs,
        )

    def get_basic_info(self):
        return self._call("get_basic_info")

    def get_tx_info(self, txid):
        return self._call("get_tx_info", txid=txid)

    def balances(self):
        return self._call("balances")

