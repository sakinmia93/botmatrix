"""TeleBot Studio (TBS) naming layer.

TBS documents the same platform with different spellings (Account.storeData, Lib.Random.hex,
Lib.Security.hashSHA256, Admin.res ...). Everything here is a thin, real implementation on top of
the existing engine - no mocks. `install()` is called once from context_objects.
"""
import base64, hashlib, hmac, io, json, secrets as _secrets, urllib.parse


# ---------- global helper namespaces ----------
class JSONNS:
    """TBS `JSON` object."""
    @staticmethod
    def encode(obj, **k):
        from backend.sandbox.context_objects import _json_default
        k.setdefault("ensure_ascii", False)
        k.setdefault("default", _json_default)
        return json.dumps(obj, **k)
    @staticmethod
    def decode(s, **k):
        if isinstance(s, (bytes, bytearray)):
            s = s.decode("utf-8")
        return json.loads(s, **k)
    dumps = encode
    parse = decode
    loads = decode


class URLNS:
    @staticmethod
    def encode(text):
        return urllib.parse.quote(str(text), safe="")
    @staticmethod
    def decode(text):
        return urllib.parse.unquote(str(text))
    @staticmethod
    def parseQuery(query):
        q = str(query or "")
        if "?" in q:
            q = q.split("?", 1)[1]
        out = {}
        for k, v in urllib.parse.parse_qsl(q, keep_blank_values=True):
            if k in out:
                out[k] = out[k] + [v] if isinstance(out[k], list) else [out[k], v]
            else:
                out[k] = v
        return out


def _b(x):
    return x if isinstance(x, (bytes, bytearray)) else str(x).encode("utf-8")


class HashNS:
    @staticmethod
    def md5(text): return hashlib.md5(_b(text)).hexdigest()
    @staticmethod
    def sha1(text): return hashlib.sha1(_b(text)).hexdigest()
    @staticmethod
    def sha256(text): return hashlib.sha256(_b(text)).hexdigest()
    @staticmethod
    def sha512(text): return hashlib.sha512(_b(text)).hexdigest()


# ---------- Admin ----------
class AdminObject:
    """TBS `Admin.res(name)` - bot-wide resource administration."""
    def __init__(self, db, bot_id, uid=None):
        self._db, self._bot_id, self._uid = db, bot_id, uid
    def res(self, resource_name, user=None):
        from backend.sandbox.libs.resources_lib import ResourcesLib
        return ResourcesLib(self._db, self._bot_id, self._uid).adminRes(resource_name, user=user)


def _handle_exportAllData(self, limit=10):
    return self.getAllData(limit)

def _handle_removeAllData(self, user=None):
    if user is None:
        return self.deleteAllUsersData(all_data=False)
    return self.deleteSingleUserData(user, all_data=False)


# ---------- security ----------
def _decode_bin(v):
    s = str(v).strip()
    try:
        return bytes.fromhex(s)
    except Exception:
        pass
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return None

def _verifyEd25519(self, public_key, payload, signature):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pk, sg = _decode_bin(public_key), _decode_bin(signature)
        if not pk or not sg or len(pk) != 32 or pk == b"\x00" * 32:
            return False
        Ed25519PublicKey.from_public_bytes(pk).verify(sg, _b(payload))
        return True
    except Exception:
        return False

def _eq(a, b):
    return hmac.compare_digest(str(a).strip().lower(), str(b).strip().lower())

def _verifyPaymentGatewayWebhook(self, gateway, payload, signature, secret_key):
    g = str(gateway or "").lower().replace("_", "").replace("-", "").replace(" ", "")
    body = _b(payload)
    key = _b(secret_key)
    try:
        if g in ("oxapay", "coinpayments", "coinbase", "coinbasecommerce", "cryptomus_hmac", "plisio"):
            algo = hashlib.sha256 if g.startswith("coinbase") else hashlib.sha512
            return _eq(hmac.new(key, body, algo).hexdigest(), signature)
        if g == "nowpayments":
            try:
                obj = json.loads(body.decode("utf-8"))
                body = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
            except Exception:
                pass
            return _eq(hmac.new(key, body, hashlib.sha512).hexdigest(), signature)
        if g == "cryptomus":
            try:
                obj = json.loads(body.decode("utf-8")); obj.pop("sign", None)
                body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("/", "\\/").encode()
            except Exception:
                pass
            exp = hashlib.md5(base64.b64encode(body) + key).hexdigest()
            return _eq(exp, signature)
        if g in ("coinsway", "ed25519"):
            return _verifyEd25519(self, secret_key, payload, signature)
        if g in ("stripe", "generic", "hmacsha256"):
            return _eq(hmac.new(key, body, hashlib.sha256).hexdigest(), signature)
    except Exception:
        return False
    raise ValueError("unsupported gateway: %s (oxapay, coinpayments, coinbase, nowpayments, cryptomus, coinsway, generic)" % gateway)


# ---------- random ----------
def _rnd_boolean(self): return _secrets.randbelow(2) == 1
def _rnd_hex(self, length=16): return _secrets.token_hex((int(length) + 1) // 2)[: int(length)]
def _rnd_bytes(self, length=16): return _secrets.token_bytes(int(length))
def _rnd_password(self, length=12, *a, **k): return self.randomPassword(length, *a, **k)
def _rnd_sample(self, seq, k=1): return self.randomSample(seq, k)
def _rnd_range(self, start, stop=None, step=1):
    import random as _r
    if stop is None: start, stop = 0, start
    return _r.randrange(int(start), int(stop), int(step or 1))
def _rnd_gauss(self, mu=0.0, sigma=1.0): return self.randomGaussian(mu, sigma)


# ---------- gifts ----------
def _gift_settings_dispatch(cls):
    cls.getGiftById = lambda self, gift_id: self.get_gift_by_id(gift_id)
    cls.getGiftsByCategory = lambda self, category=None: (
        self.get_gift_catalog(category=category) if category else self.get_gifts_by_category())
    cls.searchGifts = lambda self, query: self.search_gifts(query)
    cls.sendGiftById = lambda self, user_id, gift_id, message=None, text_parse_mode=None, bot_token=None: self.send_gift_by_id(user_id, gift_id, message=message, bot_token=bot_token)
    cls.getGiftStats = lambda self: self.get_gift_stats()
    cls.setGiftSetting = lambda self, name, value: self.set_gift_setting(name, value)
    cls.getGiftSetting = lambda self, name, default=None: self.get_gift_setting(name, default)
    cls.getAllGiftSettings = lambda self: self.get_all_gift_settings()
    old_send = cls.sendGift
    cls.sendGift = lambda self, user_id, gift_key, message=None, text_parse_mode=None, bot_token=None: old_send(self, user_id, gift_key, message=message, bot_token=bot_token)


def install():
    from backend.sandbox import context_objects as co
    from backend.sandbox.libs.random_lib import RandomLib
    from backend.sandbox.libs.security_lib import SecurityLib
    from backend.sandbox.libs.premium_gift_lib import PremiumGiftLib
    from backend.sandbox.libs.web3_lib import Web3Lib
    from backend.sandbox.libs.resources_lib import ResourceHandle
    from backend.sandbox.libs import image_lib

    RandomLib.boolean = _rnd_boolean
    RandomLib.hex = _rnd_hex
    RandomLib.bytes = _rnd_bytes
    RandomLib.password = _rnd_password
    RandomLib.sample = _rnd_sample
    RandomLib.range = _rnd_range
    RandomLib.gaussian = _rnd_gauss
    RandomLib.integer = lambda self, a, b=None: self.randomInt(a, b)
    RandomLib.decimal = lambda self, a=0.0, b=1.0: self.randomFloat(a, b)
    RandomLib.ascii = lambda self, length=8: self.randomAscii(length)

    SecurityLib.verifyEd25519 = _verifyEd25519
    SecurityLib.verifyPaymentGatewayWebhook = _verifyPaymentGatewayWebhook
    SecurityLib.hashSHA256 = lambda self, text: hashlib.sha256(_b(text)).hexdigest()
    SecurityLib.hashSHA512 = lambda self, text: hashlib.sha512(_b(text)).hexdigest()
    SecurityLib.hashMD5 = lambda self, text: hashlib.md5(_b(text)).hexdigest()

    _gift_settings_dispatch(PremiumGiftLib)

    def _is_num(x):
        try:
            float(x); return True
        except Exception:
            return False

    def _gas(k, gas_limit, gas_price):
        if gas_limit: k["gas"] = int(gas_limit)
        if gas_price: k["gasPrice"] = int(round(float(gas_price) * 10**9))   # TBS: Gwei
        return k

    def sendCoin(self, *a, **k):
        """TBS: sendCoin(network, to, value, private_key, gas_limit, gas_price, proxy, estimate_gas, retry);
        TBC: sendCoin(value, to, rpc_url, private_key, network, retry, estimate_gas)."""
        if a and isinstance(a[0], str) and not _is_num(a[0]):
            names = ["network", "to", "value", "private_key", "gas_limit", "gas_price", "proxy", "estimate_gas", "retry"]
            kw = dict(zip(names, a)); kw.update(k)
            extra = _gas({}, kw.pop("gas_limit", None), kw.pop("gas_price", None)); kw.pop("proxy", None)
            return self.sendNativeCoin(kw["value"], kw["to"], network=kw.get("network"), private_key=kw.get("private_key"),
                                       estimate_gas=kw.get("estimate_gas", True), retry=kw.get("retry", False), **extra)
        names = ["value", "to", "rpc_url", "private_key", "network", "retry", "estimate_gas"]
        kw = dict(zip(names, a)); kw.update(k)
        extra = _gas({}, kw.pop("gas_limit", None), kw.pop("gas_price", None)); kw.pop("proxy", None)
        kw.setdefault("estimate_gas", True)
        return self.sendNativeCoin(kw.pop("value"), kw.pop("to"), **kw, **extra)

    def sendToken(self, *a, **k):
        """TBS: sendToken(network, to, value, contract_address, private_key, ...);
        TBC: sendToken(value, to, contract_address, rpc_url, private_key, network, retry, estimate_gas)."""
        if a and isinstance(a[0], str) and not _is_num(a[0]):
            names = ["network", "to", "value", "contract_address", "private_key", "gas_limit", "gas_price", "proxy", "estimate_gas", "retry"]
            kw = dict(zip(names, a)); kw.update(k)
            extra = _gas({}, kw.pop("gas_limit", None), kw.pop("gas_price", None)); kw.pop("proxy", None)
            return self.sendETHER(kw["value"], kw["to"], network=kw.get("network"), contract_address=kw.get("contract_address"),
                                  private_key=kw.get("private_key"), estimate_gas=kw.get("estimate_gas", True), retry=kw.get("retry", False), **extra)
        names = ["value", "to", "contract_address", "rpc_url", "private_key", "network", "retry", "estimate_gas"]
        kw = dict(zip(names, a)); kw.update(k)
        extra = _gas({}, kw.pop("gas_limit", None), kw.pop("gas_price", None)); kw.pop("proxy", None)
        kw.setdefault("estimate_gas", True)
        return self.sendETHER(kw.pop("value"), kw.pop("to"), **kw, **extra)
    Web3Lib.sendCoin = sendCoin
    Web3Lib.sendToken = sendToken
    Web3Lib.fetchBalance = lambda self, address, network=None, rpc_url=None, **k: self.getBalance(address, rpc_url=rpc_url, network=network, **k)
    Web3Lib.fetchTokenBalance = lambda self, address, contract_address, network=None, rpc_url=None, **k: self.getTokenBalance(address, contract_address, rpc_url=rpc_url, network=network, **k)

    ResourceHandle.exportAllData = _handle_exportAllData
    ResourceHandle.removeAllData = _handle_removeAllData

    if hasattr(image_lib.CVLib, "perspective_transform"):
        image_lib.CVLib.perspectiveTransform = image_lib.CVLib.perspective_transform

    # ---- Account (TBS spelling) ----
    A = co.AccountObject
    A.storeData = lambda self, name, data: self.saveData(name, data)
    A.fetchData = lambda self, name, default=None: (lambda v: default if v is None else v)(self.getData(name))
    A.removeData = lambda self, name: self.deleteData(name)
    def _acct_export(self, name=None, output_format="json"):
        fmt = str(output_format or "json").lower()
        data = self.getAllData(name) if name is not None else self.getAllData()
        if fmt == "json":
            content, ext = json.dumps(data, ensure_ascii=False, indent=2, default=str), "json"
        elif fmt == "csv":
            import csv as _csv
            sio = io.StringIO(); w = _csv.writer(sio); w.writerow(["name", "value"])
            for k, v in data.items():
                w.writerow([k, json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v])
            content, ext = sio.getvalue(), "csv"
        else:
            content, ext = "\n".join(f"{k}={v}" for k, v in data.items()), "txt"
        buf = io.BytesIO(content.encode("utf-8")); buf.name = f"account_data.{ext}"; buf.seek(0)
        return buf
    A.exportAllData = _acct_export
    A.exportData = lambda self, name, output_format="json": _acct_export(self, name, output_format)
    A.stats = lambda self: self.get_stats()
    A.botStats = lambda self, botid: self.get_bot_stats(botid)
    A.botsStats = lambda self: self.get_bots_stats()
    A.botUsage = lambda self, botid, period="all": self.get_bot_usage(botid, period)
    A.cloneBot = lambda self, botid, new_token=None: self.clone_bot(botid, new_token)
    A.banUser = lambda self, user_id, botid=None: self.blockUser(user_id, botid)
    A.unbanUser = lambda self, user_id, botid=None: self.unblockUser(user_id)
    A.bannedUsers = lambda self, botid=None: self.getBlockedUsers(botid)
    A.exportBannedUsersFile = lambda self, botid=None, output_format="csv": self.getBlockedUsersFile(botid, output_format)
    def _acct_res(self, resource_name):
        from backend.sandbox.libs.resources_lib import ResourcesLib
        return ResourcesLib(self._db, self._account_storage_bot_id() or -1, None).accountRes(resource_name)
    A.res = _acct_res

    install_bot_methods()
    install_bot_misc()
    # ---- User ----
    U = co.UserObject
    if not hasattr(U, "exportAllData"):
        U.exportAllData = lambda self, name=None, output_format="json": self.getAllData(output_format=output_format)
    if not hasattr(U, "exportUserData"):
        U.exportUserData = lambda self, user, output_format="json": co.UserObject(self._db, self._bot_id, int(user)).getAllData(output_format=output_format)


# ================= hybrid values =================
class HybridStr(str):
    """A plain string that also answers dict-style lookups (TBC dict result <-> TBS string result)."""
    _parts = None
    def __getitem__(self, i):
        if isinstance(i, str) and self._parts is not None:
            return self._parts[i]
        return str.__getitem__(self, i)
    def get(self, k, default=None):
        return (self._parts or {}).get(k, default)
    def keys(self):
        return (self._parts or {}).keys()
    def __contains__(self, k):
        if self._parts is not None and isinstance(k, str) and k in self._parts:
            return True
        return str.__contains__(self, k)


def hybrid(text, parts):
    h = HybridStr(text)
    h._parts = parts
    return h


# ================= Lib.AI (TBS) =================
class _TBSAIClient:
    def __init__(self, provider="openai", api_key=None, base_url=None, timeout=120):
        from backend.sandbox.libs import openai_lib as ol
        self.provider = str(provider or "openai").lower()
        if self.provider not in ("openai", "gemini"):
            raise ValueError("provider must be 'openai' or 'gemini'")
        if not api_key:
            raise ValueError("apiKey is required")
        if self.provider == "gemini":
            self._c = ol.GeminiClient(api_key=api_key)
            self.default_model = "gemini-2.0-flash"
        else:
            self._c = ol.OpenAIClient(api_key=api_key, timeout=timeout, base_url=base_url or "https://api.openai.com/v1")
            self.default_model = "gpt-4o-mini"

    def chat(self, model=None, messages=None, temperature=0.7, max_tokens=None, **kw):
        if isinstance(model, list) and messages is None:
            model, messages = None, model
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if max_tokens is not None:
            kw["max_tokens"] = int(max_tokens)
        if self.provider == "gemini":
            return self._c.create_chat_completion(model or self.default_model, messages or [])
        return self._c.create_chat_completion(model or self.default_model, messages or [], temperature, **kw)

    def createAssistant(self, model=None, name="assistant", instructions="", tools=None):
        if self.provider == "gemini":
            return self._c.create_assistant(name=name, instructions=instructions, model=model or self.default_model)
        kw = {"tools": tools} if tools else {}
        return self._c.create_assistant(name=name, instructions=instructions, model=model or self.default_model, **kw)

    def createThread(self):
        return self._c.create_thread()

    def addMessage(self, thread_id, role="user", content=""):
        if content == "" and role not in ("user", "assistant"):
            role, content = "user", role
        return self._c.create_message(thread_id, content, role=role)

    def run(self, thread_id, assistant_id):
        return self._c.create_run(thread_id, assistant_id)

    def getStatus(self, thread_id, run_id):
        if self.provider == "gemini":
            return {"id": run_id, "status": "completed"}
        return self._c.get_run(thread_id, run_id)

    def getMessages(self, thread_id, limit=20):
        r = self._c.list_messages(thread_id) if self.provider == "openai" else self._c.list_messages(thread_id, limit)
        if isinstance(r, dict) and isinstance(r.get("data"), list):
            r = dict(r); r["data"] = r["data"][: int(limit)]
        return r


class _TBSAssistant:
    def __init__(self, provider="openai", apiKey=None, create_new=False, name="Assistant", instructions="", model=None):
        from backend.sandbox.libs import openai_lib as ol
        cl = _TBSAIClient(provider, apiKey)
        if cl.provider == "gemini":
            self._a = ol.GeminiAIAssistant(cl._c, create_new=create_new, name=name, instructions=instructions, model=model or cl.default_model)
        else:
            self._a = ol.AIAssistant(cl._c, create_new=create_new, name=name, instructions=instructions, model=model or cl.default_model)

    def start(self):
        return self._a.start_conversation()

    def send(self, message):
        return self._a.send_message(message)

    def history(self, limit=20):
        return self._a.get_conversation_history()


class TBSAI:
    """`Lib.AI`: `Lib.AI.client(provider, apiKey, baseUrl)` -> client; `Lib.AI.Assistant(...)`; legacy shortcuts still work."""
    def __init__(self, oai, gem):
        self.openai = oai
        self.gemini = gem
        outer = self

        class _Callable:
            def __call__(self, provider="openai", apiKey=None, baseUrl=None, **kw):
                key = apiKey or kw.get("api_key")
                if not key:
                    lib = outer.gemini if str(provider).lower() == "gemini" else outer.openai
                    key = getattr(lib, "_api_key", None) or getattr(lib, "api_key", None)
                return _TBSAIClient(provider, key, baseUrl or kw.get("base_url"))
            def __getattr__(self, n):
                if n.startswith("_"):
                    raise AttributeError(n)
                return getattr(outer.openai, n)
        self.client = _Callable()

    def Assistant(self, provider="openai", apiKey=None, create_new=False, name="Assistant", instructions="", model=None, **kw):
        return _TBSAssistant(provider, apiKey or kw.get("api_key"), create_new, name, instructions, model)

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return getattr(self.openai, n)


# ================= Bot.* TBS signatures =================
class AttrDict(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def install_bot_methods():
    from backend.sandbox import context_objects as co
    from backend import models
    B = co.BotDataObject
    _orig_after = B.runCommandAfter

    def _is_number(x):
        if isinstance(x, bool):
            return False
        if isinstance(x, (int, float)):
            return True
        try:
            float(str(x)); return True
        except Exception:
            return False

    def scheduleCommand(self, *a, **kw):
        """TBS: scheduleCommand(delay_seconds, command, user_id=None, chat_id=None, params=None, **options)
        TBC style scheduleCommand(command, seconds, options) is accepted too."""
        a = list(a)
        if a and isinstance(a[0], str) and not _is_number(a[0]) and len(a) >= 2:      # (command, seconds[, options])
            command, delay = a[0], a[1]
            rest = a[2:]
            options = rest[0] if rest else kw.pop("options", None)
            user_id = kw.pop("user_id", None); chat_id = kw.pop("chat_id", None)
        else:
            delay = a.pop(0) if a else kw.pop("delay_seconds", kw.pop("seconds", kw.pop("timeout", None)))
            command = a.pop(0) if a else kw.pop("command", None)
            user_id = a.pop(0) if a else kw.pop("user_id", None)
            chat_id = a.pop(0) if a else kw.pop("chat_id", None)
            if a: kw["params"] = a.pop(0)
            options = kw.pop("options", None)
        kw.pop("seconds", None); kw.pop("delay_seconds", None)
        if delay is None or command is None:
            raise ValueError("scheduleCommand(delay_seconds, command, ...) requires a delay and a command")
        saved = None
        if user_id is not None:
            saved = self._runtime.get("user_id")
            self._runtime["user_id"] = int(user_id)
        try:
            r = _orig_after(self, delay, command, options=options, **kw)
        finally:
            if saved is not None:
                self._runtime["user_id"] = saved
        out = AttrDict(r if isinstance(r, dict) else {"id": r})
        out.setdefault("ok", True)
        return out
    B.scheduleCommand = scheduleCommand

    def cancelScheduledCommand(self, task_id):
        r = self.cancelScheduledTask(task_id)
        return bool(r.get("ok")) if isinstance(r, dict) else bool(r)
    B.cancelScheduledCommand = cancelScheduledCommand

    def resetScheduledCommands(self, user_id=None, bot_id=None):
        from backend.scheduler.scheduler import list_pending_tasks, cancel_task
        n = 0
        for tsk in list_pending_tasks(self._db, self._bot_id, limit=100000):
            if user_id is not None and str(tsk.get("telegram_user_id")) != str(user_id):
                continue
            if cancel_task(self._db, tsk.get("id"), self._bot_id).get("ok"):
                n += 1
        return {"ok": True, "cleared": n, "cancelled": n, "user_id": user_id}
    B.resetScheduledCommands = resetScheduledCommands

    def cancelBroadcast(self, broadcast_id=None):
        """TBS: cancelBroadcast(id) cancels one; cancelBroadcast() cancels every running broadcast of the bot."""
        if broadcast_id is not None:
            r = self.stopBroadcast(broadcast_id)
            ok = bool(r.get("ok", True)) if isinstance(r, dict) else bool(r)
            return {"ok": ok, "deleted_count": 1 if ok else 0}
        n = 0
        for j in self.listBroadcasts(limit=1000):
            if str(j.get("status")) in ("running", "queued", "paused", "pending"):
                try:
                    r = self.stopBroadcast(j.get("id"))
                    if not isinstance(r, dict) or r.get("ok", True):
                        n += 1
                except Exception:
                    pass
        return {"ok": True, "deleted_count": n}
    B.cancelBroadcast = cancelBroadcast

    def sendCloneBroadcast(self, broadcast_id=None, **kw):
        if broadcast_id is None:
            kw.setdefault("mode", "single")
            return self.broadcast(**kw)
        j = self.rerunBroadcast(broadcast_id)
        return {"ok": True, "broadcast_id": j.get("broadcast_id"), "status": j.get("status"), "estimated_users": j.get("total")}
    B.sendCloneBroadcast = sendCloneBroadcast


def install_bot_misc():
    from backend.sandbox import context_objects as co
    B = co.BotDataObject
    _old_create, _old_send, _old_verify = B.createCaptcha, B.sendCaptcha, B.verifyCaptcha

    def _uid_like(x):
        return isinstance(x, int) and not isinstance(x, bool) or (isinstance(x, str) and x.lstrip("-").isdigit() and len(x) >= 5)

    def createCaptcha(self, *a, **kw):
        """TBS: createCaptcha(user_id) stores the answer for that user. TBC: createCaptcha(mode, captcha)."""
        if (a and _uid_like(a[0])) or "user_id" in kw:
            uid = int(a[0] if a else kw.pop("user_id"))
            c = self.genCaptcha()
            self.saveData(f"__captcha_{uid}", c.captcha_text)
            return c
        return _old_create(self, *a, **kw)
    B.createCaptcha = createCaptcha

    def sendCaptcha(self, *a, **kw):
        """TBS: sendCaptcha(user_id) sends the captcha image to the user."""
        if (a and _uid_like(a[0])) or "user_id" in kw:
            uid = int(a[0] if a else kw.pop("user_id"))
            c = self.genCaptcha()
            from backend.telegram.bot_wrapper import BotWrapper
            from backend import models
            b = self._db.query(models.Bot).filter_by(id=self._bot_id).first()
            BotWrapper(b.token, default_chat_id=uid).sendPhoto(chat_id=uid, photo=c.captcha_url, caption=kw.get("caption", "Enter the code:"))
            self.saveData(f"__captcha_{uid}", c.captcha_text)
            return {"ok": True, "captcha": c}
        return _old_send(self, *a, **kw)
    B.sendCaptcha = sendCaptcha

    def verifyCaptcha(self, *a, **kw):
        """TBS: verifyCaptcha(user_id, code). TBC: verifyCaptcha(answer, user_id=None)."""
        if len(a) == 2 and _uid_like(a[0]) and not (isinstance(a[1], int)):
            return _old_verify(self, a[1], user_id=a[0])
        if "code" in kw:
            return _old_verify(self, kw["code"], user_id=kw.get("user_id", a[0] if a else None))
        return _old_verify(self, *a, **kw)
    B.verifyCaptcha = verifyCaptcha

    import secrets, time, string
    B.randomID = lambda self: "".join(secrets.choice(string.digits) for _ in range(8))
    B.uniqueID = lambda self: str(int(time.time() * 1000)) + secrets.token_hex(2)


class Phrase(list):
    """Mnemonic: a list of words (TBC) that also acts like the 24-word string (TBS): str(), .split(), f-strings, `in`."""
    def __str__(self): return " ".join(self)
    __repr__ = lambda self: repr(" ".join(self))
    def split(self, sep=None, maxsplit=-1): return " ".join(self).split(sep, maxsplit)
    def strip(self, *a): return " ".join(self).strip(*a)
    def __format__(self, spec): return format(" ".join(self), spec)
    def startswith(self, *a): return " ".join(self).startswith(*a)
    def encode(self, *a, **k): return " ".join(self).encode(*a, **k)
    def __add__(self, o): return " ".join(self) + o if isinstance(o, str) else list.__add__(self, o)
    def __radd__(self, o): return o + " ".join(self) if isinstance(o, str) else list.__add__(list(o), self)
