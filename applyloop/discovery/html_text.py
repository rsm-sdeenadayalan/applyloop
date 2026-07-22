import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    text = raw
    # Greenhouse double-escapes entities; unescape until stable (max 3 rounds).
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()
