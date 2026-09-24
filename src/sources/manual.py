"""Import listings captured by hand (agency sites, other portals) from data/manual/.

CSV or JSON; column names = fields of src.models.Listing (see
config/manual_import_template.csv). Blank cells stay UNKNOWN.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..models import Listing
from .base import SourceResult, now_iso, to_bool, to_float, to_int

_FIELDS = Listing.model_fields


def _coerce(field: str, value):
    if value in (None, ""):
        return None
    ann = str(_FIELDS[field].annotation)
    if "bool" in ann:
        return to_bool(value)
    if "int" in ann and "float" not in ann:
        return to_int(value)
    if "float" in ann:
        return to_float(value)
    if "list" in ann:
        return value if isinstance(value, list) else [v.strip() for v in str(value).split(";") if v.strip()]
    return str(value).strip()


def collect_manual(directory: Path) -> SourceResult:
    res = SourceResult(source="manual", method=f"file import from {directory}")
    files = sorted(p for p in directory.glob("*") if p.suffix.lower() in (".csv", ".json"))
    if not files:
        res.notes.append("no manual files present")
        return res.finish("SKIPPED")
    scraped = now_iso()
    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else \
            list(csv.DictReader(path.open(encoding="utf-8-sig")))
        for i, row in enumerate(rows):
            data = {k: _coerce(k, v) for k, v in row.items() if k in _FIELDS}
            data = {k: v for k, v in data.items() if v is not None}
            data.setdefault("source", "manual")
            data.setdefault("scraped_at", scraped)
            data.setdefault("active_status", "UNKNOWN")
            if data.get("latitude") is not None:
                data.setdefault("coord_source", "LISTING")
                data.setdefault("coord_precision", "UNSPECIFIED")
            try:
                res.listings.append(Listing(**data))
                res.raw_records.append(row)
            except Exception as exc:  # noqa: BLE001
                res.errors.append(f"{path.name} row {i + 1}: {exc}")
    return res.finish("SUCCESS" if res.listings and not res.errors else "PARTIAL" if res.listings else "FAILED")
