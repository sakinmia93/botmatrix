"""Captcha images live only in memory (never written to disk) and are uploaded straight to Telegram."""
import io, random, string, threading, time, secrets
from collections import OrderedDict

_store: "OrderedDict[str, tuple]" = OrderedDict()
_lock = threading.Lock()
TTL = 600
MAX = 1000


def render(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    w, h = 280, 100
    img = Image.new("RGB", (w, h), (26, 26, 46))
    d = ImageDraw.Draw(img)
    for _ in range(8):
        d.line([(random.randint(0, w), random.randint(0, h)), (random.randint(0, w), random.randint(0, h))],
               fill=(random.randint(40, 90), random.randint(40, 90), random.randint(80, 160)), width=1)
    for _ in range(120):
        d.point((random.randint(0, w - 1), random.randint(0, h - 1)),
                fill=(random.randint(60, 200), random.randint(60, 200), random.randint(60, 200)))
    font = None
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(p, 42); break
        except Exception:
            pass
    font = font or ImageFont.load_default()
    try:
        bb = d.textbbox((0, 0), text, font=font); tw, th = bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        tw, th = len(text) * 24, 40
    x0, y0 = max(8, (w - tw) // 2), max(4, (h - th) // 2)
    for i, ch in enumerate(text):
        d.text((x0 + i * (tw // max(len(text), 1)) + random.randint(-2, 2), y0 + random.randint(-6, 6)), ch, font=font, fill=(233, 69, 96))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()


def put(png: bytes) -> str:
    key = secrets.token_hex(8)
    now = time.time()
    with _lock:
        _store[key] = (now + TTL, png)
        while len(_store) > MAX or (_store and next(iter(_store.values()))[0] < now):
            _store.popitem(last=False)
    return "captcha://" + key


def take(url: str):
    """Return a file-like object for a captcha:// reference, or None."""
    key = str(url)[len("captcha://"):]
    with _lock:
        item = _store.get(key)
    if not item or item[0] < time.time():
        return None
    bio = io.BytesIO(item[1]); bio.name = "captcha.png"
    return bio
