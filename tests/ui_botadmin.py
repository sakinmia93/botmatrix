"""UI checks: Admin tab (Executions / Users / Maintenance) + Chats language badge."""
import sys, time
sys.path.insert(0, "tests")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT, "username": f"a{N}_bot"})
email = f"a{N}@x.io"
tok = register(email, "Adm")["token"]
bid = api("POST", "/bots", tok, json={"token": BOT}).json()["id"]
api("PUT", f"/bots/{bid}", tok, json={"commands": [{"id": "c1", "name": "/start", "code": "bot.sendMessage('hi')\n"}, {"id": "c2", "name": "/help", "code": "bot.sendMessage('help')\n"}]})
time.sleep(2)
for i, (u, t, lg) in enumerate([(8001, "/start", "en"), (8002, "/start", "bn"), (8003, "/help", "en"), (8004, "/start", "ru"), (8001, "/help", "en")]):
    requests.post("http://127.0.0.1:8081/_mock/push", json={"token": BOT, "update": {"message": {"message_id": 10 + i, "date": int(time.time()), "from": {"id": u, "is_bot": False, "first_name": "U%d" % u, "language_code": lg}, "chat": {"id": u, "type": "private"}, "text": t}}})
time.sleep(3)
api('POST', '/settings/broadcast-limit', tok, json={'minBroadcastUsers': 1})
bcr = api('POST', '/broadcasts', tok, json={'title': 'Promo blast', 'targetBotIds': [bid], 'messageText': 'Hello there', 'messageType': 'Text', 'parseMode': 'None', 'targetUserLimit': 100})
time.sleep(4)
ok = bad = 0
def check(n, c):
    global ok, bad
    print(("  ✓ " if c else "  ✗ ") + n); ok += bool(c); bad += (not c)
pw, b = browser()
ctx, page, _, errs = login_page(b, email, "password123"); page.wait_for_timeout(2500)
page.get_by_text("My Bots", exact=True).first.click(); page.wait_for_timeout(1200)
page.get_by_role("button", name="Edit").first.click(); page.wait_for_timeout(1800)
page.get_by_text("Chats", exact=True).first.click(); page.wait_for_timeout(1800)
check("chats show language code", page.get_by_title("Telegram language code").count() >= 3)
page.get_by_text("Admin", exact=True).first.click(); page.wait_for_timeout(2000)
check("Executions sub-tab: total + command list", page.get_by_text("Total executions").count() == 1 and page.get_by_text("All commands").count() == 1 and page.get_by_text("/start", exact=True).count() >= 1)
page.screenshot(path="/tmp/ui_admin_exec.png", full_page=True)
page.get_by_role("button", name="Users", exact=True).click(); page.wait_for_timeout(1500)
for lab in ["Total users", "Active (24h)", "Active (7d)", "Active (30d)", "New (24h)", "New (7d)", "New (30d)", "Blocked", "User language / country"]:
    check("Users shows " + lab, page.get_by_text(lab, exact=True).count() >= 1)
check("language analysis lists English", page.get_by_text("English", exact=True).count() >= 1)
page.screenshot(path="/tmp/ui_admin_users.png", full_page=True)
page.get_by_role("button", name="Maintenance", exact=True).click(); page.wait_for_timeout(800)
page.get_by_role("button", name="Turn on maintenance").click(); page.wait_for_timeout(500)
check("maintenance asks for confirmation", page.get_by_text("Enable maintenance mode").count() >= 1)
page.get_by_role("button", name="Enable", exact=True).click(); page.wait_for_timeout(1200)
check("maintenance shows ON", page.get_by_text("Turn off — go live").count() == 1)
page.get_by_role("button", name="Turn off — go live").click(); page.wait_for_timeout(500)
page.get_by_role("button", name="Go live", exact=True).click(); page.wait_for_timeout(1000)
check("maintenance back OFF", page.get_by_text("Turn on maintenance").count() == 1)
check("no Bot Data / User Data tabs", page.get_by_role("button", name="Bot Data", exact=True).count() == 0 and page.get_by_role("button", name="User Data", exact=True).count() == 0)
page.get_by_role("button", name="Broadcasts", exact=True).click(); page.wait_for_timeout(1500)
check("Admin broadcast card shows title + View details", page.get_by_text("Promo blast").count() >= 1 and page.get_by_role("button", name="View details").count() >= 1)
page.screenshot(path="/tmp/ui_admin_bc.png", full_page=True)
page.get_by_role("button", name="View details").first.click(); page.wait_for_timeout(2500)
check("View details opens that broadcast's live details", page.get_by_text("Live Analytics Engine").count() >= 1)
check("detail page marks this bot", page.get_by_text("This bot", exact=True).count() >= 1)
page.screenshot(path="/tmp/ui_bc_detail.png", full_page=True)
page.get_by_role("button", name="Open bot").first.click(); page.wait_for_timeout(2000)
check("Open bot shows highlighted arrival banner", page.get_by_text("You opened this bot from a broadcast").count() == 1)
page.get_by_text("Admin", exact=True).first.click(); page.wait_for_timeout(800)
for n in ["Permissions", "Broadcasts"]:
    page.get_by_role("button", name=n, exact=True).click(); page.wait_for_timeout(900)
page.get_by_role("button", name="Maintenance", exact=True).click(); page.get_by_text("Clear error log").click(); page.wait_for_timeout(400)
check("operation asks for confirmation", page.get_by_role("button", name="Clear error log", exact=True).count() >= 1 and page.get_by_role("button", name="Cancel", exact=True).count() >= 1)
page.get_by_role("button", name="Cancel", exact=True).click()
check("no page errors", not [e for e in errs if "401" not in e and "TUNNEL" not in e])
print(errs[:3]); print(f"{ok} passed, {bad} failed")
b.close()
