"""English → Hindi (Devanagari) text layer for the client deliverables.

The English deliverables are the single source of truth. Hindi files are built from the same
final data (the workbook is translated cell by cell from the finished English file), so every
number, link, ID, address, price, rank and classification is identical; only human-readable
explanatory text changes. What is *never* translated: addresses and street names, portal /
agency / advertiser names, URLs, listing IDs, currencies, numbers and classification codes
(STRICT_ALL_IN, ACTIVE_CONFIRMED, …) — the codes are explained in Hindi in the methodology.

``t(text)`` translates when the active language is Hindi: exact glossary entry first, then a
pattern rule (numbers and names are carried over verbatim), then split on "; " / " · ".
Anything it cannot translate is returned unchanged and recorded in ``MISSING`` so the QA
gate can fail on an untranslated client-facing string.
"""
from __future__ import annotations

import re
from contextlib import contextmanager

from .i18n_hi import HI, PATTERNS

_LANG = ["en"]
MISSING: set[str] = set()

LATIN = re.compile(r"[A-Za-z]")
CODE_RX = re.compile(r"^[A-Z0-9_]+(?:\s*[;,/·+]\s*[A-Z0-9_]+)*$")
PASS_RX = re.compile(
    r"^(?:https?://\S+|[\w.+-]+@[\w.-]+|\+?\d[\d\s().-]*|(?:USD|S/|PEN)\s?[\d.,]+|[\d.,]+\s?(?:m²|%)?|—|-|…|"
    r"G\d{4}|\d{4}-\d{2}-\d{2}(?:T[\d:+-]+)?|\d+BR(?: · \d+ m²)?)$")


def lang() -> str:
    return _LANG[0]


@contextmanager
def language(code: str):
    prev = _LANG[0]
    _LANG[0] = code
    try:
        yield
    finally:
        _LANG[0] = prev


def L(en: str, hi: str) -> str:
    """Inline bilingual text for prose that embeds run values (both versions written side by side)."""
    return hi if _LANG[0] == "hi" else en


def is_passthrough(text: str) -> bool:
    s = text.strip()
    return not s or not LATIN.search(s) or bool(CODE_RX.match(s)) or bool(PASS_RX.match(s))


def _rule(text: str) -> str | None:
    if text in HI:
        return HI[text]
    low = text[:1].lower() + text[1:]
    if low in HI:
        return HI[low]
    for rx, fn in PATTERNS:
        m = rx.fullmatch(text) or rx.fullmatch(low)
        if m:
            return fn(m, t)
    return None


def t(text, *, record: bool = True):
    """Translate one client-facing string into the active language (identity in English)."""
    if _LANG[0] != "hi" or not isinstance(text, str):
        return text
    s = text.strip()
    if s in HI:
        return HI[s]
    if is_passthrough(text):
        return text
    out = _rule(s)
    if out is not None:
        return out
    for sep in ("; ", " · ", " | "):
        if sep in s:
            parts = s.split(sep)
            return sep.join(t(p, record=record) for p in parts)
    if s.endswith(".") and _rule(s[:-1]) is not None:
        return _rule(s[:-1]) + "।"
    if record:
        MISSING.add(s)
    return text
