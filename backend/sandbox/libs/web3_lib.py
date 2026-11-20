"""TBC libs.web3lib — EVM helpers (HTTP JSON-RPC, no local node required)."""
from __future__ import annotations
import json
from typing import Optional
import requests

DEFAULT_RPC = {
    # TBC documented EVM networks (31) + common aliases
    "ethereum": "https://ethereum.publicnode.com",
    "eth": "https://ethereum.publicnode.com",
    "bsc": "https://bsc-dataseed.binance.org",
    "bnb": "https://bsc-dataseed.binance.org",
    "polygon": "https://polygon-rpc.com",
    "matic": "https://polygon-rpc.com",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "avax": "https://api.avax.network/ext/bc/C/rpc",
    "fantom": "https://rpc.ftm.tools",
    "ftm": "https://rpc.ftm.tools",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "arb": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "op": "https://mainnet.optimism.io",
    "harmony": "https://api.harmony.one",
    "cronos": "https://evm.cronos.org",
    "moonriver": "https://rpc.api.moonriver.moonbeam.network",
    "moonbeam": "https://rpc.api.moonbeam.network",
    "celo": "https://forno.celo.org",
    "heco": "https://http-mainnet.hecochain.com",
    "okexchain": "https://exchainrpc.okex.org",
    "okc": "https://exchainrpc.okex.org",
    "xdai": "https://rpc.gnosischain.com",
    "gnosis": "https://rpc.gnosischain.com",
    "kcc": "https://rpc-mainnet.kcc.network",
    "metis": "https://andromeda.metis.io/?owner=1088",
    "aurora": "https://mainnet.aurora.dev",
    "base": "https://mainnet.base.org",
    "zksync": "https://mainnet.era.zksync.io",
    "scroll": "https://rpc.scroll.io",
    "linea": "https://rpc.linea.build",
    "boba": "https://mainnet.boba.network",
    "kava": "https://evm.kava.io",
    "fuse": "https://rpc.fuse.io",
    "evmos": "https://evmos-evm.publicnode.com",
    "canto": "https://canto.slingshot.finance",
    "astar": "https://evm.astar.network",
    "telos": "https://mainnet.telos.net/evm",
    "rootstock": "https://public-node.rsk.co",
    "rsk": "https://public-node.rsk.co",
    "ttcoin": "https://mainnet-rpc.thundercore.com",
    "thundercore": "https://mainnet-rpc.thundercore.com",
    "tomochain": "https://rpc.tomochain.com",
    "tomo": "https://rpc.tomochain.com",
}

CHAIN_IDS = {
    "ethereum": 1, "bsc": 56, "polygon": 137, "avalanche": 43114, "fantom": 250,
    "arbitrum": 42161, "optimism": 10, "harmony": 1666600000, "cronos": 25,
    "moonriver": 1285, "moonbeam": 1284, "celo": 42220, "heco": 128, "okexchain": 66,
    "xdai": 100, "kcc": 321, "boba": 288, "kava": 2222, "fuse": 122, "evmos": 9001,
    "canto": 7700, "astar": 592, "telos": 40, "rootstock": 30, "ttcoin": 22023,
    "base": 8453, "zksync": 324, "scroll": 534352, "linea": 59144, "aurora": 1313161554,
    "metis": 1088,
}

# Documented canonical network names (for get_supported_networks)
SUPPORTED_NETWORKS = [
    "ethereum", "bsc", "polygon", "avalanche", "fantom", "arbitrum", "optimism",
    "harmony", "cronos", "moonriver", "moonbeam", "celo", "heco", "okexchain",
    "xdai", "kcc", "metis", "aurora", "base", "zksync", "scroll", "linea",
    "boba", "kava", "fuse", "evmos", "canto", "astar", "telos", "rootstock", "ttcoin",
]

# ERC-20 selectors
_TRANSFER = "0xa9059cbb"
_BALANCE_OF = "0x70a08231"
_DECIMALS = "0x313ce567"
_UNITS = {"wei": 1, "gwei": 10**9, "ether": 10**18, "eth": 10**18}


def _norm_net(n):
    n = (n or "ethereum").lower().strip()
    return {"eth": "ethereum", "bnb": "bsc", "matic": "polygon", "avax": "avalanche",
            "ftm": "fantom", "arb": "arbitrum", "op": "optimism", "gnosis": "xdai",
            "okc": "okexchain", "rsk": "rootstock", "thundercore": "ttcoin"}.get(n, n)


class Web3Lib:
    """libs.web3lib — EVM native coin + ERC-20 helpers over plain JSON-RPC."""

    def __init__(self, private_key: Optional[str] = None):
        self._private_key = private_key

    def setKeys(self, private_Key=None, private_key=None):
        self._private_key = private_key or private_Key
        return True

    def get_default_rpc(self, network: str):
        return DEFAULT_RPC.get(_norm_net(network)) or DEFAULT_RPC["ethereum"]

    def get_supported_networks(self):
        """{network: {"chain_id": int, "rpc_url": str}} for every supported EVM chain."""
        return {n: {"chain_id": CHAIN_IDS.get(n), "rpc_url": DEFAULT_RPC.get(n)}
                for n in SUPPORTED_NETWORKS if n in DEFAULT_RPC}

    def _rpc(self, rpc_url, method, params):
        r = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=30)
        data = r.json()
        if data.get("error"):
            e = data["error"]
            raise RuntimeError(e.get("message") if isinstance(e, dict) else str(e))
        return data.get("result")

    def _resolve_rpc(self, rpc_url=None, network=None):
        if rpc_url:
            return rpc_url
        return self.get_default_rpc(network or "ethereum")

    @staticmethod
    def _addr(a):
        a = str(a or "").strip()
        if not (a.startswith("0x") and len(a) == 42):
            raise ValueError(f"invalid EVM address: {a!r}")
        int(a[2:], 16)
        return a

    def _need_account(self):
        try:
            from eth_account import Account
            return Account
        except ImportError:
            raise RuntimeError("eth-account is not installed on this server")

    def _send(self, rpc, tx, pk, estimate_gas, increase_gas, gas_default, wait, timeout, retry):
        Account = self._need_account()
        acct = Account.from_key(pk)
        tx = dict(tx)
        tx["nonce"] = int(self._rpc(rpc, "eth_getTransactionCount", [acct.address, "pending"]), 16)
        tx["chainId"] = int(self._rpc(rpc, "eth_chainId", []), 16)
        if "gas" not in tx:
            gas = gas_default
            if estimate_gas:
                try:
                    est_tx = {"from": acct.address, "to": tx["to"], "value": hex(tx.get("value", 0)), "data": tx.get("data", "0x")}
                    gas = int(self._rpc(rpc, "eth_estimateGas", [est_tx]), 16)
                except Exception:
                    pass
            if increase_gas:
                gas = int(gas * (1 + float(increase_gas) / 100)) if float(increase_gas) < 10 else int(gas + float(increase_gas))
            tx["gas"] = gas
        if "gasPrice" not in tx:
            tx["gasPrice"] = int(self._rpc(rpc, "eth_gasPrice", []), 16)
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        raw_hex = raw.hex() if hasattr(raw, "hex") else raw
        if not raw_hex.startswith("0x"):
            raw_hex = "0x" + raw_hex
        attempts = 3 if retry else 1
        last = None
        for i in range(attempts):
            try:
                tx_hash = self._rpc(rpc, "eth_sendRawTransaction", [raw_hex])
                break
            except Exception as e:
                last = e
                if i == attempts - 1:
                    raise
                import time; time.sleep(1.5)
        if wait and tx_hash:
            import time
            end = time.time() + float(timeout)
            while time.time() < end:
                rc = self._rpc(rpc, "eth_getTransactionReceipt", [tx_hash])
                if rc:
                    if rc.get("status") == "0x0":
                        raise RuntimeError(f"transaction reverted: {tx_hash}")
                    break
                time.sleep(1)
        return tx_hash

    def sendNativeCoin(self, value, to, rpc_url=None, gas=None, gasPrice=None, private_key=None,
                       increase_gas=None, wait_for_confirmation=True, confirmation_timeout=15,
                       network=None, estimate_gas=True, retry=False, chain=None, **kwargs):
        """Send ETH/BNB/MATIC/... Returns the transaction hash (str).
        `chain` is a TBC-doc alias for `network` (e.g. chain="polygon")."""
        network = network or chain or kwargs.get("chain")
        pk = private_key or self._private_key
        if not pk:
            raise ValueError("private_key is required (libs.web3lib.setKeys or private_key=...)")
        to = self._addr(to)
        rpc = self._resolve_rpc(rpc_url, network)
        wei = int(round(float(value) * 10**18))
        if wei <= 0:
            raise ValueError("value must be greater than 0")
        tx = {"to": to, "value": wei, "data": "0x"}
        if gas:
            tx["gas"] = int(gas)
        if gasPrice:
            tx["gasPrice"] = int(gasPrice)
        return self._send(rpc, tx, pk, estimate_gas, increase_gas, 21000, wait_for_confirmation, confirmation_timeout, retry)

    def sendETHER(self, value, to, rpc_url=None, gas=None, gasPrice=None, private_key=None,
                  increase_gas=None, wait_for_confirmation=True, confirmation_timeout=15,
                  network=None, contract_address=None, retry=False, estimate_gas=True, decimals=None,
                  chain=None, **kwargs):
        """Send an ERC-20 token (contract_address) — without it, sends the native coin.
        `chain` is a TBC-doc alias for `network`."""
        network = network or chain or kwargs.get("chain")
        if not contract_address:
            return self.sendNativeCoin(value, to, rpc_url=rpc_url, gas=gas, gasPrice=gasPrice, private_key=private_key,
                                       increase_gas=increase_gas, wait_for_confirmation=wait_for_confirmation,
                                       confirmation_timeout=confirmation_timeout, network=network,
                                       estimate_gas=estimate_gas, retry=retry)
        pk = private_key or self._private_key
        if not pk:
            raise ValueError("private_key is required")
        to = self._addr(to)
        contract = self._addr(contract_address)
        rpc = self._resolve_rpc(rpc_url, network)
        dec = int(decimals) if decimals is not None else self._decimals(rpc, contract)
        if not 0 <= dec <= 18:
            raise ValueError("decimals must be 0-18")
        amount = int(round(float(value) * 10**dec))
        if amount <= 0:
            raise ValueError("value must be greater than 0")
        data = _TRANSFER + to[2:].lower().rjust(64, "0") + hex(amount)[2:].rjust(64, "0")
        tx = {"to": contract, "value": 0, "data": data}
        if gas:
            tx["gas"] = int(gas)
        if gasPrice:
            tx["gasPrice"] = int(gasPrice)
        return self._send(rpc, tx, pk, estimate_gas, increase_gas, 100000, wait_for_confirmation, confirmation_timeout, retry)

    def send_ether(self, *a, **k):
        return self.sendETHER(*a, **k)

    def sendether(self, *a, **k):
        return self.sendETHER(*a, **k)

    def sendEther(self, *a, **k):
        return self.sendETHER(*a, **k)

    def send_navive_coin(self, *a, **k):
        return self.sendNativeCoin(*a, **k)

    def send_native_coin(self, *a, **k):
        return self.sendNativeCoin(*a, **k)

    def _decimals(self, rpc, contract):
        try:
            return int(self._rpc(rpc, "eth_call", [{"to": contract, "data": _DECIMALS}, "latest"]), 16)
        except Exception:
            return 18

    def getBalance(self, address, rpc_url=None, network=None, unit="ether"):
        """Native balance as float in `unit` (wei | gwei | ether)."""
        addr = self._addr(address)
        unit = (unit or "ether").lower()
        if unit not in _UNITS:
            raise ValueError("unit must be wei, gwei or ether")
        wei = int(self._rpc(self._resolve_rpc(rpc_url, network), "eth_getBalance", [addr, "latest"]), 16)
        return float(wei) if unit == "wei" else wei / _UNITS[unit]

    def get_balance(self, *a, **k):
        return self.getBalance(*a, **k)

    def getTokenBalance(self, address, contract_address, rpc_url=None, network=None, decimals=None, raw=False):
        """ERC-20 balance (float; integer units when raw=True). Decimals are auto-detected."""
        addr = self._addr(address)
        contract = self._addr(contract_address)
        rpc = self._resolve_rpc(rpc_url, network)
        res = self._rpc(rpc, "eth_call", [{"to": contract, "data": _BALANCE_OF + addr[2:].lower().rjust(64, "0")}, "latest"])
        units = int(res, 16) if res and res != "0x" else 0
        if raw:
            return units
        dec = int(decimals) if decimals is not None else self._decimals(rpc, contract)
        return units / 10**dec

    def get_token_balance(self, *a, **k):
        return self.getTokenBalance(*a, **k)

    def getGasPrice(self, rpc_url=None, network=None, unit="gwei"):
        """Current gas price. unit: wei | gwei | ether. TBC alias."""
        unit = (unit or "gwei").lower()
        if unit not in _UNITS:
            raise ValueError("unit must be wei, gwei or ether")
        wei = int(self._rpc(self._resolve_rpc(rpc_url, network), "eth_gasPrice", []), 16)
        return float(wei) if unit == "wei" else wei / _UNITS[unit]

    def get_gas_price(self, *a, **k):
        return self.getGasPrice(*a, **k)

    def sendToken(self, amount, to, contract_address, rpc_url=None, network=None, decimals=None,
                  gas=None, gasPrice=None, private_key=None, increase_gas=None,
                  wait_for_confirmation=True, confirmation_timeout=15, estimate_gas=True, retry=False):
        """ERC-20 transfer. amount in human units (or raw integer when decimals=0). Returns tx hash."""
        pk = private_key or self._private_key
        if not pk:
            raise ValueError("private_key is required (libs.web3lib.setKeys or private_key=...)")
        to_addr = self._addr(to)
        contract = self._addr(contract_address)
        rpc = self._resolve_rpc(rpc_url, network)
        dec = int(decimals) if decimals is not None else self._decimals(rpc, contract)
        try:
            raw_amt = int(amount) if dec == 0 else int(float(amount) * (10 ** dec))
        except Exception:
            raise ValueError("amount must be a number")
        if raw_amt < 0:
            raise ValueError("amount must be >= 0")
        # transfer(address,uint256) selector a9059cbb
        data = "0xa9059cbb" + to_addr[2:].lower().rjust(64, "0") + hex(raw_amt)[2:].rjust(64, "0")
        tx = {"to": contract, "value": 0, "data": data}
        if gas:
            tx["gas"] = int(gas)
        if gasPrice:
            tx["gasPrice"] = int(gasPrice)
        return self._send(rpc, tx, pk, estimate_gas, increase_gas, 100000, wait_for_confirmation, confirmation_timeout, retry)

    def send_token(self, *a, **k):
        return self.sendToken(*a, **k)

    # TBS-style helpers
    def createWallet(self):
        Account = self._need_account()
        acct = Account.create()
        return {"private_key": acct.key.hex(), "address": acct.address}

    def generateKey(self):
        """TBS: returns the new private key as a string (dict-style access to private_key/address still works)."""
        from backend.sandbox.tbs_compat import hybrid
        w = self.createWallet()
        return hybrid(w["private_key"], w)
    storeKey = lambda self, private_key: self.setKeys(private_key)

    def getRPC(self, network="ethereum"):
        return self.get_default_rpc(network)

    def networks(self):
        return self.get_supported_networks()
