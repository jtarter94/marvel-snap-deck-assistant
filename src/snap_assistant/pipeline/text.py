"""Normalise card text so the two sources can be compared fairly.

marvelsnap.pro writes ``<b>On Reveal:</b>`` and ``<i>(once per turn)</i>``;
Marvel Snap Zone writes ``<span>On Reveal</span>:``. Both use curly quotes
and odd whitespace now and then. After ``clean_text`` the same ability text
from either source should compare equal.
"""
from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")
_QUOTE_ONLY = re.compile(r'^["“][^"”]*["”]$')
_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
}


def clean_text(raw: str | None) -> str:
    """Strip markup and normalise punctuation/whitespace.

    Text that is only a quoted line (a vanilla card's flavour quote, which one
    source puts in the ability field) is treated as no ability text.
    """
    if not raw:
        return ""
    s = html.unescape(raw)
    s = _TAG.sub("", s)
    for a, b in _REPLACEMENTS.items():
        s = s.replace(a, b)
    s = _WS.sub(" ", s).strip()
    if _QUOTE_ONLY.match(s):
        return ""
    return s


def clean_name(raw: str | None) -> str:
    return _WS.sub(" ", _TAG.sub("", html.unescape(raw or ""))).strip()


def to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
