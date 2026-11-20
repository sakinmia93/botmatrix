import re as _re


class TextLib:
    """libs.Text — small text-processing helpers for message formatting."""

    def truncate(self, text, length=100, suffix="..."):
        text = text or ""
        return text if len(text) <= length else text[: max(0, length - len(suffix))] + suffix

    def slugify(self, text):
        text = (text or "").lower().strip()
        text = _re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-")

    def escape_markdown(self, text):
        specials = r"_*[]()~`>#+-=|{}.!"
        return "".join("\\" + c if c in specials else c for c in (text or ""))

    def escape_html(self, text):
        return (
            (text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def word_count(self, text):
        return len((text or "").split())

    def extract_numbers(self, text):
        return [float(n) if "." in n else int(n) for n in _re.findall(r"-?\d+\.?\d*", text or "")]

    def extract_mentions(self, text):
        return _re.findall(r"@(\w+)", text or "")

    def extract_urls(self, text):
        return _re.findall(r"https?://\S+", text or "")
