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


# fields refreshed from a successful live re-check (copied back before re-scoring)
RECHECK_FIELDS = ["rent_original", "rent_currency", "rent_usd", "rent_pen", "rent_usd_basis", "rent_pen_basis",
                  "maintenance_fee", "maintenance_currency", "maintenance_usd", "maintenance_pen",
                  "maintenance_usd_basis", "maintenance_pen_basis", "maintenance_included_in_rent",
                  "estimated_total_monthly_usd", "estimated_total_monthly_pen", "bedrooms", "built_area_m2",
                  "total_area_m2", "furnished", "semi_furnished", "minimum_contract_months", "deposit_months",
                  "phone", "whatsapp"]


def _same(a, b, tol=0.01) -> bool:
    x, y = _num(a), _num(b)
    if x is not None and y is not None:
        return abs(x - y) <= tol * max(abs(x), abs(y), 1)
    return str(a).strip().lower() == str(b).strip().lower()


def compare_fields(old: dict, fresh) -> tuple[list[str], list[str], dict]:
    """Return (confirmed, differences, updates) between the ranked record and a freshly fetched Listing."""
    confirmed, diffs, updates = [], [], {}
    pairs = [("rent", ("rent_original", "rent_currency")), ("bedrooms", ("bedrooms",)),
             ("area", ("built_area_m2", "total_area_m2")), ("maintenance", ("maintenance_fee", "maintenance_currency")),
             ("furnished", ("furnished",)), ("contract", ("minimum_contract_months",)),
             ("deposit", ("deposit_months",)), ("contact", ("phone", "whatsapp"))]
    for label, fields in pairs:
        new_vals = {f: getattr(fresh, f, None) for f in fields}
        if all(v is None for v in new_vals.values()):
            continue                                  # not re-published → nothing to confirm or contradict
        old_vals = {f: old.get(f) for f in fields}
        if all(_same(old_vals[f], new_vals[f]) for f in fields if new_vals[f] is not None):
            confirmed.append(label)
        else:
            shown_old = " ".join(str(old_vals[f]) for f in fields if old_vals[f] not in (None, ""))
            shown_new = " ".join(str(new_vals[f]) for f in fields if new_vals[f] is not None)
            diffs.append(f"{label} changed: {shown_old or 'UNKNOWN'} → {shown_new}")
    for f in RECHECK_FIELDS:
        v = getattr(fresh, f, None)
        if v is not None:
            updates[f] = v
    return confirmed, diffs, updates


class LiveRechecker:
    """Re-open each Top-10 listing just before the report is built.

    Direct polite GET first. Where a portal answers bot protection (Urbania/Adondevivir), the same
    Apify actor re-fetches exactly those listing URLs (a few cents). ACTIVE_CONFIRMED is only set
    when fresh data for the listing was actually retrieved."""

    def __init__(self, http, auth, cfg: dict, budget, fx):
        self.http, self.auth, self.cfg, self.budget, self.fx = http, auth, cfg, budget, fx

    def check(self, rows: dict) -> dict:
        results: dict = {}
        queue: dict[str, dict] = {}
        for i, row in rows.items():
            src = row.get("source")
            if src == "mercadolibre":
                results[i] = self._ml(row)
                continue
            status, note = revisit(row, self.http, self.cfg["qa"]["request_delay_s"])
            if status.startswith("UNVERIFIED") and src in ("urbania", "adondevivir") and self.auth is not None \
                    and getattr(self.auth, "available", False):
                queue.setdefault(src, {})[i] = row
            else:
                results[i] = (status, note, {})
        for src, batch in queue.items():
            results.update(self._apify(src, batch))
        return results

    def _ml(self, row: dict):
        from ..normalize.normalize import normalize_listing
        from ..sources.mercadolibre import parse_detail_html, to_listing
        try:
            resp = self.http.get_html(row["source_url"], delay=self.cfg["qa"]["request_delay_s"])
        except Exception as exc:  # noqa: BLE001
            return (f"UNVERIFIED_{type(exc).__name__.upper()}", f"re-check failed: {exc}", {})
        if resp.status_code in (404, 410):
            return ("INACTIVE", f"HTTP {resp.status_code} at {now_iso()}", {})
        if resp.status_code != 200:
            return ("UNVERIFIED_ERROR", f"HTTP {resp.status_code}", {})
        detail = parse_detail_html(resp.text)
        if detail.get("inactive"):
            return ("INACTIVE", "page marks the publication as finished/paused", {})
        card = {"url": row["source_url"], "id": row.get("source_listing_id"), "title": row.get("title"),
                "price": row.get("rent_original"), "currency": row.get("rent_currency")}
        fresh = normalize_listing(to_listing(card, detail, now_iso()), self.cfg, self.fx)
        ok, diffs, upd = compare_fields(row, fresh)
        status = "VERIFIED_ACTIVE" if not diffs else "ACTIVE_WITH_DIFFERENCES"
        return (status, f"re-opened {now_iso()}; confirmed: {', '.join(ok) or 'page alive'}"
                + (f"; {'; '.join(diffs)}" if diffs else ""), upd)

    def _apify(self, src: str, batch: dict) -> dict:
        from ..normalize.normalize import normalize_listing
        from ..sources.apify_client import ApifyClient, ApifyError, BudgetStop, build_actor_input, paid_run
        from ..sources.navent import map_navent_record
        from ..deduplicate.dedupe import norm_url
        scfg = self.cfg["sources"][src]
        out = {}
        urls = [r["source_url"] for r in batch.values()]
        if self.budget.remaining <= 0.01:
            return {i: ("UNVERIFIED_BUDGET", "no budget left for an Apify re-check", {}) for i in batch}
        try:
            client = ApifyClient(self.auth, self.http)
            info = client.actor_info(scfg["actor_id"])
            props = client.input_schema(scfg["actor_id"], info)
            run_input, _ = build_actor_input(props, {"start_urls": urls, "with_details": True}, len(urls) + 2)
            run, items, cost, _ = paid_run(client, self.budget, scfg["actor_id"], info, run_input, len(urls) + 2,
                                           f"QA re-check {src}", self.cfg["cost_control"]["unknown_pricing_run_usd"],
                                           timeout_s=600)
        except BudgetStop as exc:
            return {i: ("UNVERIFIED_BUDGET", str(exc), {}) for i in batch}
        except (ApifyError, NetworkBlocked) as exc:
            return {i: ("UNVERIFIED_APIFY", f"Apify re-check failed: {exc}", {}) for i in batch}
        fresh = [normalize_listing(map_navent_record(it, src, scfg["base_url"], now_iso()), self.cfg, self.fx)
                 for it in items]
        by_id = {f.source_listing_id: f for f in fresh if f.source_listing_id}
        by_url = {norm_url(f.source_url): f for f in fresh if f.source_url}
        for i, row in batch.items():
            f = by_id.get(str(row.get("source_listing_id"))) or by_url.get(norm_url(row.get("source_url")))
            if f is None:
                out[i] = ("UNVERIFIED_NOT_RETURNED", f"Apify re-check ({len(items)} items, USD {cost:.3f}) did not "
                                                    "return this listing — open the link manually", {})
                continue
            if f.active_status == "INACTIVE":
                out[i] = ("INACTIVE", "portal now reports the listing as inactive", {})
                continue
            ok, diffs, upd = compare_fields(row, f)
            status = "VERIFIED_ACTIVE" if not diffs else "ACTIVE_WITH_DIFFERENCES"
            out[i] = (status, f"re-fetched via Apify {now_iso()}; confirmed: {', '.join(ok) or 'listing alive'}"
                      + (f"; {'; '.join(diffs)}" if diffs else ""), upd)
        return out


def run_qa(ranked: pd.DataFrame, cfg: dict, http, manual_path: Path, live: bool = True,
           rechecker: LiveRechecker | None = None) -> pd.DataFrame:
    ranked = ranked.copy()
    for col in ("qa_status", "qa_notes", "qa_checked_at"):
        if col not in ranked.columns:
            ranked[col] = None
    in_scope = ranked["category"].isin(["PRIMARY", "STRETCH", "BORDERLINE", "NEAR_MISS"])
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
        todo = {i: ranked.loc[i].to_dict() for i in deep_idx if not already(i)}
        if rechecker is not None:
            checked = rechecker.check(todo)
        else:
            checked = {i: (*revisit(row, http, cfg["qa"]["request_delay_s"]), {}) for i, row in todo.items()}
        for i, (status, note, updates) in checked.items():
            prev = ranked.at[i, "qa_notes"]
            ranked.at[i, "qa_status"] = status
            ranked.at[i, "qa_notes"] = "; ".join(x for x in (prev, note) if x)
            ranked.at[i, "qa_checked_at"] = now_iso()
            for f, v in (updates or {}).items():
                if f in ranked.columns:
                    ranked.at[i, f] = v
            if status in ("VERIFIED_ACTIVE", "ACTIVE_WITH_DIFFERENCES"):
                ranked.at[i, "active_status"] = "ACTIVE_CONFIRMED"
                ranked.at[i, "active_evidence"] = f"listing re-checked successfully at {ranked.at[i, 'qa_checked_at']}"
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
