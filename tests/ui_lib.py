import json, time, requests
from playwright.sync_api import sync_playwright
BASE = "http://localhost:3000"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

def api(m, p, tok=None, **kw):
    h = {"Authorization": "Bearer " + tok} if tok else {}
    return requests.request(m, BASE + "/api" + p, headers=h, timeout=30, **kw)

import os
MAILF = os.path.join(os.environ.get("UI_TMP", "/tmp/ui"), "mails.jsonl")

def mail_code(to, n=0, t=10):
    end = time.time() + t
    while time.time() < end:
        try:
            ms = [json.loads(l) for l in open(MAILF) if l.strip()]
        except FileNotFoundError:
            ms = []
        ms = [m for m in ms if m["to"] == to]
        if len(ms) > n: return ms[-1]["code"]
        time.sleep(0.2)
    return ""

def n_mails(to):
    try: return len([1 for l in open(MAILF) if l.strip() and json.loads(l)["to"] == to])
    except FileNotFoundError: return 0

def register(email, name, pw="password123"):
    """sign up through the real e-mail code flow (local SMTP sink)"""
    n = n_mails(email)
    api("POST", "/auth/register", json={"email": email, "password": pw, "name": name})
    return api("POST", "/auth/register", json={"email": email, "password": pw, "name": name, "code": mail_code(email, n)}).json()

def login(email, pw="password123"):
    n = n_mails(email)
    api("POST", "/auth/login", json={"email": email, "password": pw})
    return api("POST", "/auth/login", json={"email": email, "password": pw, "code": mail_code(email, n)}).json()

def browser():
    pw = sync_playwright().start()
    b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    return pw, b

def login_page(b, email, pw, w=1366, h=860):
    ctx = b.new_context(viewport={"width": w, "height": h})
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append("console:" + m.text) if m.type == "error" else None)
    d = login(email, pw)
    page.add_init_script(f"localStorage.setItem('telebot_auth_token','{d['token']}');localStorage.setItem('telebot_user',JSON.stringify({json.dumps(d['user'])}));")
    page.goto(BASE)
    return ctx, page, d["token"], errs
