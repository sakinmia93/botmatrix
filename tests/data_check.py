import sys, time
sys.path.insert(0, "tests")
from ui_lib import *
N = int(time.time()) % 900000000 + 100000000
BOT = f"{N}:" + "A" * 35
requests.post("http://127.0.0.1:8081/_mock/add_bot", json={"token": BOT, "username": f"d{N}_bot"})
r = register(f"d{N}@x.io", "Dee"); tok = r["token"]
bid = api("POST", "/bots", tok, json={"token": BOT}).json()["id"]
cmds = [
 {"id": "c1", "name": "/start", "code": "User.saveData('visits', 1)\nBot.saveData('started', 7)\nbot.sendMessage(chat_id=chat_id, text='hi')"},
 {"id": "c2", "name": "/boom", "code": "x = 1/0"},
 {"id": "c3", "name": "/api", "code": "bot.sendMessage(chat_id=chat_id, text='')"},
]
print(api("PUT", f"/bots/{bid}", tok, json={"commands": cmds}).status_code)
def push(uid, text):
    requests.post("http://127.0.0.1:8081/_mock/push", json={"token": BOT, "update": {"message": {"message_id": 1, "date": int(time.time()), "from": {"id": uid, "is_bot": False, "first_name": "Zed", "username": "zed", "language_code": "bn"}, "chat": {"id": uid, "type": "private"}, "text": text}}})
for t in ("/start", "/boom", "/api"): push(777, t); time.sleep(1.5)
time.sleep(2)
b = api("GET", f"/bots/{bid}", tok).json()
print("errors:", [(e["command"], e["message"][:60]) for e in b.get("errors", [])])
print("chats:", api("GET", f"/chats/{bid}", tok).text[:400])
print("db bot:", api("GET", f"/database/{bid}?scope=bot", tok).text[:300])
print("db user:", api("GET", f"/database/{bid}?scope=user", tok).text[:300])
sent = requests.get("http://127.0.0.1:8081/_mock/sent").json()
print("sent:", [(s["method"], s["params"].get("text")) for s in sent if str(s["params"].get("chat_id")) == "777"])
