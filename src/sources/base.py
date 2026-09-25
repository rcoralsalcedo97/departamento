"""Shared source types and tolerant field lookup helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..models import Listing

LIMA_TZ = timezone(timedelta(hours=-5))


def now_iso() -> str:
    return datetime.now(LIMA_TZ).isoformat(timespec="seconds")


@dataclass
class SourceResult:
    source: str
    method: str
    status: str = "NOT_RUN"            # SUCCESS / PARTIAL / FAILED / SKIPPED
    raw_records: list[dict] = field(default_factory=list)
    listings: list[Listing] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)   # facts for SOURCE_AUDIT.md

    def finish(self, status: str) -> "SourceResult":
        self.status = status
        self.finished_at = now_iso()
        return self


class CostBudget:
    """Project-wide hard ceiling for paid calls.

    ``prior_spent`` is the actual spend of earlier runs (read from Apify's run records), so the cap
    applies to the whole project, not to one pipeline run. ``account_headroom`` is what the Apify
    account itself still allows this billing cycle; the stricter of the two limits applies."""

    def __init__(self, max_usd: float, prior_spent: float = 0.0, account_headroom: float | None = None):
        self.max_usd = max_usd
        self.prior_spent = prior_spent
        self.spent = prior_spent            # cumulative project spend
        self.account_headroom = account_headroom
        self.ledger: list[dict] = []        # one entry per paid run of this pipeline run

    @property
    def run_spent(self) -> float:
        return self.spent - self.prior_spent

    @property
    def remaining(self) -> float:
        left = self.max_usd - self.spent
        if self.account_headroom is not None:
            left = min(left, self.account_headroom - self.run_spent)
        return max(0.0, left)

    def charge(self, usd: float | None, label: str = "", basis: str = "") -> None:
        if usd is None:
            raise ValueError("cost must be known or conservatively estimated — never None")
        self.spent += float(usd)
        self.ledger.append({"label": label, "usd": float(usd), "basis": basis, "cumulative": self.spent,
                            "remaining": self.remaining})

    def ledger_lines(self) -> list[str]:
        return [f"{e['label']}: USD {e['usd']:.3f} · cumulative USD {e['cumulative']:.3f} of {self.max_usd:.2f} · "
                f"remaining USD {e['remaining']:.3f} — {e['basis']}" for e in self.ledger]


# --------------------------------------------------------------------------- lookup helpers
def get_path(obj: Any, path: str) -> Any:
    """Dotted path lookup that also indexes lists: 'a.b.0.c'."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if not part.isdigit() or int(part) >= len(cur):
                return None
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            else:
                lower = {k.lower(): k for k in cur if isinstance(k, str)}
                key = lower.get(part.lower())
                cur = cur[key] if key else None
        else:
            return None
    return cur


def pick(obj: dict, *paths: str) -> Any:
    for p in paths:
        v = get_path(obj, p)
        if v not in (None, "", [], {}):
            return v
    return None


def to_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return to_float(pick(v, "value", "amount", "number"))
    m = re.search(r"-?\d[\d.,]*", str(v))
    if not m:
        return None
    from ..normalize.text_signals import parse_amount
    token = m.group(0)
    if token.startswith("-"):
        val = parse_amount(token[1:])
        return -val if val is not None else None
    return parse_amount(token)


def to_int(v: Any) -> int | None:
    f = to_float(v)
    return int(round(f)) if f is not None else None


def to_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "si", "sí", "yes", "1", "y"):
        return True
    if s in ("false", "no", "0", "n"):
        return False
    return None


def iter_label_values(obj: Any) -> Iterable[tuple[str, Any]]:
    """Yield (label, value) pairs from feature structures of many shapes:
    {"CFT2": {"label": "Dormitorios", "value": "2"}}, [{"name": "Baños", "value": 1}],
    {"Dormitorios": 2}, ["2 dormitorios", "80 m²"]."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and ("label" in v or "name" in v):
                yield str(v.get("label") or v.get("name")), v.get("value", v.get("measure"))
            elif isinstance(v, (str, int, float)):
                yield str(k), v
            elif isinstance(v, (list, dict)):
                yield from iter_label_values(v)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                label = item.get("label") or item.get("name") or item.get("key") or item.get("title")
                if label is not None:
                    yield str(label), item.get("value", item.get("value_name", item.get("measure")))
                else:
                    yield from iter_label_values(item)
            elif isinstance(item, str):
                yield item, item
