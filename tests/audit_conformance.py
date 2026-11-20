"""Checks every item of the v15 audit checklist against the real engine through the editor's test runner."""
import csv, sys, time, requests, json
sys.path.insert(0, "tests")
from ui_lib import api
CSV = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/v15b/V15_FULL_AUDIT_CHECKLIST.csv"
N = int(time.time()) % 900000000 + 100000000
tok_bot = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": tok_bot, "username": f"c{N}_bot"})
t = api("POST", "/auth/register", json={"email": f"c{N}@x.io", "password": "password123", "name": "C"}).json()["token"]
bid = api("POST", "/bots", t, json={"token": tok_bot}).json()["id"]
rows = list(csv.DictReader(open(CSV)))
exprs = []
for r in rows:
    c, it = r["Category"], r["Documented item"].strip()
    if c in ("Account method", "Bot high-level method", "User method", "Library function", "Predefined/global surface", "TPY safe builtin", "Broadcast subsystem"):
        e = it
    elif c == "Telegram transport":
        e = "bot." + it.split(".", 1)[1] if it.startswith("Bot.") else it
    elif c == "Library":
        e = "libs." + it
    else:
        continue
    if " " in e.split("(")[0].strip() and "/" not in e: continue
    e = e.split(" / ")[0].split("(")[0].strip()
    if not e or " " in e: continue
    exprs.append((c, e))
bad = []
for c, e in exprs:
    parts = e.split(".")
    if parts[0] == "libs" and len(parts) > 3:  # nested class members: check up to the class
        parts = parts[:3]
    code = "try:\n    _x = " + ".".join(parts) + "\nexcept (AttributeError, NameError, KeyError) as e:\n    bot.sendMessage(chat_id=1, text='MISSING')\n"
    r = api("POST", f"/bots/{bid}/test-command", t, json={"name": "/t", "code": code}).json()
    calls = r.get("calls") or []
    if r.get("error") or any("MISSING" in json.dumps(x) for x in calls):
        bad.append((c, e, (r.get("error") or "")[:80]))
print(len(exprs), "checked,", len(bad), "missing")
for b in bad: print(b)
