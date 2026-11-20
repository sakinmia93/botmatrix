"""UI checks: Plans & Billing, notification click-through, Preferences switches, editor Run/Format, public receipt."""
import sys, time, json
sys.path.insert(0, "tests")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT, "username": f"p{N}_bot"})
adm = register("admin@x.io", "Admin") if True else None
atok = adm["token"] if adm and adm.get("token") else login("admin@x.io")["token"]
email = f"p{N}@x.io"
usr = register(email, "Pat"); tok = usr["token"]
api("POST", "/admin/plan", atok, json={"email": "admin@x.io", "plan": "Matrix Pro"})
api("POST", "/admin/plan", atok, json={"email": email, "plan": "Matrix Pro"})
bot = api("POST", "/bots", tok, json={"token": BOT}).json(); bid = bot["id"]
api("PUT", f"/bots/{bid}", tok, json={"commands": [{"id": "c1", "name": "/start", "code": "x=1\nbot.sendMessage(chat_id=chat_id,text='Hello  '+str(x))"}]})
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser()
ctx, page, _, errs = login_page(b, email, "password123")
page.wait_for_timeout(2500)
# ---- plans
page.get_by_text("Plans & Billing", exact=True).first.click(); page.wait_for_timeout(1500)
for n in ("Matrix Free", "Matrix Pro", "Matrix Growth", "Matrix Ultra"):
    check(f"plan {n} listed", page.get_by_role("heading", name=n).count() == 1)
check("prices shown", page.get_by_text("$19").count() == 1 and page.get_by_text("500,000 points").count() >= 1)
links = page.locator("a:has-text('Contact Admin')")
check("Contact Admin under every plan, URL from DB", links.count() == 4 and links.first.get_attribute("href") == "https://t.me/matrix_admin")
check("current plan marked", page.get_by_text("Current", exact=True).count() == 1)
check("unlimited bots on Ultra", page.get_by_text("Unlimited bots").count() == 1)
page.screenshot(path="/tmp/shots/plans.png", full_page=True)
# ---- preferences
page.get_by_text("Settings", exact=True).last.click(); page.wait_for_timeout(1500)
page.get_by_text("Preferences", exact=True).first.click(); page.wait_for_timeout(800)
sw = page.locator("#pref-toggle-notifications-btn")
check("notification switch present and on", sw.count() == 1 and sw.get_attribute("aria-checked") == "true")
sw.click(); page.wait_for_timeout(1200)
check("switch turns off", sw.get_attribute("aria-checked") == "false")
check("per-type switches hidden when off", page.locator("#pref-toggle-type-transfers").count() == 0)
time.sleep(1)
check("saved on the server", api("GET", "/settings", tok).json().get("notificationsEnabled") is False)
sw.click(); page.wait_for_timeout(600)
page.locator("#pref-toggle-type-billing").click(); page.wait_for_timeout(1200)
check("type switch saved", api("GET", "/settings", tok).json().get("notificationTypes", {}).get("billing") is False)
page.locator("#pref-toggle-type-billing").click(); page.wait_for_timeout(800)
page.screenshot(path="/tmp/shots/prefs.png", full_page=True)
# ---- notification click-through: a transfer request arrives
oth = register(f"q{N}@x.io", "Quinn")["token"]
r = api("POST", f"/bots/{bid}/transfer", tok, json={"email": f"q{N}@x.io"}); check("transfer created", r.status_code == 200)
octx, opage, _, oerrs = login_page(b, f"q{N}@x.io", "password123"); opage.wait_for_timeout(3500)
opage.locator("#navbar-notifications-btn").click(); opage.wait_for_timeout(600)
opage.get_by_text("Bot transfer request").first.click(); opage.wait_for_timeout(1500)
check("clicking the notification opens Transfers", opage.get_by_text("Transfers", exact=False).count() >= 2 and opage.get_by_text("Audit", exact=False).count() >= 1)
opage.screenshot(path="/tmp/shots/notif_click.png")
# accept then audit proof receipt
tid = api("GET", "/transfers", oth).json()["incoming"][0]["id"]
api("POST", f"/transfers/{tid}/accept", oth)
opage.reload(); opage.wait_for_timeout(2500)
opage.get_by_text("Transfers", exact=True).first.click(); opage.wait_for_timeout(1500)
opage.get_by_role("button", name="Audit Proof").first.click(); opage.wait_for_timeout(1200)
txt = opage.locator("text=/receipt\\//").first.inner_text()
check("audit proof shows a public link", "/receipt/" in txt)
pub = ctx.new_page(); pub.goto(txt.strip()); pub.wait_for_timeout(1500)
check("link opens a verified receipt without login", pub.get_by_text("Verified transfer receipt").count() == 1)
pub.screenshot(path="/tmp/shots/receipt.png")
bad_p = ctx.new_page(); bad_p.goto(txt.strip()[:-3] + "abc"); bad_p.wait_for_timeout(1200)
check("altered link is rejected", bad_p.get_by_text("Receipt not valid").count() == 1)
# ---- editor Run + Format
page.get_by_text("My Bots", exact=True).first.click(); page.wait_for_timeout(1200)
page.get_by_role("button", name="Edit").first.click(); page.wait_for_timeout(1800)
page.get_by_text("Commands", exact=True).first.click(); page.wait_for_timeout(1000)
page.get_by_text("/start").first.click(); page.wait_for_timeout(2500)
page.screenshot(path="/tmp/shots/editor0.png")
page.get_by_role("button", name="Format").click(); page.wait_for_timeout(1200)
code = page.evaluate("ace.edit(document.querySelector('.ace_editor')).getValue()")
check("Format cleans the code", "x = 1" in code and "text='Hello  ' + str(x)" in code and "chat_id=chat_id" in code)
page.get_by_role("button", name="Run", exact=True).click(); page.wait_for_timeout(2500)
check("Run shows the real result", page.get_by_text("Run output").count() == 1 and page.locator('pre').count() >= 1 and 'Hello  1' in page.locator('pre').first.inner_text())
page.screenshot(path="/tmp/shots/editor_run.png")
print("page errors:", errs[:3], oerrs[:3])
print(f"\n{ok} passed, {bad} failed")
b.close(); pw.stop()
