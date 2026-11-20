"""Auto-Translate: outgoing bot messages adapt to each user's language (92 languages).

Language priority: the user's own choice -> the bot's default language -> the
language set in the user's Telegram app.

What is never changed: HTML tags, links, @usernames, numbers/amounts/prices,
wallet-like addresses, emojis and anything inside <notrans>…</notrans>.
Use <trans>…</trans> to translate only the marked parts of a message.
If a translation would damage any protected part, the original text is sent.
"""
from __future__ import annotations

import os
import re
import threading
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import requests

LANGUAGES: Dict[str, str] = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic", "hy": "Armenian",
    "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian", "bn": "Bengali", "bs": "Bosnian",
    "bg": "Bulgarian", "ca": "Catalan", "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)", "hr": "Croatian", "cs": "Czech",
    "da": "Danish", "nl": "Dutch", "en": "English", "eo": "Esperanto", "et": "Estonian",
    "fi": "Finnish", "fr": "French", "gl": "Galician", "ka": "Georgian",
    "de": "German", "el": "Greek", "gu": "Gujarati", "ha": "Hausa",
    "he": "Hebrew", "hi": "Hindi", "hu": "Hungarian",
    "is": "Icelandic", "ig": "Igbo", "id": "Indonesian", "ga": "Irish", "it": "Italian",
    "ja": "Japanese", "jv": "Javanese", "kn": "Kannada", "kk": "Kazakh", "km": "Khmer",
    "ko": "Korean", "ku": "Kurdish", "ky": "Kyrgyz", "lo": "Lao",
    "lv": "Latvian", "lt": "Lithuanian", "lb": "Luxembourgish", "mk": "Macedonian",
    "mg": "Malagasy", "ms": "Malay", "ml": "Malayalam", "mt": "Maltese", "mi": "Maori",
    "mr": "Marathi", "mn": "Mongolian", "my": "Myanmar (Burmese)", "ne": "Nepali",
    "no": "Norwegian", "ps": "Pashto", "fa": "Persian",
    "pl": "Polish", "pt": "Portuguese", "pa": "Punjabi", "ro": "Romanian", "ru": "Russian",
    "sr": "Serbian", "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian", "so": "Somali",
    "es": "Spanish", "su": "Sundanese", "sw": "Swahili", "sv": "Swedish", "tl": "Filipino",
    "tg": "Tajik", "ta": "Tamil", "tt": "Tatar", "te": "Telugu", "th": "Thai", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "ug": "Uyghur", "uz": "Uzbek",
    "vi": "Vietnamese", "cy": "Welsh", "xh": "Xhosa", "yo": "Yoruba", "zu": "Zulu",
}
_LOWER = {k.lower(): k for k in LANGUAGES}

ENDPOINT = os.getenv("TRANSLATE_ENDPOINT", "https://translate.googleapis.com/translate_a/single")

# Offline phrase map for common bot UI (instant, no network). Keyed by lowercase English source.
_PHRASE_MAP = {
    "hello": {"bn": "হ্যালো", "hi": "नमस्ते", "az": "Salam", "ur": "ہیلو", "fa": "سلام"},
    "main menu": {"bn": "মূল মেনু", "hi": "मुख्य मेनू", "az": "Əsas menyu", "ur": "مین مینو", "fa": "منوی اصلی"},
    "catalog": {"bn": "ক্যাটালগ", "hi": "कैटलॉग", "az": "Kataloq", "ur": "کیٹلاگ", "fa": "کاتالوگ"},
    "my orders": {"bn": "আমার অর্ডার", "hi": "मेरे आदेश", "az": "Sifarişlərim", "ur": "میرے آرڈرز", "fa": "سفارش‌های من"},
    "balance": {"bn": "ব্যালেন্স", "hi": "बैलेंस", "az": "Balans", "ur": "بیلنس", "fa": "موجودی"},
    "your balance": {"bn": "আপনার ব্যালেন্স", "hi": "आपका बैलेंस", "az": "Sizin balansınız", "ur": "آپ کا بیلنس", "fa": "موجودی شما"},
    "add funds": {"bn": "ফান্ড যোগ করুন", "hi": "फंड जोड़ें", "az": "Balans artır", "ur": "فنڈز شامل کریں", "fa": "افزایش موجودی"},
    "language": {"bn": "ভাষা", "hi": "भाषा", "az": "Dil", "ur": "زبان", "fa": "زبان"},
    "help": {"bn": "সাহায্য", "hi": "मदद", "az": "Kömək", "ur": "مدد", "fa": "راهنما"},
    "admin panel": {"bn": "অ্যাডমিন প্যানেল", "hi": "एडमिन पैनल", "az": "Admin panel", "ur": "ایڈمن پینل", "fa": "پنل ادمین"},
    "choose your language": {"bn": "আপনার ভাষা বেছে নিন", "hi": "अपनी भाषा चुनें", "az": "Dilinizi seçin", "ur": "اپنی زبان منتخب کریں", "fa": "زبان خود را انتخاب کنید"},
    "language saved. all messages will arrive in this language.": {
        "bn": "ভাষা সংরক্ষিত। সব মেসেজ এই ভাষায় আসবে।",
        "hi": "भाषा सहेजी गई। सभी संदेश इस भाषा में आएंगे।",
        "az": "Dil yadda saxlandı. Bütün mesajlar bu dildə gələcək.",
        "ur": "زبان محفوظ ہو گئی۔ تمام پیغامات اس زبان میں آئیں گے۔",
        "fa": "زبان ذخیره شد. همه پیام‌ها به این زبان می‌رسند.",
    },
    "current": {"bn": "বর্তমান", "hi": "वर्तमान", "az": "Cari", "ur": "موجودہ", "fa": "فعلی"},
    "tap a language below.": {"bn": "নিচে একটি ভাষায় ট্যাপ করুন।", "hi": "नीचे एक भाषा पर टैप करें।", "az": "Aşağıdan dil seçin.", "ur": "نیچے ایک زبان پر ٹیپ کریں۔", "fa": "یکی از زبان‌های زیر را انتخاب کنید."},
    "digital products, delivered instantly.": {
        "bn": "ডিজিটাল পণ্য, তাৎক্ষণিক ডেলিভারি।",
        "hi": "डिजिटल उत्पाद, तुरंत डिलीवरी।",
        "az": "Rəqəmsal məhsullar, dərhal çatdırılma.",
        "ur": "ڈیجیٹل مصنوعات، فوری ڈیلیوری۔",
        "fa": "محصولات دیجیتال، تحویل فوری.",
    },
    "choose an option below.": {"bn": "নিচে একটি অপশন বেছে নিন।", "hi": "नीचे एक विकल्प चुनें।", "az": "Aşağıdan seçim edin.", "ur": "نیچے ایک اختیار منتخب کریں۔", "fa": "یکی از گزینه‌های زیر را انتخاب کنید."},
    "hello": {"bn": "হ্যালো", "hi": "नमस्ते", "az": "Salam", "ur": "سلام", "fa": "سلام"},
    "there is no such command.": {"bn": "এমন কোনো কমান্ড নেই।", "hi": "ऐसा कोई कमांड नहीं है।", "az": "Belə əmr yoxdur.", "ur": "ایسا کوئی کمانڈ نہیں۔", "fa": "چنین دستوری وجود ندارد."},
    "use the menu below.": {"bn": "নিচের মেনু ব্যবহার করুন।", "hi": "नीचे दिए मेनू का उपयोग करें।", "az": "Aşağıdakı menyudan istifadə edin.", "ur": "نیچے دیے گئے مینو کا استعمال کریں۔", "fa": "از منوی زیر استفاده کنید."},
    "i did not understand that.": {"bn": "আমি বুঝতে পারিনি।", "hi": "मैं समझ नहीं पाया।", "az": "Başa düşmədim.", "ur": "میں سمجھ نہیں پایا۔", "fa": "متوجه نشدم."},
    "please use the menu below.": {"bn": "অনুগ্রহ করে নিচের মেনু ব্যবহার করুন।", "hi": "कृपया नीचे दिए मेनू का उपयोग करें।", "az": "Zəhmət olmasa aşağıdakı menyudan istifadə edin.", "ur": "براہ کرم نیچے دیے گئے مینو کا استعمال کریں۔", "fa": "لطفاً از منوی زیر استفاده کنید."},
    "products": {"bn": "পণ্য", "hi": "उत्पाद", "az": "Məhsullar", "ur": "مصنوعات", "fa": "محصولات"},
    "page": {"bn": "পৃষ্ঠা", "hi": "पृष्ठ", "az": "Səhifə", "ur": "صفحہ", "fa": "صفحه"},
    "price": {"bn": "মূল্য", "hi": "कीमत", "az": "Qiymət", "ur": "قیمت", "fa": "قیمت"},
    "stock": {"bn": "স্টক", "hi": "स्टॉक", "az": "Stok", "ur": "اسٹاک", "fa": "موجودی انبار"},
    "out of stock": {"bn": "স্টক শেষ", "hi": "स्टॉक खत्म", "az": "Stokda yoxdur", "ur": "اسٹاک ختم", "fa": "ناموجود"},
    "quantity": {"bn": "পরিমাণ", "hi": "मात्रा", "az": "Say", "ur": "مقدار", "fa": "تعداد"},
    "total": {"bn": "মোট", "hi": "कुल", "az": "Cəmi", "ur": "کل", "fa": "جمع"},
    "confirm your order": {"bn": "অর্ডার নিশ্চিত করুন", "hi": "अपना ऑर्डर पुष्टि करें", "az": "Sifarişi təsdiqlə", "ur": "اپنا آرڈر تصدیق کریں", "fa": "سفارش را تأیید کنید"},
    "pay": {"bn": "পেমেন্ট", "hi": "भुगतान", "az": "Ödə", "ur": "ادائیگی", "fa": "پرداخت"},
    "back": {"bn": "পেছনে", "hi": "वापस", "az": "Geri", "ur": "واپس", "fa": "بازگشت"},
    "refresh": {"bn": "রিফ্রেশ", "hi": "रीफ़्रेश", "az": "Yenilə", "ur": "تازہ کریں", "fa": "بازخوانی"},
    "previous": {"bn": "আগের", "hi": "पिछला", "az": "Əvvəlki", "ur": "پچھلا", "fa": "قبلی"},
    "next": {"bn": "পরবর্তী", "hi": "अगला", "az": "Növbəti", "ur": "اگلا", "fa": "بعدی"},
    "order delivered!": {"bn": "অর্ডার ডেলিভার হয়েছে!", "hi": "ऑर्डर डिलीवर हो गया!", "az": "Sifariş çatdırıldı!", "ur": "آرڈر ڈیلیور ہو گیا!", "fa": "سفارش تحویل شد!"},
    "payment received!": {"bn": "পেমেন্ট গৃহীত!", "hi": "भुगतान प्राप्त!", "az": "Ödəniş alındı!", "ur": "ادائیگی موصول!", "fa": "پرداخت دریافت شد!"},
    "not enough balance.": {"bn": "পর্যাপ্ত ব্যালেন্স নেই।", "hi": "पर्याप्त बैलेंस नहीं।", "az": "Balans kifayət etmir.", "ur": "کافی بیلنس نہیں۔", "fa": "موجودی کافی نیست."},
    "the store is not set up yet. please contact the administrator.": {
        "bn": "স্টোর এখনও সেটআপ হয়নি। অ্যাডমিনের সাথে যোগাযোগ করুন।",
        "hi": "स्टोर अभी सेटअप नहीं है। व्यवस्थापक से संपर्क करें।",
        "az": "Mağaza hələ hazır deyil. Administratorla əlaqə saxlayın.",
        "ur": "اسٹور ابھی سیٹ اپ نہیں ہوا۔ ایڈمن سے رابطہ کریں۔",
        "fa": "فروشگاه هنوز راه‌اندازی نشده. با مدیر تماس بگیرید.",
    },
    "how it works": {"bn": "কীভাবে কাজ করে", "hi": "यह कैसे काम करता है", "az": "Necə işləyir", "ur": "یہ کیسے کام کرتا ہے", "fa": "چگونه کار می‌کند"},
    "good to know": {"bn": "জানা ভালো", "hi": "जानना अच्छा है", "az": "Bilmək yaxşıdır", "ur": "جاننا اچھا ہے", "fa": "دانستن خوب است"},
    "commands": {"bn": "কমান্ডসমূহ", "hi": "कमांड", "az": "Əmrlər", "ur": "کمانڈز", "fa": "دستورها"},
    "administrator": {"bn": "অ্যাডমিনিস্ট্রেটর", "hi": "व्यवस्थापक", "az": "Administrator", "ur": "ایڈمنسٹریٹر", "fa": "مدیر"},
}


def _phrase_lookup(text: str, target: str) -> Optional[str]:
    """Exact / near-exact offline match for common UI strings."""
    raw = str(text).strip()
    if not raw:
        return None
    # strip simple leading emoji + space for lookup
    key = raw
    if len(key) > 2 and not key[0].isalnum() and key[1] == " ":
        key = key[2:].strip()
    low = key.lower()
    entry = _PHRASE_MAP.get(low)
    if entry and target in entry:
        # preserve leading emoji if we stripped it
        if raw != key:
            return raw[:2] + entry[target]
        return entry[target]
    return None



USER_LANG_KEY = "__lang"
BOT_LANG_KEY = "__lang_global"


def normalize_lang(code: Optional[str]) -> Optional[str]:
    """Map Telegram / BCP-47 codes (pt-br, zh-hans, iw…) to a supported code."""
    if not code:
        return None
    c = str(code).strip().replace("_", "-")
    low = c.lower()
    if low in _LOWER:
        return _LOWER[low]
    alias = {"iw": "he", "zh": "zh-CN", "zh-hans": "zh-CN", "zh-hant": "zh-TW", "zh-hk": "zh-TW",
             "fil": "tl", "nb": "no", "nn": "no", "jw": "jv"}
    if low in alias:
        return alias[low]
    base = low.split("-")[0]
    if base in alias:
        return alias[base]
    return _LOWER.get(base)


# --------------------------------------------------------------------------- masking
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_URL = re.compile(r"(?:https?://|t\.me/|www\.)[^\s<>\"']+", re.I)
_MENTION = re.compile(r"(?<![\w])@[A-Za-z0-9_]{3,}")
_ADDRESS = re.compile(r"\b(?:0x[a-fA-F0-9]{20,}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{20,60}|T[A-Za-z1-9]{33}|[EU]Q[A-Za-z0-9_-]{40,})\b")
_NUMBER = re.compile(r"[$€£¥₹৳₽]?\d[\d.,:/-]*[%$€£¥₹৳₽]?")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍←-⇿⌀-⏿]+")
_CODE = re.compile(r"<(code|pre)[^>]*>.*?</\1>", re.S | re.I)
_NOTRANS = re.compile(r"<notrans>(.*?)</notrans>", re.S | re.I)
_TRANS = re.compile(r"<trans>(.*?)</trans>", re.S | re.I)
_ALL = re.compile("|".join("(?:%s)" % r.pattern for r in (_CODE, _TAG, _URL, _MENTION, _ADDRESS, _NUMBER, _EMOJI)), re.S | re.I)
_PH = "⟦{}⟧"
_PH_RE = re.compile(r"⟦\s*([a-z]+)\s*⟧")


def _idx(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


def _unidx(t: str) -> int:
    n = 0
    for ch in t:
        n = n * 26 + (ord(ch) - 96)
    return n - 1


def _mask(text: str, translate_only_marked: bool) -> Tuple[str, List[str]]:
    protected: List[str] = []

    def keep(m):
        protected.append(m.group(0))
        return _PH.format(_idx(len(protected) - 1))

    def keep_text(t: str) -> str:
        protected.append(t)
        return _PH.format(_idx(len(protected) - 1))

    s = text
    if translate_only_marked:
        out, last = [], 0
        for m in _TRANS.finditer(s):
            if s[last:m.start()]:
                out.append(keep_text(s[last:m.start()]))
            out.append(m.group(1))
            last = m.end()
        if last < len(s):
            out.append(keep_text(s[last:]))
        s = "".join(out)
    s = _NOTRANS.sub(lambda m: keep_text(m.group(1)), s)
    s = _ALL.sub(keep, s)
    return s, protected


def _unmask(text: str, protected: List[str]) -> Optional[str]:
    seen = set()

    def back(m):
        i = _unidx(m.group(1))
        if i >= len(protected):
            return m.group(0)
        seen.add(i)
        return protected[i]

    out = _PH_RE.sub(back, text)
    if len(seen) != len(protected):
        return None  # a protected part got lost -> caller keeps the original
    return out


# --------------------------------------------------------------------------- engine
_cache: "OrderedDict[Tuple[str, str], str]" = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 8192


# Shared session (connection reuse → much faster repeated translates)
_http = requests.Session()
_remote_fail_until = 0.0  # monotonic; skip network briefly after hard failures
_remote_lock = threading.Lock()

_http.headers.update({"User-Agent": "Mozilla/5.0 (compatible; BotMatrix/1.0)"})


def _argos(text: str, target: str) -> Optional[str]:
    """Offline Argos Translate — no rate limits. Language packs installed for en→bn/hi/az/ur/fa (+ more if present)."""
    try:
        import argostranslate.translate as _at
    except Exception:
        return None
    # Argos uses short codes; map our codes
    tl = target
    if tl in ("zh-CN", "zh-TW"):
        tl = "zh"
    try:
        # Prefer direct en→target
        out = _at.translate(str(text), "en", tl)
        if out and str(out).strip() and str(out).strip() != str(text).strip():
            return str(out)
        # If identical, still accept (proper noun etc.)
        if out is not None:
            return str(out)
    except Exception:
        return None
    return None


def _remote(text: str, target: str) -> Optional[str]:
    """Translate: Argos offline (unlimited) → short network fallback. Never stalls the bot long."""
    import time as _time
    global _remote_fail_until
    if not text or not str(text).strip():
        return text
    q = str(text)
    if len(q) > 4500:
        q = q[:4500]

    # 1) Offline Argos — no quota, works offline
    try:
        out = _argos(q, target)
        if out:
            return out
    except Exception:
        pass

    now = _time.monotonic()
    if now < _remote_fail_until:
        return None

    # 2) Google free endpoint (session + short timeout)
    try:
        r = _http.get(
            ENDPOINT,
            params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": q},
            timeout=2.0,
        )
        if r.status_code == 200:
            data = r.json()
            if data and data[0]:
                out = "".join(seg[0] for seg in data[0] if seg and seg[0])
                if out:
                    return out
        if r.status_code == 429:
            with _remote_lock:
                _remote_fail_until = _time.monotonic() + 180
    except Exception:
        pass

    # 3) MyMemory fallback
    try:
        r = _http.get(
            "https://api.mymemory.translated.net/get",
            params={"q": q[:500], "langpair": f"en|{target}"},
            timeout=1.8,
        )
        if r.status_code == 200:
            data = r.json()
            out = (data.get("responseData") or {}).get("translatedText")
            if out and isinstance(out, str) and out.strip() and "MYMEMORY WARNING" not in out.upper():
                return out
            if out and "MYMEMORY WARNING" in str(out).upper():
                with _remote_lock:
                    _remote_fail_until = _time.monotonic() + 3600
        elif r.status_code == 429:
            with _remote_lock:
                _remote_fail_until = _time.monotonic() + 180
    except Exception:
        pass

    with _remote_lock:
        if _time.monotonic() >= _remote_fail_until:
            _remote_fail_until = _time.monotonic() + 20
    return None


def _strip_tags(text: str) -> str:
    text = _NOTRANS.sub(lambda m: m.group(1), text)
    return _TRANS.sub(lambda m: m.group(1), text)


def translate_text(text: str, target: str, parse_mode: Optional[str] = None) -> str:
    """Translate while keeping protected content intact. Falls back to the original."""
    if not text or not isinstance(text, str):
        return text
    target = normalize_lang(target)
    has_trans_tags = bool(_TRANS.search(text))
    if not target:
        return _strip_tags(text)
    # English target → no network (bot source strings are English)
    if target == "en" and not has_trans_tags:
        return _strip_tags(text)
    key = (text, target)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    # Offline phrase table first (instant, reliable for bot UI)
    hit = _phrase_lookup(text, target)
    if hit is not None:
        with _cache_lock:
            _cache[key] = hit
            if len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
        return hit
    masked, protected = _mask(text, has_trans_tags)
    if not re.sub(r"⟦[a-z]+⟧|[\s\W_]", "", masked):
        result = _strip_tags(text)  # nothing translatable
    else:
        out = _remote(masked, target)
        restored = _unmask(out, protected) if out else None
        result = restored if restored is not None else _strip_tags(text)
    with _cache_lock:
        _cache[key] = result
        if len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return result


# --------------------------------------------------------------------------- preferences
def get_user_lang(db, bot_id: int, user_id) -> Optional[str]:
    from backend import models
    try:
        row = db.query(models.UserData).filter_by(bot_id=bot_id, telegram_user_id=int(user_id), key=USER_LANG_KEY).first()
        return normalize_lang(row.value) if row and row.value else None
    except Exception:
        return None


def set_user_lang(db, bot_id: int, user_id, lang: Optional[str]):
    from backend import models
    row = db.query(models.UserData).filter_by(bot_id=bot_id, telegram_user_id=int(user_id), key=USER_LANG_KEY).first()
    if lang is None:
        if row:
            db.delete(row)
    elif row:
        row.value = lang
    else:
        db.add(models.UserData(bot_id=bot_id, telegram_user_id=int(user_id), key=USER_LANG_KEY, value=lang))
    db.commit()


def get_bot_lang(db, bot_id: int) -> Optional[str]:
    from backend import models
    try:
        row = db.query(models.BotData).filter_by(bot_id=bot_id, key=BOT_LANG_KEY).first()
        return normalize_lang(row.value) if row and row.value else None
    except Exception:
        return None


def set_bot_lang(db, bot_id: int, lang: Optional[str]):
    from backend import models
    row = db.query(models.BotData).filter_by(bot_id=bot_id, key=BOT_LANG_KEY).first()
    if lang is None:
        if row:
            db.delete(row)
    elif row:
        row.value = lang
    else:
        db.add(models.BotData(bot_id=bot_id, key=BOT_LANG_KEY, value=lang))
    db.commit()


def resolve_lang(db, bot_id: int, user_id, telegram_lang: Optional[str]) -> Optional[str]:
    return (get_user_lang(db, bot_id, user_id) if user_id else None) \
        or get_bot_lang(db, bot_id) or normalize_lang(telegram_lang)


# --------------------------------------------------------------------------- send hook
_TEXT_FIELDS = {
    "sendmessage": ("text",), "editmessagetext": ("text",), "editmessagecaption": ("caption",),
    "sendphoto": ("caption",), "sendvideo": ("caption",), "senddocument": ("caption",),
    "sendanimation": ("caption",), "sendaudio": ("caption",), "sendvoice": ("caption",),
    "sendmediagroup": (), "answercallbackquery": ("text",),
}


def _translate_markup(raw, lang, parse_mode):
    """Translate labels of INLINE keyboards only (reply-keyboard labels are matched as commands)."""
    import json
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return raw
    if not isinstance(obj, dict) or "inline_keyboard" not in obj:
        return raw
    for row in obj["inline_keyboard"]:
        for btn in row:
            if isinstance(btn, dict) and isinstance(btn.get("text"), str):
                btn["text"] = translate_text(btn["text"], lang)
    return json.dumps(obj, ensure_ascii=False) if isinstance(raw, str) else obj


def make_hook(db, bot, update: dict):
    msg = (update.get("message") or update.get("edited_message") or {})
    cb = update.get("callback_query") or {}
    inline_q = update.get("inline_query") or {}
    frm = msg.get("from") or cb.get("from") or inline_q.get("from") or {}
    uid, tg_lang = frm.get("id"), frm.get("language_code")
    cache: Dict[str, Optional[str]] = {}

    def lang_for(chat_id) -> Optional[str]:
        # Sending to the person who triggered the update -> their language.
        # Sending to someone else (admin notices, broadcasts) -> that person's saved choice or bot default.
        key = str(chat_id)
        if key not in cache:
            same = uid is not None and str(chat_id) == str(uid)
            cache[key] = resolve_lang(db, bot.id, chat_id, tg_lang if same else None)
        return cache[key]

    def hook(method: str, data: dict):
        fields = _TEXT_FIELDS.get(method.lower())
        if fields is None:
            return data
        chat_id = data.get("chat_id") or uid
        lang = lang_for(chat_id) if chat_id is not None else normalize_lang(tg_lang)
        if method.lower() == "answercallbackquery" and not lang:
            lang = normalize_lang(tg_lang)
        for f in fields:
            if isinstance(data.get(f), str):
                data[f] = translate_text(data[f], lang, data.get("parse_mode")) if lang else _strip_tags(data[f])
        if lang and "reply_markup" in data:
            data["reply_markup"] = _translate_markup(data["reply_markup"], lang, data.get("parse_mode"))
        return data

    return hook
