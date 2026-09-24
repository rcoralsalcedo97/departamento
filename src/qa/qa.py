"""Gate 8 — quality control.

* Programmatic sanity checks on the top-N ranked records.
* Live re-check of the top-10 source pages (polite GET; a bot challenge is recorded as
  UNVERIFIED, never as ACTIVE).
* Manual QA overrides from data/processed/manual_qa.csv (source_url, qa_status, qa_notes)
  are merged last, so a human check always wins over automation.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import pandas as pd

from ..http_client import AccessBlocked, NetworkBlocked, RobotsDisallowed
from ..normalize.text_signals import fold
from ..sources.base import now_iso

INACTIVE_MARKERS = ("aviso finalizado", "publicacion finalizada", "publicacion pausada", "ya no esta disponible",
                    "este aviso ya no", "el inmueble ya fue alquilado", "aviso no disponible", "no longer available")


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def programmatic_checks(row: dict, cfg: dict) -> list[str]:
    issues = []
    if not row.get("source_url"):
        issues.append("no listing URL")
    rent = _num(row.get("rent_usd"))
    if rent is None or not (150 <= rent <= 5000):
        issues.append(f"implausible rent {rent}")
    if row.get("rent_currency") not in ("USD", "PEN"):
        issues.append("rent currency unknown")
    if _num(row.get("bedrooms")) not in (1, 2):
        issues.append("bedrooms not 1–2")
    ppm2 = _num(row.get("rent_usd_per_m2"))
    if ppm2 is not None and not (4 <= ppm2 <= 45):
        issues.append(f"USD/m² {ppm2} outside plausible 4–45 range — check area/price")
    m = _num(row.get("maintenance_usd"))
    if m is not None and rent and m > 0.6 * rent:
        issues.append("maintenance > 60% of rent — possible rent/maintenance mix-up")
    lat, lon = _num(row.get("latitude")), _num(row.get("longitude"))
    if lat is not None:
        s, w, n, e = cfg["location"]["bbox"]
        if not (s <= lat <= n and w <= lon <= e):
            issues.append("coordinates outside Miraflores bbox")
    if not (row.get("phone") or row.get("whatsapp") or row.get("agency_name")):
        issues.append("no contact channel")
    return issues


def revisit(row: dict, http, delay: float) -> tuple[str, str]:
    url = row.get("source_url")
    if not url:
        return "NOT_CHECKED", "no URL"
    try:
        resp = http.get_html(url, delay=delay)
    except AccessBlocked as exc:
        return "UNVERIFIED_BLOCKED", f"portal blocks automated re-checks ({exc}); open the link manually"
    except RobotsDisallowed:
        return "UNVERIFIED_ROBOTS", "robots.txt disallows automated re-check; open the link manually"
    except NetworkBlocked as exc:
        return "UNVERIFIED_NETWORK", f"host unreachable from this environment ({exc})"
    except Exception as exc:  # noqa: BLE001
        return "UNVERIFIED_ERROR", f"{type(exc).__name__}: {exc}"
    if resp.status_code in (404, 410):
        return "INACTIVE", f"HTTP {resp.status_code} at {now_iso()}"
    if resp.status_code != 200:
        return "UNVERIFIED_ERROR", f"HTTP {resp.status_code}"
    page = fold(resp.text[:400000])
    if any(mk in page for mk in INACTIVE_MARKERS):
        return "INACTIVE", "page marks the listing as finished / rented"
    notes = []
    rent = _num(row.get("rent_original"))
    if rent:
        pattern = f"{rent:,.0f}"
        variants = {pattern, pattern.replace(",", "."), f"{rent:.0f}"}
        if not any(v in resp.text for v in variants):
            notes.append(f"published rent {rent:,.0f} not found on page — price may have changed")
    area = _num(row.get("area_m2"))
    if area and not re.search(rf"\b{int(area)}\s*m", page):
        notes.append(f"area {area:.0f} m² not found verbatim")
    status = "VERIFIED_ACTIVE" if not notes else "ACTIVE_WITH_DIFFERENCES"
    return status, (f"page reachable at {now_iso()}; " + "; ".join(notes)).strip("; ")


def run_qa(ranked: pd.DataFrame, cfg: dict, http, manual_path: Path, live: bool = True) -> pd.DataFrame:
    ranked = ranked.copy()
    for col in ("qa_status", "qa_notes", "qa_checked_at"):
        if col not in ranked.columns:
            ranked[col] = None
    in_scope = ranked["category"].isin(["PRIMARY", "STRETCH", "NEAR_MISS"])
    top_n = cfg["qa"]["top_n_programmatic"]
    deep_n = cfg["qa"]["top_n_deep"]
    prim = ranked[in_scope].sort_values(["category", "rank_in_category"])
    top_idx = list(ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category").index[:top_n])
    top_idx += list(prim[prim["category"] != "PRIMARY"].index)   # stretch + near misses get checked too
    deep_idx = top_idx[:deep_n]
    live_done = ("VERIFIED_ACTIVE", "ACTIVE_WITH_DIFFERENCES", "UNVERIFIED", "INACTIVE")
    already = lambda i: str(ranked.at[i, "qa_status"] or "").startswith(live_done)   # noqa: E731
    for i in top_idx:
        if already(i):
            continue
        issues = programmatic_checks(ranked.loc[i].to_dict(), cfg)
        ranked.at[i, "qa_status"] = "PROGRAMMATIC_PASS" if not issues else "PROGRAMMATIC_WARN"
        ranked.at[i, "qa_notes"] = "; ".join(issues)
        ranked.at[i, "qa_checked_at"] = now_iso()
    if live:
        for i in deep_idx:
            if already(i):
                continue
            status, note = revisit(ranked.loc[i].to_dict(), http, cfg["qa"]["request_delay_s"])
            prev = ranked.at[i, "qa_notes"]
            ranked.at[i, "qa_status"] = status
            ranked.at[i, "qa_notes"] = "; ".join(x for x in (prev, note) if x)
            ranked.at[i, "qa_checked_at"] = now_iso()
            if status in ("VERIFIED_ACTIVE", "ACTIVE_WITH_DIFFERENCES"):
                ranked.at[i, "active_status"] = "ACTIVE_CONFIRMED"
                ranked.at[i, "active_evidence"] = f"source page re-opened successfully at {ranked.at[i, 'qa_checked_at']}"
            elif status == "INACTIVE":
                ranked.at[i, "active_status"] = "INACTIVE"
                ranked.at[i, "active_evidence"] = note
    if manual_path.exists():
        for rec in csv.DictReader(manual_path.open(encoding="utf-8-sig")):
            hit = ranked["source_url"] == rec.get("source_url")
            if hit.any():
                ranked.loc[hit, "qa_status"] = rec.get("qa_status") or ranked.loc[hit, "qa_status"]
                ranked.loc[hit, "qa_notes"] = f"MANUAL: {rec.get('qa_notes', '')}"
                ranked.loc[hit, "qa_checked_at"] = rec.get("checked_at") or now_iso()
                if rec.get("qa_status") == "VERIFIED_ACTIVE":
                    ranked.loc[hit, "active_status"] = "ACTIVE_CONFIRMED"
                    ranked.loc[hit, "active_evidence"] = f"manually verified {rec.get('checked_at', '')}"
                elif rec.get("qa_status") == "INACTIVE":
                    ranked.loc[hit, "active_status"] = "INACTIVE"
    return ranked
