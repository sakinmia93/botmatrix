"""Registration with a real e-mailed code, against a local SMTP sink (no external mail)."""
import os, re, socketserver, subprocess, sys, tempfile, threading, time, requests, base64
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAILS = []

class H(socketserver.StreamRequestHandler):
    def handle(self):
        w = lambda s: (self.wfile.write((s + "\r\n").encode()), self.wfile.flush())
        w("220 sink"); data = False; buf = []
        for raw in self.rfile:
            line = raw.decode(errors="ignore").rstrip("\r\n")
            if data:
                if line == ".":
                    MAILS.append("\n".join(buf)); data = False; buf = []; w("250 ok")
                else: buf.append(line)
                continue
            u = line.upper()
            if u.startswith("EHLO"): w("250-sink"); w("250 AUTH PLAIN LOGIN")
            elif u.startswith("AUTH PLAIN"): w("235 ok")
            elif u.startswith("AUTH LOGIN"): w("334 VXNlcm5hbWU6"); self.rfile.readline(); w("334 UGFzc3dvcmQ6"); self.rfile.readline(); w("235 ok")
            elif u.startswith("DATA"): w("354 go"); data = True
            elif u.startswith("QUIT"): w("221 bye"); return
            else: w("250 ok")

class S(socketserver.ThreadingTCPServer): allow_reuse_address = True
srv = S(("127.0.0.1", 2526), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
T = tempfile.mkdtemp()
env = dict(os.environ, APP_DB_PATH=f"{T}/a.db", DATABASE_URL=f"sqlite:///{T}/e.db", API_PORT="5002", SECRET_KEY="t",
           SMTP_HOST="127.0.0.1", SMTP_PORT="2526", SMTP_STARTTLS="0", SMTP_USER="u@x.io", SMTP_PASSWORD="pw", BM_TEST_NO_RATE_LIMIT="1")
p = subprocess.Popen([sys.executable, "-m", "backend.server"], cwd=ROOT, env=env)
API = "http://127.0.0.1:5002/api"; bad = 0
def check(n, c):
    global bad; print(("  ✓ " if c else "  ✗ ") + n); bad += 0 if c else 1
try:
    for _ in range(60):
        try: requests.get(API + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    r = requests.post(API + "/auth/register", json={"email": "o@x.io", "password": "password123", "name": "O"}).json()
    check("register asks for a code, no session yet", r.get("otpRequired") is True and "token" not in r)
    time.sleep(0.5); body = MAILS[-1] if MAILS else ""
    code = (re.search(r"code: (\d{6})", body) or [None, ""])[1]
    check("real e-mail was sent with a 6-digit code", len(code) == 6 and "o@x.io" in body)
    check("wrong code refused", requests.post(API + "/auth/register", json={"email": "o@x.io", "password": "password123", "name": "O", "code": "000000"}).status_code == 400)
    r = requests.post(API + "/auth/register", json={"email": "o@x.io", "password": "password123", "name": "O", "code": code})
    check("right code creates the account", r.status_code == 200 and r.json().get("token"))
    check("code is single-use", requests.post(API + "/auth/register", json={"email": "o@x.io", "password": "password123", "name": "O", "code": code}).status_code in (400, 409))
    n = len(MAILS)
    r = requests.post(API + "/auth/login", json={"email": "o@x.io", "password": "password123"}).json()
    check("login asks for a code, no session yet", r.get("otpRequired") is True and "token" not in r)
    time.sleep(0.5); lc = (re.search(r"code: (\d{6})", MAILS[-1]) or [None, ""])[1]
    check("login code e-mailed", len(lc) == 6 and len(MAILS) > n)
    check("login with wrong code refused", requests.post(API + "/auth/login", json={"email": "o@x.io", "password": "password123", "code": "000000"}).status_code == 400)
    r = requests.post(API + "/auth/login", json={"email": "o@x.io", "password": "password123", "code": lc})
    check("login with the right code", r.status_code == 200 and r.json().get("token"))
    n = len(MAILS)
    requests.post(API + "/auth/forgot-password", json={"email": "o@x.io"}); time.sleep(0.6)
    check("reset code is e-mailed too", len(MAILS) > n and "reset your BOT MATRIX password" in MAILS[-1])
finally:
    p.terminate(); srv.shutdown(); sys.exit(1 if bad else 0)

