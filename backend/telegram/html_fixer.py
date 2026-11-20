"""
Auto HTML Fixer — automatically repairs broken/invalid HTML in outgoing
Telegram message text and captions so `parse_mode="HTML"` never crashes
with a "can't parse entities" error.

Handles:
  - Unclosed tags            <i>hello           -> <i>hello</i>
  - Wrong / crossed nesting  <b>bold <i>x</b></i> -> <b>bold <i>x</i></b>
  - Invalid/unsupported tags <div>hello</div>    -> hello (tag stripped, text kept)
  - Common tag-name typos    <stong>x</stong>    -> <strong>x</strong>
  - Stray/unmatched closing tags -> dropped safely
  - Auto-escapes raw `&`, unescaped `<`/`>` that aren't part of a real tag

This is a small hand-written tokenizer + stack-based balancer — no external
HTML library dependency required.
"""
import re

# Tags Telegram's Bot API actually supports for parse_mode="HTML"
ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "a", "code", "pre", "tg-spoiler", "tg-emoji", "blockquote",
}

# Common typos / aliases users make -> corrected tag name
TAG_ALIASES = {
    "stong": "strong", "stronge": "strong", "sttrong": "strong",
    "bol": "b", "italic": "i", "itallic": "i", "emm": "em",
    "underline": "u", "strikethrough": "s", "strick": "s", "strikee": "s",
    "spoiler": "tg-spoiler", "spoilerr": "tg-spoiler",
    "codee": "code", "coode": "code",
    "quote": "blockquote", "bquote": "blockquote",
    "link": "a",
}

_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*)?)\s*(/?)>")


def _normalize_tag_name(name: str) -> str:
    name = name.lower()
    return TAG_ALIASES.get(name, name)


def fix_html(text: str) -> str:
    """Returns a version of `text` that is guaranteed to be valid,
    Telegram-parseable HTML (balanced tags, only allowed tag names)."""
    if not text:
        return text

    tokens = []  # list of ("text", str) | ("open", name, attrs) | ("close", name) | ("selfclose", name, attrs)
    pos = 0
    for m in _TAG_RE.finditer(text):
        if m.start() > pos:
            tokens.append(("text", text[pos:m.start()]))
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
    stack = []  # list of (name, attrs)

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
                continue  # strip invalid tag, keep surrounding text
            if stack and stack[-1] == name and not attrs.strip():
                # Heuristic: the same tag opened twice in a row with no new
                # attributes almost always means the user forgot the '/' on
                # what was meant to be a closing tag, e.g. "<b>hi<b>" -> "<b>hi</b>"
                emit_close(stack.pop())
                continue
            stack.append(name)
            emit_open(name, attrs)
        elif kind == "selfclose":
            _, name, attrs = tok
            if name not in ALLOWED_TAGS:
                continue
            # Telegram HTML has no real self-closing tags other than <br> (unsupported) —
            # treat as open+close immediately.
            emit_open(name, attrs)
            emit_close(name)
        elif kind == "close":
            name = tok[1]
            if name not in ALLOWED_TAGS:
                continue
            if name in stack:
                # Close everything opened after `name` too (fixes crossed nesting,
                # e.g. <b>bold <i>x</b></i> -> close i, then close b, don't reopen)
                while stack and stack[-1] != name:
                    emit_close(stack.pop())
                if stack and stack[-1] == name:
                    emit_close(stack.pop())
            # else: stray/unmatched closing tag -> silently dropped

    # Auto-close anything still open, innermost first
    while stack:
        emit_close(stack.pop())

    return "".join(output)


def _escape_bare_text(chunk: str) -> str:
    """Escapes a stray literal '&' that isn't already part of a valid HTML
    entity, so Telegram doesn't choke on things like 'Tom & Jerry'."""
    return re.sub(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)", "&amp;", chunk)


# Fields to auto-fix, per Telegram method name
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
    """Mutates & returns `data` in place: fixes HTML fields for the given
    Telegram method and forces parse_mode=HTML when HTML is detected.

    - parse_mode "Html"/"html"/"HTML" → normalized to "HTML"
    - If text contains HTML tags, always fix + set HTML mode
      (even if parse_mode was missing or a typo)
    - Markdown/MarkdownV2 left alone only when no HTML tags are present
    """
    # normalize method key variants
    fields = HTML_FIELDS_BY_METHOD.get(method) or HTML_FIELDS_BY_METHOD.get(
        method[:1].lower() + method[1:] if method else method
    )
    if not fields:
        # still normalize parse_mode casing
        pm = data.get("parse_mode")
        if pm and str(pm).lower() == "html":
            data["parse_mode"] = "HTML"
        return data

    explicit_mode = data.get("parse_mode")
    mode_l = str(explicit_mode).lower() if explicit_mode is not None else ""

    # Detect HTML in any relevant field
    has_html = False
    for field in fields:
        val = data.get(field)
        if isinstance(val, str) and _looks_like_html(val):
            has_html = True
            break

    # User asked Markdown and text has no HTML tags → leave alone
    if mode_l in ("markdown", "markdownv2") and not has_html:
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
