"""Lib.PIL / Lib.CV with the exact TeleBot Studio signatures (camelCase). In-memory only, no file access."""
import io

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageChops
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False
try:
    import cv2
    import numpy as np
    _CV = True
except Exception:  # pragma: no cover
    _CV = False

MAX_PIXELS = 40_000_000


def _need(ok, name):
    if not ok:
        raise RuntimeError(f"{name} is not installed on the server")


def _col(c, default=(255, 255, 255)):
    if c is None:
        return default
    if isinstance(c, (list, tuple)):
        return tuple(int(x) for x in c)
    return c


def _check_size(w, h):
    w, h = int(w), int(h)
    if w < 1 or h < 1:
        raise ValueError("width and height must be positive")
    if w * h > MAX_PIXELS:
        raise ValueError("image too large")
    return w, h


class TBSPIL:
    """Lib.PIL (Pillow)."""
    _FILTERS = {"blur": "BLUR", "sharpen": "SHARPEN", "contour": "CONTOUR", "emboss": "EMBOSS", "edge_enhance": "EDGE_ENHANCE",
                "smooth": "SMOOTH", "detail": "DETAIL", "find_edges": "FIND_EDGES"}

    def openFromBytes(self, image_bytes):
        _need(_PIL, "Pillow")
        im = Image.open(io.BytesIO(bytes(image_bytes)))
        if im.width * im.height > MAX_PIXELS:
            raise ValueError("image too large")
        im.load()
        return im

    def toBytes(self, image, format="JPEG", **params):
        fmt = str(format or "JPEG").upper().lstrip(".")
        if fmt == "JPG":
            fmt = "JPEG"
        im = image
        if fmt == "JPEG" and im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format=fmt, **params)
        return buf.getvalue()

    def createImage(self, width, height, color=(255, 255, 255)):
        _need(_PIL, "Pillow")
        w, h = _check_size(width, height)
        return Image.new("RGB", (w, h), _col(color))

    def createGradient(self, width, height, start_color, end_color, direction="horizontal"):
        _need(_PIL, "Pillow")
        w, h = _check_size(width, height)
        if direction not in ("horizontal", "vertical"):
            raise ValueError("direction must be 'horizontal' or 'vertical'")
        a, b = _col(start_color), _col(end_color)
        im = Image.new("RGB", (w, h))
        px = im.load()
        n = (w if direction == "horizontal" else h)
        for i in range(n):
            t = i / max(1, n - 1)
            c = tuple(int(round(a[k] + (b[k] - a[k]) * t)) for k in range(3))
            if direction == "horizontal":
                for y in range(h):
                    px[i, y] = c
            else:
                for x in range(w):
                    px[x, i] = c
        return im

    def resize(self, image, width=None, height=None, resample=None):
        w0, h0 = image.size
        if width and not height:
            height = max(1, int(round(h0 * (int(width) / w0))))
        elif height and not width:
            width = max(1, int(round(w0 * (int(height) / h0))))
        elif not width and not height:
            return image.copy()
        w, h = _check_size(width, height)
        rs = Image.LANCZOS if resample is None else resample
        return image.resize((w, h), rs)

    def crop(self, image, box):
        return image.crop(tuple(int(x) for x in box))

    def rotate(self, image, angle, expand=False):
        return image.rotate(float(angle), expand=bool(expand), resample=Image.BICUBIC)

    def flip(self, image, direction="horizontal"):
        if direction == "horizontal":
            return ImageOps.mirror(image)
        if direction == "vertical":
            return ImageOps.flip(image)
        raise ValueError("direction must be 'horizontal' or 'vertical'")

    def _enh(self, cls, image, factor):
        return cls(image).enhance(float(factor))

    def adjustBrightness(self, image, factor): return self._enh(ImageEnhance.Brightness, image, factor)
    def adjustContrast(self, image, factor): return self._enh(ImageEnhance.Contrast, image, factor)
    def adjustColor(self, image, factor): return self._enh(ImageEnhance.Color, image, factor)
    def adjustSharpness(self, image, factor): return self._enh(ImageEnhance.Sharpness, image, factor)

    def applyFilter(self, image, filter_type):
        ft = str(filter_type).lower()
        if ft == "grayscale":
            return ImageOps.grayscale(image).convert("RGB") if image.mode != "L" else image
        name = self._FILTERS.get(ft)
        if not name:
            raise ValueError("filter_type must be one of: blur, sharpen, grayscale, contour, emboss, edge_enhance, smooth, detail, find_edges")
        im = image.convert("RGB") if image.mode in ("P", "1") else image
        return im.filter(getattr(ImageFilter, name))

    def invert(self, image):
        im = image
        if im.mode == "RGBA":
            r, g, b, a = im.split()
            return Image.merge("RGBA", (*ImageOps.invert(Image.merge("RGB", (r, g, b))).split(), a))
        return ImageOps.invert(im.convert("RGB") if im.mode not in ("L", "RGB") else im)

    def composite(self, image1, image2, mask=None):
        b = image2.convert(image1.mode).resize(image1.size)
        m = mask if mask is not None else Image.new("L", image1.size, 128)
        if m.size != image1.size:
            m = m.resize(image1.size)
        return Image.composite(image1, b, m.convert("L"))

    def paste(self, base_image, image_to_paste, position=(0, 0), mask=None):
        out = base_image.copy()
        m = mask
        if m is None and image_to_paste.mode == "RGBA":
            m = image_to_paste.split()[3]
        out.paste(image_to_paste, tuple(int(x) for x in position), m)
        return out

    def blend(self, image1, image2, alpha=0.5):
        a = float(alpha)
        if not 0.0 <= a <= 1.0:
            raise ValueError("alpha must be between 0.0 and 1.0")
        mode = "RGBA" if "A" in (image1.mode + image2.mode) else "RGB"
        b2 = image2.convert(mode).resize(image1.size)
        return Image.blend(image1.convert(mode), b2, a)

    def addBorder(self, image, border, color="black"):
        return ImageOps.expand(image, border=border if isinstance(border, (tuple, list)) is False else tuple(border), fill=_col(color, "black"))

    def addWatermark(self, image, watermark, position=None, opacity=1.0):
        base = image.convert("RGBA")
        wm = watermark.convert("RGBA")
        op = max(0.0, min(1.0, float(opacity)))
        if op < 1.0:
            al = wm.split()[3].point(lambda p: int(p * op))
            wm.putalpha(al)
        if position is None:
            position = (max(0, base.width - wm.width), max(0, base.height - wm.height))
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        layer.paste(wm, tuple(int(x) for x in position), wm)
        out = Image.alpha_composite(base, layer)
        return out.convert(image.mode) if image.mode in ("RGB", "L") else out

    def applyMask(self, image, mask):
        out = image.convert("RGBA")
        out.putalpha(mask.convert("L").resize(image.size))
        return out

    def drawText(self, image, text, position, color=(255, 255, 255), font_size=20, font_path=None):
        out = image.copy()
        d = ImageDraw.Draw(out)
        font = None
        if font_path:
            raise ValueError("font_path is not available (no file access in the sandbox)")
        for cand in ("DejaVuSans.ttf", "arial.ttf", "LiberationSans-Regular.ttf"):
            try:
                font = ImageFont.truetype(cand, int(font_size)); break
            except Exception:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size=int(font_size))
            except Exception:
                font = ImageFont.load_default()
        d.text(tuple(int(x) for x in position), str(text), fill=_col(color), font=font)
        return out

    def drawRectangle(self, image, xy, outline="black", fill=None, width=1):
        out = image.copy(); ImageDraw.Draw(out).rectangle(tuple(xy), outline=_col(outline, "black"), fill=_col(fill, None) if fill else None, width=int(width)); return out

    def drawCircle(self, image, xy, outline="black", fill=None, width=1):
        out = image.copy(); ImageDraw.Draw(out).ellipse(tuple(xy), outline=_col(outline, "black"), fill=_col(fill, None) if fill else None, width=int(width)); return out

    def drawLine(self, image, xy, fill="black", width=1):
        out = image.copy(); ImageDraw.Draw(out).line(tuple(xy), fill=_col(fill, "black"), width=int(width)); return out

    def convertMode(self, image, mode):
        return image.convert(str(mode))

    def splitChannels(self, image):
        ch = image.convert("RGB").split()
        return ch[0], ch[1], ch[2]

    def mergeChannels(self, r, g, b):
        return Image.merge("RGB", (r, g, b))

    def getSize(self, image):
        return tuple(image.size)


class TBSCV:
    """Lib.CV (OpenCV). Images are NumPy arrays (BGR inside); `color` arguments are RGB tuples."""
    _face = None

    def _bgr(self, c):
        c = _col(c)
        return (int(c[2]), int(c[1]), int(c[0])) if len(c) >= 3 else (int(c[0]),) * 3

    def readImage(self, image_bytes):
        _need(_CV, "opencv")
        arr = np.frombuffer(bytes(image_bytes), np.uint8)
        im = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if im is None:
            raise ValueError("could not decode image bytes")
        if im.shape[0] * im.shape[1] > MAX_PIXELS:
            raise ValueError("image too large")
        return im

    def toBytes(self, image, format=".jpg", params=None):
        ext = str(format or ".jpg")
        if not ext.startswith("."):
            ext = "." + ext
        ok, buf = cv2.imencode(ext, image, list(params or []))
        if not ok:
            raise ValueError("could not encode image")
        return buf.tobytes()

    def createBlank(self, width, height, color=(255, 255, 255)):
        w, h = _check_size(width, height)
        im = np.zeros((h, w, 3), np.uint8)
        im[:] = self._bgr(color)
        return im

    def resize(self, image, width=None, height=None):
        h0, w0 = image.shape[:2]
        if width and not height:
            height = max(1, int(round(h0 * (int(width) / w0))))
        elif height and not width:
            width = max(1, int(round(w0 * (int(height) / h0))))
        elif not width and not height:
            return image.copy()
        w, h = _check_size(width, height)
        return cv2.resize(image, (w, h))

    def rotate(self, image, angle):
        h, w = image.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
        return cv2.warpAffine(image, m, (w, h))

    def perspectiveTransform(self, image, src_points, dst_points):
        if len(src_points) != 4 or len(dst_points) != 4:
            raise ValueError("src_points and dst_points need exactly 4 points")
        m = cv2.getPerspectiveTransform(np.float32(src_points), np.float32(dst_points))
        h, w = image.shape[:2]
        return cv2.warpPerspective(image, m, (w, h))

    _CONV = {"gray": cv2.COLOR_BGR2GRAY if _CV else 0, "rgb": cv2.COLOR_BGR2RGB if _CV else 0, "hsv": cv2.COLOR_BGR2HSV if _CV else 0,
             "hls": cv2.COLOR_BGR2HLS if _CV else 0, "lab": cv2.COLOR_BGR2LAB if _CV else 0}

    def convertColor(self, image, conversion_type):
        k = str(conversion_type).lower()
        if k not in self._CONV:
            raise ValueError("conversion_type must be one of: gray, rgb, hsv, hls, lab")
        return cv2.cvtColor(image, self._CONV[k])

    def _gray(self, image):
        return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def threshold(self, image, thresh_value=127, max_value=255, type="binary"):
        t = {"binary": cv2.THRESH_BINARY, "binary_inv": cv2.THRESH_BINARY_INV, "trunc": cv2.THRESH_TRUNC,
             "tozero": cv2.THRESH_TOZERO, "tozero_inv": cv2.THRESH_TOZERO_INV}.get(str(type).lower())
        if t is None:
            raise ValueError("type must be one of: binary, binary_inv, trunc, tozero, tozero_inv")
        return cv2.threshold(self._gray(image), float(thresh_value), float(max_value), t)[1]

    def adaptiveThreshold(self, image, max_value=255, block_size=11, c=2):
        bs = int(block_size)
        if bs % 2 == 0 or bs < 3:
            raise ValueError("block_size must be an odd number >= 3")
        return cv2.adaptiveThreshold(self._gray(image), float(max_value), cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, bs, float(c))

    def applyFilter(self, image, filter_type):
        ft = str(filter_type).lower()
        if ft == "blur":
            return cv2.GaussianBlur(image, (7, 7), 0)
        if ft == "sharpen":
            return cv2.filter2D(image, -1, np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], np.float32))
        if ft == "grayscale":
            return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        if ft == "sepia":
            k = np.array([[0.272, 0.534, 0.131], [0.349, 0.686, 0.168], [0.393, 0.769, 0.189]], np.float32)
            return cv2.transform(image, k)
        if ft == "invert":
            return cv2.bitwise_not(image)
        if ft == "emboss":
            return cv2.filter2D(image, -1, np.array([[-2, -1, 0], [-1, 1, 1], [0, 1, 2]], np.float32))
        raise ValueError("filter_type must be one of: blur, sharpen, grayscale, sepia, invert, emboss")

    def detectEdges(self, image, threshold1=100, threshold2=200):
        return cv2.Canny(self._gray(image), float(threshold1), float(threshold2))

    def morphOperations(self, image, operation, kernel_size=5):
        op = {"erode": cv2.MORPH_ERODE, "dilate": cv2.MORPH_DILATE, "open": cv2.MORPH_OPEN, "close": cv2.MORPH_CLOSE,
              "gradient": cv2.MORPH_GRADIENT}.get(str(operation).lower())
        if op is None:
            raise ValueError("operation must be one of: erode, dilate, open, close, gradient")
        k = np.ones((int(kernel_size), int(kernel_size)), np.uint8)
        return cv2.morphologyEx(image, op, k)

    def blendImages(self, image1, image2, alpha=0.5):
        a = float(alpha)
        if not 0.0 <= a <= 1.0:
            raise ValueError("alpha must be between 0.0 and 1.0")
        b = cv2.resize(image2, (image1.shape[1], image1.shape[0]))
        if b.ndim != image1.ndim:
            b = cv2.cvtColor(b, cv2.COLOR_GRAY2BGR) if image1.ndim == 3 else cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        return cv2.addWeighted(image1, 1 - a, b, a, 0)

    def drawText(self, image, text, position, color=(255, 255, 255), font_scale=1.0, thickness=2):
        out = image.copy()
        cv2.putText(out, str(text), tuple(int(x) for x in position), cv2.FONT_HERSHEY_SIMPLEX, float(font_scale), self._bgr(color), int(thickness), cv2.LINE_AA)
        return out

    def drawRectangle(self, image, pt1, pt2, color=(0, 0, 0), thickness=2):
        out = image.copy()
        cv2.rectangle(out, tuple(int(x) for x in pt1), tuple(int(x) for x in pt2), self._bgr(color), int(thickness))
        return out

    def findContours(self, image, mode="external", method="simple"):
        m = {"external": cv2.RETR_EXTERNAL, "list": cv2.RETR_LIST, "tree": cv2.RETR_TREE, "ccomp": cv2.RETR_CCOMP}.get(str(mode).lower(), cv2.RETR_EXTERNAL)
        me = {"simple": cv2.CHAIN_APPROX_SIMPLE, "none": cv2.CHAIN_APPROX_NONE}.get(str(method).lower(), cv2.CHAIN_APPROX_SIMPLE)
        cs, _h = cv2.findContours(self._gray(image).copy(), m, me)
        return list(cs)

    def drawContours(self, image, contours, color=(0, 255, 0), thickness=2):
        out = image.copy()
        if out.ndim == 2:
            out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        cv2.drawContours(out, list(contours), -1, self._bgr(color), int(thickness))
        return out

    def detectFaces(self, image):
        if TBSCV._face is None:
            TBSCV._face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = TBSCV._face.detectMultiScale(self._gray(image), 1.1, 5)
        return [tuple(int(v) for v in f) for f in faces]

    def drawFaces(self, image, faces, color=(0, 255, 0), thickness=2):
        out = image.copy()
        for (x, y, w, h) in faces:
            cv2.rectangle(out, (int(x), int(y)), (int(x + w), int(y + h)), self._bgr(color), int(thickness))
        return out
