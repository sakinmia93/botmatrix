"""Builds the `libs` object injected into every sandboxed command."""
from backend.sandbox.libs.random_lib import RandomLib
from backend.sandbox.libs.datetime_lib import DateAndTimeLib
from backend.sandbox.libs.http_lib import HTTPLib
from backend.sandbox.libs.csv_lib import CSVLib
from backend.sandbox.libs.resources_lib import ResourcesLib
from backend.sandbox.libs.openai_lib import OpenAILib, GeminiLib
from backend.sandbox.libs.webhook_lib import WebhookLib
from backend.sandbox.libs.security_lib import SecurityLib
from backend.sandbox.libs.translate_lib import TranslateLib
from backend.sandbox.libs.utils_lib import UtilsLib
from backend.sandbox.libs.cache_lib import CacheLib
from backend.sandbox.libs.referral_lib import ReferralLib
from backend.sandbox.libs.moderation_lib import ModerationLib
from backend.sandbox.libs.forms_lib import FormsLib
from backend.sandbox.libs.menu_lib import MenuLib
from backend.sandbox.libs.logger_lib import LoggerLib
from backend.sandbox.libs.stats_lib import StatsLib
from backend.sandbox.libs.reflib_lib import RefLib
# image_lib imported lazily in __init__ (cv2/numpy are heavy)
from backend.sandbox.libs.request_lib import RequestModule
from backend.sandbox.libs.premium_gift_lib import PremiumGiftLib
from backend.sandbox.libs.keyboard_lib import KeyboardLib
from backend.sandbox.libs.text_lib import TextLib
from backend.sandbox.libs.qr_lib import QRLib
from backend.sandbox.libs.validator_lib import ValidatorLib
from backend.sandbox.libs.web3_lib import Web3Lib
from backend.sandbox.libs.ton_lib import TonLib
from backend.sandbox.libs.crypto_lib import CryptoLib
from backend.sandbox.libs.payments_lib import (
    OxapayLib, CoinbaseLib, CoinpaymentsLib,
)
try:
    from backend.sandbox.libs.telegram_session_lib import TelegramSession as _TelegramSessionCls
except Exception as _tg_imp_err:  # telethon missing / expand failure / syntax
    _TelegramSessionCls = None
    _TG_IMP_ERR = str(_tg_imp_err)
else:
    _TG_IMP_ERR = None

try:
    from backend.sandbox.libs.mention_lib import MentionLib as _MentionLibCls
except Exception as _mn_imp_err:
    _MentionLibCls = None
    _MN_IMP_ERR = str(_mn_imp_err)
else:
    _MN_IMP_ERR = None

from backend.config import BASE_URL


class LibsNamespace:
    """Exposed as `libs.CSV`, `libs.Random`, `libs.Resources`, etc. in user code."""

    def __init__(self, db, bot_id: int, telegram_user_id: int, storage_root: str, secrets: dict):
        _random = RandomLib()
        self.Random = _random
        self.random = _random

        _dt = DateAndTimeLib()
        self.DateAndTime = _dt
        self.datetime = _dt
        self.DateTime = _dt

        _http = HTTPLib(ctx=(bot_id, telegram_user_id))
        self.customHTTP = _http
        self.HTTP = _http
        self.http = _http

        self.CSV = CSVLib(bot_id, storage_root)
        self.Resources = ResourcesLib(db, bot_id, telegram_user_id)
        self.resources = self.Resources

        self.openai_lib = OpenAILib(secrets.get("openai_api_key"))
        self.openai = self.openai_lib
        self.gemini_lib = GeminiLib(secrets.get("gemini_api_key"))
        self.gemini = self.gemini_lib

        self.Webhook = WebhookLib(db=db, bot_id=bot_id, base_url=BASE_URL)
        self.webhook = self.Webhook

        _sec = SecurityLib()
        self.security = _sec
        self.Security = _sec

        self.translate = TranslateLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id, storage_root=storage_root)
        self.Translate = self.translate
        self.Utils = UtilsLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id)
        self.utils = self.Utils
        self.Cache = CacheLib(db=db, bot_id=bot_id)
        self.cache = self.Cache
        self.Referral = ReferralLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id)
        self.referral = self.Referral
        self.Moderation = ModerationLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id)
        self.moderation = self.Moderation
        self.Forms = FormsLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id)
        self.forms = self.Forms
        self.Menu = MenuLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id)
        self.menu = self.Menu
        self.Logger = LoggerLib(db=db, bot_id=bot_id)
        self.logger = self.Logger
        self.Stats = StatsLib(db=db, bot_id=bot_id)
        self.stats = self.Stats
        # TeleBot Studio style
        _uname = None
        try:
            from backend import models as _m
            _bb = db.query(_m.Bot).filter_by(id=bot_id).first()
            _uname = _bb.username if _bb else None
        except Exception:
            pass
        self.RefLib = RefLib(db=db, bot_id=bot_id, telegram_user_id=telegram_user_id, bot_username=_uname)
        try:
            from backend.sandbox.libs.image_lib import PILLib, CVLib
            from backend.sandbox.tbs_media import TBSPIL, TBSCV
            self.Pillow = PILLib()
            self.OpenCV = CVLib()
            self.PIL = TBSPIL()
            self.CV = TBSCV()
        except Exception as _img_err:
            class _ImgStub:
                def __getattr__(self, n):
                    raise RuntimeError("Image libs unavailable on this host (low memory). " + str(_img_err))
            self.Pillow = self.OpenCV = self.PIL = self.CV = _ImgStub()
        _tok = None
        try:
            from backend import models as _m
            _b = db.query(_m.Bot).filter_by(id=bot_id).first()
            _tok = _b.token if _b else None
        except Exception:
            pass
        self.PremiumGift = PremiumGiftLib(db=db, bot_id=bot_id, bot_token=_tok, storage_root=storage_root)
        self.premium_gift = self.PremiumGift

        self.Keyboard = KeyboardLib()
        self.Text = TextLib()
        self.QR = QRLib()
        self.Validator = ValidatorLib()

        _web3 = Web3Lib(secrets.get("web3_private_key"))
        self.web3lib = _web3
        self.Web3 = _web3
        self.TBC_Web3_ = _web3
        self.web3_ = _web3

        _ton = TonLib(
            mnemonics=secrets.get("ton_mnemonics"),
            api_key=secrets.get("ton_api_key"),
            db=db, bot_id=bot_id, base_url=BASE_URL,
        )
        self.TonLib = _ton
        self.ton = _ton
        self.TON = _ton
        self.EVM = self.web3lib

        # Telegram user client (MTProto) + mass-mention helpers
        # Always expose the attribute so SECTION code never hits AttributeError.
        # NOTE: never close over `except Exception as X` variables inside nested
        # classes/methods — Python 3.11+ deletes them after the except block and
        # later calls raise: cannot access free variable 'X' ...
        if _TelegramSessionCls is not None:
            try:
                _tg_sess = _TelegramSessionCls(db=db, bot_id=bot_id, base_url=BASE_URL)
            except Exception as _e:
                _tg_fail_msg = "TelegramSession failed to initialize: " + str(_e)
                class _TgSessBroken:
                    def __getattr__(self, name, _msg=_tg_fail_msg):
                        raise RuntimeError(_msg)
                _tg_sess = _TgSessBroken()
        else:
            _tg_miss_msg = (
                "TelegramSession library is not available. "
                "Install telethon and ensure telegram_session_lib.py is deployed. "
                "Import error: " + str(_TG_IMP_ERR)
            )
            class _TgSessMissing:
                def __getattr__(self, name, _msg=_tg_miss_msg):
                    raise RuntimeError(_msg)
            _tg_sess = _TgSessMissing()
        self.TelegramSession = _tg_sess
        self.telegram_session = _tg_sess
        self.TgSession = _tg_sess

        if _MentionLibCls is not None:
            try:
                _mention = _MentionLibCls(db=db, bot_id=bot_id, bot_token=_tok)
            except Exception as _e:
                _mn_fail_msg = "Mention failed to initialize: " + str(_e)
                class _MentionBroken:
                    def __getattr__(self, name, _msg=_mn_fail_msg):
                        raise RuntimeError(_msg)
                _mention = _MentionBroken()
        else:
            _mn_miss_msg = (
                "Mention library is not available. Import error: " + str(_MN_IMP_ERR)
            )
            class _MentionMissing:
                def __getattr__(self, name, _msg=_mn_miss_msg):
                    raise RuntimeError(_msg)
            _mention = _MentionMissing()
        self.Mention = _mention
        self.mention = _mention

        # TBC crypto network aliases (docs: libs.Polygon, libs.ARB, ...)
        class _NetWeb3:
            def __init__(self, w3, network):
                self._w3 = w3
                self._network = network
            def send(self, value, to, contract, private_key=None, **k):
                """Deprecated TBC API: send tokens through a contract on this chain."""
                return self._w3.sendETHER(value, to, private_key=private_key, contract_address=contract, network=self._network, **k)
            def _native(self, value, to, private_key=None, **k):
                return self._w3.sendNativeCoin(value, to, private_key=private_key, network=self._network, **k)
            def __getattr__(self, name):
                if name.startswith("send") and name not in ("sendNativeCoin", "sendETHER", "sendCoin", "sendToken", "send_ether", "sendEther", "sendether", "send_native_coin", "send_navive_coin") and not hasattr(self._w3, name):
                    return self._native      # sendPolygon, sendARB, sendTTcoin, sendTomochain, ...
                attr = getattr(self._w3, name)
                if callable(attr):
                    def wrapper(*a, **k):
                        # inject default network only when not already provided
                        if "network" not in k and not a:
                            k["network"] = self._network
                        elif "network" not in k and name in (
                            "sendNativeCoin", "sendCoin", "sendToken", "sendETHER",
                            "fetchBalance", "balance", "fetchTokenBalance", "get_default_rpc",
                        ):
                            # keyword-only inject when method uses network=
                            import inspect
                            try:
                                sig = inspect.signature(attr)
                                if "network" in sig.parameters:
                                    k.setdefault("network", self._network)
                            except Exception:
                                k.setdefault("network", self._network)
                        return attr(*a, **k)
                    return wrapper
                return attr
        self.Polygon = _NetWeb3(self.web3lib, "polygon")
        self.ARB = _NetWeb3(self.web3lib, "arbitrum")
        self.Tomochain = _NetWeb3(self.web3lib, "tomochain")
        self.TTcoin = _NetWeb3(self.web3lib, "ttcoin")

        from backend.sandbox.tbs_compat import TBSAI
        self.AI = TBSAI(self.openai_lib, self.gemini_lib)
        self.TeleGifts = self.PremiumGift

        self.Crypto = CryptoLib()
        self.crypto = self.Crypto

        self.Oxapay = OxapayLib(secrets.get("oxapay_key"))
        self.oxapay = self.Oxapay

        self.coinbase = CoinbaseLib()
        self.Coinbase = self.coinbase
        if secrets.get("coinbase_key"):
            self.coinbase.setKeys(secrets.get("coinbase_key"), secrets.get("coinbase_secret") or "")

        self.coinpayments = CoinpaymentsLib()
        self.Coinpayments = self.coinpayments
        if secrets.get("coinpayments_public"):
            self.coinpayments.setKeys(
                secrets.get("coinpayments_public"),
                secrets.get("coinpayments_private") or "",
            )
