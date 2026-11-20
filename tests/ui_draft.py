import sys, time
sys.path.insert(0, ".")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT1 = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT1, "username": f"d{N}_bot"})
r = register(f"d{int(time.time())}@x.io", "Dr")
tok = r["token"]; bot = api("POST", "/bots", tok, json={"token": BOT1}).json()
api("PUT", f"/bots/{bot['id']}", tok, json={"commands": [{"id": "c1", "name": "/start", "code": "bot.sendMessage(chat_id=chat_id, text='hi')\n"}]})
pw, b = browser(); ctx = b.new_context(viewport={"width": 1366, "height": 860}); page = ctx.new_page()
page.add_init_script(f"if(!localStorage.getItem('telebot_auth_token')){{localStorage.setItem('telebot_auth_token','{tok}');localStorage.setItem('telebot_user',JSON.stringify({json.dumps(r['user'])}));}}")
page.goto(BASE); page.wait_for_timeout(2000)
def open_editor():
    page.get_by_text("My Bots", exact=True).first.click(); page.wait_for_timeout(900)
    page.get_by_role("button", name="Edit").first.click(); page.wait_for_timeout(1200)
    page.get_by_text("Commands", exact=True).first.click(); page.wait_for_timeout(600)
    page.get_by_text("/start").first.click(); page.wait_for_timeout(1500)
open_editor()
page.locator(".ace_content").first.click(); page.keyboard.press("Control+End"); page.keyboard.type("\n# unsaved work", delay=40); page.wait_for_timeout(900)
print("draft keys:", page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('bm_draft'))"))
page.reload(); page.wait_for_timeout(2500)
page.screenshot(path="/tmp/shots/d0.png")
# after reload we may need to reopen
page.get_by_text('/start').first.click(); page.wait_for_timeout(1500)
page.wait_for_timeout(800)
print("prompt:", page.get_by_text("Continue where you left off?").count())
page.get_by_role("button", name="Yes, continue").click(); page.wait_for_timeout(600)
print("restored:", "# unsaved work" in " ".join(page.locator(".ace_line").all_inner_texts()))
page.screenshot(path="/tmp/shots/d1.png")
page.locator("button[title=\"Back to commands list\"]").click(); page.wait_for_timeout(500)
print("leave confirm:", page.get_by_text("Leave the editor?").count())
b.close(); pw.stop()
