"""
Auto HTML Fixer — repairs broken/invalid HTML in outgoing Telegram text/captions
so parse_mode="HTML" never fails with "can't parse entities".

Handles:
  - Unclosed tags            <i>hello           -> <i>hello</i>
  - Empty close tags         <code>0.0</>       -> <code>0.0</code>
  - Wrong / crossed nesting  <b>bold <i>x</b></i> -> balanced
  - Invalid/unsupported tags stripped (text kept)
  - Tag-name typos           <stong>x</stong>   -> <strong>x</strong>
  - Stray closing tags       dropped
  - Bare & auto-escaped
  - Markdown light balance when parse_mode is Markdown*
"""
from __future__ import annotations

import re

ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "a", "code", "pre", "tg-spoiler", "tg-emoji", "blockquote",
}

TAG_ALIASES = {
    "stong": "strong", "stronge": "strong", "sttrong": "strong",
    "bol": "b", "italic": "i", "itallic": "i", "emm": "em",
    "underline": "u", "strikethrough": "s", "strick": "s", "strikee": "s",
    "spoiler": "tg-spoiler", "spoilerr": "tg-spoiler",
    "codee": "code", "coode": "code",
    "quote": "blockquote", "bquote": "blockquote",
    "link": "a",
}

# Matches normal tags AND empty close `</>` (closes top of stack)
_TAG_RE = re.compile(
    r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*)?)\s*(/?)>|</>"
)


def _normalize_tag_name(name: str) -> str:
    name = name.lower()
    return TAG_ALIASES.get(name, name)


def fix_html(text: str) -> str:
    """Return Telegram-safe balanced HTML."""
    if not text:
        return text

    tokens = []
    pos = 0
    for m in _TAG_RE.finditer(text):
        if m.start() > pos:
            tokens.append(("text", text[pos:m.start()]))
        if m.group(0) == "</>":
            tokens.append(("close_top",))
        else:
            is_close, raw_name, attrs, self_close = m.group(1), m.group(2), m.group(3) or "", m.group(4)
            name = _normalize_tag_name(raw_name)
            if is_close:
                tokens.append(("close", name))
            elif self_close:
                tokens.append(("selfclose", name, attrs))
            else:
                tokens.append(("open", name, attrs))
        pos = m.end()
    if pos < len(text):
        tokens.append(("text", text[pos:]))

    output = []
    stack = []

    def emit_open(name, attrs):
        output.append(f"<{name}{attrs}>")

    def emit_close(name):
        output.append(f"</{name}>")

    for tok in tokens:
        kind = tok[0]
        if kind == "text":
            output.append(_escape_bare_text(tok[1]))
        elif kind == "open":
            _, name, attrs = tok
            if name not in ALLOWED_TAGS:
                continue
            if stack and stack[-1] == name and not (attrs or "").strip():
                emit_close(stack.pop())
                continue
            stack.append(name)
            emit_open(name, attrs)
        elif kind == "selfclose":
            _, name, attrs = tok
            if name not in ALLOWED_TAGS:
                continue
            emit_open(name, attrs)
            emit_close(name)
        elif kind == "close_top":
            if stack:
                emit_close(stack.pop())
        elif kind == "close":
            name = tok[1]
            if name not in ALLOWED_TAGS:
                continue
            if name in stack:
                while stack and stack[-1] != name:
                    emit_close(stack.pop())
                if stack and stack[-1] == name:
                    emit_close(stack.pop())

    while stack:
        emit_close(stack.pop())

    return "".join(output)


def _escape_bare_text(chunk: str) -> str:
    return re.sub(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)", "&", chunk)


def fix_markdown(text: str) -> str:
    """Light Markdown safety: balance unpaired * _ `."""
    if not text:
        return text
    out = text
    for ch in ("*", "_", "`"):
        n = len(re.findall(r"(?<!\\)" + re.escape(ch), out))
        if n % 2 == 1:
            out = out + ch
    return out


HTML_FIELDS_BY_METHOD = {
    "sendMessage": ["text"],
    "sendPhoto": ["caption"],
    "sendVideo": ["caption"],
    "sendAudio": ["caption"],
    "sendDocument": ["caption"],
    "sendVoice": ["caption"],
    "sendAnimation": ["caption"],
    "sendPaidMedia": ["caption"],
    "editMessageText": ["text"],
    "editMessageCaption": ["caption"],
    "copyMessage": ["caption"],
    "sendPoll": ["explanation"],
}


def _looks_like_html(s: str) -> bool:
    if not s or "<" not in s:
        return False
    return bool(_TAG_RE.search(s))


def apply_auto_html_fix(method: str, data: dict) -> dict:
    """Fix HTML/Markdown fields; force parse_mode=HTML when tags found."""
    fields = HTML_FIELDS_BY_METHOD.get(method)
    if not fields and method:
        for k, v in HTML_FIELDS_BY_METHOD.items():
            if k.lower() == method.lower():
                fields = v
                break

    explicit_mode = data.get("parse_mode")
    mode_l = str(explicit_mode).lower() if explicit_mode is not None else ""

    if not fields:
        if mode_l == "html":
            data["parse_mode"] = "HTML"
        return data

    has_html = False
    for field in fields:
        val = data.get(field)
        if isinstance(val, str) and _looks_like_html(val):
            has_html = True
            break

    if mode_l in ("markdown", "markdownv2") and not has_html:
        for field in fields:
            val = data.get(field)
            if isinstance(val, str) and val:
                data[field] = fix_markdown(val)
        return data

    touched = False
    for field in fields:
        val = data.get(field)
        if isinstance(val, str) and val:
            if has_html or mode_l in ("html", ""):
                data[field] = fix_html(val)
                touched = True

    if touched or has_html or mode_l == "html":
        data["parse_mode"] = "HTML"

    return data
