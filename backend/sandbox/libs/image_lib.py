"""libs.Pillow / libs.OpenCV — REAL image processing (replaces the old stub).

Method names cover BOTH:
  - the official TBC docs (snake_case: open_from_bytes, to_bytes, draw_text, ...)
  - the earlier build's camelCase names (openFromBytes, toBytes, drawText, ...)
so existing bot code and docs-based code both keep working.

Images are handled purely in-memory (bytes in, bytes out) — no filesystem access,
matching the sandbox's "no local file paths" rule.
"""
from __future__ import annotations
from io import BytesIO

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps, ImageChops
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    _NP_OK = False

try:
    import cv2
    _CV_OK = True
except ImportError:
    _CV_OK = False


def _need(ok, name):
    if not ok:
        raise RuntimeError(
            f"{name} is not installed on the server. Run: pip install {name.lower()}"
        )


class _ImgResult(dict):
    """Dict that also supports attribute access, for TBC-style `result.ok` access."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


# ============================================================= libs.Pillow
class PILLib:
    """Real Pillow-backed image editing (`libs.Pillow` / `libs.PIL`)."""

    def info(self):
        if _PIL_OK:
            import PIL
            return {"available": True, "version": getattr(PIL, "__version__", "?")}
        return {"available": False}

    # ---- I/O ----------------------------------------------------------
    def open_from_bytes(self, image_bytes):
        _need(_PIL_OK, "Pillow")
        return Image.open(BytesIO(image_bytes)).convert("RGBA") if False else Image.open(BytesIO(image_bytes))

    def to_bytes(self, image, format="JPEG", **params):
        _need(_PIL_OK, "Pillow")
        buf = BytesIO()
        img = image
        fmt = (format or "JPEG").upper().lstrip(".")
        if fmt in ("JPG", "JPEG") and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(buf, format=fmt, **params)
        buf.seek(0)
        return buf

    def create_image(self, width, height, color=(255, 255, 255)):
        _need(_PIL_OK, "Pillow")
        return Image.new("RGB", (int(width), int(height)), color)

    def create_gradient(self, width, height, start_color, end_color, direction="horizontal"):
        _need(_PIL_OK, "Pillow")
        width, height = int(width), int(height)
        base = Image.new("RGB", (width, height), start_color)
        top = Image.new("RGB", (width, height), end_color)
        mask = Image.new("L", (width, height))
        mask_data = []
        if direction == "vertical":
            for y in range(height):
                mask_data.extend([int(255 * (y / max(height - 1, 1)))] * width)
        else:
            row = [int(255 * (x / max(width - 1, 1))) for x in range(width)]
            for _ in range(height):
                mask_data.extend(row)
        mask.putdata(mask_data)
        return Image.composite(top, base, mask)

    # ---- transform ------------------------------------------------------
    def resize(self, image, width=None, height=None, resample=None):
        _need(_PIL_OK, "Pillow")
        w0, h0 = image.size
        if width and not height:
            height = int(h0 * (width / w0))
        elif height and not width:
            width = int(w0 * (height / h0))
        elif not width and not height:
            return image.copy()
        resample = resample or Image.LANCZOS
        return image.resize((int(width), int(height)), resample)

    def crop(self, image, box):
        _need(_PIL_OK, "Pillow")
        return image.crop(tuple(box))

    def rotate(self, image, angle, expand=False):
        _need(_PIL_OK, "Pillow")
        return image.rotate(angle, expand=expand)

    def mirror(self, image, direction="horizontal"):
        _need(_PIL_OK, "Pillow")
        return ImageOps.mirror(image) if direction == "horizontal" else ImageOps.flip(image)

    def get_size(self, image):
        return {"width": image.size[0], "height": image.size[1]}

    # ---- adjustments & filters -----------------------------------------
    def adjust_brightness(self, image, factor):
        _need(_PIL_OK, "Pillow")
        return ImageEnhance.Brightness(image).enhance(float(factor))

    def adjust_contrast(self, image, factor):
        _need(_PIL_OK, "Pillow")
        return ImageEnhance.Contrast(image).enhance(float(factor))

    def adjust_color(self, image, factor):
        _need(_PIL_OK, "Pillow")
        return ImageEnhance.Color(image).enhance(float(factor))

    def adjust_sharpness(self, image, factor):
        _need(_PIL_OK, "Pillow")
        return ImageEnhance.Sharpness(image).enhance(float(factor))

    _FILTERS = {
        "blur": "BLUR", "contour": "CONTOUR", "detail": "DETAIL",
        "edge_enhance": "EDGE_ENHANCE", "emboss": "EMBOSS",
        "sharpen": "SHARPEN", "smooth": "SMOOTH", "find_edges": "FIND_EDGES",
    }

    def apply_filter(self, image, filter_type):
        _need(_PIL_OK, "Pillow")
        name = self._FILTERS.get(str(filter_type).lower(), "BLUR")
        return image.filter(getattr(ImageFilter, name))

    def invert(self, image):
        _need(_PIL_OK, "Pillow")
        rgb = image.convert("RGB")
        return ImageOps.invert(rgb)

    # ---- composition -----------------------------------------------------
    def composite(self, image1, image2, mask=None):
        _need(_PIL_OK, "Pillow")
        if mask is None:
            mask = Image.new("L", image1.size, 128)
        return Image.composite(image1, image2, mask)

    def paste(self, base_image, image_to_paste, position=(0, 0), mask=None):
        _need(_PIL_OK, "Pillow")
        out = base_image.copy()
        out.paste(image_to_paste, tuple(position), mask)
        return out

    def blend(self, image1, image2, alpha=0.5):
        _need(_PIL_OK, "Pillow")
        im2 = image2.resize(image1.size) if image2.size != image1.size else image2
        return Image.blend(image1.convert("RGB"), im2.convert("RGB"), float(alpha))

    def blend_images(self, image1, image2, alpha=0.5):
        return self.blend(image1, image2, alpha)

    def add_border(self, image, border, color="black"):
        _need(_PIL_OK, "Pillow")
        return ImageOps.expand(image, border=int(border), fill=color)

    def add_watermark(self, image, watermark, position=None, opacity=0.5):
        _need(_PIL_OK, "Pillow")
        base = image.convert("RGBA")
        if isinstance(watermark, str):
            layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            pos = position or (base.size[0] // 4, base.size[1] // 2)
            draw.text(pos, watermark, fill=(255, 255, 255, int(255 * opacity)))
            return Image.alpha_composite(base, layer)
        wm = watermark.convert("RGBA")
        pos = position or (base.size[0] - wm.size[0] - 10, base.size[1] - wm.size[1] - 10)
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        layer.paste(wm, pos, wm)
        return Image.alpha_composite(base, layer)

    def apply_mask(self, image, mask):
        _need(_PIL_OK, "Pillow")
        out = image.convert("RGBA")
        out.putalpha(mask.convert("L"))
        return out

    # ---- drawing ----------------------------------------------------------
    def draw_text(self, image, text, position, fill=(0, 0, 0), font_size=20, **kwargs):
        _need(_PIL_OK, "Pillow")
        out = image.copy()
        draw = ImageDraw.Draw(out)
        font = None
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", int(font_size))
        except Exception:
            font = ImageFont.load_default()
        draw.text(tuple(position), str(text), fill=fill, font=font, **{
            k: v for k, v in kwargs.items() if k in ("align", "spacing", "stroke_width", "stroke_fill")
        })
        return out

    def draw_rectangle(self, image, xy, outline="black", width=2, fill=None):
        _need(_PIL_OK, "Pillow")
        out = image.copy()
        ImageDraw.Draw(out).rectangle(tuple(xy), outline=outline, width=int(width), fill=fill)
        return out

    def draw_circle(self, image, xy, radius=10, outline="black", width=2, fill=None):
        _need(_PIL_OK, "Pillow")
        x, y = xy
        box = (x - radius, y - radius, x + radius, y + radius)
        out = image.copy()
        ImageDraw.Draw(out).ellipse(box, outline=outline, width=int(width), fill=fill)
        return out

    def draw_line(self, image, xy, fill="black", width=2):
        _need(_PIL_OK, "Pillow")
        out = image.copy()
        ImageDraw.Draw(out).line(tuple(xy), fill=fill, width=int(width))
        return out

    # ---- channels & modes -----------------------------------------------
    def convert_mode(self, image, mode):
        _need(_PIL_OK, "Pillow")
        return image.convert(mode)

    def split_channels(self, image):
        _need(_PIL_OK, "Pillow")
        return list(image.convert("RGB").split())

    def merge_channels(self, r, g, b):
        _need(_PIL_OK, "Pillow")
        return Image.merge("RGB", (r, g, b))

    def ascii(self, image):
        return {"ok": True, "ascii": "(ascii art not implemented)"}

    # ------------------------------------------------- camelCase aliases
    createImage = create_image
    createGradient = create_gradient
    openFromBytes = open_from_bytes
    toBytes = to_bytes
    getSize = get_size
    flip = mirror
    convertMode = convert_mode
    adjustBrightness = adjust_brightness
    adjustContrast = adjust_contrast
    adjustColor = adjust_color
    adjustSharpness = adjust_sharpness
    applyFilter = apply_filter
    addBorder = add_border
    addWatermark = add_watermark
    drawText = draw_text
    drawCircle = draw_circle
    drawRectangle = draw_rectangle
    drawLine = draw_line
    convertColor = convert_mode
    mergeChannels = merge_channels
    splitChannels = split_channels
    applyMask = apply_mask
    blendImages_camel = blend_images

    def readImage(self, path_or_url):
        # Legacy convenience: fetch bytes over HTTP and open them.
        import requests
        r = requests.get(str(path_or_url), timeout=30)
        return self.open_from_bytes(r.content)


# ============================================================= libs.OpenCV
class CVLib:
    """Real OpenCV-backed image processing (`libs.OpenCV` / `libs.CV`)."""

    _face_cascade = None

    def info(self):
        if _CV_OK:
            return {"available": True, "version": cv2.__version__}
        return {"available": False}

    def _cascade(self):
        _need(_CV_OK, "opencv-python-headless")
        if CVLib._face_cascade is None:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            CVLib._face_cascade = cv2.CascadeClassifier(path)
        return CVLib._face_cascade

    # ---- I/O --------------------------------------------------------------
    def read_image_from_bytes(self, image_bytes):
        _need(_CV_OK, "opencv-python-headless")
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes")
        return img

    def to_bytes(self, image, format=".jpg", params=None):
        _need(_CV_OK, "opencv-python-headless")
        ok, buf = cv2.imencode(format, image, params or [])
        if not ok:
            raise ValueError("Could not encode image")
        return BytesIO(buf.tobytes())

    def create_blank(self, width, height, color=(255, 255, 255)):
        _need(_CV_OK, "opencv-python-headless")
        img = np.zeros((int(height), int(width), 3), dtype=np.uint8)
        img[:] = tuple(reversed(color))  # RGB -> BGR
        return img

    # ---- geometry & color --------------------------------------------------
    def resize(self, image, width=None, height=None):
        h0, w0 = image.shape[:2]
        if width and not height:
            height = int(h0 * (width / w0))
        elif height and not width:
            width = int(w0 * (height / h0))
        elif not width and not height:
            return image.copy()
        return cv2.resize(image, (int(width), int(height)))

    def rotate(self, image, angle):
        h, w = image.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(image, m, (w, h))

    def perspective_transform(self, image, src_points, dst_points):
        src = np.float32(src_points)
        dst = np.float32(dst_points)
        m = cv2.getPerspectiveTransform(src, dst)
        h, w = image.shape[:2]
        return cv2.warpPerspective(image, m, (w, h))

    _COLOR_MAP = {
        "gray": cv2.COLOR_BGR2GRAY if _CV_OK else None,
        "grayscale": cv2.COLOR_BGR2GRAY if _CV_OK else None,
        "rgb": cv2.COLOR_BGR2RGB if _CV_OK else None,
        "hsv": cv2.COLOR_BGR2HSV if _CV_OK else None,
    }

    def convert_color(self, image, conversion_type="gray"):
        _need(_CV_OK, "opencv-python-headless")
        code = self._COLOR_MAP.get(str(conversion_type).lower(), cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(image, code)

    def threshold(self, image, thresh_value=127, max_value=255, threshold_type="binary"):
        _need(_CV_OK, "opencv-python-headless")
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ttype = {"binary": cv2.THRESH_BINARY, "binary_inv": cv2.THRESH_BINARY_INV,
                 "trunc": cv2.THRESH_TRUNC, "tozero": cv2.THRESH_TOZERO}.get(threshold_type, cv2.THRESH_BINARY)
        _, out = cv2.threshold(gray, thresh_value, max_value, ttype)
        return out

    def adaptive_threshold(self, image, max_value=255, block_size=11, c=2):
        _need(_CV_OK, "opencv-python-headless")
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.adaptiveThreshold(
            gray, max_value, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c
        )

    # ---- filters & effects --------------------------------------------------
    def apply_filter(self, image, filter_type="blur"):
        _need(_CV_OK, "opencv-python-headless")
        ft = str(filter_type).lower()
        if ft == "blur":
            return cv2.GaussianBlur(image, (5, 5), 0)
        if ft == "sharpen":
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            return cv2.filter2D(image, -1, kernel)
        if ft == "median":
            return cv2.medianBlur(image, 5)
        if ft == "sepia":
            kernel = np.array([[0.272, 0.534, 0.131],
                                [0.349, 0.686, 0.168],
                                [0.393, 0.769, 0.189]])
            return cv2.transform(image, kernel)
        return image

    def detect_edges(self, image, threshold1=100, threshold2=200):
        _need(_CV_OK, "opencv-python-headless")
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.Canny(gray, threshold1, threshold2)

    def morph_operations(self, image, operation="dilate", kernel_size=5):
        _need(_CV_OK, "opencv-python-headless")
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        ops = {
            "dilate": cv2.dilate, "erode": cv2.erode,
            "open": lambda i, k: cv2.morphologyEx(i, cv2.MORPH_OPEN, k),
            "close": lambda i, k: cv2.morphologyEx(i, cv2.MORPH_CLOSE, k),
        }
        fn = ops.get(operation, cv2.dilate)
        return fn(image, kernel)

    def blend_images(self, image1, image2, alpha=0.5):
        _need(_CV_OK, "opencv-python-headless")
        im2 = image2
        if im2.shape[:2] != image1.shape[:2]:
            im2 = cv2.resize(im2, (image1.shape[1], image1.shape[0]))
        return cv2.addWeighted(image1, alpha, im2, 1 - alpha, 0)

    # ---- drawing --------------------------------------------------------------
    def draw_text(self, image, text, position, font_scale=1.0, color=(255, 255, 255), thickness=2):
        _need(_CV_OK, "opencv-python-headless")
        out = image.copy()
        cv2.putText(out, str(text), tuple(position), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, tuple(reversed(color)), thickness, cv2.LINE_AA)
        return out

    def draw_rectangle(self, image, pt1, pt2, color=(0, 255, 0), thickness=2):
        _need(_CV_OK, "opencv-python-headless")
        out = image.copy()
        cv2.rectangle(out, tuple(pt1), tuple(pt2), tuple(reversed(color)), thickness)
        return out

    def find_contours(self, image, mode="external"):
        _need(_CV_OK, "opencv-python-headless")
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, 0)
        m = cv2.RETR_EXTERNAL if mode == "external" else cv2.RETR_LIST
        contours, _ = cv2.findContours(thresh, m, cv2.CHAIN_APPROX_SIMPLE)
        return list(contours)

    def draw_contours(self, image, contours, color=(0, 255, 0), thickness=2):
        _need(_CV_OK, "opencv-python-headless")
        out = image.copy()
        cv2.drawContours(out, contours, -1, tuple(reversed(color)), thickness)
        return out

    # ---- faces --------------------------------------------------------------
    def detect_faces(self, image):
        _need(_CV_OK, "opencv-python-headless")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self._cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        return [tuple(int(v) for v in f) for f in faces]

    def draw_faces(self, image, faces, color=(0, 255, 0), thickness=2):
        _need(_CV_OK, "opencv-python-headless")
        out = image.copy()
        for (x, y, w, h) in faces:
            cv2.rectangle(out, (x, y), (x + w, y + h), tuple(reversed(color)), thickness)
        return out

    # ------------------------------------------------- camelCase aliases
    convertColor = convert_color
    detectEdges = detect_edges
    detectFaces = detect_faces
    drawFaces = draw_faces
    findContours = find_contours
    drawContours = draw_contours

    def readImage(self, path):
        import requests
        r = requests.get(str(path), timeout=30)
        return self.read_image_from_bytes(r.content)
