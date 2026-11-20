"""UI checks: command names, duplicates, Edit raw, Intro/Errors tabs, draft restore with undo history."""
import sys, time
sys.path.insert(0, "tests")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT, "username": f"s{N}_bot"})
email = f"s{N}@x.io"
tok = register(email, "Sam")["token"]
bid = api("POST", "/bots", tok, json={"token": BOT}).json()["id"]
api("PUT", f"/bots/{bid}", tok, json={"commands": [{"id": "c1", "name": "/start", "code": "x = 1\n"}]})
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser()
ctx, page, _, errs = login_page(b, email, "password123"); page.wait_for_timeout(2500)
page.get_by_text("My Bots", exact=True).first.click(); page.wait_for_timeout(1200)
page.get_by_role("button", name="Edit").first.click(); page.wait_for_timeout(1800)
check("Intro shows real health", page.get_by_text("Health", exact=True).count() >= 1 and page.get_by_text("Telegram connection").count() >= 1)
check("no fake numbers", page.get_by_text("99.98").count() == 0 and page.get_by_text("Local Node").count() == 0 and page.get_by_text("+14.8%").count() == 0)
page.get_by_text("Errors", exact=True).first.click(); page.wait_for_timeout(1500)
check("Errors tab is live", page.get_by_text("No errors in the last 30 days").count() == 1)
page.get_by_text("Manage", exact=True).first.click(); page.wait_for_timeout(1000)
page.get_by_text("Edit raw").click(); page.wait_for_timeout(500)
page.locator("textarea").first.fill("APP_URL=https://x.io\nADMIN_IDS=[1,2]")
page.get_by_role("button", name="Apply").click(); page.wait_for_timeout(500)
check("Edit raw applies variables", page.locator("input[value='APP_URL']").count() >= 1)
page.get_by_text("Commands", exact=True).first.click(); page.wait_for_timeout(1000)
def open_start():
    page.get_by_text("/start").first.click(); page.wait_for_timeout(2200)
def ed(js): return page.evaluate("(()=>{const e=ace.edit(document.querySelector('.ace_editor'));" + js + "})()")
def leave():
    page.locator("button[title*='Back'], button[aria-label*='Back']").first.click(); page.wait_for_timeout(600)
    if page.get_by_role("button", name="Leave").count(): page.get_by_role("button", name="Leave").click()
    page.wait_for_timeout(1000)
open_start()
ed("e.session.insert({row:0,column:0},'# my draft\\n'); return 1")
page.wait_for_timeout(700)
ed("e.session.insert({row:0,column:0},'# second\\n'); return 1"); page.wait_for_timeout(700)
leave()
open_start()
check("first return asks to continue", page.get_by_text("Continue where you left off?").count() == 1)
page.get_by_role("button", name="Yes, continue").click(); page.wait_for_timeout(800)
check("draft restored", "# second" in ed("return e.getValue()"))
leave()
open_start()
check("second return asks AGAIN (draft still differs from saved)", page.get_by_text("Continue where you left off?").count() == 1)
page.get_by_role("button", name="Yes, continue").click(); page.wait_for_timeout(800)
check("draft restored again", "# my draft" in ed("return e.getValue()"))
check("undo history survived", ed("return e.session.getUndoManager().hasUndo()") is True)
ed("e.undo(); return 1")
check("undo removes only the last edit", "# second" not in ed("return e.getValue()") and "# my draft" in ed("return e.getValue()"))
ed("e.session.setValue('x=1\\nif x:\\n    y  =  2'); e.session.getUndoManager().reset(); e.insert('\\n'); return 1")
messy = ed("return e.getValue()")
page.get_by_role("button", name="Format").click(); page.wait_for_timeout(1500)
fmt = ed("return e.getValue()")
check("format changed the code", fmt != messy and "x = 1" in fmt)
ed("e.undo(); return 1"); check("undo after Format restores unformatted", ed("return e.getValue()") == messy)
ed("e.redo(); return 1"); check("redo after Format restores formatted", ed("return e.getValue()") == fmt)
print("page errors:", errs[:3])
print(f"{ok} passed, {bad} failed")
b.close(); pw.stop()
