"""UI check: broadcast composer shows pin, plan-limited speed, language popover and button rows."""
import sys, time
sys.path.insert(0, "tests")
from ui_lib import *
register("admin@x.io", "Admin") if False else None
adm = login("admin@x.io")["token"] if True else None
em = f"bc{int(time.time())}@x.io"
r = register(em, "B")
api("POST", "/admin/plan", adm, json={"email": em, "plan": "Matrix Ultra"})
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser(); ctx = b.new_context(viewport={"width": 1366, "height": 1500}); page = ctx.new_page()
page.add_init_script(f"if(!localStorage.getItem('telebot_auth_token')){{localStorage.setItem('telebot_auth_token','{r['token']}');localStorage.setItem('telebot_user',JSON.stringify({json.dumps(r['user'])}));}}")
page.goto(BASE); page.wait_for_timeout(1500)
page.get_by_text("Broadcast Manager", exact=True).first.click(); page.wait_for_timeout(700)
page.get_by_role("button", name="New Broadcast").first.click(); page.wait_for_timeout(1200)
check("pin toggle present", page.get_by_text("Pin broadcast").count() == 1)
check("Ultra can pin", page.locator("label:has-text('Pin broadcast') input").is_enabled())
check("Unlimited speed offered", page.locator("option", has_text="Unlimited (Turbo)").count() >= 1)
page.locator("button[title='Which languages your users speak']").click(); page.wait_for_timeout(400)
check("language popover opens", page.get_by_text("Select a bot first").count() == 1)
page.get_by_role("button", name="URL").first.click(); page.get_by_role("button", name="Callback").first.click(); page.wait_for_timeout(300)
check("arrange per row appears", page.get_by_role("button", name="2 per row").count() == 1)
page.get_by_role("button", name="2 per row").click(); page.wait_for_timeout(300)
check("both buttons on row 1", page.locator("input[type=number]").evaluate_all("els=>els.filter(e=>e.max=='20').map(e=>e.value)") == ["1", "1"])
check("colour and premium emoji inputs", page.get_by_text("Premium emoji ID").count() == 2)
page.screenshot(path="/tmp/shots/bc2.png")
print(f"{ok} passed, {bad} failed")
b.close(); pw.stop()
