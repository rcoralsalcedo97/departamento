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

from .i18n_hi import CODE_HI, HI, PATTERNS

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
    """Inline bilingual text for prose that embeds run values (both versions written side by side).
    In Hindi, bare classification codes in the prose become "हिंदी (CODE)"."""
    return decorate_codes(hi) if _LANG[0] == "hi" else en


_CODE_RX = re.compile(r"(?<![\w(/])(" + "|".join(sorted((re.escape(k) for k in CODE_HI if "_" in k or k in (
    "STRETCH", "BORDERLINE", "UNKNOWN", "HIGH", "MEDIUM", "APPROVED", "REJECTED", "SKIPPED")), key=len, reverse=True))
    + r")(?![\w)])")


def code_hi(code) -> str:
    """One classification code → "हिंदी (CODE)" in Hindi; unchanged in English or when not a known code."""
    if _LANG[0] != "hi" or not isinstance(code, str) or code.strip() not in CODE_HI:
        return code
    return f"{CODE_HI[code.strip()]} ({code.strip()})"


def codes_hi(value) -> str:
    """A cell of codes ("A; B" or "A / B") → each known code labelled in Hindi; other tokens untouched."""
    if not isinstance(value, str):
        return value
    return "; ".join(" / ".join(code_hi(x) for x in part.split(" / ")) for part in value.split("; "))


def decorate_codes(text: str) -> str:
    """Label bare codes inside Hindi prose; codes already in parentheses or glued to other words are left alone."""
    return _CODE_RX.sub(lambda m: f"{CODE_HI[m.group(1)]} ({m.group(1)})", text)


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
