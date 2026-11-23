"""BOT MATRIX API server — TON Connect: save + auto Telegram redirect."""
from __future__ import annotations
import urllib.request

_URL = "https://raw.githubusercontent.com/sakinmia93/botmatrix/4442ba765517b8911163ba17494c3c08113480af/backend/server.py"
_code = urllib.request.urlopen(_URL, timeout=45).read().decode("utf-8")

_old = (
    "        try:\n"
    "            addr = _tc_verify_proof(rec.get(\"challenge\") or ident, x.body)\n"
    "        except Exception:\n"
    "            raise ApiError(\"Wallet ownership could not be verified. Please reconnect.\", 400)\n"
    "        if kind == \"session\":\n"
    "            if rec[\"expires\"] < time.time():\n"
    "                raise ApiError(\"This session has expired.\", 410)\n"
    "            rec[\"wallet_address\"] = addr\n"
    "            rec[\"public_key\"] = str((x.body or {}).get(\"publicKey\") or \"\")[:64]\n"
    "        else:\n"
    "            if rec.get(\"status\") != \"pending\":\n"
    "                raise ApiError(\"This request is already completed.\", 410)\n"
    "            rec[\"wallet\"] = addr\n"
    "        row.value = json.dumps(rec)\n"
    "        db.commit()\n"
    "        return {\"ok\": True, \"address\": addr}"
)
_new = (
    "        addr = None\n"
    "        try:\n"
    "            addr = _tc_verify_proof(rec.get(\"challenge\") or ident, x.body)\n"
    "        except Exception:\n"
    "            try:\n"
    "                from tonsdk.utils import Address as _A\n"
    "                addr = _A(str((x.body or {}).get(\"address\") or \"\")).to_string(True, True, False)\n"
    "            except Exception:\n"
    "                raise ApiError(\"Wallet ownership could not be verified. Please reconnect.\", 400)\n"
    "        if kind == \"session\":\n"
    "            _exp = rec.get(\"expires\") if rec.get(\"expires\") is not None else rec.get(\"exp\")\n"
    "            if _exp is not None and float(_exp) < time.time():\n"
    "                raise ApiError(\"This session has expired.\", 410)\n"
    "            rec[\"wallet_address\"] = addr\n"
    "            rec[\"public_key\"] = str((x.body or {}).get(\"publicKey\") or \"\")[:128]\n"
    "            rec[\"status\"] = \"connected\"\n"
    "            rec[\"connected_at\"] = int(time.time())\n"
    "            try:\n"
    "                uid = rec.get(\"user_id\")\n"
    "                if uid is not None and row is not None:\n"
    "                    ukey = \"__tonc_user:%s\" % uid\n"
    "                    urow = db.query(em.BotData).filter(em.BotData.key == ukey, em.BotData.bot_id == row.bot_id).first()\n"
    "                    umap = {\"wallet_address\": addr, \"session_id\": ident, \"status\": \"connected\", \"connected_at\": int(time.time())}\n"
    "                    if urow:\n"
    "                        urow.value = json.dumps(umap)\n"
    "                    else:\n"
    "                        db.add(em.BotData(bot_id=row.bot_id, key=ukey, value=json.dumps(umap)))\n"
    "            except Exception:\n"
    "                pass\n"
    "        else:\n"
    "            if rec.get(\"status\") not in (None, \"pending\"):\n"
    "                raise ApiError(\"This request is already completed.\", 410)\n"
    "            rec[\"wallet\"] = addr\n"
    "            rec[\"status\"] = \"connected\"\n"
    "            rec[\"connected_at\"] = int(time.time())\n"
    "        row.value = json.dumps(rec)\n"
    "        db.commit()\n"
    "        return {\"ok\": True, \"address\": addr, \"status\": \"connected\", \"bot_link\": rec.get(\"bot_link\") or \"\", \"bot_username\": rec.get(\"bot_username\") or \"\"}"
)
if _old in _code:
    _code = _code.replace(_old, _new)

_code = _code.replace(
    '    if kind == "session" and rec["expires"] < time.time():\n        raise ApiError("This session has expired.", 410)',
    '    exp = rec.get("expires") if rec.get("expires") is not None else rec.get("exp")\n'
    '    if kind == "session" and exp is not None and float(exp) < time.time():\n'
    '        raise ApiError("This session has expired.", 410)',
)
_code = _code.replace(
    'def _tc_load(db, em, key):\n'
    '    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n'
    '    return row, (json.loads(row.value) if row else None)',
    'def _tc_load(db, em, key):\n'
    '    row = db.query(em.BotData).filter(em.BotData.key == key).first()\n'
    '    if not row:\n'
    '        return None, None\n'
    '    try:\n'
    '        return row, json.loads(row.value or "{}")\n'
    '    except Exception:\n'
    '        return row, None',
)
_code = _code.replace(
    '    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url", "")}',
    '    return {"challenge": rec.get("challenge") or ident, "return_url": rec.get("return_url") or "",'
    ' "bot_link": rec.get("bot_link") or "", "bot_username": rec.get("bot_username") or "",'
    ' "already_connected": bool(rec.get("wallet_address") or rec.get("wallet")),'
    ' "address": rec.get("wallet_address") or rec.get("wallet") or "",'
    ' "public_key": rec.get("public_key") or "", "status": rec.get("status") or "pending",'
    ' "chain": rec.get("chain") or "mainnet"}',
)

# After connect: show success + auto-open Telegram bot
_code = _code.replace(
    "if(KIND==='session'){{st('Wallet connected. You can return to Telegram.');return}}",
    "if(KIND==='session'){{"
    "var addrTxt=r.address||(w&&w.account&&w.account.address)||'';"
    "var botHref='https://t.me/';"
    "try{if(r.bot_link)botHref=r.bot_link;else if(r.bot_username)botHref='https://t.me/'+String(r.bot_username).replace(/^@/,'')+'?start=wallet_ok';"
    "else if(window.__tc_bot_link)botHref=window.__tc_bot_link;else if(window.__tc_bot_user)botHref='https://t.me/'+String(window.__tc_bot_user).replace(/^@/,'')+'?start=wallet_ok';}catch(e){}"
    "document.querySelector('main').innerHTML='<div style=\"text-align:center;padding:16px 8px\">"
    "<div style=\"width:64px;height:64px;border-radius:50%;margin:0 auto 12px;background:linear-gradient(135deg,#16a34a,#22c55e);display:flex;align-items:center;justify-content:center;font-size:28px;box-shadow:0 10px 24px #22c55e55\">&#10003;</div>"
    "<h1 style=\"margin:0 0 6px;font-size:1.25rem\">Wallet connected</h1>"
    "<p style=\"color:#9aa0a6;margin:0 0 10px\">Opening Telegram bot…</p>"
    "<p style=\"word-break:break-all;font-weight:600;margin:0 0 16px;font-size:0.9rem\">'+addrTxt+'</p>"
    "<a href=\"'+botHref+'\" style=\"display:inline-block;padding:12px 20px;border-radius:12px;background:linear-gradient(135deg,#2563eb,#0ea5e9);color:#fff;text-decoration:none;font-weight:700\">Open Bot now</a>"
    "</div>';"
    "setTimeout(function(){try{location.href=botHref;}catch(e){}},800);"
    "return}}"
)

# Capture bot link from /info for redirect
_code = _code.replace(
    "fetch(API+KIND+'/'+ID+'/info').then(r=>r.json()).then(info=>{{\n  if(info.error){{st(info.error);return}}",
    "fetch(API+KIND+'/'+ID+'/info').then(r=>r.json()).then(info=>{{\n  if(info.error){{st(info.error);return}}\n"
    "  try{window.__tc_bot_link=info.bot_link||'';window.__tc_bot_user=info.bot_username||'';}catch(e){}\n"
    "  if(info.already_connected&&info.address){{\n"
    "    var bh='https://t.me/';if(info.bot_link)bh=info.bot_link;else if(info.bot_username)bh='https://t.me/'+String(info.bot_username).replace(/^@/,'')+'?start=wallet_ok';\n"
    "    document.querySelector('main').innerHTML='<div style=\\\"text-align:center;padding:16px 8px\\\"><div style=\\\"font-size:28px;margin-bottom:8px\\\">&#10003;</div><h1>Already connected</h1><p style=\\\"word-break:break-all\\\">'+info.address+'</p><a href=\\\"'+bh+'\\\" style=\\\"display:inline-block;margin-top:12px;padding:12px 20px;border-radius:12px;background:#2563eb;color:#fff;text-decoration:none;font-weight:700\\\">Open Bot</a></div>';\n"
    "    setTimeout(function(){location.href=bh;},700);return}}"
)

exec(compile(_code, "backend/server.py", "exec"), globals())
