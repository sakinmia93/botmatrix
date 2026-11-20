import json, os, subprocess, sys, time, requests, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = tempfile.mkdtemp()
MOCK = "http://127.0.0.1:8081"; API = "http://127.0.0.1:5001/api"
CONNECT = "9000000001:" + "C" * 35
BOT1 = "8822824343:" + "A" * 35
BOT2 = "7000000002:" + "B" * 35
env = dict(os.environ, TELEGRAM_API_ROOT=MOCK, CONNECT_BOT_TOKEN=CONNECT, APP_DB_PATH=f"{T}/app.db",
           DATABASE_URL=f"sqlite:///{T}/engine.db", API_PORT="5001", SECRET_KEY="test-secret", TURNSTILE_ENABLED="1", TURNSTILE_SECRET_KEY="sek", TURNSTILE_SITE_KEY="site", TURNSTILE_VERIFY_URL="http://127.0.0.1:8081/turnstile", REQUIRE_EMAIL_OTP="0", ADMIN_EMAILS="a@x.io", ADMIN_CONTACT_URL="https://t.me/matrix_admin", PYTHONUNBUFFERED="1")
MAILF = f"{T}/mails.jsonl"; open(MAILF, "w").close()
env.update(SMTP_HOST="127.0.0.1", SMTP_PORT="2527", SMTP_STARTTLS="0", SMTP_USER="u@x.io", SMTP_PASSWORD="pw")
procs = [subprocess.Popen([sys.executable, "tests/mock_telegram.py", "8081"], cwd=ROOT), subprocess.Popen([sys.executable, "tests/smtp_sink.py", "2527", MAILF], cwd=ROOT)]
time.sleep(0.8)
def mock(path, **b): return requests.post(MOCK + path, json=b).json()
mock("/_mock/add_bot", token=CONNECT, username="matrix_connect_bot")
mock("/_mock/add_bot", token=BOT1, username="my_test_bot")
mock("/_mock/add_bot", token=BOT2, username="second_bot")
def start():
    s = subprocess.Popen([sys.executable, "-m", "backend.server"], cwd=ROOT, env=env); procs.append(s)
    for _ in range(60):
        try:
            requests.get(API + "/health", timeout=1); return s
        except Exception: time.sleep(0.5)
srv = start()
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
    cfg = requests.get(API + "/config").json()
    check("public config shows site key", cfg["turnstile"] == {"enabled": True, "siteKey": "site"} and cfg["otpRequired"] is False, str(cfg))
    reg = lambda **k: requests.post(API + "/auth/register", json={"email": "t@x.io", "password": "password123", "name": "T", **k})
    check("register without token refused", reg().status_code == 400)
    check("register with bad token refused", reg(captchaToken="nope").status_code == 400)
    r = reg(captchaToken="good-token"); check("register with good token (OTP off -> direct)", r.status_code == 200 and r.json().get("token"), r.text)
    lg = lambda pw="password123", **k: requests.post(API + "/auth/login", json={"email": "t@x.io", "password": pw, **k})
    check("login without token refused", lg().status_code == 400)
    check("login with good token", lg(captchaToken="good-token").status_code == 200)
    codes = [lg("wrong-password", captchaToken="good-token").status_code for _ in range(15)]
    check("no rate limit on repeated wrong logins", set(codes) == {401}, str(set(codes)))
    check("forgot-password needs token", requests.post(API + "/auth/forgot-password", json={"email": "t@x.io"}).status_code == 400)
finally:
    print(f"\n{ok} passed, {fail} failed")
    for p in procs: p.terminate()
    shutil.rmtree(T, ignore_errors=True)
    sys.exit(1 if fail else 0)
