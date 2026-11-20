import sys, time, json
sys.path.insert(0, ".")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT1 = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT1, "username": f"t{N}_bot"})
r = register(f"w{int(time.time())}@x.io", "Walk")
tok = r["token"]
pw, b = browser()
ctx = b.new_context(viewport={"width": 1366, "height": 860}); page = ctx.new_page()
errs = []
page.on("pageerror", lambda e: errs.append(str(e)))
page.on("console", lambda m: errs.append("console:" + m.text + " " + str(m.location.get('url',''))) if m.type == "error" else None)
page.add_init_script(f"if(!localStorage.getItem('telebot_auth_token')){{localStorage.setItem('telebot_auth_token','{tok}');localStorage.setItem('telebot_user',JSON.stringify({json.dumps(r['user'])}));}}")
page.goto(BASE); page.wait_for_timeout(2000)
def nav(n):
    page.get_by_text(n, exact=True).first.click(); page.wait_for_timeout(1000)
# create bot with invalid token in modal
nav("My Bots")
page.get_by_role("button", name="Create New Bot").first.click()
page.wait_for_timeout(500)
inp = page.locator("input[placeholder*='oken'], input[placeholder*=':']").first
inp.fill("123:bad"); page.locator("form button[type=submit]").last.click(); page.wait_for_timeout(1500)
print("modal-error:", page.locator("[role=alert]").all_inner_texts())
page.screenshot(path="/tmp/shots/w01_modal_err.png")
inp.fill(BOT1); page.locator("form button[type=submit]").last.click(); page.wait_for_timeout(2500)
page.screenshot(path="/tmp/shots/w02_after_create.png")
for n in ["Dashboard","My Bots","Bot Store","Broadcast Manager","Recycle Bin","Transfers","Settings","Notifications","Help","Support"]:
    try:
        nav(n); page.screenshot(path=f"/tmp/shots/w_{n.replace(' ','_')}.png")
    except Exception as e: print("NAVFAIL", n, str(e)[:100])
# settings persistence
nav("Settings")
page.get_by_text("Telegram Connect", exact=True).first.click(); page.wait_for_timeout(1500)
page.screenshot(path="/tmp/shots/w_tg_before.png")
page.reload(); page.wait_for_timeout(2500)
print("after reload shows telegram tab:", page.get_by_text("Telegram Connect Bot").count(), "page:", page.get_by_text("Settings").count())
page.screenshot(path="/tmp/shots/w_tg_reload.png")
# connect via real link-code through connect bot
st = api("GET", "/telegram/status", tok).json(); print("status", st.get("available"), st.get("connectBotUsername"))
code = api("POST", "/telegram/link-code", tok).json(); print("code", code.get("url"))
requests.post("http://127.0.0.1:8081/_mock/push", json={"token": "9000000001:CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC", "update": {"message": {"message_id": 1, "date": int(time.time()), "chat": {"id": 7667568339, "type": "private"}, "from": {"id": 7667568339, "first_name": "Tester", "username": "tester"}, "text": "/start " + code["code"]}}})
page.wait_for_timeout(6000)
page.screenshot(path="/tmp/shots/w_tg_connected.png")
print("connected shown:", page.get_by_text("Live Routing").count())
print("ERRS", errs[:12])
b.close(); pw.stop()
