"""TBC libs.TonLib — bootstrap from known-good + setKeys/sendTON fixes."""
from __future__ import annotations

import urllib.request

_URL = (
    "https://raw.githubusercontent.com/sakinmia93/botmatrix/"
    "68eea626fcc189fc4e1bdf81de08f4e0f7532b1f/backend/sandbox/libs/ton_lib.py"
)

def _bootstrap():
    with urllib.request.urlopen(_URL, timeout=45) as r:
        src = r.read().decode("utf-8")
    start = src.find("    def setKeys(self, mnemonics):")
    end = src.find("    def _keys(self, mnemonics=None):")
    if start >= 0 and end > start:
        new_set = (
            "    def setKeys(self, mnemonics):\n"
            "        \"\"\"Store mnemonics. Returns {ok, address, words, version, stored}.\"\"\"\n"
            "        words = _norm_mnemonics(mnemonics)\n"
            "        if not words or len(words) not in (12, 18, 24):\n"
            "            raise ValueError(\"mnemonics must be a 12/18/24 word phrase\")\n"
            "        self._mnemonics = words\n"
            "        stored = False\n"
            "        try:\n"
            "            from backend import security\n"
            "            self._kv_set(KEYS_KEY, security.encrypt(\" \".join(words)))\n"
            "            stored = True\n"
            "        except Exception:\n"
            "            pass\n"
            "        try:\n"
            "            address = self.getWalletAddress(words)\n"
            "        except Exception as e:\n"
            "            return {\"ok\": False, \"error\": \"invalid mnemonics: %s\" % e, \"words\": len(words), \"stored\": stored}\n"
            "        return {\"ok\": True, \"address\": address, \"words\": len(words), \"version\": \"v4r2\", \"stored\": stored}\n"
        )
        src = src[:start] + new_set + "\n" + src[end:]
    src = src.replace(
        "raise ValueError(f\"insufficient balance: {bal / 1e9} TON\")",
        "raise ValueError(\"insufficient balance: have %.9f TON, need %.9f TON (amount=%s + fee~0.01) from=%s\" % (bal / 1e9, (nano + 10_000_000) / 1e9, float(amount), src))",
    )
    g = globals()
    exec(compile(src, __file__, "exec"), g)

_bootstrap()
