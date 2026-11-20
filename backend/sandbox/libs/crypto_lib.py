"""TBC libs.Crypto documented surface."""
import time
import requests

_ID_MAP = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "bnb": "binancecoin",
    "sol": "solana",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "dot": "polkadot",
    "matic": "matic-network",
    "ltc": "litecoin",
    "avax": "avalanche-2",
    "link": "chainlink",
    "uni": "uniswap",
    "atom": "cosmos",
    "xlm": "stellar",
    "near": "near",
    "algo": "algorand",
    "ftm": "fantom",
    "trx": "tron",
    "ape": "apecoin",
    "fil": "filecoin",
    "sand": "the-sandbox",
    "mana": "decentraland",
    "aave": "aave",
    "shib": "shiba-inu",
    "cake": "pancakeswap-token",
    "usdt": "tether",
    "usdc": "usd-coin",
    "dai": "dai",
    "busd": "binance-usd",
    "usdp": "usdp",
    "tusd": "tusd",
    "usdd": "usdd",
    "frax": "frax",
    "lusd": "lusd",
    "mkr": "maker",
    "comp": "compound-governance-token",
    "snx": "havven",
    "crv": "curve-dao-token",
    "yfi": "yearn-finance",
    "sushi": "sushi",
    "1inch": "1inch",
    "bal": "balancer",
    "rune": "thorchain",
    "kava": "kava",
    "op": "optimism",
    "arb": "arbitrum",
    "imx": "immutable-x",
    "metis": "metis",
    "boba": "boba",
    "axs": "axie-infinity",
    "gala": "gala",
    "enj": "enjincoin",
    "ilv": "ilv",
    "magic": "magic",
    "gmt": "stepn",
    "agix": "singularitynet",
    "fet": "fetch-ai",
    "ocean": "ocean-protocol",
    "nmr": "numeraire",
    "grt": "the-graph",
    "xmr": "monero",
    "zec": "zcash",
    "dash": "dash",
    "zen": "zen",
    "scrt": "scrt",
    "band": "band",
    "api3": "api3",
    "uma": "uma",
    "pha": "pha",
    "dia": "dia",
    "storj": "storj",
    "ankr": "ankr",
    "ar": "ar",
    "sc": "sc",
    "hnt": "hnt",
    "bat": "basic-attention-token",
    "lpt": "lpt",
    "audio": "audio",
    "rss3": "rss3",
    "deso": "deso",
    "ren": "ren",
    "cro": "crypto-com-chain",
    "ckb": "ckb",
    "coti": "coti",
    "syn": "syn",
    "egld": "elrond-egld",
    "vet": "vechain",
    "xtz": "tezos",
    "eos": "eos",
    "iota": "iota",
    "neo": "neo",
    "waves": "waves",
    "qtum": "qtum",
    "zil": "zilliqa",
    "ont": "ontology",
    "icx": "icon",
    "ksm": "kusama",
    "dcr": "decred",
    "zrx": "0x",
    "omg": "omisego",
    "nano": "nano",
    "rvn": "ravencoin",
    "hot": "holotoken",
    "one": "harmony",
    "iost": "iostoken",
    "celr": "celer-network",
    "chz": "chiliz",
    "rep": "augur",
    "loom": "loom-network",
    "req": "request-network",
    "data": "data",
    "rlc": "iexec-rlc",
    "powr": "power-ledger",
    "lrc": "loopring",
    "fun": "funfair",
    "knc": "kyber-network-crystal",
    "quick": "quickswap",
    "joe": "joe",
    "spell": "spell-token",
    "time": "time",
    "ohm": "ohm",
    "toke": "toke",
    "alcx": "alcx",
    "fxs": "frax-share",
    "cvx": "convex-finance",
    "btrfly": "btrfly",
    "inv": "inverse-finance",
    "kp3r": "kp3r",
    "bond": "bond",
    "pendle": "pendle",
    "gno": "gnosis",
}

class CryptoLib:
    def __init__(self):
        self._price_cache = {}
        self._info_cache = {}

    def _cached(self, cache, key, ttl):
        item = cache.get(key)
        if item and time.time() - item[0] < ttl:
            return item[1]
        return None

    def fetch_price(self, symbol, vs="usd"):
        cid = _ID_MAP.get(str(symbol).lower(), str(symbol).lower())
        vs = str(vs).lower()
        key = (cid, vs)
        cached = self._cached(self._price_cache, key, 15)
        if cached is not None:
            return cached
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": cid, "vs_currencies": vs}, timeout=20)
        data = r.json()
        price = (data.get(cid) or {}).get(vs)
        result = {"ok": price is not None, "symbol": symbol, "vs": vs,
                  "price": price, "raw": data}
        self._price_cache[key] = (time.time(), result)
        return result

    def convert(self, _from, _to, _amo):
        a = self.fetch_price(_from, "usd")
        b = self.fetch_price(_to, "usd")
        if not a.get("price") or not b.get("price"):
            return {"ok": False, "error": "price unavailable"}
        amount = float(_amo)
        return {"ok": True, "from": _from, "to": _to, "amount": amount,
                "result": amount * float(a["price"]) / float(b["price"])}

    def get_price(self, _currency, _pricein="USDT"):
        vs = "usd" if str(_pricein).upper() in ("USDT", "USD") else str(_pricein).lower()
        return self.fetch_price(_currency, vs)

    def get_coin_info(self, symbol):
        cid = _ID_MAP.get(str(symbol).lower(), str(symbol).lower())
        cached = self._cached(self._info_cache, cid, 300)
        if cached is not None:
            return cached
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/{cid}", timeout=20)
        if r.status_code != 200:
            return {"ok": False, "error": r.text[:200]}
        result = {"ok": True, "data": r.json()}
        self._info_cache[cid] = (time.time(), result)
        return result

    # --- TBS "Lib.Crypto" utilities (hashing / signing) delegate to the Security lib ---
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        from backend.sandbox.libs.security_lib import SecurityLib
        sec = SecurityLib()
        if hasattr(sec, name):
            return getattr(sec, name)
        import hashlib
        if name in ("md5", "sha1", "sha256", "sha512"):
            return lambda text: getattr(hashlib, name)(str(text).encode()).hexdigest()
        raise AttributeError(name)
