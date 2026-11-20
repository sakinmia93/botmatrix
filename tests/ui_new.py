"""UI checks: mandatory login OTP, Intro Start/Stop, token eye, user import/export, notification shown once."""
import sys, time, json, os
sys.path.insert(0, "tests")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT, "username": f"n{N}_bot"})
email = f"n{N}@x.io"
r = register(email, "Newbie"); tok = r["token"]
_adm = login("admin@x.io")["token"]
api("POST", "/admin/plan", _adm, json={"email": email, "plan": "Matrix Pro"})
bot = api("POST", "/bots", tok, json={"token": BOT}).json(); bid = bot["id"]
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser(); ctx = b.new_context(viewport={"width": 1366, "height": 1000}, accept_downloads=True); page = ctx.new_page()
errs = []
page.on("pageerror", lambda e: errs.append(str(e)))
# ---- 1. login with e-mailed code
page.goto(BASE); page.wait_for_timeout(1500)
page.locator("input[type=email]").first.fill(email); page.locator("input[type=password]").first.fill("password123")
n = n_mails(email)
page.locator("form button[type=submit]").first.click(); page.wait_for_timeout(1500)
check("login asks for the e-mailed code", page.locator("#register-otp-input").count() == 1)
page.locator("#register-otp-input").fill("000000"); page.locator("form button[type=submit]").first.click(); page.wait_for_timeout(1200)
check("wrong code shows an error", page.get_by_text("wrong or has expired").count() >= 1)
page.locator("#register-otp-input").fill(mail_code(email, n)); page.locator("form button[type=submit]").first.click(); page.wait_for_timeout(2500)
check("right code signs in", page.locator("#register-otp-input").count() == 0 and page.get_by_text("My Bots", exact=True).count() >= 1)
page.screenshot(path="/tmp/shots/n_login.png")
# ---- 2. open the bot
page.get_by_text("My Bots", exact=True).first.click(); page.wait_for_timeout(1200)
page.get_by_role("button", name="Edit").first.click(); page.wait_for_timeout(1800)
# Intro Start / Stop
stop = page.get_by_role("button", name="Stop Bot")
check("intro shows Stop Bot for a running bot", stop.count() >= 1)
stop.first.click(); page.wait_for_timeout(1200)
conf = page.get_by_role("button", name="Stop", exact=True)
if conf.count(): conf.last.click(); page.wait_for_timeout(1500)
st = api("GET", f"/bots/{bid}", tok).json()["status"]
check("Stop really stops the bot (server)", st == "stopped")
check("Intro now offers Start Bot", page.get_by_role("button", name="Start Bot").count() >= 1)
page.get_by_role("button", name="Start Bot").first.click(); page.wait_for_timeout(1200)
conf = page.get_by_role("button", name="Start", exact=True)
if conf.count(): conf.last.click(); page.wait_for_timeout(1500)
check("Start really starts the bot (server)", api("GET", f"/bots/{bid}", tok).json()["status"] == "working")
# ---- 3. Manage: import / export
page.screenshot(path="/tmp/shots/n_pre_manage.png"); page.get_by_role("button", name="Manage", exact=True).first.click(timeout=5000); page.wait_for_timeout(1000)
check("Users import/export card is under Manage", page.get_by_text("Users — Import & Export").count() == 1)
ids = "\n".join(str(900000 + i) for i in range(25))
open("/tmp/ui_users.txt", "w").write(ids)
page.locator("#users-import-export input[type=file]").set_input_files("/tmp/ui_users.txt")
page.wait_for_timeout(1500); page.screenshot(path="/tmp/shots/n_import_running.png")
check("import progress shows", page.get_by_text("Verifying").count() + page.get_by_text("Import complete").count() >= 1)
page.get_by_text("Import complete").wait_for(timeout=15000)
check("import adds all 25 verified users", page.get_by_text("25 added").count() == 1 or "25" in page.locator("#users-import-export").inner_text())
check("server has 25 audience rows", api("GET", f"/chats/{bid}", tok).json()["total"] == 25)
page.get_by_role("button", name="Start export").click()
page.get_by_role("button", name="Download").wait_for(timeout=15000)
with page.expect_download() as dl: page.get_by_role("button", name="Download").click()
path = dl.value.path(); txt = open(path).read()
check("export downloads a CSV with 25 users", len(txt.strip().splitlines()) == 26 and dl.value.suggested_filename.endswith(".csv"))
page.screenshot(path="/tmp/shots/n_manage.png", full_page=True)
# ---- 4. Settings: token eye
page.get_by_role("button", name="Settings", exact=True).last.click(); page.wait_for_timeout(1000)
eye = page.locator("button[title='Show token']")
check("eye icon is on the token card", eye.count() == 1)
check("token hidden by default", BOT not in page.content())
eye.click(); page.wait_for_timeout(800)
check("eye reveals the real token", BOT in page.content())
page.locator("button[title='Hide token']").click(); page.wait_for_timeout(300)
check("eye hides it again", BOT not in page.content())
page.screenshot(path="/tmp/shots/n_settings.png")
# ---- 5. notification popup shows once across reloads
api("POST", "/telegram/test-alert", tok)
for i in range(3): page.reload(); page.wait_for_timeout(2500)
shown = page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('bm_notif_shown_'))")
check("notification dedupe key persisted", len(shown) >= 1)
print("pageerrors:", errs[:5])
print(f"\n{ok} passed, {bad} failed")
b.close(); pw.stop(); sys.exit(1 if bad else 0)
