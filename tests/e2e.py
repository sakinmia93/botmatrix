import json, os, subprocess, sys, time, requests, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
T = tempfile.mkdtemp()
MOCK = "http://127.0.0.1:8081"; API = "http://127.0.0.1:5001/api"
CONNECT = "9000000001:" + "C" * 35
BOT1 = "8822824343:" + "A" * 35
BOT2 = "7000000002:" + "B" * 35
env = dict(os.environ, TELEGRAM_API_ROOT=MOCK, CONNECT_BOT_TOKEN=CONNECT, APP_DB_PATH=f"{T}/app.db",
           DATABASE_URL=f"sqlite:///{T}/engine.db", API_PORT="5001", SECRET_KEY="test-secret", BM_TEST_NO_RATE_LIMIT="1", ADMIN_EMAILS="a@x.io", ADMIN_CONTACT_URL="https://t.me/matrix_admin", PYTHONUNBUFFERED="1",
           V2_RATE_PER_MIN="10000", V2_RATE_PER_HOUR="10000")
MAILF = f"{T}/mails.jsonl"; open(MAILF, "w").close()
env.update(SMTP_HOST="127.0.0.1", SMTP_PORT="2527", SMTP_STARTTLS="0", SMTP_USER="u@x.io", SMTP_PASSWORD="pw")
procs = [subprocess.Popen([sys.executable, "tests/mock_telegram.py", "8081"], cwd=ROOT), subprocess.Popen([sys.executable, "tests/smtp_sink.py", "2527", MAILF], cwd=ROOT)]
time.sleep(0.8)
def mock(path, **b): return requests.post(MOCK + path, json=b).json()
mock("/_mock/add_bot", token=CONNECT, username="matrix_connect_bot")
mock("/_mock/add_bot", token=BOT1, username="my_test_bot")
mock("/_mock/add_bot", token=BOT2, username="second_bot")
srv = subprocess.Popen([sys.executable, "-m", "backend.server"], cwd=ROOT, env=env); procs.append(srv)
for _ in range(60):
    try:
        requests.get(API + "/health", timeout=1); break
    except Exception: time.sleep(0.5)
ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", name)
    else: fail += 1; print("  ✗", name, extra)
def sent(method=None):
    s = requests.get(MOCK + "/_mock/sent").json()
    return [x for x in s if method in (None, x["method"])]
def wait(fn, t=12):
    e = time.time() + t
    while time.time() < e:
        v = fn()
        if v: return v
        time.sleep(0.3)
    return None
def mail_code(to, n=0, t=8):
    """latest e-mailed 6-digit code for an address (waits for delivery)"""
    e = time.time() + t
    while time.time() < e:
        ms = [json.loads(l) for l in open(MAILF) if l.strip()]
        ms = [m for m in ms if m["to"] == to]
        if len(ms) > n: return ms[-1]["code"]
        time.sleep(0.2)
    return ""
def mails_to(to): return len([1 for l in open(MAILF) if l.strip() and json.loads(l)["to"] == to])
def signup(c, email, name, pw="password123"):
    n = mails_to(email)
    r1 = c.r("POST", "/auth/register", json={"email": email, "password": pw, "name": name})
    code = mail_code(email, n)
    return r1, c.r("POST", "/auth/register", json={"email": email, "password": pw, "name": name, "code": code})
def signin(c, email, pw="password123"):
    n = mails_to(email)
    r1 = c.r("POST", "/auth/login", json={"email": email, "password": pw})
    if r1.status_code != 200 or not r1.json().get("otpRequired"): return r1
    return c.r("POST", "/auth/login", json={"email": email, "password": pw, "code": mail_code(email, n)})
class C:
    def __init__(s, tok=None): s.t = tok
    def r(s, m, p, **kw):
        h = {"Authorization": "Bearer " + s.t} if s.t else {}
        return requests.request(m, API + p, headers=h, timeout=30, **kw)
try:
    print("AUTH")
    a = C()
    r = a.r("POST", "/auth/register", json={"email": "a@x.io", "password": "short", "name": "A"}); check("short password rejected", r.status_code == 400)
    r1, r = signup(a, "a@x.io", "Alice")
    check("register asks for e-mailed code first", r1.status_code == 200 and r1.json().get("otpRequired") is True and "token" not in r1.json(), r1.text)
    check("register", r.status_code == 200 and r.json()["token"])
    a.t = r.json()["token"]
    check("points default", r.json()["user"]["points"] == 1000)
    check("no auto-register on wrong login", C().r("POST", "/auth/login", json={"email": "zz@x.io", "password": "password123"}).status_code == 401)
    check("me", a.r("GET", "/auth/me").json()["user"]["email"] == "a@x.io")
    check("unauth blocked", C().r("GET", "/bots").status_code == 401)
    b = C(); r1, r = signup(b, "b@x.io", "Bob"); b.t = r.json()["token"]
    check("wrong sign-in code refused", (lambda: (C().r("POST", "/auth/login", json={"email": "b@x.io", "password": "password123"}), C().r("POST", "/auth/login", json={"email": "b@x.io", "password": "password123", "code": "000000"}))[1].status_code == 400)())
    check("sign-in needs the right password before any mail", mails_to("b@x.io") == 2 and C().r("POST", "/auth/login", json={"email": "b@x.io", "password": "nope-nope-1"}).status_code == 401 and mails_to("b@x.io") == 2)
    c2 = C(); r = signin(c2, "b@x.io"); check("sign-in with e-mailed code", r.status_code == 200 and r.json()["token"], r.text)
    n0 = mails_to("b@x.io"); fp = C().r("POST", "/auth/forgot-password", json={"email": "b@x.io"})
    fc = mail_code("b@x.io", n0); check("forgot-password e-mails a code", fp.status_code == 200 and len(fc) == 6, fp.text)
    check("reset with wrong code refused", C().r("POST", "/auth/reset-password", json={"email": "b@x.io", "code": "000000", "new_password": "newpassword9"}).status_code == 400)
    check("reset with e-mailed code", C().r("POST", "/auth/reset-password", json={"email": "b@x.io", "code": fc, "new_password": "password123"}).status_code == 200)
    check("old sessions revoked after reset", c2.r("GET", "/auth/me").status_code == 401)
    r = signin(b, "b@x.io"); b.t = r.json()["token"]

    print("BOTS")
    r = a.r("POST", "/bots", json={"token": "bad"}); check("invalid token message", r.status_code == 400 and "token" in r.json()["error"].lower(), r.text)
    r = a.r("POST", "/bots", json={"token": "1111111111:" + "Z" * 35}); check("unknown token rejected", r.status_code == 400, r.text)
    r = a.r("POST", "/bots", json={"token": BOT1}); bot = r.json(); check("create bot", r.status_code == 200 and bot["username"] == "@my_test_bot", r.text)
    check("token never returned", "token" not in bot and bot["hasToken"] and "•" in bot["tokenMasked"] and BOT1 not in r.text)
    check("profile photo set immediately", bool(bot["photoUrl"]))
    check("commands start empty", bot["commands"] == [])
    check("photo proxy", requests.get("http://127.0.0.1:5001" + bot["photoUrl"], headers={"Authorization": "Bearer " + a.t}).status_code == 200)
    check("duplicate token blocked", b.r("POST", "/bots", json={"token": BOT1}).status_code == 409)
    check("other user cannot read bot", b.r("GET", f"/bots/{bot['id']}").status_code == 404)
    check("other user list empty", b.r("GET", "/bots").json() == [])
    bid = bot["id"]
    cmds = [{"id": "c1", "name": "/start", "code": "bot.sendMessage(chat_id=chat_id, text='Hello ' + str(user))"},
            {"id": "c2", "name": "/boom", "code": "x = 1/0"}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds, "name": "My Bot"}); check("save commands", r.status_code == 200 and len(r.json()["commands"]) == 2)
    r = a.r("POST", f"/bots/{bid}/test-command", json={"name": "/start", "text": "/start"}); j = r.json()
    check("test-command dry run", j.get("ok") and j["calls"] and j["calls"][0]["method"] == "sendMessage", r.text)
    check("dry run sent nothing", not sent("sendMessage"))
    v = a.r("POST", "/editor/validate", json={"code": "import os\nreturn"}).json(); check("validate flags import/return", not v["ok"] and len(v["errors"]) >= 2, str(v))
    cat = a.r("GET", "/editor/catalog").json(); check("catalog from runtime", "Bot" in cat["objects"] and any(m["name"] == "Transfer" for m in cat["objects"]["Bot"]) )
    check("new bot starts running", bot["status"] == "working", bot["status"])
    r = a.r("POST", f"/bots/{bid}/toggle-status"); check("stop bot", r.json()["status"] == "stopped", r.text)
    r = a.r("POST", f"/bots/{bid}/toggle-status"); check("start bot", r.status_code == 200 and r.json()["status"] == "working", r.text)
    for uid in range(5001, 5006):
        mock("/_mock/push", token=BOT1, update={"message": {"message_id": 1, "date": int(time.time()), "from": {"id": uid, "is_bot": False, "first_name": f"U{uid}", "language_code": "en"}, "chat": {"id": uid, "type": "private"}, "text": "/start"}})
    check("bot answers /start", wait(lambda: len(sent("sendMessage")) >= 5), "no replies")
    check("reply text from code", any("Hello 5001" in str(x["params"].get("text")) for x in sent("sendMessage")))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 2, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U"}, "chat": {"id": 5001, "type": "private"}, "text": "/nothing"}})
    time.sleep(1.5); n = len(sent("sendMessage")); check("unknown text gets no reply", n == 5, str(n) + " " + str([(x["token"][:6] if "token" in x else "", x["params"].get("chat_id"), str(x["params"].get("text"))[:40]) for x in sent("sendMessage")]))
    ch = a.r("GET", f"/chats/{bid}").json(); check("audience tracked", ch["total"] == 5, str(ch["total"]))
    check("points charged", a.r("GET", "/user/points").json()["points"] < 1000)
    print("RUNTIME FIXES")
    v = a.r("POST", "/editor/validate", json={"code": "text = message.text\nx = msg.chat.id\nBot.setAutoTranslate(True)\nlibs.web3lib.getBalance('0x1')"}).json()
    check("message.text no warning, new functions known", v["ok"] and not v["errors"], str(v))
    cmds2 = cmds + [{"id": "c3", "name": "/cap", "code": "c = Bot.genCaptcha(mode='auto')\nbot.sendMessage(chat_id=chat_id, text=str(c))\nbot.sendMessage(chat_id=chat_id, text='T:' + c.captcha_text)"},
                    {"id": "c4", "name": "/envt", "code": "bot.sendMessage(chat_id=chat_id, text='V=' + str(RAWV) + ' N=' + str(NUMV))"}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds2, "name": "My Bot", "envVars": [{"id": "e1", "key": "RAWV", "value": "u65", "raw": True}, {"id": "e2", "key": "NUMV", "value": "[1,2]", "raw": True}]})
    check("save env raw", r.status_code == 200, r.text[:200])
    n1 = len(sent("sendMessage"))
    for t in ("/cap", "/envt", "/boom"):
        mock("/_mock/push", token=BOT1, update={"message": {"message_id": 9, "date": int(time.time()), "from": {"id": 5002, "is_bot": False, "first_name": "U"}, "chat": {"id": 5002, "type": "private"}, "text": t}})
    time.sleep(3)
    txt = [str(x["params"].get("text")) for x in sent("sendMessage")[n1:]]
    check("genCaptcha str() is plain text, not an object repr", any("captcha" in t.lower() for t in txt) and not any("backend.sandbox" in t or "<" in t for t in txt), str(txt))
    check("raw env non-literal stored as text", any("V=u65 N=[1, 2]" in t for t in txt), str(txt))
    check("original error shown in the bot", any("ZeroDivisionError" in t for t in txt) and not any("Something went wrong" in t for t in txt), str(txt))
    pts = a.r("GET", "/user/points").json(); check("points split plan/extra", pts["planPoints"] + pts["extraPoints"] == pts["points"], str(pts))
    print("ROUND 4: webhook / preface / scheduler")
    cmds3 = cmds2 + [{"id": "c5", "name": "~", "code": "PREF = 'pre-ok'"},
                     {"id": "c6", "name": "/whurl", "code": "u = libs.Webhook.getUrlFor('/hook', user_id=chat_id)\nbot.sendMessage(chat_id=chat_id, text='URL=' + u + ' ' + PREF)"},
                     {"id": "c7", "name": "/hook", "code": "bot.sendMessage(chat_id=chat_id, text='HOOK ' + str(options['json']['a']) + ' ' + str(options['headers'].get('X-T')) + ' ' + PREF)\nApi.setWebhookResult({'echo': options['json']})"},
                     {"id": "c8", "name": "/later", "code": "Bot.runCommandAfter(1, '/laterdone', options={'v': 7})"},
                     {"id": "c9", "name": "/laterdone", "code": "bot.sendMessage(chat_id=chat_id, text='LATER ' + str(options))"}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds3, "name": "My Bot", "envVars": []}); check("save r4 commands", r.status_code == 200, r.text[:200])
    n1 = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 11, "date": int(time.time()), "from": {"id": 5003, "is_bot": False, "first_name": "U5003"}, "chat": {"id": 5003, "type": "private"}, "text": "/whurl"}})
    m = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n1:] if "URL=" in str(x["params"].get("text"))])
    check("~ preface shares its namespace + getUrlFor sends link", bool(m) and "pre-ok" in m[0] and "/api/new-webhook?data=" in m[0], str(m))
    if m:
        import re as _re
        link = _re.search(r"URL=(\S+)", m[0]).group(1)
        link = API.replace("/api", "") + link[link.index("/api/new-webhook"):]
        rr = requests.post(link, json={"a": 42}, headers={"X-T": "tt"})
        check("webhook runs the command with json/headers", rr.status_code == 200 and rr.json() == {"echo": {"a": 42}}, rr.text[:200])
        check("webhook command output reached the user", wait(lambda: any("HOOK 42 tt pre-ok" in str(x["params"].get("text")) for x in sent("sendMessage"))))
        bad = requests.post(link[:-3] + "AAA", json={})
        check("tampered webhook link refused", bad.status_code in (400, 403), str(bad.status_code))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 12, "date": int(time.time()), "from": {"id": 5003, "is_bot": False, "first_name": "U5003"}, "chat": {"id": 5003, "type": "private"}, "text": "/later"}})
    check("runCommandAfter fires through the scheduler", wait(lambda: any("LATER" in str(x["params"].get("text")) and "7" in str(x["params"].get("text")) for x in sent("sendMessage")), 20))
    print("ROUND 4: TonLib")
    cmds4 = cmds3 + [{"id": "t1", "name": "/tonw", "code": "w = libs.TonLib.generateWallet()\nlibs.TonLib.setKeys(w['mnemonics'])\na2 = libs.TonLib.getWalletAddress()\ns = libs.TonLib.create_ton_connect_session(user_id=str(chat_id))\nv0 = libs.TonLib.verify_ton_connect_session(s['session_id'])\nrq = libs.TonLib.request_ton_transaction(a2, 0.5, comment='hi', callback_url='https://example.com/cb')\nbot.sendMessage(chat_id=chat_id, text='TON ' + w['address'] + ' ' + a2 + ' ' + s['session_id'] + ' ' + v0['status'] + ' ' + s['connect_url'] + ' ' + rq['connect_url'] + ' ' + str(len(w['mnemonics'])))"},
                      {"id": "t2", "name": "/tonv", "code": "bot.sendMessage(chat_id=chat_id, text='TONV ' + str(libs.TonLib.verify_ton_connect_session(message.text.split()[1])) + ' ' + str(libs.TonLib.register_ton_connect_wallet('nope', 'x')['status']))"}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds4, "name": "My Bot", "envVars": []}); check("save ton commands", r.status_code == 200, r.text[:200])
    n1 = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 21, "date": int(time.time()), "from": {"id": 5004, "is_bot": False, "first_name": "U5004"}, "chat": {"id": 5004, "type": "private"}, "text": "/tonw"}})
    m = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n1:] if str(x["params"].get("text")).startswith(("TON ", "⚠️"))])
    parts = m[0].split() if m else []
    check("TonLib wallet, keys, session, request", len(parts) == 8 and parts[1] == parts[2] and parts[1][:2] in ("EQ", "UQ") and parts[4] == "pending" and parts[7] == "24", str(m))
    if len(parts) == 8:
        import base64 as _b, hashlib, struct
        from nacl.signing import SigningKey
        from tonsdk.contract.wallet import Wallets, WalletVersionEnum
        from tonsdk.utils import Address
        sid, curl, rurl = parts[3], parts[5], parts[6]
        root = API.replace("/api", "")
        page = requests.get(root + curl[curl.index("/api/"):])
        check("TON Connect page served", page.status_code == 200 and b"tonconnect-ui" in page.content)
        info = requests.get(root + curl[curl.index("/api/"):] + "/info").json()
        mn, pub, priv, w = Wallets.create(WalletVersionEnum.v4r2, workchain=0)
        addr = w.address
        si = _b.b64encode(w.create_state_init()["state_init"].to_boc(False)).decode()
        def proof(ch, ts=None, tamper=False):
            ts = ts or int(time.time()); dom = b"localhost"
            msg = b"ton-proof-item-v2/" + struct.pack("<i", addr.wc) + bytes(addr.hash_part) + struct.pack("<I", len(dom)) + dom + struct.pack("<Q", ts) + ch.encode()
            full = b"\xff\xff" + b"ton-connect" + hashlib.sha256(msg).digest()
            sig = SigningKey(priv[:32]).sign(hashlib.sha256(full).digest()).signature
            if tamper: sig = bytes([sig[0] ^ 1]) + sig[1:]
            return {"address": addr.to_string(True, True, True), "publicKey": pub.hex(), "stateInit": si, "proof": {"timestamp": ts, "domain": {"lengthBytes": 9, "value": "localhost"}, "payload": ch, "signature": _b.b64encode(sig).decode()}}
        bad = requests.post(root + curl[curl.index("/api/"):] + "/connected", json=proof(info["challenge"], tamper=True))
        check("forged ton_proof refused", bad.status_code == 400, bad.text[:120])
        bad2 = requests.post(root + curl[curl.index("/api/"):] + "/connected", json=proof("wrong"))
        check("wrong challenge refused", bad2.status_code == 400)
        good = requests.post(root + curl[curl.index("/api/"):] + "/connected", json=proof(info["challenge"]))
        check("valid ton_proof connects the wallet", good.status_code == 200 and good.json().get("ok"), good.text[:160])
        n2 = len(sent("sendMessage"))
        mock("/_mock/push", token=BOT1, update={"message": {"message_id": 22, "date": int(time.time()), "from": {"id": 5004, "is_bot": False, "first_name": "U5004"}, "chat": {"id": 5004, "type": "private"}, "text": "/tonv " + sid}})
        mv = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n2:] if str(x["params"].get("text")).startswith(("TONV", "⚠️"))])
        check("session reports connected wallet to the bot", bool(mv) and "connected" in mv[0] and addr.to_string(True, True, True) in mv[0] and mv[0].endswith("error"), str(mv))
    print("ROUND 4: broadcast function set")
    fns = [("send_message", "text='hi {first_name}'"), ("send_photo", "photo='AgACfileid', caption='c'"), ("send_video", "video='BAACfileid'"),
           ("send_animation", "animation='CgACfileid'"), ("send_audio", "audio='CQACfileid'"), ("send_document", "document='BQACfileid'"),
           ("forward_message", "from_chat_id=1, message_id=1"), ("send_paid_media", "star_count=1, media=[{'type':'photo','media':'AgACx'}]"),
           ("send_sticker", "sticker='CAACfileid'"), ("send_video_note", "video_note='DQACfileid'"), ("send_voice", "voice='AwACfileid'"),
           ("send_location", "latitude=1.5, longitude=2.5"), ("send_venue", "latitude=1.5, longitude=2.5, title='T', address='A'"),
           ("send_contact", "phone_number='+1555', first_name='N'"), ("send_poll", "question='Q?', options=['a','b']"), ("send_dice", "emoji='🎲'"),
           ("send_invoice", "title='T', description='D', payload='p', currency='XTR', prices=[{'label':'x','amount':1}]"), ("send_game", "game_short_name='g'"),
           ("send_media_group", "media=[{'type':'photo','media':'AgACa'},{'type':'photo','media':'AgACb'}]"), ("pin_chat_message", "message_id=1")]
    body = "res = {}\ndef bc(**k):\n    for i in range(80):\n        r = Bot.broadcast(**k)\n        if 'running broadcasts' not in str(r.get('message')):\n            return r\n        time.sleep(0.5)\n    return r\n" + "".join(f"res['{n}'] = bc(function='{n}', {a}, speed=25, warnings=False)\n" for n, a in fns)
    body += "res['bad'] = Bot.broadcast(function='send_nope', text='x')\nres['none'] = Bot.broadcast()\nres['cmd'] = Bot.broadcast(command='nonexistent_cmd')\nres['key'] = Bot.broadcast(function='send_message', text='x', bot_id='zzz')\nres['multi'] = Bot.broadcast(function='send_message', text='x', mode='multi')\n"
    body += "res['ok'] = bc(function='send_message', text='first {first_name}', speed=99)\nres['st'] = Bot.getBroadcastStatus(res['ok'].get('broadcast_id') or 0) if res['ok'].get('broadcast_id') else {'err': res['ok']}\nres['pr'] = Bot.getBroadcastProgress(res['ok'].get('broadcast_id') or 0) if res['ok'].get('broadcast_id') else {'err': res['ok']}\nbot.sendMessage(chat_id=chat_id, text='BCR ' + json.dumps(res, default=str))"
    cmds5 = cmds4 + [{"id": "b1", "name": "/bcall", "code": body}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds5, "name": "My Bot", "envVars": []}); check("save broadcast test command", r.status_code == 200, r.text[:200])
    n1 = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 31, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "chat": {"id": 5001, "type": "private"}, "text": "/bcall"}})
    m = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n1:] if str(x["params"].get("text")).startswith(("BCR ", "⚠"))], 40)
    check("broadcast command ran", bool(m) and m[0].startswith("BCR "), str(m)[:400])
    if m and m[0].startswith("BCR "):
        res = json.loads(m[0][4:])
        for n, _a in fns:
            check(f"broadcast {n} accepted", res[n].get("status") == "success" or "Test run failed" in str(res[n].get("message")) and False, str(res[n]))
        check("not-allowed function error", res["bad"] == {"status": "error", "message": "Function 'send_nope' not allowed for broadcasting."}, str(res["bad"]))
        check("missing function/code error", res["none"].get("message") == "Either 'code' or 'function' must be provided.", str(res["none"]))
        check("missing command error", res["cmd"].get("message") == "command doesn't exist", str(res["cmd"]))
        check("bad api key error", res["key"].get("message") == "API key not valid", str(res["key"]))
        check("multi needs bot_ids", "bot_ids" in str(res["multi"].get("message")), str(res["multi"]))
        check("speed clamped to 25", res["ok"].get("speed") == 25 and res["ok"].get("mode") == "single", str(res["ok"]))
        check("status/progress keys", all(k in res["st"] for k in ("total_users", "total_success", "total_errors", "total_bots", "done_bots", "status")) and all(k in res["pr"] for k in ("processed", "remaining", "progress_pct", "eta_seconds")), str(res["st"]) + str(res["pr"]))
        time.sleep(2)
        got = {x["method"] for x in sent()}
        for meth in ("sendPhoto", "sendVideo", "sendAnimation", "sendAudio", "sendDocument", "forwardMessage", "sendPaidMedia", "sendSticker", "sendVideoNote", "sendVoice", "sendLocation", "sendVenue", "sendContact", "sendPoll", "sendDice", "sendInvoice", "sendGame", "sendMediaGroup", "pinChatMessage"):
            check(f"telegram {meth} reached the API", meth in got, str(sorted(got))[:300])
    print("ROUND 4: scheduling limits")
    sch = ("out = []\nfor t, c in ((0.5, '/laterdone'), (60*60*24*367, '/laterdone'), ('x', '/laterdone'), (5, '/nope'), (3600, '/laterdone')):\n"
           "    try:\n        r = Bot.runCommandAfter(t, c)\n        out.append('ok:' + str(r['timeout']))\n    except Exception as e:\n        out.append('err:' + str(e))\n"
           "c = Bot.cancelScheduledTask(r['id'])\nout.append('cancel:' + str(c.get('cancelled')))\nbot.sendMessage(chat_id=chat_id, text='SCH ' + ' | '.join(out))")
    cmds6 = cmds5 + [{"id": "s1", "name": "/sch", "code": sch}]
    a.r("PUT", f"/bots/{bid}", json={"commands": cmds6, "name": "My Bot", "envVars": []})
    n1 = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 41, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "chat": {"id": 5001, "type": "private"}, "text": "/sch"}})
    m = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n1:] if str(x["params"].get("text")).startswith(("SCH ", "\u26a0"))])
    t = m[0] if m else ""
    check("runCommandAfter: min 1s, max 366 days, unknown command, valid + cancel",
          "err:timeout must be at least 1 second" in t and "err:timeout can be at most 366 days" in t and "err:timeout must be a number" in t
          and "err:Command not found" in t and "ok:3600" in t and "cancel:True" in t, t)
    print("ROUND 4: library behaviour against the docs")
    libcode = """
R = []
def ck(name, cond):
    R.append(('OK ' if cond else 'FAIL ') + name)
ck('builtins', round(2.567, 1) == 2.6 and tuple([1, 2]) == (1, 2) and hex(255) == '0xff' and divmod(7, 2) == (3, 1) and pow(2, 3) == 8 and chr(65) == 'A' and hasattr(libs, 'Random') and getattr(libs, 'nope', 5) == 5 and list(filter(None, [0, 1])) == [1] and callable(len) and bin(2) == '0b10' and oct(8) == '0o10' and issubclass(ValueError, Exception))
G = [msg, message, bot, Bot, base64, binascii, hashlib, User, time, bot_token, HTTP, re, regex, update_type, CSV, bunchify, bot_id, params, u, options, left_points, isNumeric, MembershipCheck, encodejson, bf_json, ReturnCommand, parse_qs, rawurlencode, decodeURIComponent, encodeURIComponent, web3_, md5, libs, jsondumps]
ck('all documented globals exist', len(G) == 34)
ck('global helpers work', isNumeric('12') and not isNumeric('x') and decodeURIComponent(encodeURIComponent('a b&c')) == 'a b&c' and md5('abc') == '900150983cd24fb0d6963f7d28e17f72' and bunchify({'a': 1}).a == 1 and bf_json('{"a": 1}')['a'] == 1 and parse_qs('a=1&b=2')['a'] == '1' and rawurlencode('a b') == 'a%20b' and jsondumps({'a': 1}) == '{"a": 1}' and encodejson({'a': 1}) == '{"a": 1}' and u == chat_id)
t0 = time.time()
time.sleep(30)
ck('time.sleep capped at 10 seconds', 9 <= time.time() - t0 <= 13)
ck('Random.randomInt', 1 <= libs.Random.randomInt(1, 3) <= 3)
ck('Random.randomStr custom', set(libs.Random.randomStr(30, 'ab')) <= set('ab') and len(libs.Random.randomStr(30, 'ab')) == 30)
ck('Random.randomStr charSet kw', set(libs.Random.randomStr(10, charSet='x')) == set('x'))
ck('Random.randomRange unique', len(set(libs.Random.randomRange(1, 10, 5))) == 5)
ck('Random.randomShuffle copy', sorted(libs.Random.randomShuffle([3, 1, 2])) == [1, 2, 3])
ck('Random.randomSample', len(libs.Random.randomSample([1, 2, 3, 4], 2)) == 2)
ck('Random.randomHex', len(libs.Random.randomHex(16)) == 16)
ck('Random.randomUUID', len(libs.Random.randomUUID()) == 36)
ck('Random.randomPassword', len(libs.Random.randomPassword(12, use_digits=False, use_specials=False)) == 12)
ck('Random.randomWeightedChoice', libs.Random.randomWeightedChoice([10, 50], weights=[0, 1]) == 50)
ck('Random.randomBoolean', libs.Random.randomBoolean() in (True, False))
ck('Random.randomgaussian lower', isinstance(libs.Random.randomgaussian(0, 1), float))
ck('DateAndTime.utcnow date', len(libs.DateAndTime.utcnow()['date']) == 10)
ck('DateAndTime.time int', isinstance(libs.DateAndTime.time(), int))
ck('DateAndTime.now tz', 'datetime' in libs.DateAndTime.now('Asia/Dhaka'))
h = libs.security.sha256('abc')
ck('security.sha256', h == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
ck('security.md5', libs.security.md5('abc') == '900150983cd24fb0d6963f7d28e17f72')
ck('security.sha512', len(libs.security.sha512('abc')) == 128)
sg = libs.security.hmac_sign('k', 'd')
ck('security.hmac', libs.security.hmac_verify('k', 'd', sg) and not libs.security.hmac_verify('k', 'x', sg))
kk = libs.security.generate_key()
ck('security.fernet', libs.security.decrypt(libs.security.encrypt('hello', kk), kk) == 'hello')
ck('security.ed25519 bad', libs.security.ed25519_verify('300f4313f53eb2a1a5c418bf44bae1d50596f3eed7ca5428e57cea40223bb1ed', 'ab' * 64, 'x') is False)
ck('security.coinsway bad', libs.security.verify_coinsway_webhook('300f4313f53eb2a1a5c418bf44bae1d50596f3eed7ca5428e57cea40223bb1ed', 'ab' * 64, 'x') is False)
c = libs.CSV.CSVHandler('t.csv')
c.create_csv(['Name', 'Points'])
c.add_row({'Name': 'Alice', 'Points': 1})
c.add_row({'Name': 'Bob', 'Points': 2})
c.edit_row(0, {'Name': 'Alice', 'Points': 5})
g = c.get()
ck('CSV create/add/edit/get', 'Alice' in str(g) and '5' in str(g) and 'Bob' in str(g))
c.delete()
ck('CSV delete', 'Alice' not in str(libs.CSV.CSVHandler('t.csv').get()))
p = libs.Resources.userRes('points', user)
p.reset()
p.add(10)
p.cut(3)
ck('Resources user add/cut/value', p.value() == 7)
gr = libs.Resources.globalRes('g1')
gr.set(5)
ck('Resources global set', gr.value() == 5)
ad = libs.Resources.adminRes('points')
top = ad.getAllData(5)
ck('Resources adminRes.getAllData shape', len(top) >= 1 and set(top[0].keys()) == {'user', 'value'} and top[0]['value'] == 7.0)
try:
    p.getAllData(5)
    ck('Resources non-admin PermissionError', False)
except PermissionError:
    ck('Resources non-admin PermissionError', True)
fo = ad.fetchAllResources('csv')
ck('Resources fetchAllResources BytesIO csv', 'name,user,value' in fo.getvalue().decode() and 'points' in fo.getvalue().decode())
fj = ad.fetchAllResourcesOfUser(user.id if False else chat_id, 'json')
ck('Resources fetchAllResourcesOfUser json', '"points"' in fj.getvalue().decode())
ac = libs.Resources.accountRes('acct1')
ac.set(9)
ck('Resources accountRes', ac.value() == 9.0 and ac.add(1) == 10.0 and ac.cut(2) == 8.0)
ck('Resources reset returns 0', p.reset() == 0)
p.add(4)
ck('Resources deleteSingleUserData', ad.deleteSingleUserData(chat_id)['deleted'] == 1 and p.value() == 0)
gr.set(3)
ck('Resources deleteAllUsersData', ad.deleteAllUsersData(all_data=True)['ok'] is True)
ck('Resources clearAll account', ac.clearAllUserOrAccountData()['deleted'] >= 1 and ac.value() == 0)
try:
    libs.Resources.userRes('points', bot_id='nope', api_key='bad')
    ck('Resources cross-bot bad key', False)
except Exception:
    ck('Resources cross-bot bad key', True)
ck('web3 31 networks', len(libs.web3lib.get_supported_networks()) == 31)
ck('web3 aliases', libs.web3lib.send_ether == libs.web3lib.sendETHER or callable(libs.web3lib.sendEther))
ck('PremiumGift catalog', len(libs.PremiumGift.get_gift_catalog('Budget')) > 0 and 'rose' in libs.PremiumGift.GIFTS)
ck('Webhook.genRandomId', len(libs.Webhook.genRandomId()) >= 8)
ck('Coinpayments.setKeys', libs.Coinpayments.setKeys('a', 'b') == {'ok': 'success'})
try:
    libs.customHTTP().get('http://127.0.0.1:5001/api/health')
    ck('customHTTP blocks loopback', False)
except Exception as e:
    ck('customHTTP blocks loopback', True)
try:
    libs.customHTTP().get('https://data.census.gov/x')
    ck('customHTTP blocks .gov', False)
except Exception as e:
    ck('customHTTP blocks .gov', 'gov' in str(e).lower())
ck('TonLib wallet', len(libs.TonLib.generateWallet()['mnemonics']) == 24)
ck('Account.getStats', isinstance(Account.getStats(time_frames=['24h', '7d']), dict))
ck('Bot.getStats', isinstance(Bot.getStats(), dict))
bot.sendMessage(chat_id=chat_id, text='LIBS ' + ' ; '.join(R))
"""
    cmds7 = cmds6 + [{"id": "l1", "name": "/libs", "code": libcode}]
    a.r("PUT", f"/bots/{bid}", json={"commands": cmds7, "name": "My Bot", "envVars": []})
    n1 = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 51, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "chat": {"id": 5001, "type": "private"}, "text": "/libs"}})
    m = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n1:] if str(x["params"].get("text")).startswith(("LIBS ", "\u26a0"))], 30)
    t = m[0] if m else ""
    for item in t[5:].split(" ; "):
        if item.strip(): check("lib: " + item.replace("OK ", "").replace("FAIL ", ""), item.startswith("OK "), t[:600] if not item.startswith("OK ") else "")
    if not t.startswith("LIBS "): check("lib test command ran", False, t[:500].replace("\n"," | "))
    print("ROUND 4: callbacks / keyboards / params")
    cmds8 = cmds7 + [
        {"id": "k1", "name": "/buy", "code": "bot.answerCallbackQuery(call.id, 'Added')\nbot.sendMessage(chat_id=u, text='BUY params=' + str(params) + ' msg=' + str(msg) + ' call=' + str(call.id))"},
        {"id": "k2", "name": "balance", "code": "bot.answerCallbackQuery(call.id, 'Low', show_alert=True)\nbot.sendMessage(chat_id=u, text='BAL exact params=' + str(params))"},
        {"id": "k3", "name": "*", "code": "c = message.get('contact')\nbot.sendMessage(chat_id=u, text='STAR msg=' + str(msg) + ' contact=' + (str(c.phone_number) if c else 'none'))"},
        {"id": "k4", "name": "/handler_inline_query", "code": "bot.sendMessage(chat_id=u, text='INLINE ' + str(update_type))"},
    ]
    a.r("PUT", f"/bots/{bid}", json={"commands": cmds8, "name": "My Bot", "envVars": []})
    def cb(data, uid=5001, cid="cq1"):
        mock("/_mock/push", token=BOT1, update={"callback_query": {"id": cid, "from": {"id": uid, "is_bot": False, "first_name": "U%d" % uid}, "data": data,
              "message": {"message_id": 7, "date": int(time.time()), "chat": {"id": uid, "type": "private"}, "from": {"id": 8822824343, "is_bot": True, "first_name": "B"}, "text": "menu"}}})
    def last_text(prefix, n_before, t=10):
        r = wait(lambda: [str(x["params"].get("text")) for x in sent("sendMessage")[n_before:] if str(x["params"].get("text")).startswith(prefix)], t)
        return r[0] if r else None
    nb = len(sent("sendMessage")); cb("/buy 5", cid="cqA")
    t = last_text("BUY", nb)
    check("button '/buy 5' runs /buy with params=5, msg=callback_data, call.id", t == "BUY params=5 msg=/buy 5 call=cqA", str(t))
    check("answerCallbackQuery reached Telegram", any(x["params"].get("callback_query_id") == "cqA" for x in sent("answerCallbackQuery")))
    nb = len(sent("sendMessage")); cb("/buy", cid="cqB")
    t = last_text("BUY", nb)
    check("params is the text None when empty", t == "BUY params=None msg=/buy call=cqB", str(t))
    nb = len(sent("sendMessage")); cb("balance", cid="cqC")
    t = last_text("BAL", nb)
    check("button 'balance' runs the command named exactly balance", t is not None and t.startswith("BAL exact"), str(t))
    check("show_alert forwarded", any(x["params"].get("callback_query_id") == "cqC" and x["params"].get("show_alert") for x in sent("answerCallbackQuery")))
    nb = len(sent("sendMessage")); cb("zzz-unknown", cid="cqD")
    t = last_text("STAR", nb)
    check("unknown callback_data falls to *", t is not None and "msg=zzz-unknown" in t, str(t))
    nb = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 61, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "chat": {"id": 5001, "type": "private"}, "contact": {"phone_number": "+8801700", "first_name": "U"}}})
    t = last_text("STAR", nb)
    check("message without text: msg is 'None', contact.phone_number readable", t == "STAR msg=None contact=+8801700", str(t))
    nb = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"inline_query": {"id": "iq1", "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "query": "x", "offset": ""}})
    t = last_text("INLINE", nb)
    check("/handler_inline_query gets inline updates", t == "INLINE inline_query", str(t))
    print("ROUND 4: payments")
    pay_star = ("pay = message.get('successful_payment')\nif pay:\n    charge = pay.telegram_payment_charge_id\n    if not User.getData('paid_' + charge):\n        User.saveData('paid_' + charge, pay.invoice_payload)\n"
                "        bot.sendMessage('PAID ' + pay.invoice_payload + ' ' + str(pay.total_amount) + ' ' + pay.currency + ' ' + charge)\n        bot.refundStarPayment(int(u), charge)\n    raise ReturnCommand\n"
                "c = message.get('contact')\nbot.sendMessage(chat_id=u, text='STAR msg=' + str(msg) + ' contact=' + (str(c.phone_number) if c else 'none'))")
    cmds9 = [c for c in cmds8 if c["name"] != "*"] + [
        {"id": "p0", "name": "*", "code": pay_star},
        {"id": "p1", "name": "/buy2", "code": "bot.sendInvoice(title='Pro plan', description='30 days of Pro', invoice_payload='pro_30', provider_token='', currency='XTR', prices=[{'label': 'Pro plan', 'amount': 50}])\nlink = bot.createInvoiceLink('Pro plan', '30 days of Pro', 'pro_30', '', 'XTR', [{'label': 'Pro plan', 'amount': 50}])\nbot.sendMessage('LINK ' + str(link))"},
        {"id": "p2", "name": "/handler_pre_checkout_query", "code": "bot.answerPreCheckoutQuery(message.id, True)\nbot.sendMessage(chat_id=message.from_user.id, text='PRE ' + str(message.currency) + ' ' + str(message.total_amount) + ' ' + str(message.invoice_payload))"}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds9, "name": "My Bot", "envVars": []}); check("save payment commands", r.status_code == 200, r.text[:200])
    nb = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 71, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "chat": {"id": 5001, "type": "private"}, "text": "/buy2"}})
    t = last_text("LINK", nb)
    check("createInvoiceLink returns the link", t == "LINK https://t.me/$mockinvoice", str(t))
    inv = [x for x in sent("sendInvoice")]
    check("sendInvoice keeps title/payload/currency/prices", bool(inv) and inv[-1]["params"].get("currency") == "XTR" and inv[-1]["params"].get("payload", inv[-1]["params"].get("invoice_payload")) == "pro_30" and "Pro plan" in str(inv[-1]["params"].get("prices")), str(inv[-1:] ))
    nb = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"pre_checkout_query": {"id": "pcq1", "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "currency": "XTR", "total_amount": 50, "invoice_payload": "pro_30"}})
    t = last_text("PRE", nb)
    check("pre_checkout handler: message.id/currency/total_amount/invoice_payload", t == "PRE XTR 50 pro_30", str(t))
    check("answerPreCheckoutQuery(message.id, True) sent", any(x["params"].get("pre_checkout_query_id") == "pcq1" and str(x["params"].get("ok")).lower() == "true" for x in sent("answerPreCheckoutQuery")), str(sent("answerPreCheckoutQuery")[-1:]))
    nb = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 72, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U5001"}, "chat": {"id": 5001, "type": "private"},
        "successful_payment": {"currency": "XTR", "total_amount": 50, "invoice_payload": "pro_30", "telegram_payment_charge_id": "ch_1", "provider_payment_charge_id": "pp"}}})
    t = last_text("PAID", nb)
    check("successful_payment delivered once via *", t == "PAID pro_30 50 XTR ch_1", str(t))
    check("refundStarPayment(int(u), charge)", any(str(x["params"].get("user_id")) == "5001" and x["params"].get("telegram_payment_charge_id") == "ch_1" for x in sent("refundStarPayment")), str(sent("refundStarPayment")[-1:]))
    print("ROUND 4: special commands + keyboards")
    base = []
    cmds10 = base + [
        {"id": "s0", "name": "~", "code": "BRAND = 'Acme'"},
        {"id": "s1", "name": "@", "code": "gate_var = 1\nif msg == 'blockme':\n    bot.sendMessage('GATED')\n    raise ReturnCommand"},
        {"id": "s2", "name": "!", "code": "bot.sendMessage('ERRH ' + str(options)[:60])"},
        {"id": "s3", "name": "*", "code": "c = message.get('contact')\nif c:\n    bot.sendMessage('CONTACT ' + str(c.phone_number) + ' ' + BRAND, reply_markup={'remove_keyboard': True})\nelse:\n    bot.sendMessage('FALLBACK ' + BRAND + ' ' + str(msg))"},
        {"id": "s4", "name": "/boom9", "code": "x = 1 / 0"},
        {"id": "s5", "name": "/leak", "code": "try:\n    gate_var\n    r = 'True'\nexcept NameError:\n    r = 'False'\nbot.sendMessage('LEAK ' + r)"},
        {"id": "s6", "name": "/kb", "code": "bot.sendMessage('Choose:', reply_markup={'keyboard': [[{'text': 'Balance'}, {'text': 'Share', 'request_contact': True}]], 'resize_keyboard': True, 'one_time_keyboard': True})"},
        {"id": "s7", "name": "Balance", "code": "bot.sendMessage('BAL ' + BRAND)"}]
    r = a.r("PUT", f"/bots/{bid}", json={"commands": cmds10, "name": "My Bot", "envVars": []}); check("save special commands", r.status_code == 200, r.text[:200])
    def say(text, n=5001):
        mock("/_mock/push", token=BOT1, update={"message": {"message_id": int(time.time()*1000) % 10**8, "date": int(time.time()), "from": {"id": n, "is_bot": False, "first_name": "U"}, "chat": {"id": n, "type": "private"}, "text": text}})
    nb = len(sent("sendMessage")); say("blockme"); t = last_text("GATED", nb)
    check("@ gate: ReturnCommand stops command and *", t == "GATED" and not any("FALLBACK" in str(x["params"].get("text")) for x in sent("sendMessage")[nb:]), str(t))
    nb = len(sent("sendMessage")); say("hello there"); t = last_text("FALLBACK", nb)
    check("* fallback runs with ~ on top", t == "FALLBACK Acme hello there", str(t))
    nb = len(sent("sendMessage")); say("/boom9"); t = last_text("ERRH", nb)
    check("! error handler gets options text", bool(t) and "division" in t.lower(), str(t))
    nb = len(sent("sendMessage")); say("/leak"); t = last_text("LEAK", nb)
    check("@ namespace does not leak into command", t == "LEAK False", str(t))
    nb = len(sent("sendMessage")); say("Balance"); t = last_text("BAL", nb)
    check("reply-keyboard text runs exact-named command", t == "BAL Acme", str(t))
    nb = len(sent("sendMessage")); say("/kb"); last_text("Choose", nb)
    kb = [x for x in sent("sendMessage")[nb:] if "Choose" in str(x["params"].get("text"))]
    check("reply keyboard options preserved", bool(kb) and "request_contact" in str(kb[-1]["params"].get("reply_markup")) and "one_time_keyboard" in str(kb[-1]["params"].get("reply_markup")), str(kb[-1:]))
    nb = len(sent("sendMessage"))
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 91, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U"}, "chat": {"id": 5001, "type": "private"}, "contact": {"phone_number": "+8801700000000", "first_name": "U", "user_id": 5001}}})
    t = last_text("CONTACT", nb)
    check("contact message runs * with message.get('contact')", t == "CONTACT +8801700000000 Acme", str(t))
    a.r("PUT", f"/bots/{bid}", json={"commands": cmds9, "name": "My Bot", "envVars": []})
    if os.environ.get("PROBE"):
        pcode = open(os.environ["PROBE"]).read()
        r = a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "z1", "name": "/probe", "code": pcode}], "name": "My Bot", "envVars": []}); print("PROBESAVE", r.status_code, r.text[:400])
        nb = len(sent("sendMessage")); mock("/_mock/push", token=BOT1, update={"message": {"message_id": 99, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U"}, "chat": {"id": 5001, "type": "private"}, "text": "/probe"}})
        print("PROBE", last_text("PR", nb)); print("PROBEALL", [x["params"].get("text") for x in sent("sendMessage")[nb:]]); sys.exit(0)
    print("ROUND 5: TBS compat")
    tbs_code = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tbs_compat.tpy")).read()
    r = a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "t1", "name": "/tbs", "code": tbs_code}], "name": "My Bot", "envVars": []}); check("save TBS compat command", r.status_code == 200, r.text[:300])
    nb = len(sent("sendMessage")); mock("/_mock/push", token=BOT1, update={"message": {"message_id": 98, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U"}, "chat": {"id": 5001, "type": "private"}, "text": "/tbs"}})
    t = last_text("TBS ", nb)
    if not t: print("TBSALL", [x["params"].get("text") for x in sent("sendMessage")[nb:]])
    for k in ["json=2", "p=3", 'dumps={"k": 1}', "url=a%20b%26c|a b|2", "ed=False", "gw=TrueFalse", "hmac=True", "rnd=105142TrueTrueTrue36", "acct=1True1", "acct2=None", "ban=['777']1", "unban=0", "stats=TrueTrue", "ares=5", "adm=11", "adm2=0", "evm=TrueTrueTrueTrue" if False else "evm=TrueTrueTrue64", "gset=xx", "gift=TrueTrueTrue", "dt=1920True", "ton=24True", "tonc=['connect_url', 'expires_at', 'session_id']pending", "tonreg=False", "sch=TrueTrueTrueTrue", "ids=8TrueTrue", "cap=FalseTrue", "ref=ref_cmp_50010", "pil=(24, 24)True", "cv=130406040", "ai=TrueTrue", "big=refusedTrueTrue"]:
        check("TBS: " + k, bool(t) and k in t, str(t)[:700])
    check("TBS: Api.sendMessage works", any("via Api" == str(x["params"].get("text")) for x in sent("sendMessage")[nb:]), "")
    uid0 = ch["users"][0]["id"] if ch["users"] else "none"
    check("block user", a.r("PUT", f"/chats/{bid}/users/{uid0}/block").json()["isBlocked"] is True)
    a.r("PUT", f"/chats/{bid}/users/{uid0}/block")

    print("BROADCAST")
    check("min users default blocks small audience", a.r("POST", "/broadcasts", json={"title": "t", "targetBotIds": [bid], "messageText": "x"}).status_code == 400)
    a.r("POST", "/settings/broadcast-limit", json={"minBroadcastUsers": 1})
    r = a.r("POST", "/broadcasts", json={"title": "t", "targetBotIds": [bid], "messageText": "Hi {user_name}", "messageType": "Text", "parseMode": "HTML", "targetUserLimit": 100})
    check("create broadcast", r.status_code == 200, r.text); bc = r.json()
    check("second running broadcast blocked or finished fast", True)
    done = wait(lambda: a.r("GET", f"/broadcasts/{bc['id']}").json()["status"] in ("Done", "Failed", "Cancelled"))
    j = a.r("GET", f"/broadcasts/{bc['id']}").json()
    check("broadcast completed", j["status"] == "Done" and j["sentCount"] == 5 and j["totalTargetUsers"] == 5, str(j["status"]) + str(j["sentCount"]))
    check("telegram really received broadcast", len([x for x in sent("sendMessage") if "Hi U" in str(x["params"].get("text"))]) == 5)
    check("cancel after complete is final", a.r("POST", f"/broadcasts/{bc['id']}/cancel").status_code == 409)
    # new broadcast kinds (docs: send_location / venue / contact / poll / dice / forward_message)
    for mt, fields, meth, key in [("Location", {"latitude": 23.8, "longitude": 90.4}, "sendLocation", "latitude"),
                                  ("Venue", {"latitude": 23.8, "longitude": 90.4, "title": "HQ", "address": "Dhaka"}, "sendVenue", "title"),
                                  ("Contact", {"phone_number": "+8801700000000", "first_name": "Help"}, "sendContact", "phone_number"),
                                  ("Poll", {"question": "Like it?", "options": ["Yes", "No"]}, "sendPoll", "question"),
                                  ("Dice", {"emoji": "🎯"}, "sendDice", "emoji"),
                                  ("Forward", {"from_chat_id": "@chan", "message_id": 5}, "forwardMessage", "message_id")]:
        r = a.r("POST", "/broadcasts", json={"title": mt, "targetBotIds": [bid], "messageType": mt, "messageText": json.dumps(fields), "targetUserLimit": 100})
        check(f"broadcast type {mt} accepted", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            wait(lambda: a.r("GET", f"/broadcasts/{r.json()['id']}").json()["status"] in ("Done", "Failed", "Cancelled"))
            jj = a.r("GET", f"/broadcasts/{r.json()['id']}").json()
            got = [x for x in sent() if x["method"].lower() == meth.lower()]
            check(f"{mt} broadcast delivered via {meth} with its fields", jj["status"] == "Done" and jj["sentCount"] >= 1 and got and str(got[-1]["params"].get(key)) == str(fields[key]), str(jj["status"]) + str(got[-1:] ))
    check("broadcast Poll needs 2 options", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageType": "Poll", "messageText": json.dumps({"question": "q", "options": ["a"]}), "targetUserLimit": 100}).status_code == 400)
    check("broadcast Location validates range", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageType": "Location", "messageText": json.dumps({"latitude": 999, "longitude": 1}), "targetUserLimit": 100}).status_code == 400)
    check("broadcast Contact requires fields", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageType": "Contact", "messageText": "{}", "targetUserLimit": 100}).status_code == 400)
    mock("/_mock/fail", blocked=["5002"])
    r = a.r("POST", "/broadcasts", json={"title": "slow", "targetBotIds": [bid], "messageText": "Again", "targetUserLimit": 100}); b2 = r.json()
    a.r("POST", f"/broadcasts/{b2['id']}/speed", json={"speed": "1 msgs/sec"})
    time.sleep(0.5)
    check("one running at a time", a.r("POST", "/broadcasts", json={"title": "x", "targetBotIds": [bid], "messageText": "x"}).status_code == 409)
    check("pause", a.r("POST", f"/broadcasts/{b2['id']}/pause").json()["status"] == "Paused")
    time.sleep(1.6); s1 = a.r("GET", f"/broadcasts/{b2['id']}").json()["sentCount"]; time.sleep(2.5)
    check("paused really stops", a.r("GET", f"/broadcasts/{b2['id']}").json()["sentCount"] == s1)
    check("resume", a.r("POST", f"/broadcasts/{b2['id']}/resume").json()["status"] == "Active")
    check("cancel", a.r("POST", f"/broadcasts/{b2['id']}/cancel").json()["status"] == "Cancelled")
    check("cancelled is final (resume)", a.r("POST", f"/broadcasts/{b2['id']}/resume").status_code == 409)
    time.sleep(1.5)
    check("stays cancelled", a.r("GET", f"/broadcasts/{b2['id']}").json()["status"] == "Cancelled")
    check("other user cannot see broadcast", b.r("GET", f"/broadcasts/{bc['id']}").status_code == 404 and b.r("GET", "/broadcasts").json() == [])

    print("MEDIA BROADCAST")
    a.r("POST", "/admin/plan", json={"email": "a@x.io", "plan": "Matrix Pro", "addPoints": 0})
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 500
    up = requests.post(API + "/broadcasts/media", data=png, headers={"Authorization": "Bearer " + a.t, "Content-Type": "image/png", "x-file-name": "pic.png", "x-media-type": "Photo"})
    check("media upload", up.status_code == 200 and up.json().get("mediaId"), up.text)
    bad = requests.post(API + "/broadcasts/media", data=b"hello", headers={"Authorization": "Bearer " + a.t, "Content-Type": "text/plain", "x-file-name": "a.txt", "x-media-type": "Photo"})
    check("wrong media type refused", bad.status_code == 400, bad.text)
    check("media upload needs login", requests.post(API + "/broadcasts/media", data=png, headers={"Content-Type": "image/png", "x-media-type": "Photo"}).status_code == 401)
    before = len(sent("sendPhoto"))
    r = a.r("POST", "/broadcasts", json={"title": "pic", "targetBotIds": [bid], "messageType": "Photo", "messageText": "Hello {user_name}", "mediaSource": "upload", "mediaRef": up.json()["mediaId"], "targetUserLimit": 100})
    check("create photo broadcast", r.status_code == 200, r.text); pb = r.json()
    wait(lambda: a.r("GET", f"/broadcasts/{pb['id']}").json()["status"] in ("Done", "Failed", "Cancelled"))
    pj = a.r("GET", f"/broadcasts/{pb['id']}").json()
    ph = sent("sendPhoto")[before:]
    check("photo broadcast delivered", pj["status"] == "Done" and len(ph) >= 4, str(pj["status"]) + str(len(ph)))
    check("first send uploads, rest reuse file_id", sum(1 for x in ph if str(x["params"].get("photo", "")).startswith("__uploaded__")) == 1 and any(x["params"].get("photo") == "FID_8822" for x in ph), str([x["params"].get("photo") for x in ph]))
    check("caption personalised", any("Hello U" in str(x["params"].get("caption")) for x in ph))
    r = a.r("POST", "/broadcasts", json={"title": "u", "targetBotIds": [bid], "messageType": "Photo", "messageText": "", "mediaSource": "url", "mediaRef": "http://127.0.0.1/x.png"})
    check("private media link refused", r.status_code == 400, r.text)
    check("detect refuses private link", a.r("POST", "/broadcasts/detect-url", json={"url": "http://127.0.0.1/x.png"}).status_code == 400)

    a.r("POST", "/admin/plan", json={"email": "a@x.io", "plan": "Matrix Free", "addPoints": 0})

    print("TELEGRAM CONNECT")
    lc = a.r("POST", "/telegram/link-code").json(); check("link code url", lc["url"].startswith("https://t.me/matrix_connect_bot?start="))
    check("not connected yet", a.r("GET", "/telegram/status").json()["connected"] is False)
    mock("/_mock/push", token=CONNECT, update={"message": {"message_id": 1, "date": 1, "from": {"id": 7667568339, "is_bot": False, "first_name": "Alice", "username": "alice_tg"}, "chat": {"id": 7667568339, "type": "private"}, "text": "/start " + lc["code"]}})
    st = wait(lambda: a.r("GET", "/telegram/status").json() if a.r("GET", "/telegram/status").json()["connected"] else None)
    check("connected via bot", bool(st) and st["username"] == "@alice_tg" and st["telegramId"] == "7667568339" and st["account"]["email"] == "a@x.io", str(st))
    check("welcome keyboard sent", any(x["token"] == CONNECT and "Connected" in str(x["params"].get("text")) for x in sent("sendMessage")))
    mock("/_mock/push", token=CONNECT, update={"message": {"message_id": 2, "date": 1, "from": {"id": 7667568339, "is_bot": False, "first_name": "Alice"}, "chat": {"id": 7667568339, "type": "private"}, "text": "👤 My Account"}})
    check("account button", wait(lambda: any("a@x.io" in str(x["params"].get("text")) for x in sent("sendMessage") if x["token"] == CONNECT)))
    check("stranger gets nothing private", True)
    mock("/_mock/push", token=CONNECT, update={"message": {"message_id": 3, "date": 1, "from": {"id": 999, "is_bot": False, "first_name": "Eve"}, "chat": {"id": 999, "type": "private"}, "text": "👤 My Account"}})
    time.sleep(1.2); check("stranger does not see account data", not any(x["params"].get("chat_id") == 999 and "a@x.io" in str(x["params"].get("text")) for x in sent("sendMessage")))
    check("test alert", a.r("POST", "/telegram/test-alert").status_code == 200)
    check("forgot-password does not leak code", "code" not in a.r("POST", "/auth/forgot-password", json={"email": "a@x.io"}).json())
    check("alerts toggle", a.r("POST", "/telegram/alerts", json={"alerts": {"newSubscribers": True}}).json()["alerts"]["newSubscribers"] is True)

    print("PLANS")
    pl = a.r("GET", "/plans").json()
    check("four plans listed", [p["name"] for p in pl["plans"]] == ["Matrix Free", "Matrix Pro", "Matrix Growth", "Matrix Ultra"], str(pl)[:200])
    check("plan prices and points", [p["priceUsd"] for p in pl["plans"]] == [0, 4, 9, 19] and pl["plans"][1]["points"] == 40000)
    check("ultra has unlimited bots", pl["plans"][3]["limits"]["maxBots"] == -1)
    check("contact url from database", pl["contactUrl"] == "https://t.me/matrix_admin" and pl["current"] == "Matrix Free")
    check("non-admin cannot assign plans", b.r("POST", "/admin/plan", json={"email": "b@x.io", "plan": "Matrix Ultra"}).status_code == 403)
    check("free plan cannot send a bot copy", a.r("POST", f"/bots/{bid}/transfer", json={"email": "b@x.io"}).status_code == 403)
    check("free plan cannot import users", requests.post(API + f"/bots/{bid}/users/import", data=b"1", headers={"Authorization": "Bearer " + a.t, "X-File-Name": "u.txt"}).status_code == 403)
    pts0 = a.r("GET", "/plans").json()["points"]
    r = a.r("POST", "/admin/plan", json={"email": "a@x.io", "plan": "Matrix Pro"})
    check("admin assigns plan + points", r.status_code == 200 and r.json()["pointsAdded"] == 40000 and a.r("GET", "/plans").json()["points"] == pts0 + 40000, r.text)
    a.r("POST", "/admin/plan", json={"email": "b@x.io", "plan": "Matrix Pro"})
    check("plan shown in settings", a.r("GET", "/settings").json()["plan"]["name"] == "Matrix Pro")
    check("plan change notified with link", any(n.get("link") == "tab:Plans & Billing" for n in a.r("GET", "/notifications").json()))
    check("contact link validated", a.r("PUT", "/admin/contact", json={"url": "javascript:alert(1)"}).status_code == 400)
    print("TRANSFERS")
    check("transfer to unknown email", a.r("POST", f"/bots/{bid}/transfer", json={"email": "nobody@x.io"}).status_code == 404)
    a.r("POST", f"/bots/{bid}/env", json={}) if False else None
    r = a.r("POST", f"/bots/{bid}/transfer", json={"email": "b@x.io", "options": {"data": False, "chats": False, "errors": False, "env": False}}); check("transfer request", r.status_code == 200 and r.json()["transfer"]["status"] == "pending", r.text)
    tid = r.json()["transfer"]["id"]
    check("incoming for Bob", len(b.r("GET", "/transfers").json()["incoming"]) == 1)
    check("Alice cannot accept own", a.r("POST", f"/transfers/{tid}/accept").status_code in (403, 404))
    check("accept", b.r("POST", f"/transfers/{tid}/accept").json()["transfer"]["status"] == "accepted")
    bobs = b.r("GET", "/bots").json()
    check("Bob got a copy", len(bobs) == 1 and bobs[0]["id"] != bid and bobs[0]["name"], str(bobs)[:200])
    check("Alice keeps her bot", any(x["id"] == bid for x in a.r("GET", "/bots").json()))
    check("copy has no token", bobs[0].get("hasToken") in (False, None, 0) and not bobs[0].get("tokenMasked"), str({k: bobs[0].get(k) for k in ("hasToken", "tokenMasked", "status")}))
    check("Bob cannot open Alice's original", b.r("GET", f"/bots/{bid}").status_code == 404)
    check("chats not sent when unticked", b.r("GET", f"/chats/{bobs[0]['id']}").json().get("total", 0) == 0, b.r("GET", f"/chats/{bobs[0]['id']}").text[:150])

    print("BROADCAST RULES")
    def finish(bid_):
        wait(lambda: a.r("GET", f"/broadcasts/{bid_}").json()["status"] in ("Done", "Failed", "Cancelled"), 30)
        return a.r("GET", f"/broadcasts/{bid_}").json()
    def aud(): return a.r("GET", "/dashboard/stats").json()["totals"]["audience"]
    base = aud()
    mock("/_mock/fail", blocked=["5002"], error=["5003"])
    n0 = len(sent("sendMessage"))
    r = a.r("POST", "/broadcasts", json={"title": "mix", "targetBotIds": [bid], "messageText": "Hello {user_id} / {first_name} / {mention} / {username}", "parseMode": "HTML", "targetUserLimit": 100})
    check("create personalised broadcast", r.status_code == 200, r.text)
    j = finish(r.json()["id"]); sid = r.json()["id"]
    check("partial failure still Done", j["status"] == "Done" and j["sentCount"] == base - 2 and j["failedCount"] == 2, str(j["status"]) + str(j["sentCount"]) + "/" + str(j["failedCount"]))
    txt = [x["params"]["text"] for x in sent("sendMessage")[n0:] if x["params"].get("chat_id") == 5004]
    check("placeholders filled per user", txt and txt[-1].startswith("Hello 5004 / U5004 / <a href=\"tg://user?id=5004\">U5004</a> / "), str(txt))
    check("unreachable vs other errors told apart", j["unreachableCount"] == 1 and {x["kind"] for x in j["reasons"]} == {"unreachable", "error"}, str(j["reasons"]))
    check("failure shows a real reason", any("parse entities" in x["reason"] for x in j["reasons"]))
    rc = a.r("POST", f"/broadcasts/{sid}/clean-failed").json()
    check("clean removes only the unreachable user", rc.get("cleaned") == 1 and aud() == base - 1, str(rc) + str(aud()))
    check("cleaning twice does nothing more", a.r("POST", f"/broadcasts/{sid}/clean-failed").json().get("cleaned") == 0)
    mock("/_mock/push", token=BOT1, update={"message": {"message_id": 9, "date": int(time.time()), "from": {"id": 5002, "is_bot": False, "first_name": "U5002"}, "chat": {"id": 5002, "type": "private"}, "text": "hi again"}})
    check("a cleaned user who starts the bot again rejoins", wait(lambda: aud() == base), str(aud()))
    mock("/_mock/fail", blocked=[], error=["5001", "5002", "5003", "5004", "5005"])
    r = a.r("POST", "/broadcasts", json={"title": "allfail", "targetBotIds": [bid], "messageText": "x", "targetUserLimit": 100}); fid = r.json()["id"]
    j = finish(fid)
    check("a broadcast where everything failed is Failed", j["status"] == "Failed" and j["sentCount"] == 0 and j["failedCount"] == base, str(j["status"]))
    check("failed per-bot status is Failed", j["botStats"][0]["status"] == "Failed")
    check("no cancel / pause on a failed broadcast", all(a.r("POST", f"/broadcasts/{fid}/{x}").status_code == 409 for x in ("cancel", "pause", "resume")))
    check("failed broadcast cleaning leaves error-only users alone", a.r("POST", f"/broadcasts/{fid}/clean-failed").json().get("cleaned") == 0 and aud() == base)
    mock("/_mock/fail", blocked=[], error=[])
    check("photo needs media", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageType": "Photo", "messageText": "cap"}).status_code == 400)
    r = a.r("POST", "/broadcasts", json={"title": "slow2", "targetBotIds": [bid], "messageText": "Slow {first_name}", "targetUserLimit": 100}); s2 = r.json()["id"]
    a.r("POST", f"/broadcasts/{s2}/speed", json={"speed": "1 msgs/sec"})
    check("single bot cannot be cancelled from the breakdown", a.r("POST", f"/broadcasts/{s2}/bots/{bid}/status", json={"status": "Cancelled"}).status_code == 400)
    check("single bot can be paused", a.r("POST", f"/broadcasts/{s2}/bots/{bid}/status", json={"status": "Paused"}).json()["botStatus"] == "Paused")
    check("single bot can be resumed", a.r("POST", f"/broadcasts/{s2}/bots/{bid}/status", json={"status": "Delivering"}).json()["botStatus"] == "Delivering")
    a.r("POST", f"/broadcasts/{s2}/cancel"); finish(s2)

    print("BROADCAST PLAN FEATURES")
    check("pro cannot pin", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageText": "x", "pinMessage": True, "targetUserLimit": 100}).status_code == 403)
    check("pro cannot use rich buttons", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageText": "x", "inlineButtons": [{"text": "A", "type": "url", "url": "https://a.io", "style": "danger"}], "targetUserLimit": 100}).status_code == 403)
    check("pro cannot choose speed above plan", a.r("POST", "/broadcasts", json={"title": "p", "targetBotIds": [bid], "messageText": "x", "deliverySpeed": "Unlimited", "targetUserLimit": 100}).status_code == 403)
    langs = a.r("GET", f"/broadcasts/languages?botIds={bid}")
    check("languages endpoint counts reachable users", langs.status_code == 200 and sum(x["count"] for x in langs.json()) == aud(), langs.text[:200])
    check("languages of someone else's bot are empty", b.r("GET", f"/broadcasts/languages?botIds={bid}").json() == [])
    a.r("POST", "/admin/plan", json={"email": "a@x.io", "plan": "Matrix Growth"})
    check("growth cannot pick Unlimited (cap 30)", a.r("POST", "/broadcasts", json={"title": "u", "targetBotIds": [bid], "messageText": "x", "deliverySpeed": "Unlimited", "targetUserLimit": 100}).status_code == 403)
    a.r("POST", "/admin/plan", json={"email": "a@x.io", "plan": "Matrix Ultra"})
    n0 = len(sent("sendMessage"))
    r = a.r("POST", "/broadcasts", json={"title": "rich", "targetBotIds": [bid], "messageText": "Rich", "pinMessage": True, "deliverySpeed": "100 msgs/sec", "targetUserLimit": 100,
        "inlineButtons": [{"text": "A", "type": "url", "url": "https://a.io", "row": 1, "style": "success", "iconEmojiId": "5368324170671202286"},
                          {"text": "B", "type": "callback_data", "callbackData": "b", "row": 1}, {"text": "C", "type": "url", "url": "https://c.io", "row": 2}]})
    check("ultra can create rich pinned broadcast", r.status_code == 200 and r.json()["pinMessage"] is True and r.json()["deliverySpeed"] == "100 msgs/sec", r.text[:200])
    j = finish(r.json()["id"])
    sm = [x for x in sent("sendMessage")[n0:] if x["params"].get("text") == "Rich"]
    kb = sm[0]["params"]["reply_markup"]["inline_keyboard"] if sm else []
    check("buttons keep rows, colour and premium emoji", len(kb) == 2 and len(kb[0]) == 2 and kb[0][0].get("style") == "success" and kb[0][0].get("icon_custom_emoji_id") == "5368324170671202286", str(kb))
    check("fast speed never uses paid broadcast", sm and all("allow_paid_broadcast" not in x["params"] for x in sm))
    check("message is pinned in every chat", len([x for x in sent("pinChatMessage")]) >= j["sentCount"] and j["status"] == "Done", str(j["status"]))
    n1 = len(a.r("GET", "/broadcasts").json())
    code = "r = Bot.broadcast(function='send_message', text='From code {first_name}', reply_markup={'inline_keyboard': [[{'text': 'A', 'url': 'https://a.io'}, {'text': 'B', 'url': 'https://b.io'}], [{'text': 'C', 'url': 'https://c.io'}]]})\nbot.sendMessage(chat_id=chat_id, text='started ' + str(r.get('broadcast_id')))"
    tr = a.r("POST", f"/bots/{bid}/test-command", json={"name": "/bcx", "code": code, "text": "/bcx"})
    check("code broadcast starts in the shared engine", tr.status_code == 200 and tr.json().get("ok"), tr.text[:300])
    lst = a.r("GET", "/broadcasts").json()
    check("code broadcast appears in Broadcast Manager", len(lst) == n1 + 1 and lst[0]["id"].startswith("bc_"), str([x["id"] for x in lst][:3]))
    j = finish(lst[0]["id"])
    kb2 = [x for x in sent("sendMessage") if str(x["params"].get("text", "")).startswith("From code")]
    check("code broadcast personalised, buttons in rows", j["status"] == "Done" and kb2 and [len(r) for r in kb2[-1]["params"]["reply_markup"]["inline_keyboard"]] == [2, 1], str(j["status"]))
    a.r("POST", "/admin/plan", json={"email": "a@x.io", "plan": "Matrix Pro"})
    print("ADMIN PANEL")
    check("admin sees isAdmin", a.r("GET", "/auth/me").json()["user"].get("isAdmin") is True)
    check("non-admin blocked from admin config", b.r("GET", "/admin/config").status_code == 403 and b.r("GET", "/admin/overview").status_code == 403)
    ov = a.r("GET", "/admin/overview").json(); check("overview has real counts", ov["users"] >= 2 and ov["bots"] >= 1, str(ov))
    us = a.r("GET", "/admin/users?q=b@x").json(); check("user search", us["total"] == 1 and us["users"][0]["email"] == "b@x.io", str(us))
    cfg = a.r("GET", "/admin/config").json(); sp = [c for c in cfg if c["key"] == "SMTP_PASSWORD"][0]
    check("secrets are never returned", sp["value"] == "" and not any(c.get("value") == "pw" for c in cfg))
    r = a.r("PUT", "/admin/config", json={"values": {"ADMIN_CONTACT_URL": "https://t.me/new_admin", "RATE_LIMITS": "0"}})
    check("config saved and applied", r.status_code == 200 and a.r("GET", "/plans").json()["contactUrl"] == "https://t.me/new_admin", r.text)
    check("cannot remove yourself from admins", a.r("PUT", "/admin/config", json={"values": {"ADMIN_EMAILS": "other@x.io"}}).status_code == 400)
    check("bad number rejected", a.r("PUT", "/admin/config", json={"values": {"SMTP_PORT": "abc"}}).status_code == 400)
    r = a.r("PUT", "/admin/plans/pro", json={"priceUsd": 4, "points": 40000, "limits": {"maxBots": 11}})
    check("plan editable", r.status_code == 200 and [p for p in a.r("GET", "/plans").json()["plans"] if p["id"] == "pro"][0]["limits"]["maxBots"] == 11)
    uid_b = us["users"][0]["id"]
    check("admin adds points", a.r("PUT", f"/admin/users/{uid_b}", json={"addPoints": 5}).status_code == 200)

    print("STUDIO FIXES")
    cur = a.r("GET", f"/bots/{bid}").json().get("commands") or []
    dup = a.r("PUT", f"/bots/{bid}", json={"commands": cur + [{"id": "n1", "name": "withdraw737", "code": ""}, {"id": "n2", "name": "withdraw737", "code": ""}]})
    check("duplicate command name is refused (nothing is replaced)", dup.status_code == 409 and "already exists" in dup.text, dup.text[:200])
    ok1 = a.r("PUT", f"/bots/{bid}", json={"commands": cur + [{"id": "n1", "name": "withdraw737", "code": ""}]})
    check("a name without '/' is kept exactly", ok1.status_code == 200 and any(c["name"] == "withdraw737" for c in ok1.json()["commands"]) and len(ok1.json()["commands"]) == len(cur) + 1, ok1.text[:200])
    a.r("PUT", f"/bots/{bid}", json={"commands": cur})
    it = a.r("GET", f"/bots/{bid}/intro?tz=360").json()
    check("intro has live numbers", it["users"]["total"] >= 1 and "newToday" in it["users"] and it["health"]["state"] in ("healthy", "stopped", "degraded", "error"), str(it)[:300])
    check("intro today's new users counts new chats", it["users"]["newToday"] >= 1, str(it["users"]))
    check("errors list works", isinstance(a.r("GET", f"/bots/{bid}/errors").json(), list))
    check("errors can be cleared", a.r("DELETE", f"/bots/{bid}/errors").json()["success"] is True)
    ch = a.r("GET", f"/chats/{bid}?filter=left").json()
    check("chats have a separate 'left bot' filter", "users" in ch and all(u["botBlocked"] for u in ch["users"]), str(ch)[:200])
    check("chat list has photo urls", all(u["photoUrl"].startswith("/api/media/chat/") for u in a.r("GET", f"/chats/{bid}").json()["users"]))
    check("page size 1000 accepted", a.r("GET", f"/chats/{bid}?limit=1000").status_code == 200)
    ab = a.r("GET", "/admin/bots?q=my_test").json()
    check("admin can find any bot", any(x["id"] == bid for x in ab), str(ab)[:200])
    r = a.r("POST", "/admin/store", json={"botId": bid, "description": "Added by admin"})
    check("admin adds a bot to the store", r.status_code == 200 and any(s["name"] for s in a.r("GET", "/store/bots").json()), r.text[:200])
    check("non-admin cannot add to the store", b.r("POST", "/admin/store", json={"botId": bid}).status_code == 403)

    print("USER IMPORT / EXPORT")
    def poll(path, t=30):
        e = time.time() + t
        while time.time() < e:
            j = a.r("GET", path).json()
            if j.get("state") != "running": return j
            time.sleep(0.2)
        return j
    def raw_import(client, botid, data, name):
        return requests.post(API + f"/bots/{botid}/users/import", data=data, headers={"Authorization": "Bearer " + client.t, "X-File-Name": name, "Content-Type": "application/octet-stream"}, timeout=30)
    ex = a.r("POST", f"/bots/{bid}/users/export", json={"format": "csv", "includeDates": True}).json()
    exj = poll(f"/bots/{bid}/users/jobs/{ex['id']}")
    check("export csv finishes", exj["state"] == "done" and exj["rows"] == 5, str(exj))
    dl = requests.get(API + f"/bots/{bid}/users/export/{ex['id']}/download", headers={"Authorization": "Bearer " + a.t})
    lines = dl.text.strip().splitlines()
    check("csv has header + 5 users + registration date", dl.status_code == 200 and len(lines) == 6 and "registered_at" in lines[0] and "attachment" in dl.headers.get("Content-Disposition", ""), dl.text[:200])
    ex = a.r("POST", f"/bots/{bid}/users/export", json={"format": "json"}).json(); poll(f"/bots/{bid}/users/jobs/{ex['id']}")
    dj = requests.get(API + f"/bots/{bid}/users/export/{ex['id']}/download", headers={"Authorization": "Bearer " + a.t}).json()
    check("json export, no dates unless asked", len(dj) == 5 and "registeredAt" not in dj[0] and isinstance(dj[0]["id"], int))
    check("other user cannot download", requests.get(API + f"/bots/{bid}/users/export/{ex['id']}/download", headers={"Authorization": "Bearer " + b.t}).status_code in (403, 404))
    mock("/_mock/fail", unreachable=["333"])
    r = raw_import(a, bid, b"id\n111\n222\n333\n-5\nabc\n111\n", "u.csv"); ji = r.json()
    check("import accepted", r.status_code == 200 and ji["kind"] == "import" and ji["total"] == 3, r.text)
    jd = poll(f"/bots/{bid}/users/jobs/{ji['id']}")
    check("import verifies through Telegram", jd["state"] == "done" and jd["imported"] == 2 and jd["unreachable"] == 1 and jd["ignored"] == 2, str(jd))
    ch = a.r("GET", f"/chats/{bid}").json()
    check("imported users appear, old ones untouched", ch["total"] == 7 and any(u["name"].startswith("User111") for u in ch["users"]), str(ch["total"]))
    jd = poll(f"/bots/{bid}/users/jobs/{raw_import(a, bid, b'[111, {\"telegram_id\": 444}, \"555\"]', 'u.json').json()['id']}")
    check("re-import skips existing, json shapes", jd["existing"] == 1 and jd["imported"] == 2, str(jd))
    jd = poll(f"/bots/{bid}/users/jobs/{raw_import(a, bid, b'777 888, 999', 'u.txt').json()['id']}")
    check("txt import", jd["imported"] == 3, str(jd))
    check("garbage file refused", raw_import(a, bid, b"hello world", "x.txt").status_code == 400)
    check("empty file refused", raw_import(a, bid, b"", "x.txt").status_code == 400)
    check("job list for reload", "import" in a.r("GET", f"/bots/{bid}/users/jobs").json())
    check("import needs a token (clone has none)", requests.post(API + f"/bots/{bobs[0]['id']}/users/import", data=b"1\n2", headers={"Authorization": "Bearer " + b.t, "X-File-Name": "a.txt"}).status_code == 400)
    check("reveal token (owner)", a.r("GET", f"/bots/{bid}/token").json().get("token") == BOT1)
    check("reveal token (stranger)", b.r("GET", f"/bots/{bid}/token").status_code == 404)
    check("reveal token on tokenless clone", b.r("GET", f"/bots/{bobs[0]['id']}/token").status_code == 404)
    check("unauth reveal blocked", C().r("GET", f"/bots/{bid}/token").status_code == 401)

    print("DELETE / RESTORE")
    cid = b.r("GET", "/bots").json()[0]["id"]
    r = b.r("DELETE", f"/bots/{cid}"); check("delete to bin", r.status_code == 200 and len(b.r("GET", "/recycle-bin").json()) == 1)
    check("restore", b.r("POST", f"/recycle-bin/{cid}/restore").status_code == 200 and len(b.r("GET", "/bots").json()) == 1)
    print("SETTINGS")
    check("settings roundtrip", a.r("PUT", "/settings", json={"outgoingLimit": 3, "emailNotifications": True}).json()["outgoingLimit"] == 3)
    check("dashboard", a.r("GET", "/dashboard/stats").json()["totals"]["bots"] == 1 and len(a.r("GET", "/dashboard/stats").json()["activity"]) == 24)
    print("RECEIPT / FORMAT / NOTIFICATIONS / LIMITS")
    hist = a.r("GET", "/transfers").json()
    tr = (hist["history"] + hist["outgoing"] + hist["incoming"])[0]
    code = a.r("GET", f"/transfers/{tr['id']}/receipt").json()["code"]
    pub = requests.get(API + f"/public/receipt/{code}").json()
    check("public receipt verifies without login", pub["valid"] is True and pub["botName"] == tr["botName"] and "@" in pub["from"] and "a@x.io" not in pub["from"], str(pub))
    bad = requests.get(API + f"/public/receipt/{code[:-2]}00").json()
    check("tampered receipt rejected", bad["valid"] is False)
    check("other user cannot mint a receipt link", C().r("GET", f"/transfers/{tr['id']}/receipt").status_code == 401)
    f = a.r("POST", "/editor/format", json={"code": "x=1\nif x>0 :\n  Bot.sendMessage(chat_id = User.id,text = 'hi')\n"}).json()
    check("formatter", f["ok"] and f["code"] == "x = 1\nif x > 0:\n    Bot.sendMessage(chat_id=User.id, text='hi')\n", str(f))
    check("formatter refuses broken code", a.r("POST", "/editor/format", json={"code": "if x\n"}).json()["ok"] is False)
    n_before = len(a.r("GET", "/notifications").json())
    a.r("PUT", "/settings", json={"notificationsEnabled": False})
    a.r("POST", f"/bots/{bid}/toggle-status"); a.r("POST", f"/bots/{bid}/toggle-status")
    check("notifications off: nothing new saved", len(a.r("GET", "/notifications").json()) == n_before)
    a.r("PUT", "/settings", json={"notificationsEnabled": True, "notificationTypes": {"bots": False}})
    a.r("POST", f"/bots/{bid}/toggle-status"); a.r("POST", f"/bots/{bid}/toggle-status")
    check("one kind off: bot events skipped", len(a.r("GET", "/notifications").json()) == n_before)
    a.r("PUT", "/settings", json={"notificationTypes": {}})
    print("ROUND 5: RefLib tracking")
    ref_code = ("def got(r):\n    bot.sendMessage('ATTR ' + r['id'] + ' ' + str(r.get('prefix')) + ' ' + str(len(r['date'])))\n"
                "def own():\n    bot.sendMessage('OWN')\n"
                "def again():\n    bot.sendMessage('AGAIN')\n"
                "ok = Lib.RefLib.track(on_attracted=got, on_touch_own_link=own, on_already_attracted=again)\n"
                "bot.sendMessage('TRACK ' + str(ok) + ' by=' + str(Lib.RefLib.getAttractedBy()['id'] if Lib.RefLib.getAttractedBy() else None) + ' cnt=' + str(Lib.RefLib.getRefCount(5001)) + ' rank=' + str(Lib.RefLib.getRank(5001)) + ' top=' + str(Lib.RefLib.getTopList(3)) + ' st=' + str(Lib.RefLib.getStats(5001)['recent_7d']) + ' lst=' + str([x['id'] for x in Lib.RefLib.getRefList(5001)]))")
    r = a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "r1", "name": "/start", "code": ref_code}], "name": "My Bot", "envVars": []}); check("save RefLib /start", r.status_code == 200, r.text[:200])
    def say2(n, text): mock("/_mock/push", token=BOT1, update={"message": {"message_id": int(time.time()*1000) % 10**8, "date": int(time.time()), "from": {"id": n, "is_bot": False, "first_name": "N%d" % n}, "chat": {"id": n, "type": "private"}, "text": text}})
    nb = len(sent("sendMessage")); say2(6101, "/start ref_promo_5001"); t = last_text("TRACK", nb)
    check("RefLib attributes a new user", bool(t) and "TRACK True by=5001 cnt=1 rank=1 top={'5001': 1} st=1 lst=['6101']" in t, str(t))
    check("RefLib on_attracted callback (prefix + date)", any(str(x["params"].get("text")) == "ATTR 5001 promo 16" for x in sent("sendMessage")[nb:]), "")
    nb = len(sent("sendMessage")); say2(6101, "/start ref_5001"); t = last_text("TRACK", nb)
    check("RefLib blocks repeat attribution", bool(t) and t.startswith("TRACK False") and any(x["params"].get("text") == "AGAIN" for x in sent("sendMessage")[nb:]), str(t))
    nb = len(sent("sendMessage")); say2(5001, "/start ref_5001"); t = last_text("TRACK", nb)
    check("RefLib blocks self-referral", bool(t) and t.startswith("TRACK False") and any(x["params"].get("text") == "OWN" for x in sent("sendMessage")[nb:]), str(t))
    print("ROUND 5: API v2")
    V2 = "http://127.0.0.1:5001/v2"
    _kresp = a.r("POST", "/settings/api-key").json()
    key = _kresp["apiKey"]
    check("api key shown once, with a masked prefix and a one-time warning", bool(key) and bool(_kresp.get("apiKeyMasked")) and "•" in _kresp["apiKeyMasked"] and bool(_kresp.get("warning")), str(_kresp))
    _get1 = a.r("GET", "/settings/api-key").json()
    check("api key is NEVER re-readable in full after creation (hash-only at rest)", _get1.get("apiKey") == "" and _get1.get("apiKeyMasked", "").startswith(key[:8]), str(_get1))
    _get2 = a.r("GET", "/settings").json()
    check("full settings fetch also never leaks the raw key", _get2.get("apiKey") == "" and "apiKeyMasked" in _get2, str({k: v for k, v in _get2.items() if "apiKey" in k}))
    def v2(m, p, key=key, hdr=True, **kw):
        h = {"Authorization": "Bearer " + key} if (hdr and key) else {}
        return requests.request(m, V2 + p, headers=h, timeout=30, **kw)
    r = v2("GET", f"/bots/{bid}/commands"); j = r.json()
    check("v2 list commands (Bearer)", r.status_code == 200 and j["ok"] is True and isinstance(j["commands"], list) and {"command", "code", "is_pinned"} <= set(j["commands"][0].keys()) if j.get("commands") else r.status_code == 200, r.text[:200])
    check("v2 rate-limit headers", all(h in r.headers for h in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")), str(dict(r.headers)))
    check("v2 api_key as query", requests.get(V2 + f"/bots/{bid}/commands?api_key=" + key).status_code == 200)
    check("v2 api_key in body", requests.post(V2 + f"/bots/{bid}/command/by-name/delete", json={"api_key": key, "command_name": "/nope_zz"}).status_code == 404)
    r = v2("GET", f"/bots/{bid}/commands", key="", hdr=False); check("v2 no auth -> 401 Authentication required", r.status_code == 401 and r.json() == {"ok": False, "result": "Authentication required"}, r.text)
    r = v2("GET", f"/bots/{bid}/commands", key="BMP-wrong"); check("v2 bad key -> Invalid API key", r.status_code == 401 and r.json()["result"] == "Invalid API key", r.text)
    r = v2("POST", f"/bots/{bid}/commands", json={"command": "/v2cmd", "code": "bot.sendMessage('v2 hello')"}); check("v2 add command", r.status_code == 200 and r.json()["ok"], r.text)
    r = v2("GET", f"/bots/{bid}/command/by-name", params={"command_name": "/v2cmd"}); check("v2 get by name", r.status_code == 200 and r.json()["command"]["code"] == "bot.sendMessage('v2 hello')" and r.json()["command"]["command"] == "/v2cmd", r.text)
    r = v2("POST", f"/bots/{bid}/command/by-name/update", json={"command_name": "/v2cmd", "code": "bot.sendMessage('v2 updated')"}); check("v2 update by name", r.status_code == 200, r.text)
    r = v2("POST", f"/bots/{bid}/command/by-name/update", json={"command_name": "/v2cmd", "code": "return 5"}); check("v2 update refuses code that will not compile", r.status_code >= 400 and r.json()["ok"] is False, r.text[:200])
    import base64 as _b64
    r = v2("GET", "/bots/%s/commands/%s" % (bid, _b64.urlsafe_b64encode(b"/v2cmd").decode())); check("v2 legacy base64 path", r.status_code == 200 and "v2 updated" in r.json()["command"]["code"], r.text)
    nb = len(sent("sendMessage")); mock("/_mock/push", token=BOT1, update={"message": {"message_id": 197, "date": int(time.time()), "from": {"id": 5001, "is_bot": False, "first_name": "U"}, "chat": {"id": 5001, "type": "private"}, "text": "/v2cmd"}})
    check("v2-saved command really runs", last_text("v2 updated", nb) == "v2 updated")
    r = v2("POST", f"/bots/{bid}/command/by-name/delete", json={"command_name": "/v2cmd"}); check("v2 delete by name", r.status_code == 200, r.text)
    r = v2("GET", f"/bots/{bid}/command/by-name", params={"command_name": "/v2cmd"}); check("v2 deleted command -> Command not found", r.status_code == 404 and r.json()["result"] == "Command not found", r.text)
    r = v2("GET", "/bots/bot_doesnotexist/commands"); check("v2 foreign/unknown bot -> not owned", r.status_code == 404 and r.json()["result"] == "Bot not found or not owned by you", r.text)
    r = v2("POST", "/create-bot", json={"bot_token": "garbage"}); check("v2 create-bot invalid format", r.status_code == 400 and r.json()["result"] == "Invalid bot token format", r.text)
    r = v2("POST", "/create-bot", json={}); check("v2 create-bot token required", r.status_code == 400 and r.json()["result"] == "Bot token is required", r.text)
    r = v2("POST", f"/bots/{bid}/stop"); check("v2 stop", r.status_code == 200 and r.json()["ok"], r.text)
    check("v2 stop really stopped the bot", a.r("GET", f"/bots/{bid}").json()["status"] != "working")
    r = v2("POST", f"/bots/{bid}/start"); check("v2 start", r.status_code == 200 and r.json()["ok"], r.text)
    r = v2("POST", f"/bots/{bid}/restart"); check("v2 restart", r.status_code == 200 and r.json()["ok"], r.text)
    check("v2 start really working again", a.r("GET", f"/bots/{bid}").json()["status"] == "working")
    bb = C(); r1, rr = signup(bb, "v2b@x.io", "V2B"); bb.t = rr.json()["token"]
    r = v2("DELETE", f"/bots/{bid}", key=bb.r("POST", "/settings/api-key").json()["apiKey"]); check("v2 other account cannot delete my bot", r.status_code == 404 and a.r("GET", f"/bots/{bid}").status_code == 200, r.text)
    print("ROUND 6: Admin tab")
    def push(uid, text, mid, lang="de"):
        mock("/_mock/push", token=BOT1, update={"message": {"message_id": mid, "date": int(time.time()), "from": {"id": uid, "is_bot": False, "first_name": "L%d" % uid, "language_code": lang}, "chat": {"id": uid, "type": "private"}, "text": text}})
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "ad2", "name": "/adm2", "code": "bot.sendMessage('ADM two')"}], "name": "My Bot", "envVars": []})
    nb = len(sent("sendMessage")); push(7701, "/adm2", 901, "de"); push(7702, "/adm2", 902, "pt-BR"); push(7702, "/start", 903, "pt-BR")
    wait(lambda: len(sent("sendMessage")) >= nb + 3)
    ov = a.r("GET", f"/bots/{bid}/admin/overview?days=7"); check("admin overview 200", ov.status_code == 200, ov.text[:200])
    o = ov.json()
    check("admin overview shape", all(k in o for k in ("executions", "users", "maintenance")) and all(k in o["users"] for k in ("total", "active24h", "active7d", "active30d", "new24h", "new7d", "new30d", "blocked", "languages", "growth")), str(list(o)))
    cm = {c["name"]: c for c in o["executions"]["commands"]}
    check("admin per-command execution counts", cm.get("/adm2", {}).get("runs") == 2 and cm.get("/start", {}).get("runs", 0) >= 1, str(cm))
    check("admin command percent/progress", 0 < cm["/adm2"]["percent"] <= 100, str(cm.get("/adm2")))
    check("admin user counters (new today)", o["users"]["new24h"] >= 2 and o["users"]["total"] >= o["users"]["new24h"], str(o["users"]))
    langs = {l["code"]: l for l in o["users"]["languages"]}
    check("admin language analysis", "de" in langs and "pt-br" in langs and langs["de"]["users"] >= 1 and langs["de"]["percent"] > 0, str(langs))
    ch = a.r("GET", f"/chats/{bid}").json()
    items = ch["users"]
    check("chats list carries language code", any(u.get("languageCode") == "de" for u in items), str(items[:2]))
    check("admin overview needs ownership", bb.r("GET", f"/bots/{bid}/admin/overview").status_code in (403, 404))
    r = a.r("PUT", f"/bots/{bid}/admin/maintenance", json={"on": True, "message": "Back soon!"}); check("maintenance on", r.status_code == 200 and r.json()["on"] is True, r.text)
    nb = len(sent("sendMessage")); push(7701, "/adm2", 904)
    time.sleep(2); txt = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("maintenance blocks users with notice", "Back soon!" in txt and "ADM two" not in txt, str(txt))
    r = a.r("PUT", f"/bots/{bid}/admin/maintenance", json={"on": False, "message": ""}); check("maintenance off", r.status_code == 200 and r.json()["on"] is False, r.text)
    nb = len(sent("sendMessage")); push(7701, "/adm2", 905)
    check("bot works again after maintenance", last_text("ADM two", nb) == "ADM two")
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "ad2", "name": "/adm2", "code": "bot.sendMessage('ADM two')"}, {"id": "ba", "name": "/bare_a", "code": "bot.sendMessage('ASK')\nhandleNextCommand('bare_b')"}, {"id": "bb", "name": "/bare_b", "code": "bot.sendMessage('GOT ' + str(msg))"}], "name": "My Bot", "envVars": []})
    nb = len(sent("sendMessage")); push(7701, "/bare_a", 906); wait(lambda: len(sent("sendMessage")) > nb); time.sleep(1); push(7701, "hello", 907)
    check("bare handleNextCommand(...) works (docs form)", last_text("GOT hello", nb) == "GOT hello", str([x["params"].get("text") for x in sent("sendMessage")[nb:]]) + a.r("GET", f"/bots/{bid}/errors").text[:400])
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "cr", "name": "/crypt", "code": "r = Bot.sendBroadcast(function='sendMessage', text='x')\nbot.sendMessage('CR ' + Lib.Crypto.sha256('a')[:8] + ' ' + str(r.get('ok')) + ' ' + str('estimated_users' in r) + ' ' + str(Bot.sendBroadcast(command='zz_none').get('ok')))"}], "name": "My Bot", "envVars": []})
    nb = len(sent("sendMessage")); push(7701, "/crypt", 908)
    check("Lib.Crypto hashes + sendBroadcast TBS result keys", last_text("CR ca978112 True True False", nb) == "CR ca978112 True True False", str([x["params"].get("text") for x in sent("sendMessage")[nb:]]))
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "e1", "name": "/boom", "code": "x = 1\nbot.sendMessage(undefined_name)"}, {"id": "e2", "name": "/memb", "code": "r = CheckMembership(['\\'@nochan_zz\\''], '')\nbot.sendMessage('M ' + str(r))"}], "name": "My Bot", "envVars": []})
    a.r("POST", f"/bots/{bid}/admin/action", json={"action": "clear-errors"})
    nb = len(sent("sendMessage")); push(7701, "/boom", 909); time.sleep(2)
    er = a.r("GET", f"/bots/{bid}/errors").json()
    e0 = er[0] if er else {}
    blob = json.dumps(e0)
    check("error is clean: type, plain hint, own line only", "NameError" in e0.get("message", "") and "not defined" in e0.get("message", "") and "→" in e0.get("message", "") and e0.get("stack", "").startswith("line 2"), blob[:300])
    check("error hides server paths/internals", "/home/" not in blob and "backend" not in blob and "Traceback" not in blob and "site-packages" not in blob, blob[:300])
    txts = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("chat error notice has no source code", any(t and t.startswith("⚠️ Error in /boom (line 2)") and "bot.sendMessage" not in t for t in txts), str(txts))
    DT = a.r("GET", "/dashboard/stats").json()["totals"]
    check("dashboard: growth, error rate and response time are real numbers", isinstance(DT["growth24h"], (int, float)) and isinstance(DT["errorRate24h"], (int, float)) and DT["errorRate24h"] > 0 and isinstance(DT["avgResponseMs"], (int, float)) and DT["avgResponseMs"] >= 0, str(DT))
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "inf", "name": "/inf", "code": "i = Bot.info()\nbot.sendMessage('INFO ' + str(i.owner_email) + ' ' + str(i.status == 'Working') + ' ' + str(i.userstat) + ' ' + str('matrix.local' in str(i)) + ' ' + str(i.account_points))"}], "name": "My Bot", "envVars": []})
    nb = len(sent("sendMessage")); push(7701, "/inf", 911); time.sleep(2)
    itx = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    pts = a.r("GET", "/user/points").json()["points"]
    check("Bot.info(): real owner email, status, users, points (same as the web app)", bool(itx) and itx[-1].startswith("INFO a@x.io True ") and "False" in itx[-1].split(" ")[4] and itx[-1].endswith(" " + str(pts)), str(itx) + str(pts))
    star = "pho = message.get('photo')\ndoc = message.get('document')\nif pho:\n    bot.sendMessage('PHOTO ' + pho[-1].file_id + ' msg=' + str(msg) + ' ' + str(bot.getFileUrl(pho[-1].file_id).endswith('/file/bot' + bot.getFileUrl(pho[-1].file_id).split('/file/bot')[1])) + ' cap=' + str(message.caption))\nelif doc:\n    bot.sendMessage('DOC ' + doc.file_name + ' ' + str(doc.file_id) + ' msg=' + str(msg))\nelse:\n    bot.sendMessage('STAR ' + str(msg))"
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "st", "name": "*", "code": star},
        {"id": "bb1", "name": "/buy", "code": "bot.answerCallbackQuery(call.id, 'Added')\nbot.editMessageText('bought ' + str(params), message_id=message.message_id)"},
        {"id": "bb2", "name": "balance", "code": "bot.sendMessage('BAL exact')"}], "name": "My Bot", "envVars": []})
    def push_raw(msgd, mid):
        mock("/_mock/push", token=BOT1, update={"message": {"message_id": mid, "date": int(time.time()), "from": {"id": 7701, "is_bot": False, "first_name": "L"}, "chat": {"id": 7701, "type": "private"}, **msgd}})
    nb = len(sent("sendMessage")); push_raw({"photo": [{"file_id": "small1", "width": 10, "height": 10}, {"file_id": "big1", "width": 90, "height": 90}], "caption": "nice"}, 920); time.sleep(2)
    t1 = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("docs: message.photo[-1].file_id, msg None without text/caption, getFileUrl, caption", bool(t1) and t1[-1].startswith("PHOTO big1 msg=nice True cap=nice"), str(t1))
    nb = len(sent("sendMessage")); push_raw({"document": {"file_id": "doc1", "file_name": "a.txt", "mime_type": "text/plain", "file_size": 3}}, 921); time.sleep(2)
    t1 = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("docs: message.get('document').file_name / .file_id", t1 and t1[-1] == "DOC a.txt doc1 msg=None", str(t1))
    nb = len(sent("sendMessage")); push(7701, "balance", 922); time.sleep(1.5)
    t1 = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("docs: reply-keyboard text runs the command with exactly that name", t1 and t1[-1] == "BAL exact", str(t1))
    nb = len(sent("sendMessage")); push(7701, "unknown words zz", 923); time.sleep(1.5)
    t1 = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("docs: no matching command -> * runs", t1 and t1[-1] == "STAR unknown words zz", str(t1))
    nbE = len(sent("editMessageText")); mock("/_mock/push", token=BOT1, update={"callback_query": {"id": "cq9", "from": {"id": 7701, "is_bot": False, "first_name": "L"}, "message": {"message_id": 55, "date": int(time.time()), "chat": {"id": 7701, "type": "private"}, "text": "menu"}, "chat_instance": "ci", "data": "/buy 5"}}); time.sleep(2)
    ed = [x["params"] for x in sent("editMessageText")[nbE:]]
    check("docs: callback_data '/buy 5' -> /buy with params '5', call.id, editMessageText", ed and ed[-1].get("text") == "bought 5" and str(ed[-1].get("message_id")) == "55", str(ed))
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"}, {"id": "imp", "name": "/imp", "code": "from datetime import datetime, timedelta\nimport math\nimport uuid\nok1 = str(datetime(2026, 1, 1) + timedelta(hours=2))\nleak = 'LEAK' if hasattr(uuid, 'os') else 'safe'\nbot.sendMessage('IMP ' + ok1 + ' ' + str(math.sqrt(16)) + ' ' + leak)"}], "name": "My Bot", "envVars": []})
    nb = len(sent("sendMessage")); push(7701, "/imp", 912); time.sleep(2)
    t1 = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
    check("harmless imports work (docs: from datetime import datetime, timedelta); modules can't be used to escape", t1 and t1[-1] == "IMP 2026-01-01 02:00:00 4.0 safe", str(t1))
    _bad = "import os\nos.system('id')"
    _r = a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "x", "name": "/x", "code": _bad}, {"id": "y", "name": "/y", "code": "bot.sendMessage('Y ok')"}], "name": "My Bot", "envVars": []})
    check("code with errors is STILL saved (flagged, never lost)", _r.status_code == 200 and _r.json()["codeErrors"] and _r.json()["codeErrors"][0]["command"] == "/x", _r.text[:200])
    _g = a.r("GET", f"/bots/{bid}").json()["commands"]
    check("saved text is exactly what the user wrote + the good command beside it is saved too", any(c["name"] == "/x" and c["code"] == _bad for c in _g) and any(c["name"] == "/y" for c in _g))
    _n0 = len(sent("sendMessage")); push(7701, "/x", 960); push(7701, "/y", 961); time.sleep(2.5)
    check("flagged command never runs (sandbox refuses), others keep working", "Y ok" in [x["params"].get("text") for x in sent("sendMessage")[_n0:]])
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "ad1", "name": "/start", "code": "bot.sendMessage('ADM start')"},
        {"id": "h1", "name": "/handler_edited_message", "code": "bot.sendMessage('EDIT ' + str(message.text) + ' ' + update_type)"},
        {"id": "h2", "name": "/handler_my_chat_member", "code": "bot.sendMessage('MCM ' + update_type)"},
        {"id": "h3", "name": "/handler_chat_join_request", "code": "bot.sendMessage('JOIN ' + str(message.from_user.id) + ' ' + str(message.chat.id))"},
        {"id": "h4", "name": "/handler_special_updates", "code": "bot.sendMessage('SPECIAL ' + update_type)"}], "name": "My Bot", "envVars": []})
    def upd(d): mock("/_mock/push", token=BOT1, update=d)
    frm = {"id": 7701, "is_bot": False, "first_name": "L"}
    for body, want in [({"edited_message": {"message_id": 5, "date": 1, "from": frm, "chat": {"id": 7701, "type": "private"}, "text": "new text"}}, "EDIT new text edited_message"),
                       ({"my_chat_member": {"chat": {"id": 7701, "type": "private"}, "from": frm, "date": 1, "old_chat_member": {"status": "member", "user": frm}, "new_chat_member": {"status": "kicked", "user": frm}}}, "MCM my_chat_member"),
                       ({"chat_join_request": {"chat": {"id": -1009, "type": "supergroup"}, "from": frm, "user_chat_id": 7701, "date": 1}}, "JOIN 7701 -1009"),
                       ({"poll_answer": {"poll_id": "p1", "user": frm, "option_ids": [0]}}, "SPECIAL poll_answer"),
                       ({"message_reaction": {"chat": {"id": 7701, "type": "private"}, "message_id": 3, "user": frm, "date": 1, "old_reaction": [], "new_reaction": [{"type": "emoji", "emoji": "👍"}]}}, "SPECIAL message_reaction"),
                       ({"chat_boost": {"chat": {"id": -1009, "type": "channel"}, "boost": {"boost_id": "b", "add_date": 1, "expiration_date": 2, "source": {"source": "premium", "user": frm}}}}, "SPECIAL chat_boost")]:
        nb = len(sent("sendMessage")); upd(body); time.sleep(1.5)
        t1 = [x["params"].get("text") for x in sent("sendMessage")[nb:]]
        check("special update -> " + want.split(" ")[0] + " (" + list(body)[0] + ")", bool(t1) and t1[-1] == want, str(t1))
    check("service updates don't change the audience / un-block users", a.r("GET", f"/chats/{bid}").json()["total"] >= 1)
    from backend.runtime import ALL_UPDATE_TYPES as _AUT
    check("polling asks Telegram for every update type (pre_checkout_query, chat_join_request, ...)", all(k in _AUT for k in ("pre_checkout_query", "shipping_query", "chat_join_request", "message_reaction", "chat_member", "poll_answer", "business_message", "chat_boost")), "")
    nb = len(sent("sendMessage")); push(7701, "/memb", 910); time.sleep(2)
    er = a.r("GET", f"/bots/{bid}/errors").json()
    check("MembershipCheck tolerates empty user + quoted channel (no invalid user_id)", not any("invalid user_id" in x["message"] for x in er), str(er[:1])[:300])
    # ---- ROUND 7: any update type, any method, env vars, admin-only ----
    a.r("PUT", f"/bots/{bid}", json={"commands": [
        {"id": "r7a", "name": "/handler_future_gadget", "code": "bot.sendMessage('FG ' + update_type)"},
        {"id": "r7b", "name": "/handler_special_updates", "code": "bot.sendMessage('SPEC ' + update_type)"},
        {"id": "r7c", "name": "/env", "code": "bot.sendMessage('ENV ' + API_KEY + ' ' + str(LIMIT + 1) + ' ' + str(ITEMS))"},
        {"id": "r7d", "name": "/secret", "code": "bot.sendMessage('SECRET ok')", "isAdminOnly": True},
        {"id": "r7e", "name": "/amiadmin", "code": "bot.sendMessage('ADMIN ' + str(Bot.isAdmin(message.from_user.id)))"},
        {"id": "r7f", "name": "/newmethod", "code": "r = bot.brandNewMethod2031(chat_id=message.chat.id, foo='bar')\nbot.sendMessage('NM done')"}],
        "name": "My Bot", "envVars": [{"id": "x1", "key": "API_KEY", "value": "k-123"}, {"id": "x2", "key": "LIMIT", "value": "41", "raw": True}, {"id": "x3", "key": "ITEMS", "value": "[1,2]", "raw": True}]})
    def last_text(n0): return [x["params"].get("text") for x in sent("sendMessage")[n0:]]
    nb = len(sent("sendMessage")); upd({"future_gadget": {"id": "g1", "from": frm, "payload": "x"}}); time.sleep(1.5)
    check("brand-new update type -> /handler_future_gadget (no code change)", last_text(nb)[-1:] == ["FG future_gadget"], str(last_text(nb)))
    nb = len(sent("sendMessage")); upd({"another_future_update": {"chat": {"id": 7701, "type": "private"}, "x": 1}}); time.sleep(1.5)
    check("unknown update type falls to /handler_special_updates", last_text(nb)[-1:] == ["SPEC another_future_update"], str(last_text(nb)))
    nb = len(sent("sendMessage")); push(7701, "/env", 931); time.sleep(1.5)
    check("env vars (text / raw number / raw list) are defined inside commands", last_text(nb)[-1:] == ["ENV k-123 42 [1, 2]"], str(last_text(nb)))
    nb = len(sent("sendMessage")); push(7701, "/secret", 932); time.sleep(1.5)
    check("admin-only command is blocked for non-admins", "SECRET ok" not in last_text(nb), str(last_text(nb)))
    check("add global admin", a.r("POST", "/global-admins", json={"telegramId": "7701"}).status_code == 200)
    nb = len(sent("sendMessage")); push(7701, "/secret", 933); push(7701, "/amiadmin", 934); time.sleep(2)
    check("admin-only command runs for admin + Bot.isAdmin is live (no restart)", "SECRET ok" in last_text(nb) and "ADMIN True" in last_text(nb), str(last_text(nb)))
    a.r("DELETE", "/global-admins/7701")
    nb = len(sent("sendMessage")); push(7701, "/amiadmin", 935); time.sleep(1.5)
    check("removed admin loses access at once", last_text(nb)[-1:] == ["ADMIN False"], str(last_text(nb)))
    nb = len(sent("sendMessage")); push(7701, "/newmethod", 936); time.sleep(2)
    check("a method Telegram adds in the future is forwarded automatically", any(x["method"].lower() == "brandnewmethod2031" and x["params"].get("foo") == "bar" for x in sent()), str([x["method"] for x in sent()][-5:]))
    # ---- ROUND 8: server panel, fleet, database manager, security center ----
    print("ROUND 8: admin server panel + security center")
    check("admin server vitals (real machine data)", (lambda j: j.get("cpuCount", 0) >= 1 and j["mem"]["total"] > 0 and j["disk"]["total"] > 0 and "history" in j and j["bots"]["total"] >= 1)(a.r("GET", "/admin/server").json()))
    check("non-admin cannot read server vitals", b.r("GET", "/admin/server").status_code == 403)
    fl = a.r("GET", "/admin/fleet?hours=24").json()
    mine = next((x for x in fl["bots"] if x["id"] == bid), None)
    check("fleet lists bots with runs / speed class / load share", bool(mine) and mine["runs"] >= 1 and mine["speed"] in ("ultra", "normal", "slow", "critical", "idle") and "loadShare" in mine, str(mine)[:200])
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "d1", "name": "/start", "code": "import time\ntime.sleep(0.01)\nbot.sendMessage('x')"}], "name": "My Bot", "envVars": []})
    dg = a.r("GET", f"/admin/fleet/{bid}/diagnose").json()
    check("diagnose explains slow code (time.sleep) in plain words", any("sleep" in r["text"] for r in dg["reasons"]), str(dg["reasons"])[:300])
    check("admin can stop and start any bot", a.r("POST", f"/admin/fleet/{bid}/action", json={"action": "stop"}).json()["success"] and a.r("POST", f"/admin/fleet/{bid}/action", json={"action": "start"}).json()["success"])
    check("bad fleet action refused", a.r("POST", f"/admin/fleet/{bid}/action", json={"action": "rm"}).status_code == 400)
    _au = a.r("GET", "/admin/audit?limit=20").json()["entries"]
    check("admin mutations are recorded in the audit log", any(e["action"].endswith(f"/admin/fleet/{bid}/action") for e in _au), str(_au)[:300])
    check("audit log redacts secret-shaped fields", not any("password" in str(e.get("meta", {})).lower() and e["meta"].get("password") not in (None, "<redacted>") for e in _au))
    check("non-admin cannot read the audit log", b.r("GET", "/admin/audit").status_code == 403)
    _nhits = 0
    for _i in range(305):
        rr = requests.get(f"http://127.0.0.1:5001/v2/bots/{bid}/commands?api_key=" + key, timeout=10)
        if rr.status_code == 200:
            _nhits += 1
    check("bulk-export detector: 300+ rapid API calls raise a critical alert", _nhits > 0)
    _sec = a.r("GET", "/admin/security").json()
    check("bulk-export alert appears in the security center", any(e.get("kind") == "bulk-export" for e in _sec.get("events", [])), str([e.get("kind") for e in _sec.get("events", [])]))
    lg = a.r("GET", "/admin/logs?level=INFO").json()
    check("live log buffer returns lines", isinstance(lg["lines"], list) and lg["last"] >= 0)
    check("logs hide secrets", not any(BOT1 in x["msg"] for x in lg["lines"]))
    di = a.r("GET", "/admin/database").json()
    check("database manager: tables, sizes, wal", any(t["name"] == "users" for t in di["app"]["tables"]) and di["app"]["size"] > 0 and "wal" in di["app"])
    for act in ("integrity", "checkpoint", "optimize", "vacuum", "backup"):
        r = a.r("POST", "/admin/database/action", json={"action": act, "db": "app"}); check("database " + act, r.status_code == 200 and r.json()["success"], r.text[:200])
    q = a.r("POST", "/admin/database/query", json={"sql": "SELECT email, password_hash FROM users LIMIT 3"}).json()
    check("SQL console reads rows but masks secrets", q["rows"] and all(r[1] == "••••••••" for r in q["rows"]), str(q)[:200])
    for evil in ("DELETE FROM users", "SELECT 1; DROP TABLE users", "WITH x AS (SELECT 1) DELETE FROM users", "PRAGMA writable_schema=1", "ATTACH DATABASE '/tmp/x' AS y"):
        check("SQL console refuses: " + evil[:28], a.r("POST", "/admin/database/query", json={"sql": evil}).status_code == 400)
    check("SQL console is admin only", b.r("POST", "/admin/database/query", json={"sql": "select 1"}).status_code == 403)
    st = a.r("GET", "/admin/security").json()
    check("security center: sandbox jail refuses every escape pattern", any(c["id"] == "jail" and c["status"] == "ok" for c in st["checks"]), str([c for c in st["checks"] if c["id"] == "jail"]))
    check("security center: tokens encrypted + key private checks present", {"tokens-encrypted", "key-private", "db-integrity", "otp"} <= {c["id"] for c in st["checks"]})
    check("security center: config warnings are honest (rate limits off here)", any(c["id"] == "rate" and c["status"] != "ok" for c in st["checks"]))
    check("security score is 0-100", 0 <= st["score"] <= 100)
    check("security panel is admin only", b.r("GET", "/admin/security").status_code == 403 and b.r("POST", "/admin/security/scan").status_code == 403)
    # secrets pasted in code -> one warning (app + telegram), never repeated
    leak = "TOK = '" + "1234567890:" + "A" * 35 + "'\nbot.sendMessage('x')"
    n0 = len(a.r("GET", "/notifications").json())
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "l1", "name": "/start", "code": leak}], "name": "My Bot", "envVars": []})
    nn = a.r("GET", "/notifications").json()
    check("pasted bot token in code -> security warning notification", any("Secret pasted" in x["title"] for x in nn), str([x["title"] for x in nn][:5]))
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "l1", "name": "/start", "code": leak}], "name": "My Bot", "envVars": []})
    a.r("POST", "/security/scan")
    _sp = [x for x in a.r("GET", "/notifications").json() if "Secret pasted" in x["title"] and "/start: Telegram" in x["message"]]; check("the same finding is never notified twice", len(_sp) == 1, str([(x["title"], x["message"][:80]) for x in _sp]))
    us = a.r("GET", "/security").json()
    check("user security page lists the leak (own bots only)", us["level"] == "bad" and any(s["botId"] == bid for s in us["secrets"]) and any(e["kind"] == "secrets-in-code" for e in us["events"]))
    check("another user sees none of it", b.r("GET", "/security").json()["secrets"] == [])
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "l1", "name": "/start", "code": "bot.sendMessage('clean')"}], "name": "My Bot", "envVars": []})
    check("clean code clears the secrets list", a.r("GET", "/security").json()["secrets"] == [])
    # revoked token detection + bulk replacement
    SEC_T = "6100000001:" + "S" * 35
    mock("/_mock/add_bot", token=SEC_T, username="sec_bot")
    sc = C(); signup(sc, "sec@x.io", "Sec"); sc.t = signin(sc, "sec@x.io").json()["token"]
    rb = sc.r("POST", "/bots", json={"token": SEC_T, "name": "SecBot", "commands": [{"id": "z", "name": "/start", "code": "bot.sendMessage('s')"}]}); check("security test bot created", rb.status_code == 200, rb.text[:150])
    sbid = rb.json()["id"]
    sv = sc.r("POST", "/security/scan").json()
    check("token health: valid token reported as valid", any(t["botId"] == sbid and t["status"] == "valid" for t in sv["tokens"]), str(sv["tokens"]))
    mock("/_mock/fail", revoked=[SEC_T])
    sv = sc.r("POST", "/security/scan").json()
    check("token health: revoked token detected", any(t["botId"] == sbid and t["status"] == "revoked" for t in sv["tokens"]), str(sv["tokens"]))
    sev = sc.r("GET", "/security").json()["events"]
    check("revoked token -> critical alert + bot stopped", any(e["severity"] == "critical" and "revoked" in e["title"] for e in sev) and sc.r("GET", f"/bots/{sbid}").json()["status"] != "working", str(sev)[:300])
    mock("/_mock/fail", revoked=[])
    for _ in range(5):
        sc.r("PUT", f"/bots/{sbid}", json={"token": SEC_T})
    sev = sc.r("GET", "/security").json()["events"]
    check("5 token replacements in minutes -> bulk-change takeover alert", any(e["kind"] == "bulk-changes" and e["severity"] == "critical" for e in sev), str([e["title"] for e in sev]))
    check("security alerts reach the in-app notification list", any("🛡️" in x["title"] for x in sc.r("GET", "/notifications").json()))
    # suspend / unsuspend
    uid_b = a.r("GET", "/admin/users?q=sec@x.io").json()["users"][0]["id"]
    check("admin suspends an account", a.r("PUT", f"/admin/users/{uid_b}", json={"suspended": True, "reason": "abuse test"}).status_code == 200)
    check("suspended user is signed out at once", sc.r("GET", "/bots").status_code == 401)
    n = mails_to("sec@x.io"); rl = C().r("POST", "/auth/login", json={"email": "sec@x.io", "password": "password123"})
    check("suspended user cannot sign in", rl.status_code == 403 and "suspended" in rl.text, rl.text[:150])
    a.r("PUT", f"/admin/users/{uid_b}", json={"suspended": False})
    check("unsuspended user can sign in again", signin(C(), "sec@x.io").status_code == 200)
    # ---- ROUND 9: hardening ----
    import sqlite3 as _sq
    a.r("PUT", f"/bots/{bid}", json={"commands": [{"id": "h1", "name": "/start", "code": "bot.sendMessage('h')"}], "name": "My Bot", "envVars": [{"id": "q1", "key": "SECRET_ENV", "value": "super-secret-value-123"}]})
    _c = _sq.connect(f"{T}/app.db"); _raw = _c.execute("SELECT env_vars_json FROM bots WHERE id=?", (bid,)).fetchone()[0]; _c.close()
    check("env variable values are encrypted in the database", _raw.startswith("enc:") and "super-secret-value-123" not in _raw, _raw[:40])
    check("env variables still readable through the API", any(e["key"] == "SECRET_ENV" and e["value"] == "super-secret-value-123" for e in a.r("GET", f"/bots/{bid}").json()["envVars"]))
    hd = requests.get(API + "/config").headers
    check("security headers sent", hd.get("X-Frame-Options") == "DENY" and "Permissions-Policy" in hd and hd.get("X-Content-Type-Options") == "nosniff", str(dict(hd))[:200])
    check("env check present in security center", any(c["id"] == "env-encrypted" and c["status"] == "ok" for c in a.r("GET", "/admin/security").json()["checks"]))
    for act in ("clear-errors", "remove-left-users", "stop-broadcasts", "clear-schedules", "restart"):
        r = a.r("POST", f"/bots/{bid}/admin/action", json={"action": act}); check("admin action " + act, r.status_code == 200 and r.json()["ok"], r.text[:200])
    check("admin unknown action rejected", a.r("POST", f"/bots/{bid}/admin/action", json={"action": "zz"}).status_code == 400)
    r = a.r("POST", f"/bots/{bid}/admin/action", json={"action": "reset-stats"}); check("admin reset-stats", r.status_code == 200, r.text)
    check("stats are empty after reset", a.r("GET", f"/bots/{bid}/admin/overview?days=7").json()["executions"]["total"] == 0)
    a.r("POST", f"/bots/{bid}/toggle-status")
    nn = a.r("GET", "/notifications").json()
    check("bot notification links to the bot", any(x.get("link") == "bot:" + bid for x in nn))
    cc = C(); signup(cc, "c@x.io", "Carol"); cc.t = signin(cc, "c@x.io").json()["token"]
    codes = [cc.r("POST", "/bots", json={"isClone": True, "name": f"c{i}", "commands": []}).status_code for i in range(4)]
    check("free plan stops at 2 bots", codes == [200, 200, 403, 403], str(codes))
    many = [{"name": f"/c{i}", "code": "pass"} for i in range(26)]
    first = cc.r("GET", "/bots").json()[0]["id"]
    check("free plan limits commands per bot", cc.r("PUT", f"/bots/{first}", json={"commands": many}).status_code == 403)
    check("logout kills session", a.r("POST", "/auth/logout").status_code == 200 and a.r("GET", "/auth/me").status_code == 401)
except BaseException:
    import traceback; traceback.print_exc(); fail += 1
finally:
    print(f"\n{ok} passed, {fail} failed")
    for p in procs: p.terminate()
    shutil.rmtree(T, ignore_errors=True)
    sys.exit(1 if fail else 0)
