"""Miraflores Rental Intelligence — reproducible pipeline (Gates 0–10).

    python -m src.pipeline --mode preflight   # Gate 0 only: credentials + reachability
    python -m src.pipeline --mode validate    # Gates 0–3: 10–20 records per source + field coverage
    python -m src.pipeline --mode full        # Gates 0–10: full search → Excel + PDF + templates
    python -m src.pipeline --mode report      # rebuild deliverables from data/processed (e.g. after manual QA)
    python -m src.pipeline --mode demo        # offline end-to-end run on SYNTHETIC fixtures → docs/preview/
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

from . import config as K
from .deduplicate.dedupe import deduplicate
from .geospatial.geocode import geocode_missing
from .geospatial.osm import OsmLayers, fetch_overpass, geo_features, parse_layers
from .http_client import PoliteClient, probe
from .models import Listing
from .normalize.currency import FxRate, fetch_fx
from .normalize.normalize import normalize_listing
from .qa.final_qa import final_qa
from .qa.qa import RECHECK_FIELDS, LiveRechecker, run_qa
from .reporting import common as C
from .reporting.contact_templates import write_contact_templates
from .reporting.excel import build_workbook
from .reporting.excel_hi import translate_workbook
from .reporting.i18n import L, MISSING, language
from .reporting.i18n import t as t_
from .reporting.report import build_report_html, html_to_pdf
from .runlog import RunLog
from .scoring.scoring import rank, score_all
from .geospatial.geocode import address_evidence
from .http_client import NetworkBlocked
from .sources.apify_client import ApifyAuth, ApifyClient, ApifyError, resolve_apify_auth
from .sources.base import CostBudget, SourceResult, now_iso
from .sources.manual import collect_manual
from .sources.mercadolibre import collect_mercadolibre
from .sources.navent import collect_navent, map_navent_record
from .sources.registry import CANDIDATES, REFERENCE_REPO_AUDIT, REGISTRY, RESEARCH_DATE

PROBES = {
    "api.apify.com": "https://api.apify.com/v2/",
    "urbania.pe": "https://urbania.pe/",
    "www.urbania.pe": "https://www.urbania.pe/",
    "adondevivir.com": "https://adondevivir.com/",
    "www.adondevivir.com": "https://www.adondevivir.com/",
    "inmuebles.mercadolibre.com.pe": "https://inmuebles.mercadolibre.com.pe/",
    "departamento.mercadolibre.com.pe": "https://departamento.mercadolibre.com.pe/",
    "overpass-api.de": "https://overpass-api.de/api/status",
    "nominatim.openstreetmap.org": "https://nominatim.openstreetmap.org/status",
    "estadisticas.bcrp.gob.pe": "https://estadisticas.bcrp.gob.pe/",
    "www.sunat.gob.pe": "https://www.sunat.gob.pe/",
}
COVERAGE_FIELDS = [
    ("URL", ["source_url"]), ("rent", ["rent_original"]), ("currency", ["rent_currency"]),
    ("bedrooms", ["bedrooms"]), ("area", ["total_area_m2", "built_area_m2"]),
    ("maintenance", ["maintenance_fee", "maintenance_included_in_rent"]), ("coordinates", ["latitude"]),
    ("address", ["address"]), ("publication date", ["publication_date"]), ("contact", ["phone", "whatsapp"]),
    ("description", ["description"]), ("images", ["image_count"]),
]
PREVIEW_BANNER = "SYNTHETIC DEMO DATA — FORMAT PREVIEW ONLY — THESE ARE NOT REAL LISTINGS"


# --------------------------------------------------------------------------- helpers
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _isnull(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or v == ""


def coverage(listings: list[Listing]) -> dict[str, float]:
    if not listings:
        return {name: 0.0 for name, _ in COVERAGE_FIELDS}
    out = {}
    for name, fields in COVERAGE_FIELDS:
        hits = sum(1 for lst in listings if any(not _isnull(getattr(lst, f)) and getattr(lst, f) is not False
                                                 or (f == "maintenance_included_in_rent" and getattr(lst, f) is True)
                                                 for f in fields))
        out[name] = hits / len(listings)
    return out


def source_status(res: SourceResult, cov: dict[str, float]) -> str:
    if not res.listings:
        joined = " ".join(res.errors)
        if "unreachable" in joined or "NetworkBlocked" in joined:
            return "PENDING (environment egress blocked)"
        if res.status == "SKIPPED":
            return "SKIPPED"
        return "REJECTED"
    core = min(cov["URL"], cov["rent"], cov["currency"], cov["bedrooms"])
    if len(res.listings) >= 5 and core >= 0.9 and cov["area"] >= 0.6:
        return "APPROVED"
    return "PARTIAL"


def validation_row(name: str, res: SourceResult) -> dict:
    ls = res.listings
    n = len(ls)

    def pct(pred) -> str:
        return f"{100 * sum(1 for x in ls if pred(x)) / n:.0f}%" if n else "—"
    return {
        "SOURCE": name,
        "ACTOR / METHOD": res.method,
        "RECORDS": n,
        "VALID RENT %": pct(lambda x: x.rent_original and x.rent_currency in ("USD", "PEN") and 150 <= x.rent_original <= 60000),
        "VALID BEDROOMS %": pct(lambda x: x.bedrooms is not None and 0 <= x.bedrooms <= 10),
        "VALID AREA %": pct(lambda x: any(a and 12 <= a <= 400 for a in (x.built_area_m2, x.total_area_m2))),
        "MAINTENANCE %": pct(lambda x: x.maintenance_fee is not None or x.maintenance_included_in_rent is True),
        "COORDINATES %": pct(lambda x: x.latitude is not None),
        "CONTACT %": pct(lambda x: bool(x.phone or x.whatsapp)),
        "DATE %": pct(lambda x: bool(x.publication_date)),
        "ERRORS": "; ".join(res.errors)[:160] or "—",
        "COST": f"USD {res.cost_usd:.3f}",
    }


PORTAL_HOSTS = {"urbania": "urbania.pe", "adondevivir": "adondevivir.com", "mercadolibre": "mercadolibre.com.pe"}


def usable_url(row: dict) -> bool:
    """An https link on the listing's own portal that names its posting id."""
    url = str(row.get("source_url") or "")
    lid = str(row.get("source_listing_id") or "")
    host = re.sub(r"^https://", "", url).split("/")[0].lower()
    return url.startswith("https://") and PORTAL_HOSTS.get(row.get("source"), host) in host and (not lid or lid in url)


def validation_analysis(val_results: dict[str, SourceResult], cfg: dict, fx: FxRate, http: PoliteClient | None,
                        geocode_ok: bool) -> list[tuple[str, list[str]]]:
    """Run the real normalise → de-duplicate → geocode → classify steps on the validation sample (no OSM
    layers, no QA, no deliverables) and describe the result per source and bedroom segment."""
    listings = [lst.model_copy(deep=True) for r in val_results.values() for lst in r.listings]
    if not listings:
        return [("Validation sample analysis", ["no records to analyse"])]
    df = pd.DataFrame([normalize_listing(lst, cfg, fx).model_dump() for lst in listings])
    df = deduplicate(df, cfg)
    geo_line = "Nominatim unreachable — no geocoding attempted"
    if geocode_ok and http is not None:
        done, errs = geocode_missing(df, cfg, http, K.GEO / "geocode_cache.json", max_queries=40)
        geo_line = f"Nominatim queries made: {done}" + (f"; errors: {errs}" if errs else "")
    df["_has_address"] = [address_evidence(r.get("address"), r.get("title"), r.get("description")) is not None
                          for r in df.to_dict("records")]
    scored = score_all(df, cfg)                                          # every record
    ranked = rank(scored, cfg["budget"]["strict_preference_margin"])      # one canonical record per property
    out: list[tuple[str, list[str]]] = []

    # ---- per source × bedroom segment
    rows, seen = [], set()
    for src, res in val_results.items():
        sub = scored[scored["source"] == src]
        segs = res.audit.get("segments") or [{"bedrooms": None, "runs": []}]
        if sub.empty and not res.errors:
            continue
        for seg in segs:
            label = f"{seg['bedrooms']}BR" if seg["bedrooms"] else "all"
            part = sub[sub["search_segment"] == label] if seg["bedrooms"] else sub
            recs = part.to_dict("records")
            n = len(recs)

            def pct(pred, recs=recs, n=n) -> str:
                return f"{100 * sum(1 for x in recs if pred(x)) / n:.0f}%" if n else "—"
            groups = set(part["duplicate_group_id"])
            new = groups - seen
            seen |= groups
            cost = sum(r["cost_usd"] for r in seg["runs"]) if seg["runs"] else res.cost_usd
            rows.append({
                "SOURCE": src, "BEDROOM SEGMENT": label, "RAW RECORDS": n,
                "VALID RENT %": pct(lambda x: _num(x.get("rent_usd")) is not None and 150 <= _num(x["rent_usd"]) <= 20000),
                "VALID BEDROOMS %": pct(lambda x: _num(x.get("bedrooms")) is not None and (
                    seg["bedrooms"] is None or int(_num(x["bedrooms"])) == seg["bedrooms"])),
                "VALID AREA %": pct(lambda x: any((_num(a) or 0) >= 12 and (_num(a) or 0) <= 400
                                                  for a in (x.get("built_area_m2"), x.get("total_area_m2")))),
                "MAINTENANCE %": pct(lambda x: _num(x.get("maintenance_fee")) is not None
                                     or x.get("maintenance_included_in_rent") is True),
                "SPECIFIC ADDRESS %": pct(lambda x: x["_has_address"]),
                "COORDINATES %": pct(lambda x: _num(x.get("latitude")) is not None),
                "USABLE URL %": pct(usable_url),
                "UNIQUE AFTER DEDUPE": len(new),
                "ACTUAL COST": f"USD {cost:.3f}",
                "ERRORS": "; ".join(res.errors)[:120] or "—",
            })
    out.append(("Validation sample — per source and bedroom segment", md_table(rows) + [
        "", "VALID BEDROOMS = bedroom count present and equal to the segment searched. UNIQUE AFTER DEDUPE = new "
        "properties this row adds (rows are counted in order, so a cross-post is credited to the first portal). "
        "ACTUAL COST = Apify run records of that segment's runs."]))

    # ---- coordinates
    canon = ranked

    def coord_counts(d: pd.DataFrame) -> str:
        return (f"listing-provided {int((d['coord_source'] == 'LISTING').sum())} · high-confidence geocode "
                f"{int((d['geocoding_confidence'] == 'HIGH').sum())} · medium-confidence (street-level) "
                f"{int((d['geocoding_confidence'] == 'MEDIUM').sum())} · unknown {int(d['latitude'].isna().sum())}")
    ev_lines = [f"{r['source']}:{r['source_listing_id']} → {r['address_evidence']} → "
                f"{r.get('geocoding_confidence') or 'no match'}"
                for r in scored.to_dict("records") if isinstance(r.get("address_evidence"), str)]
    out.append(("Validation sample — coordinates", [
        f"all {len(scored)} records: {coord_counts(scored)}", f"{len(canon)} unique properties: {coord_counts(canon)}",
        geo_line, "District/neighbourhood-only locations are never geocoded (coordinates stay UNKNOWN)."] + ev_lines))

    # ---- currency
    both = scored[scored["rent_usd_published"].notna() & scored["rent_pen_published"].notna()].copy()
    both["_abs"] = both["rent_usd_published_diff_pct"].abs()
    thr = cfg["fx"]["published_mismatch_flag_pct"]
    cur_lines = [f"Reference rate: 1 USD = S/ {fx.usd_pen:.3f} — {fx.source}",
                 f"records publishing both currencies: {len(both)}; CURRENCY_CONVERSION_MISMATCH (>{thr}%): "
                 f"{int((both['_abs'] > thr).sum())}"]
    for r in both.sort_values("_abs", ascending=False).to_dict("records"):
        cur_lines.append(f"{r['source']}:{r['source_listing_id']} ({r['rent_currency']}-priced): published S/ "
                         f"{r['rent_pen_published']:,.0f} · published USD {r['rent_usd_published']:,.0f} · normalised "
                         f"USD {r['rent_usd']:,.2f} · published vs S/÷rate {r['rent_usd_published_diff_pct']:+.1f}%"
                         + (" · CURRENCY_CONVERSION_MISMATCH" if r["_abs"] > thr else ""))
    out.append(("Validation sample — currency normalisation", cur_lines))

    # ---- de-duplication
    sizes = scored.groupby("duplicate_group_id").size()
    dup_lines = [f"raw records: {len(scored)} · duplicate groups (≥2 records): {int((sizes > 1).sum())} · "
                 f"unique properties: {len(sizes)}"]
    for gid in sizes[sizes > 1].index:
        g = scored[scored["duplicate_group_id"] == gid].to_dict("records")
        members = ", ".join(f"{r['source']}:{r['source_listing_id']}" for r in g)
        first = g[0]
        dup_lines.append(f"{gid}: {members} — {_num(first['bedrooms']) or 0:.0f}BR · {first.get('total_area_m2') or '?'} m² · "
                         f"USD {first['rent_usd']:,.0f} — evidence: {first['dedupe_evidence'] or '—'}")
    poss = ranked[ranked["possible_duplicate_of"].astype(str).str.len() > 0]
    dup_lines.append(f"possible duplicates kept separate (score close but no identity anchor): {len(poss)}")
    out.append(("Validation sample — de-duplication", dup_lines))

    # ---- hard-rule survivors (canonical records)
    def hard_ok(r: dict) -> bool:
        if r["category"] in ("PRIMARY", "STRETCH"):
            return True
        reasons = [x for x in str(r.get("exclusion_reason") or "").split("; ") if x]
        return r["category"] == "BORDERLINE" or (r["category"] == "EXCLUDED" and bool(reasons)
                                                  and all("above stretch ceiling" in x for x in reasons))
    crecs = canon.to_dict("records")
    ok = [r for r in crecs if hard_ok(r)]
    by_beds = {b: sum(1 for r in ok if _num(r.get("bedrooms")) == b) for b in (1, 2)}
    cats = canon["category"].value_counts().to_dict()
    reasons = canon[canon["category"] == "EXCLUDED"]["exclusion_reason"].str.split("; ").explode().value_counts()
    out.append(("Validation sample — Miraflores + rent + apartment + 1–2 bedroom rules", [
        f"unique properties passing the hard rules: {len(ok)} of {len(crecs)} (1BR {by_beds[1]}, 2BR {by_beds[2]})",
        f"categories (unique): " + ", ".join(f"{k} {v}" for k, v in cats.items()),
        "exclusion reasons: " + ("; ".join(f"{k} ({v})" for k, v in reasons.items()) or "none")]))
    return out


def md_table(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |" for r in rows]
    return out


def validation_ok(res: SourceResult) -> bool:
    """Proceed to full extraction only if the sample is usable."""
    ls = res.listings
    if len(ls) < 5:
        return False
    ok = lambda pred: sum(1 for x in ls if pred(x)) / len(ls)   # noqa: E731
    return (ok(lambda x: bool(x.source_url)) >= 0.9 and ok(lambda x: bool(x.rent_original and x.rent_currency)) >= 0.8
            and ok(lambda x: x.bedrooms is not None) >= 0.7)


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def completeness_text(cov: dict[str, float]) -> str:
    return ", ".join(f"{k} {_pct(v)}" for k, v in cov.items())


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def collect(name: str, cfg: dict, http: PoliteClient, budget: CostBudget, mode: str, auth,
            max_items: int | None = None) -> SourceResult:
    scfg = cfg["sources"][name]
    if name in ("urbania", "adondevivir"):
        return collect_navent(name, scfg, cfg, http, budget, mode, auth, max_items)
    if name == "mercadolibre":
        return collect_mercadolibre(scfg, cfg, http, mode)
    if name == "manual":
        return collect_manual(K.ROOT / scfg["directory"])
    raise ValueError(name)


# --------------------------------------------------------------------------- gates
def gate0_preflight(cfg: dict, log: RunLog) -> dict[str, tuple[bool, str]]:
    """One HEAD request per host. PASS = the network path works (any HTTP status, including a site's own
    bot-protection 403); FAIL = the connection itself was refused (e.g. egress policy) or timed out."""
    probes = {host: probe(url) for host, url in PROBES.items()}
    lines = [f"{'PASS' if ok else 'FAIL'}  {host} — {msg}" for host, (ok, msg) in probes.items()]
    log.section("Gate 0 — network preflight (one small request per host)", lines)
    return probes


def build_audit_rows(results: dict[str, SourceResult], cov: dict[str, dict], statuses: dict[str, str]) -> list[dict]:
    rows = []
    for name, reg in REGISTRY.items():
        res = results.get(name)
        c = cov.get(name) if res and res.listings else None
        errors = "; ".join((res.errors + res.notes) if res else ["not run"])
        rows.append({
            "Source": reg["source_name"], "Status": statuses.get(name, "NOT RUN"),
            "Method": res.method if res else reg["extraction_method"],
            "Target search URL": reg["target_search_url"],
            "Records collected": len(res.listings) if res else 0,
            "Public access": reg["public_access"], "Pagination": reg["pagination"],
            "Detail pages": reg["detail_pages"], "Contact data": reg["contact_data"],
            "Coordinates": reg["coordinates"] + (f" · observed {_pct(c['coordinates'])}" if c else ""),
            "Publication date": reg["publication_date"] + (f" · observed {_pct(c['publication date'])}" if c else ""),
            "Maintenance fee": reg["maintenance_fee"] + (f" · observed {_pct(c['maintenance'])}" if c else ""),
            "Completeness": completeness_text(c) if c and res and res.listings else "not measured (no records)",
            "Limitations / errors": (errors + " | " if errors else "") + reg["limitations"],
        })
    for cand in CANDIDATES:
        rows.append({"Source": cand["source_name"], "Status": "PENDING (not automated this iteration)",
                     "Method": "not automated — use manual import", "Target search URL": cand["source_url"],
                     "Records collected": 0, "Public access": "public (search index)", "Pagination": "not tested",
                     "Detail pages": "not tested", "Contact data": "not tested", "Coordinates": "not tested",
                     "Publication date": "not tested", "Maintenance fee": "not tested", "Completeness": "not measured",
                     "Limitations / errors": cand["note"] + " | could not be opened from this environment "
                                                             "(egress policy); verify before relying on it"})
    return rows


def write_source_audit_md(rows: list[dict], probes: dict | None, stamp: str) -> None:
    lines = ["# SOURCE_AUDIT", "",
             f"Research date: {RESEARCH_DATE}. Last automated update: {stamp}.", "",
             "Status meanings: **APPROVED** = validation run returned records with ≥90% core-field coverage "
             "(URL, rent, currency, bedrooms) and ≥60% area coverage · **PARTIAL** = records returned but weaker "
             "coverage or errors · **REJECTED** = source answered but could not be used (e.g. bot challenge — "
             "never bypassed) · **PENDING** = not yet testable (environment egress blocked or not automated).", ""]
    if probes:
        lines += ["## Reachability from the run environment", "", "| Host | Result |", "|---|---|"]
        lines += [f"| {h} | {'reachable' if ok else 'UNREACHABLE'} — {m} |" for h, (ok, m) in probes.items()]
        lines.append("")
    for r in rows:
        lines += [f"## {r['Source']} — {r['Status']}", ""]
        for key in ("Method", "Target search URL", "Records collected", "Public access", "Pagination", "Detail pages",
                    "Contact data", "Coordinates", "Publication date", "Maintenance fee", "Completeness",
                    "Limitations / errors"):
            lines.append(f"- **{key}:** {r[key]}")
        lines.append("")
    lines.append(REFERENCE_REPO_AUDIT)
    (K.ROOT / "SOURCE_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")


def methodology_rows(cfg: dict, fx: FxRate, meta: dict) -> list[tuple[str, str]]:
    """Methodology sheet rows in the active language (i18n.L). Same facts in English and Hindi."""
    s = cfg["scoring"]
    nm = cfg["noise_model"]
    bl = cfg["budget"]["borderline_max_over_pct"]
    fxp = cfg["fx"]["published_mismatch_flag_pct"]
    return [
        (L("Objective", "उद्देश्य"),
         L("Find the strongest currently advertised 1–2 bedroom rentals inside Miraflores (Lima) for a couple, at or "
           "below USD 1,000/month, prioritising quiet and usable space.",
           "Miraflores (Lima) में एक दंपति के लिए अभी विज्ञापित सबसे उपयुक्त 1–2 बेडरूम किराये के अपार्टमेंट खोजना — मासिक "
           "किराया USD 1,000 या उससे कम, शांत वातावरण और उपयोगी जगह को प्राथमिकता।")),
        (L("Hard requirements", "अनिवार्य शर्तें"),
         L("Miraflores only · rent (not sale) · apartment · 1–2 bedrooms (studios excluded unless the listing classifies "
           "the unit as 1 bedroom) · base rent ≤ USD 1,000. A high score never overrides a hard requirement.",
           "केवल Miraflores · किराया (बिक्री नहीं) · अपार्टमेंट · 1–2 बेडरूम (स्टूडियो शामिल नहीं, जब तक विज्ञापन उसे 1 बेडरूम "
           "न बताए) · मूल किराया ≤ USD 1,000। ऊँचा स्कोर कभी भी किसी अनिवार्य शर्त से ऊपर नहीं होता।")),
        (L("Budget classes", "बजट श्रेणियाँ"),
         L(f"STRICT_ALL_IN = rent + known maintenance ≤ USD 1,000 · BASE_RENT_COMPLIANT = rent ≤ USD 1,000 but the total "
           f"is above USD 1,000 or unknown · STRETCH = rent USD 1,001–1,100 (separate sheet) · BORDERLINE = at most {bl:g}% "
           f"above USD 1,100 after currency conversion (NEAR_MISSES sheet; never budget-compliant). STRICT_ALL_IN gets a "
           f"{cfg['budget']['strict_preference_margin']}-point ranking preference.",
           f"STRICT_ALL_IN = किराया + ज्ञात रखरखाव शुल्क ≤ USD 1,000 · BASE_RENT_COMPLIANT = किराया ≤ USD 1,000, पर कुल खर्च "
           f"USD 1,000 से अधिक या अज्ञात · STRETCH = किराया USD 1,001–1,100 (अलग शीट) · BORDERLINE = मुद्रा-रूपांतरण के बाद "
           f"USD 1,100 से अधिकतम {bl:g}% ऊपर (लगभग उपयुक्त शीट; कभी बजट के भीतर नहीं)। STRICT_ALL_IN को रैंकिंग में "
           f"{cfg['budget']['strict_preference_margin']} अंकों की प्राथमिकता मिलती है।")),
        (L("Near misses", "लगभग उपयुक्त"),
         L(f"Outside Miraflores → NEAR_MISSES only if within {cfg['near_misses']['max_distance_outside_m']} m of the "
           f"boundary, budget-compliant and fit ≥ {cfg['near_misses']['min_fit_score']}.",
           f"Miraflores के बाहर → लगभग उपयुक्त शीट में केवल तभी, जब सीमा से {cfg['near_misses']['max_distance_outside_m']} "
           f"मीटर के भीतर हो, बजट में हो और उपयुक्तता स्कोर ≥ {cfg['near_misses']['min_fit_score']} हो।")),
        (L("Run", "यह खोज"),
         L(f"Generated {meta['generated_at']}. Records collected: {meta['n_raw']}; unique after de-duplication: "
           f"{meta['n_unique']}; budget-compliant: {meta['n_primary']}; stretch: {meta['n_stretch']}; borderline: "
           f"{meta.get('n_borderline', 0)}; near misses: {meta['n_near']}. Cumulative project cost (Apify run records): "
           f"USD {meta['cost']:.2f} of the USD 5.00 cap.",
           f"तैयार: {meta['generated_at']}। एकत्रित रिकॉर्ड: {meta['n_raw']}; दोहराव हटाने के बाद अद्वितीय: {meta['n_unique']}; "
           f"बजट के भीतर: {meta['n_primary']}; स्ट्रेच: {meta['n_stretch']}; सीमा-रेखा: {meta.get('n_borderline', 0)}; "
           f"लगभग उपयुक्त: {meta['n_near']}। परियोजना की कुल लागत (Apify रन रिकॉर्ड): USD 5.00 की सीमा में से "
           f"USD {meta['cost']:.2f}।")),
        (L("Sources", "स्रोत"),
         L("Urbania and Adondevivir via Apify (free plan: at most 10 records per run, list-level data only — no detail "
           "pages, so no coordinates, phone numbers or publication dates). One run per bedroom count so neither segment "
           "crowds out the other. Mercado Libre: polite direct requests only; any bot challenge stops it (never bypassed).",
           "Urbania और Adondevivir, Apify के माध्यम से (निःशुल्क प्लान: प्रति रन अधिकतम 10 रिकॉर्ड, केवल सूची-स्तर की "
           "जानकारी — विवरण पेज नहीं, इसलिए निर्देशांक, फ़ोन नंबर या प्रकाशन तिथि नहीं)। बेडरूम की हर संख्या के लिए अलग रन, "
           "ताकि कोई एक श्रेणी दूसरी की जगह न ले। Mercado Libre: केवल सामान्य सीधे अनुरोध; कोई भी बॉट-जाँच आने पर रुक जाता है "
           "(कभी दरकिनार नहीं)।")),
        (L("Exchange rate", "विनिमय दर"),
         L(f"1 USD = S/ {fx.usd_pen:.3f} · {fx.source} · {fx.timestamp}. One rate for every conversion. Budget, ranking, "
           f"USD/m² and totals use one comparable USD value: the USD price for USD-priced listings, otherwise PEN ÷ this "
           f"rate (CALCULATED). The portal's own USD figure is kept separately; a gap above {fxp}% is flagged "
           f"CURRENCY_CONVERSION_MISMATCH.",
           f"1 USD = S/ {fx.usd_pen:.3f} · {fx.source} · {fx.timestamp}। हर रूपांतरण के लिए एक ही दर। बजट, रैंकिंग, USD/m² "
           f"और कुल खर्च के लिए एक तुलनीय USD मान: USD में दिए किराये के लिए वही USD, अन्यथा PEN ÷ यह दर (CALCULATED)। "
           f"पोर्टल का अपना USD आँकड़ा अलग रखा गया है; {fxp}% से अधिक अंतर पर CURRENCY_CONVERSION_MISMATCH चिह्न।")),
        (L("Fit score (100)", "उपयुक्तता स्कोर (100)"),
         L(f"Quietness {s['quietness']} · Budget/total cost {s['budget']} · Space/layout {s['space']} · Location/daily "
           f"livability {s['location']} · Furnishing {s['furnishing']} · Building/security/amenities {s['building']} · "
           f"Listing quality/freshness {s['listing_quality']}.",
           f"शांत वातावरण {s['quietness']} · बजट/कुल खर्च {s['budget']} · जगह/बनावट {s['space']} · स्थान/दैनिक सुविधा "
           f"{s['location']} · फ़र्नीचर {s['furnishing']} · भवन/सुरक्षा/सुविधाएँ {s['building']} · विज्ञापन की गुणवत्ता "
           f"{s['listing_quality']}।")),
        (L("Noise categories", "शोर की श्रेणियाँ"),
         L("LIKELY QUIET = low risk with medium/high confidence · POSSIBLY QUIET = positive listing wording only (e.g. "
           "interior-facing) · NOISE UNCERTAIN = no or mixed evidence · LIKELY NOISY = on a major arterial (e.g. Av. Paseo "
           "de la República / Vía Expresa), faces an avenue, or high risk with a reliable location. Risk LOW/MEDIUM/HIGH/"
           "UNKNOWN always comes with a confidence HIGH/MEDIUM/LOW; UNKNOWN = no location and no noise wording. "
           "Low-confidence evidence never pushes an otherwise good apartment down the ranking.",
           "संभवतः शांत = कम जोखिम, मध्यम/उच्च विश्वसनीयता · शायद शांत = केवल विज्ञापन में सकारात्मक उल्लेख (जैसे भीतर की ओर) "
           "· शोर अनिश्चित = प्रमाण नहीं या मिश्रित · संभवतः शोरगुल वाला = मुख्य सड़क पर (जैसे Av. Paseo de la República / "
           "Vía Expresa), एवेन्यू की ओर, या भरोसेमंद स्थान के साथ अधिक जोखिम। जोखिम (कम/मध्यम/अधिक/अज्ञात) के साथ हमेशा "
           "विश्वसनीयता (उच्च/मध्यम/कम) दी गई है; अज्ञात = न स्थान, न शोर का कोई उल्लेख। कम विश्वसनीयता वाला प्रमाण किसी अच्छे "
           "अपार्टमेंट को रैंकिंग में नीचे नहीं धकेलता।")),
        (L("Noise model", "शोर का आकलन"),
         L(f"With a reliable position: baseline {nm['baseline']}, penalties for major roads (≤{nm['major_road']['strong_m']} m "
           f"−{nm['major_road']['strong_penalty']}), arterials, nightclubs and bar clusters (OpenStreetMap), plus listing "
           "text (interior-facing, acoustic windows, avenue view, high floor). Without a position: listing text only, "
           "shrunk towards neutral, confidence LOW. It is an estimate — confirm in person.",
           f"भरोसेमंद स्थान होने पर: आधार {nm['baseline']}, मुख्य सड़कों (≤{nm['major_road']['strong_m']} मीटर "
           f"−{nm['major_road']['strong_penalty']}), आर्टेरियल सड़कों, नाइटक्लब और बार के समूह (OpenStreetMap) के लिए अंक "
           "घटाए जाते हैं, साथ में विज्ञापन का विवरण (भीतर की ओर, ध्वनिरोधी खिड़कियाँ, एवेन्यू की ओर, ऊँची मंज़िल)। स्थान न होने "
           "पर: केवल विज्ञापन का विवरण, तटस्थ की ओर समायोजित, विश्वसनीयता कम। यह एक अनुमान है — स्वयं पुष्टि करें।")),
        (L("Coordinates", "निर्देशांक"),
         L("Geocoded (OpenStreetMap Nominatim) only from specific address text in the listing: street + number → HIGH "
           "confidence when the house number matches, otherwise street-level MEDIUM; street + block → MEDIUM. District or "
           "zone names alone are never geocoded — those listings keep an UNKNOWN location. Only HIGH / exact positions "
           "are drawn on the report map.",
           "स्थान (OpenStreetMap Nominatim) केवल विज्ञापन में लिखे स्पष्ट पते से निकाला गया: सड़क + नंबर → मकान नंबर मिलने पर "
           "उच्च विश्वसनीयता, अन्यथा सड़क-स्तर मध्यम; सड़क + ब्लॉक → मध्यम। केवल ज़िले या क्षेत्र के नाम से कभी स्थान नहीं "
           "निकाला गया — ऐसे अपार्टमेंट का स्थान अज्ञात रखा गया। रिपोर्ट के नक्शे पर केवल उच्च/सटीक स्थान दिखाए गए।")),
        (L("Foreign-tenant friendliness", "विदेशी किरायेदार के लिए अनुकूलता"),
         L("From listing text only: HIGH (foreigners/passport/corporate lease explicitly welcome), MEDIUM (temporary "
           "stays, no guarantor, English listing, furnished + utilities), POTENTIAL_FRICTION (asks for a Peruvian "
           "guarantor, carné de extranjería or DNI), UNKNOWN (silent — the normal case, never penalised). Where silent, "
           "confirm passport acceptance, carné de extranjería, proof of income, guarantor (aval), deposit and minimum term.",
           "केवल विज्ञापन के विवरण से: HIGH = विदेशियों/पासपोर्ट/कंपनी-अनुबंध का स्पष्ट स्वागत; MEDIUM = अस्थायी अवधि, गारंटर "
           "नहीं, अंग्रेज़ी विज्ञापन, सुसज्जित + सेवाएँ शामिल; POTENTIAL_FRICTION = पेरू के गारंटर, carné de extranjería या DNI "
           "की माँग; UNKNOWN = कोई उल्लेख नहीं — सामान्य स्थिति, कोई नकारात्मक अंक नहीं। उल्लेख न होने पर पासपोर्ट की "
           "स्वीकार्यता, carné de extranjería, आय का प्रमाण, गारंटर (aval), जमा राशि और न्यूनतम अवधि की पुष्टि करें।")),
        (L("Availability", "उपलब्धता"),
         L("ACTIVE_CONFIRMED = listing re-opened successfully during the final Top-10 re-check · LIKELY_ACTIVE = returned "
           "by the live search, automated re-check not possible (portal bot protection) · UNKNOWN = not confirmed. Never "
           "stated as guaranteed.",
           "ACTIVE_CONFIRMED = अंतिम शीर्ष-10 पुनः-जाँच में विज्ञापन सफलतापूर्वक दोबारा खुला · LIKELY_ACTIVE = लाइव खोज में "
           "मिला, स्वचालित पुनः-जाँच संभव नहीं (पोर्टल की बॉट-सुरक्षा) · UNKNOWN = पुष्टि नहीं। कभी गारंटी नहीं दी गई।")),
        (L("De-duplication", "दोहराव हटाना"),
         L("Pairs scored on URL, portal id, coordinates, area, price, bathrooms, maintenance, advertiser, fuzzy title and "
           "description, address and shared photo ids. A merge also needs an identity anchor (same URL or posting id, the "
           "same photo file, coordinates within a few metres or the same numbered address): matching price, area and "
           "maintenance alone never merge two listings. Every source link is kept.",
           "जोड़ियों की तुलना URL, पोर्टल ID, निर्देशांक, क्षेत्रफल, किराया, बाथरूम, रखरखाव शुल्क, विज्ञापनदाता, शीर्षक व विवरण की "
           "समानता, पते और साझा फ़ोटो ID से की गई। जोड़ने के लिए पहचान का ठोस आधार भी चाहिए (एक ही URL या पोस्टिंग ID, एक ही "
           "फ़ोटो फ़ाइल, कुछ मीटर के भीतर निर्देशांक या एक ही नंबर वाला पता): केवल किराया, क्षेत्रफल और रखरखाव शुल्क का मेल कभी "
           "दो विज्ञापनों को नहीं जोड़ता। हर स्रोत का लिंक रखा गया है।")),
        (L("Codes used", "प्रयुक्त कोड"),
         L("Classification codes are kept identical in the English and Hindi files: STRICT_ALL_IN, BASE_RENT_COMPLIANT, "
           "STRETCH, BORDERLINE (budget) · ACTIVE_CONFIRMED, LIKELY_ACTIVE, UNKNOWN (availability) · HIGH, MEDIUM, "
           "POTENTIAL_FRICTION, UNKNOWN (foreign tenant) · PUBLISHED / CALCULATED (value published by the listing or "
           "converted) · red-flag codes such as UNKNOWN_MAINTENANCE (maintenance not published), NO_COORDINATES (no map "
           "position), ON_MAJOR_ARTERIAL (address on a major arterial).",
           "हर श्रेणी का हिंदी नाम दिया गया है और अंग्रेज़ी फ़ाइल से मिलान के लिए मूल कोड कोष्ठक में रखा गया है — बजट: "
           "STRICT_ALL_IN, BASE_RENT_COMPLIANT, STRETCH, BORDERLINE; उपलब्धता: ACTIVE_CONFIRMED, LIKELY_ACTIVE, UNKNOWN; "
           "विदेशी किरायेदार: HIGH, MEDIUM, POTENTIAL_FRICTION; मान का स्रोत: PUBLISHED, CALCULATED; चेतावनी संकेत, जैसे "
           "UNKNOWN_MAINTENANCE, NO_COORDINATES, ON_MAJOR_ARTERIAL।")),
        (L("Unknown values", "अज्ञात मान"),
         L("Shown as UNKNOWN (Hindi: जानकारी उपलब्ध नहीं). Nothing is imputed; no phone number, WhatsApp or date is ever "
           "invented. The listing link is the contact path when no phone is published.",
           "जानकारी उपलब्ध न होने पर यही लिखा गया है। कुछ भी अनुमान से नहीं भरा गया; कोई फ़ोन नंबर, WhatsApp या तिथि कभी गढ़ी "
           "नहीं गई। फ़ोन न होने पर विज्ञापन का लिंक ही संपर्क का माध्यम है।")),
        (L("Limitations", "सीमाएँ"),
         L("Advertiser-reported data; the free Apify plan returns list-level data only; most locations are known only to "
           "the zone; OpenStreetMap may miss venues; availability changes daily. Scores rank options — they do not replace "
           "a visit.",
           "जानकारी विज्ञापनदाताओं द्वारा दी गई है; Apify का निःशुल्क प्लान केवल सूची-स्तर की जानकारी देता है; अधिकांश स्थान "
           "केवल क्षेत्र तक ज्ञात हैं; OpenStreetMap में कुछ स्थान छूट सकते हैं; उपलब्धता रोज़ बदलती है। स्कोर केवल विकल्पों को "
           "क्रम देते हैं — ये स्वयं जाकर देखने का विकल्प नहीं हैं।")),
    ]


def enrich_geo(df: pd.DataFrame, layers: OsmLayers | None, cfg: dict) -> pd.DataFrame:
    if layers is None:
        return df
    feats = []
    for _, r in df.iterrows():
        lat, lon = r.get("latitude"), r.get("longitude")
        if _isnull(lat) or _isnull(lon):
            feats.append({})
        else:
            feats.append(geo_features(layers, float(lat), float(lon), cfg))
    geo = pd.DataFrame(feats, index=df.index)
    return pd.concat([df.drop(columns=[c for c in geo.columns if c in df.columns]), geo], axis=1)


# --------------------------------------------------------------------------- main flow
def process(listings: list[Listing], cfg: dict, fx: FxRate, http: PoliteClient | None, layers: OsmLayers | None,
            log: RunLog, live_qa: bool, geocode: bool, persist: bool = True, auth: ApifyAuth | None = None,
            budget: CostBudget | None = None) -> pd.DataFrame:
    norm = [normalize_listing(lst, cfg, fx) for lst in listings]
    df = pd.DataFrame([n.model_dump() for n in norm])
    if df.empty:
        return df
    if persist:   # demo mode never touches data/ (synthetic rows must not mix with real ones)
        K.NORMALIZED.mkdir(parents=True, exist_ok=True)
        df.to_csv(K.NORMALIZED / "listings_normalized.csv", index=False)

    df = deduplicate(df, cfg)
    n_groups = df["duplicate_group_id"].nunique()
    multi = (df.groupby("duplicate_group_id").size() > 1).sum()
    log.section("Gate 5 — normalise & de-duplicate", [
        f"records normalised: {len(df)}", f"unique listings (groups): {n_groups}",
        f"groups with ≥2 records (cross-posted/duplicated): {multi}",
        f"duplicate records folded: {len(df) - n_groups}",
        f"groups with conflicting data: {(df['dup_inconsistencies'].astype(str).str.len() > 0).sum()}"])

    geo_lines = []
    if geocode and http is not None:
        done, errs = geocode_missing(df, cfg, http, K.GEO / "geocode_cache.json")
        geo_lines.append(f"geocoded {done} addresses via Nominatim" + (f"; errors: {errs}" if errs else ""))
    df = enrich_geo(df, layers, cfg)
    geo_lines.append(f"OSM layers: {layers.provenance if layers else 'UNAVAILABLE — noise estimated from text only'}")
    if layers:
        geo_lines.append(f"major-road segments {len(layers.major_roads.geoms)}, arterials {len(layers.arterial_roads.geoms)}, "
                         f"nightclubs {len(layers.nightclubs.geoms)}, bars {len(layers.bars.geoms)}, "
                         f"supermarkets {len(layers.supermarkets.geoms)}, parks {len(layers.parks.geoms)}, "
                         f"district boundary {'found' if layers.boundary is not None else 'NOT found'}")
    geo_lines.append(f"records with coordinates: {df['latitude'].notna().sum()} / {len(df)}")
    log.section("Gate 6 — geospatial / noise enrichment", geo_lines)

    qa_cols = ["qa_status", "qa_notes", "qa_checked_at", "active_status", "active_evidence"]
    for col in qa_cols[:3]:
        df[col] = None
    ranked = rank(score_all(df, cfg), cfg["budget"]["strict_preference_margin"])
    counts = ranked["category"].value_counts().to_dict()
    log.section("Gate 7 — score & rank", [f"{k}: {v}" for k, v in counts.items()] + [
        "top exclusion reasons: " + "; ".join(f"{k} ({v})" for k, v in
                                               ranked[ranked['category'] == 'EXCLUDED']['exclusion_reason']
                                               .str.split('; ').explode().value_counts().head(6).items())])

    # QA can demote a Top-10 listing (e.g. found inactive); re-score and re-check until the Top 10 is stable
    manual_qa = K.PROCESSED / "manual_qa.csv"
    rechecker = LiveRechecker(http, auth, cfg, budget or CostBudget(0), fx) if (live_qa and http is not None) else None
    copy_cols = qa_cols + [c for c in RECHECK_FIELDS if c in df.columns]
    for _ in range(4):
        before = list(ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category").head(10).index)
        ranked = run_qa(ranked, cfg, http, manual_qa, live=live_qa and http is not None, rechecker=rechecker)
        df.loc[ranked.index, copy_cols] = ranked[copy_cols]
        ranked = rank(score_all(df, cfg), cfg["budget"]["strict_preference_margin"])
        after = list(ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category").head(10).index)
        if after == before:
            break
    qa_counts = ranked["qa_status"].value_counts(dropna=True).to_dict()
    log.section("Gate 8 — QA", [f"{k}: {v}" for k, v in qa_counts.items()] or ["no records reached QA"])
    return ranked


def deliver(ranked: pd.DataFrame, cfg: dict, fx: FxRate, meta: dict, audit_rows: list[dict],
            layers: OsmLayers | None, out_dir: Path, banner: str | None, prefix: str = "",
            http: PoliteClient | None = None) -> dict[str, tuple[Path, Path, Path]]:
    """English master deliverables, then the Hindi copies of the *same* final data.

    The Hindi workbook is translated cell by cell from the finished English workbook; the Hindi PDF and
    contact templates render the same ranked records (no re-scoring, no re-ranking)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    geo = {"boundary_ll": layers.boundary_ll, "road_lines_ll": layers.road_lines_ll} if layers else None
    top = ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category").head(meta["top_n"])
    MISSING.clear()
    paths: dict[str, tuple[Path, Path, Path]] = {}
    for lang in ("en", "hi"):
        sfx = f"_{lang.upper()}"
        xlsx = out_dir / f"{prefix}Miraflores_Rental_Shortlist{sfx}.xlsx"
        html_path = out_dir / f"{prefix}Miraflores_Rental_Executive_Report{sfx}.html"
        pdf = out_dir / f"{prefix}Miraflores_Rental_Executive_Report{sfx}.pdf"
        txt = out_dir / f"{prefix}Contact_Templates{sfx}.txt"
        with language(lang):
            meth = methodology_rows(cfg, fx, meta)
            contacts = [{"_label": C.property_label(r), "_contact": " · ".join(t_(p, record=False) for p in C.contact_text(r).split(" · ")), **r} for r in C.records(top)]
        if lang == "en":
            build_workbook(xlsx, ranked, meta, audit_rows, meth, banner)
        else:
            translate_workbook(paths["en"][0], xlsx, meth)
        html_path.write_text(build_report_html(ranked, meta, audit_rows, geo, banner, lang=lang), encoding="utf-8")
        html_to_pdf(html_path, pdf, banner, lang=lang)
        write_contact_templates(txt, contacts, lang=lang)
        paths[lang] = (xlsx, pdf, txt)
    return paths


def fetch_thumbnails(top: pd.DataFrame, http: PoliteClient) -> dict[str, str]:
    """Small data-URI thumbnails for the page-1 Top 5. Any failure → no image (never a broken icon)."""
    import base64
    out = {}
    for r in C.records(top):
        url = r.get("main_image_url")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        try:
            resp = http.request_json("GET", url, timeout=15)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ctype.startswith("image/") and len(resp.content) < 2_500_000:
                out[str(r.get("source_url"))] = f"data:{ctype.split(';')[0]};base64," + \
                    base64.b64encode(resp.content).decode()
        except Exception:  # noqa: BLE001
            continue
    return out


def make_meta(cfg: dict, fx: FxRate, n_raw: int, ranked: pd.DataFrame, cost: float) -> dict:
    canon = ranked if ranked.empty else ranked[ranked["is_canonical"]]
    cat = canon["category"].value_counts().to_dict() if not canon.empty else {}
    short = "BCRP live" if fx.live else "fallback"
    return {"generated_at": now_iso(), "fx_rate": fx.usd_pen, "fx_source": f"{fx.source} ({fx.timestamp})",
            "fx_source_short": short, "n_raw": n_raw, "n_unique": len(canon), "n_primary": cat.get("PRIMARY", 0),
            "n_stretch": cat.get("STRETCH", 0), "n_near": cat.get("NEAR_MISS", 0), "cost": cost,
            "n_borderline": cat.get("BORDERLINE", 0), "fx_flag_pct": cfg["fx"]["published_mismatch_flag_pct"],
            "top_n": cfg["shortlist"]["top_n"], "alternatives_max": cfg["shortlist"]["alternatives_max"],
            "budget": cfg["budget"]["target_max_rent"]}


def empty_ranked() -> pd.DataFrame:
    cols = list(Listing.model_fields) + ["category", "rank_in_category", "is_canonical", "fit_score",
                                         "duplicate_group_id", "rent_usd_per_m2", "area_m2", "value_band",
                                         "quietness_score_0_100", "noise_risk", "noise_confidence", "pts_space",
                                         "qa_status", "estimated_total_text", "main_drawback", "maintenance_usd"]
    return pd.DataFrame(columns=cols)


def allocate_full_items(cfg: dict, val_results: dict[str, SourceResult], budget: CostBudget,
                        apify_sources: list[str]) -> dict[str, tuple[int, str]]:
    """Records per bedroom segment for each paid full run, sized from the *actual* validation cost per
    record (start events included) within the remaining project budget. Every run is still checked
    against its own worst case before launch."""
    alloc: dict[str, tuple[int, str]] = {}
    cc = cfg["cost_control"]
    pool = budget.remaining * cc["full_budget_share"]
    nseg = {n: len(cfg["sources"][n]["segments"]) for n in apify_sources}
    weights = {n: cfg["sources"][n]["full_max_items_per_segment"] * nseg[n] for n in apify_sources}
    total_w = sum(weights.values()) or 1
    for n in apify_sources:
        r = val_results[n]
        cap = cfg["sources"][n]["full_max_items_per_segment"]
        cpi = (r.cost_usd / len(r.raw_records)) if r.raw_records and r.cost_usd else None
        basis = "observed"
        if cpi is None:
            cpi, basis = cc["unknown_pricing_run_usd"] / max(1, cc["validation_items_per_segment"]), "assumed"
        share = pool * weights[n] / total_w
        items = max(0, min(cap, int(share / cpi / nseg[n])))
        alloc[n] = (items, f"≈USD {cpi:.4f}/record {basis} → {items} records per bedroom segment within USD {share:.2f}")
    return alloc


def init_budget(cfg: dict, http: PoliteClient, auth: ApifyAuth, log: RunLog) -> CostBudget:
    """Project-wide budget: the cap minus the *actual* spend of every earlier run of the project's actors
    (Apify run records), bounded again by the Apify account's own remaining monthly allowance. If that
    history cannot be read, the budget is set to zero so no paid call can start."""
    cc = cfg["cost_control"]
    cap = float(cc["max_external_usd"])
    paid = [n for n, sc in cfg["sources"].items() if sc.get("enabled") and sc.get("method") == "apify"]
    if not paid or not auth.available:
        return CostBudget(cap)
    try:
        client = ApifyClient(auth, http)
        ids = {client.actor_info(cfg["sources"][n]["actor_id"])["id"] for n in paid}
        prior, lines = client.project_spend(ids, cc["project_start_utc"])
        headroom, acct = client.account_headroom_usd()
    except (ApifyError, NetworkBlocked) as exc:
        log.section("Apify spend ledger — PAID CALLS BLOCKED", [
            f"Project spend could not be verified from Apify's run records: {exc}",
            "An unknown spend is never assumed to be zero, so no paid Actor run will start in this run."])
        return CostBudget(cap, prior_spent=cap)
    budget = CostBudget(cap, prior, headroom)
    log.section("Apify spend ledger — before this run", lines + [
        f"Project spend so far: USD {prior:.3f} of the USD {cap:.2f} project cap (source: Apify run records of "
        f"{', '.join(cfg['sources'][n]['actor_id'] for n in paid)} since {cc['project_start_utc']}; each run priced as "
        "chargedEventCounts × eventPriceUsd, or usageTotalUsd if higher)",
        acct,
        f"Usable now: USD {budget.remaining:.3f} (the stricter of the project cap and the account allowance)"])
    return budget


def reconcile_spend(budget: CostBudget, http: PoliteClient, auth: ApifyAuth) -> list[str]:
    """Re-read every paid run of this pipeline run from Apify and raise any ledger entry whose record has
    since settled higher (Apify books event charges asynchronously). Figures are never lowered."""
    entries = [e for e in budget.ledger if e.get("run_id")]
    if not entries:
        return []
    from .sources.apify_client import charged_from_record
    lines = []
    try:
        client = ApifyClient(auth, http)
        for e in entries:
            rec = client.run_record(e["run_id"])
            computed, detail = charged_from_record(rec)
            figures = [x for x in (computed, rec.get("usageTotalUsd")) if x is not None]
            settled = max(float(x) for x in figures) if figures else e["usd"]
            delta = budget.adjust(e, settled, f"RECONCILED with Apify run record {e['run_id']}: {detail}; "
                                              f"usageTotalUsd={rec.get('usageTotalUsd')}")
            if delta:
                lines.append(f"{e['label']}: raised by USD {delta:.3f} to the settled Apify figure USD {e['usd']:.3f}")
    except (ApifyError, NetworkBlocked) as exc:
        lines.append(f"reconciliation could not re-read run records ({exc}); logged figures are the pre-settlement "
                     "floors, and the next run's ledger re-reads Apify")
    return lines or ["all logged run costs match Apify's run records"]


def spend_lines(budget: CostBudget) -> list[str]:
    return budget.ledger_lines() + [
        f"This run: USD {budget.run_spent:.3f} · project cumulative: USD {budget.spent:.3f} of USD "
        f"{budget.max_usd:.2f} · remaining: USD {budget.remaining:.3f}"]


def run(mode: str, out: Path | None = None) -> int:
    K.load_dotenv()
    K.ensure_dirs()
    cfg = K.load_config()
    log = RunLog(K.ROOT / "RUN_LOG.md", mode)
    if mode == "demo":
        return run_demo(cfg, log, out)
    cfg["_production"] = True          # integrity guard on: demo/synthetic records are rejected

    probes = gate0_preflight(cfg, log)
    http = PoliteClient(cfg["http"]["user_agent"], cfg["http"]["timeout_s"], cfg["http"]["min_delay_s"])
    auth = resolve_apify_auth(http)
    log.section("Apify authentication", auth.display())
    token = K.apify_token()
    if mode == "preflight":
        log.write()
        return 0

    budget = init_budget(cfg, http, auth, log) if mode in ("validate", "full") else CostBudget(0.0)
    fx, fx_err = fetch_fx(cfg, http)
    log.section("Exchange rate", [f"1 USD = S/ {fx.usd_pen:.3f} — {fx.source} — {fx.timestamp}"]
                + ([f"live fetch failed ({fx_err}); documented fallback used"] if fx_err else []))

    if mode == "report":
        ranked = pd.read_pickle(K.PROCESSED / "ranked.pkl")
        ranked = run_qa(ranked, cfg, http, K.PROCESSED / "manual_qa.csv", live=False)
        audit_rows = json.loads((K.PROCESSED / "audit_rows.json").read_text(encoding="utf-8"))
        meta = json.loads((K.PROCESSED / "meta.json").read_text(encoding="utf-8"))
        meta["generated_at"] = now_iso()
        layers = _load_layers(cfg, http, log)
        paths = deliver(ranked, cfg, fx, meta, audit_rows, layers, K.OUTPUTS, None, http=http)
        log.section("Gate 9 — deliverables (rebuilt)", [str(p.relative_to(K.ROOT)) for v in paths.values() for p in v])
        qa_lines, ok = final_qa(ranked, paths, cfg, token, http)
        log.section("Gate 10 — final QA", qa_lines)
        log.write()
        return 0 if ok else 3

    # ---- Gates 1–3: audit + validation (10–20 records per source)
    enabled = [n for n, sc in cfg["sources"].items() if sc.get("enabled")]
    uses_apify = [n for n in enabled if cfg["sources"][n].get("method") == "apify"]
    if uses_apify and not auth.available:
        log.section("Apify NOT used — paid actors skipped", [
            f"Reason: {auth.reason}",
            "To enable: allow api.apify.com in the environment's network access and set APIFY_TOKEN "
            "(in .env for local runs, or an Apify credential for cloud runs).",
            "Urbania/Adondevivir fall back to one polite direct request each (stops at any bot challenge)."])
    val_results, cov, statuses = {}, {}, {}
    for name in enabled:
        # full mode: a paid source is collected once, directly at full size (the sample was validated in the
        # separate --mode validate run); paying for a second, smaller copy of the same records adds nothing
        direct_full = mode == "full" and cfg["sources"][name].get("method") == "apify" and auth.available
        res = collect(name, cfg, http, budget, "full" if direct_full else "validate", auth)
        val_results[name] = res
        cov[name] = coverage(res.listings)
        statuses[name] = source_status(res, cov[name])
        save_json(K.RAW / f"{name}_{'full' if direct_full else 'validation'}_{res.started_at[:19].replace(':', '')}.json",
                  res.raw_records)
    vrows = [validation_row(n, r) for n, r in val_results.items()]
    details = []
    for n, r in val_results.items():
        if "input_schema" in r.audit:
            details.append(f"{n}: actor input schema {r.audit['input_schema']}; properties = "
                           f"{r.audit.get('input_properties')}")
        for seg in r.audit.get("segments", []):
            for run in seg["runs"]:
                details.append(f"{n} {seg['bedrooms']}BR: run {run['run_id']} {run['status']} · {run['items']}/"
                               f"{run['requested']} records · USD {run['cost_usd']:.3f} · input "
                               f"{json.dumps(run['input'], ensure_ascii=False)}")
        if r.audit.get("dataset_fields"):
            details.append(f"{n}: dataset fields (non-empty count) = {', '.join(r.audit['dataset_fields'])}")
        if r.notes:
            details.append(f"{n}: notes = {'; '.join(r.notes)}")
    log.section("Gates 2–3 — validation run (per source)", md_table(vrows) + [""] + details)
    audit_rows = build_audit_rows(val_results, cov, statuses)
    write_source_audit_md(audit_rows, probes, now_iso())
    if mode == "validate":
        geocode_ok = probes.get("nominatim.openstreetmap.org", (False,))[0]
        for title, lines in validation_analysis(val_results, cfg, fx, http, geocode_ok):
            log.section(title, lines)
        rec_lines = reconcile_spend(budget, http, auth)
        log.section("Apify spend — this run", spend_lines(budget) + rec_lines)
        log.write()
        print("\nValidation complete. Review SOURCE_AUDIT.md and RUN_LOG.md, then run --mode full.")
        return 0

    # ---- Gate 4: full collection (only for sources whose validation sample is usable)
    apify_ok = [n for n in uses_apify if auth.available and validation_ok(val_results[n])]
    alloc = allocate_full_items(cfg, val_results, budget, apify_ok)
    results: dict[str, SourceResult] = {}
    plan = []
    for name in enabled:
        vres = val_results[name]
        if mode == "full" and cfg["sources"][name].get("method") == "apify" and auth.available:
            results[name] = vres
            plan.append(f"{name}: collected once at full size (one run per bedroom segment, ≤ "
                        f"{cfg['cost_control']['apify_max_items_per_run']} records per run on the current Apify plan); "
                        f"{len(vres.listings)} records")
            continue
        if name == "manual" or not validation_ok(vres):
            results[name] = vres
            plan.append(f"{name}: no full run ({'manual import' if name == 'manual' else 'validation sample not usable'}); "
                        f"{len(vres.listings)} validation records kept for screening")
            continue
        items = alloc.get(name, (None, "direct HTML — no cost"))[0]
        plan.append(f"{name}: full run — {alloc.get(name, (None, 'direct HTML — no cost'))[1]}")
        res = collect(name, cfg, http, budget, "full", auth, max_items=items)
        if not res.listings:
            res.notes.append("full run returned nothing — validation records used instead")
            res.listings, res.raw_records = vres.listings, vres.raw_records
        results[name] = res
        save_json(K.RAW / f"{name}_full_{res.started_at[:19].replace(':', '')}.json", res.raw_records)
    all_listings = [lst for r in results.values() for lst in r.listings]
    log.section("Apify spend — collection", spend_lines(budget) + reconcile_spend(budget, http, auth))
    log.section("Gate 4 — full collection", plan + [
        f"{n}: {r.status} · {len(r.listings)} records · cost USD {r.cost_usd:.3f}"
        + (f" · errors: {'; '.join(r.errors)}" if r.errors else "") for n, r in results.items()]
        + [f"total records: {len(all_listings)}",
           f"external cost so far: USD {budget.spent:.3f} (cap USD {budget.max_usd:.2f})"])
    audit_rows = build_audit_rows(results, {n: coverage(r.listings) for n, r in results.items()}, statuses)
    write_source_audit_md(audit_rows, probes, now_iso())

    if not all_listings:
        log.section("STOPPED — no listings collected", [
            "No source returned listings, so no client deliverable was produced (an empty shortlist would be "
            "misleading). Fix the blockers above and re-run: python -m src.pipeline --mode full"])
        log.write()
        return 2

    layers = _load_layers(cfg, http, log)
    ranked = process(all_listings, cfg, fx, http, layers, log, live_qa=True,
                     geocode=probes.get("nominatim.openstreetmap.org", (False,))[0], auth=auth, budget=budget)
    meta = make_meta(cfg, fx, len(all_listings), ranked, budget.spent)
    meta["by_source"] = {n: len(r.listings) for n, r in results.items()}
    K.PROCESSED.mkdir(parents=True, exist_ok=True)
    ranked.to_pickle(K.PROCESSED / "ranked.pkl")
    ranked.drop(columns=["image_keys", "text_signals", "amenities"], errors="ignore") \
        .to_csv(K.PROCESSED / "listings_ranked.csv", index=False)
    save_json(K.PROCESSED / "audit_rows.json", audit_rows)
    save_json(K.PROCESSED / "meta.json", meta)
    paths = deliver(ranked, cfg, fx, meta, audit_rows, layers, K.OUTPUTS, None, http=http)
    log.section("Gate 9 — deliverables", [str(p.relative_to(K.ROOT)) for v in paths.values() for p in v])
    qa_lines, ok = final_qa(ranked, paths, cfg, token, http)
    reconcile_spend(budget, http, auth)
    log.section("Gate 10 — final QA", qa_lines + [f"project external cost (cumulative, reconciled): USD {budget.spent:.3f}"])
    log.write()
    http.close()
    return 0 if ok else 3


def _load_layers(cfg: dict, http: PoliteClient, log: RunLog) -> OsmLayers | None:
    data, prov = fetch_overpass(cfg, http, K.GEO / "osm_miraflores.json")
    if data is None:
        log.section("OSM", [f"Overpass unavailable: {prov}"])
        return None
    return parse_layers(data, prov)


# --------------------------------------------------------------------------- demo (offline, synthetic)
def run_demo(cfg: dict, log: RunLog, out: Path | None = None) -> int:
    """End-to-end run on SYNTHETIC fixtures to preview the deliverable format. Never writes to outputs/."""
    fx_dir = K.ROOT / "tests" / "fixtures"
    fx = FxRate(3.385, "SYNTHETIC DEMO RATE (same value as documented fallback)", now_iso(), live=False)
    raw = json.loads((fx_dir / "synthetic_navent.json").read_text(encoding="utf-8"))
    listings = [map_navent_record(r, r.pop("_source"), "https://example.com", now_iso()) for r in raw]
    osm = json.loads((fx_dir / "synthetic_osm.json").read_text(encoding="utf-8"))
    layers = parse_layers(osm, "SYNTHETIC OSM fixture (demo only)")
    log.section("Demo", ["SYNTHETIC data — format preview only", f"{len(listings)} synthetic records"])
    ranked = process(listings, cfg, fx, None, layers, log, live_qa=False, geocode=False, persist=False)
    meta = make_meta(cfg, fx, len(listings), ranked, 0.0)
    audit_rows = build_audit_rows({}, {}, {})
    out = out or K.ROOT / "docs" / "preview"
    paths = deliver(ranked, cfg, fx, meta, audit_rows, layers, out, PREVIEW_BANNER, prefix="PREVIEW_SYNTHETIC_")
    log.section("Demo deliverables", [str(p) for v in paths.values() for p in v])
    lines, _ = final_qa(ranked, paths, cfg, None, None, production=False)
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["preflight", "validate", "full", "report", "demo"], default="full")
    ap.add_argument("--out", type=Path, default=None, help="demo mode only: output directory (default docs/preview)")
    args = ap.parse_args(argv)
    return run(args.mode, args.out)


if __name__ == "__main__":
    sys.exit(main())
