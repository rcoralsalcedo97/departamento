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
from .reporting.report import build_report_html, html_to_pdf
from .runlog import RunLog
from .scoring.scoring import rank, score_all
from .sources.apify_client import ApifyAuth, resolve_apify_auth
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
    s = cfg["scoring"]
    nm = cfg["noise_model"]
    return [
        ("Objective", "Find the strongest currently advertised 1–2 bedroom rentals inside Miraflores (Lima) for a "
                      "couple, at or below USD 1,000/month, prioritising quiet and usable space."),
        ("Hard requirements", "Miraflores only · rent (not sale) · apartment · 1–2 bedrooms (studios excluded unless "
                              "the listing classifies the unit as 1 bedroom) · base rent ≤ USD 1,000. A high score "
                              "never overrides a hard requirement."),
        ("Stretch / near misses", "Rent USD 1,001–1,100 → STRETCH_NEGOTIABLE only. Outside Miraflores → NEAR_MISSES "
                                  f"only if within {cfg['near_misses']['max_distance_outside_m']} m of the boundary, "
                                  f"budget-compliant and fit ≥ {cfg['near_misses']['min_fit_score']}."),
        ("Run", f"Generated {meta['generated_at']}. Listings collected: {meta['n_raw']}; unique after de-duplication: "
                f"{meta['n_unique']}; budget-compliant matches: {meta['n_primary']}; stretch: {meta['n_stretch']}; "
                f"near misses: {meta['n_near']}. External cost: USD {meta['cost']:.2f}."),
        ("Exchange rate", f"1 USD = S/ {fx.usd_pen:.3f} · {fx.source} · {fx.timestamp}. Used for every conversion. "
                          "Values published by the listing are marked PUBLISHED; converted values CALCULATED. "
                          "When a listing publishes both currencies, both are kept as published."),
        ("Fit score (100)", f"Quietness {s['quietness']} · Budget/total cost {s['budget']} · Space/layout {s['space']} · "
                            f"Location/daily livability {s['location']} · Furnishing {s['furnishing']} · "
                            f"Building/security/amenities {s['building']} · Listing quality/freshness {s['listing_quality']}."),
        ("Budget classes", "STRICT_ALL_IN = rent + known maintenance ≤ USD 1,000 · BASE_RENT_COMPLIANT = rent ≤ USD 1,000 "
                           "but the total is above USD 1,000 or unknown (maintenance not published) · STRETCH = rent "
                           f"USD 1,001–1,100 (separate sheet). Ranking gives STRICT_ALL_IN a {cfg['budget']['strict_preference_margin']}-point "
                           "preference, so a BASE_RENT_COMPLIANT unit only ranks above it with a clearly higher fit."),
        ("Budget points", "Full points need a known total (rent + maintenance) ≤ USD 1,000; lower totals score higher. "
                          "Unknown maintenance is scored on rent only and capped below a known total, and flagged."),
        ("Foreign-tenant friendliness", "Evidence from listing text only: HIGH (foreigners/passport/corporate lease "
                                        "explicitly welcome), MEDIUM (temporary stays, no guarantor, English listing, "
                                        "furnished + utilities), POTENTIAL_FRICTION (asks for a Peruvian guarantor, carné "
                                        "de extranjería or DNI), UNKNOWN (silent — the normal case, never penalised). "
                                        "Not part of the fit score; no legal assumptions."),
        ("Space points", "Area bands per bedroom count (1BR: <40 small, 40–49 acceptable, 50–59 good, ≥60 very spacious; "
                         "2BR: <55, 55–69, 70–84, ≥85). Built (techada) area preferred over total area. Bonuses: 2nd "
                         "bathroom, balcony/terrace, study, laundry, walk-in closet."),
        ("Noise model", f"Baseline {nm['baseline']}. Major road (OSM motorway/trunk/primary) ≤{nm['major_road']['strong_m']} m "
                        f"−{nm['major_road']['strong_penalty']}, ≤{nm['major_road']['moderate_m']} m −{nm['major_road']['moderate_penalty']}, "
                        f"≤{nm['major_road']['mild_m']} m −{nm['major_road']['mild_penalty']}; secondary arterial ≤{nm['arterial_road']['strong_m']} m "
                        f"−{nm['arterial_road']['strong_penalty']}; nightclub ≤{nm['nightclub']['strong_m']} m −{nm['nightclub']['strong_penalty']}, "
                        f"≤{nm['nightclub']['moderate_m']} m −{nm['nightclub']['moderate_penalty']}; ≥{nm['bar_cluster']['many_threshold']} bars "
                        f"within {nm['bar_cluster']['radius_m']} m −{nm['bar_cluster']['many_penalty']}; interior-facing "
                        f"+{nm['text_signals']['interior_view']}; acoustic windows +{nm['text_signals']['acoustic_windows']}; "
                        f"avenue view {nm['text_signals']['avenue_view']}; floor ≥{nm['text_signals']['high_floor_min']} "
                        f"+{nm['text_signals']['high_floor_bonus']}. LOW risk ≥{nm['risk_thresholds']['low_from']}, "
                        f"MEDIUM ≥{nm['risk_thresholds']['medium_from']}, else HIGH. Confidence HIGH needs exact "
                        "coordinates + stated orientation; LOW when location is approximate or missing (then the "
                        "score is shrunk toward neutral). It is an estimate — confirm in person."),
        ("Change vs brief", "Added a secondary-arterial tier and restaurant-cluster penalty (busy frontage), and "
                            "confidence shrinkage when coordinates are missing. Near misses additionally require "
                            "proximity to the boundary. Portal price filter set to USD 1,150 (not 1,000) so the "
                            "stretch band and PEN-priced listings are not lost; every record is re-validated. "
                            "Ranking rule: units with HIGH estimated noise (medium/high confidence) are ranked after "
                            "all LOW/MEDIUM units, because quiet is the first priority; with LOW confidence (approximate "
                            "or missing location) no demotion is applied."),
        ("Livability", "Distance to supermarket (≤500 m), pharmacy (≤400 m), park (≤300 m), café (≤300 m), bus/"
                       "Metropolitano stop (≤400 m), Malecón (≤900 m); half credit up to 1.6× those distances. "
                       "Nightlife is never rewarded."),
        ("Value bands", "USD per m² within the same bedroom count, relative to this sample only: lowest quartile "
                        "EXCELLENT_VALUE, then GOOD, FAIR, EXPENSIVE_RELATIVE_TO_SAMPLE. Not an official valuation."),
        ("De-duplication", "Pairs scored on URL, portal id (Urbania/Adondevivir share posting ids), coordinates, area, "
                           "price, phone, fuzzy title and description (rapidfuzz), normalised address and shared photo "
                           "ids. Groups keep every source URL; the most complete record is canonical; conflicts are flagged."),
        ("Availability", "LIKELY_ACTIVE = returned by a live search at scrape time. ACTIVE_CONFIRMED = source page "
                         "re-opened successfully during QA. Never stated as guaranteed."),
        ("Unknown values", "Shown as UNKNOWN. Nothing is imputed. Maintenance read from description text is used "
                           "only when the portal field is empty and is flagged in the evidence column."),
        ("Data sources", "Portals via Apify actors or polite direct requests (robots.txt, ≥2 s spacing, no login, "
                         "no CAPTCHA solving). Map data © OpenStreetMap contributors (ODbL) via Overpass."),
        ("Limitations", "Advertiser-reported data; approximate portal locations; OSM may miss venues; the noise model "
                        "cannot see building insulation or neighbours; availability changes daily."),
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
            layers: OsmLayers | None, out_dir: Path, banner: str | None, prefix: str = "", suffix: str = "",
            http: PoliteClient | None = None) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx = out_dir / f"{prefix}Miraflores_Rental_Shortlist{suffix}.xlsx"
    html_path = out_dir / f"{prefix}Miraflores_Rental_Executive_Report{suffix}.html"
    pdf = out_dir / f"{prefix}Miraflores_Rental_Executive_Report{suffix}.pdf"
    txt = out_dir / f"{prefix}Contact_Templates{suffix}.txt"
    build_workbook(xlsx, ranked, meta, audit_rows, methodology_rows(cfg, fx, meta), banner)
    geo = {"boundary_ll": layers.boundary_ll, "road_lines_ll": layers.road_lines_ll} if layers else None
    top = ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category").head(meta["top_n"])
    thumbs = fetch_thumbnails(top.head(5), http) if http is not None else {}
    html_path.write_text(build_report_html(ranked, meta, audit_rows, geo, banner, thumbs), encoding="utf-8")
    html_to_pdf(html_path, pdf, banner)
    write_contact_templates(txt, [{"_label": C.property_label(r), "_contact": C.contact_text(r), **r}
                                  for r in C.records(top)])
    return xlsx, pdf, txt


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
    """Size each paid full run from the *observed* validation cost per item, within the run budget."""
    alloc: dict[str, tuple[int, str]] = {}
    pool = budget.remaining * cfg["cost_control"]["full_budget_share"]
    weights = {n: cfg["sources"][n]["full_max_items"] for n in apify_sources}
    total_w = sum(weights.values()) or 1
    for n in apify_sources:
        r = val_results[n]
        cap = cfg["sources"][n]["full_max_items"]
        cpi = (r.cost_usd / len(r.raw_records)) if r.raw_records and r.cost_usd else None
        if cpi is None and r.audit.get("estimated_cost_usd"):
            cpi = r.audit["estimated_cost_usd"] / max(1, cfg["cost_control"]["validation_max_items"])
        share = pool * weights[n] / total_w
        if cpi and cpi > 0:
            items = max(0, min(cap, int(share / cpi)))
            alloc[n] = (items, f"≈USD {cpi:.4f}/item observed → {items} items within USD {share:.2f}")
        else:
            alloc[n] = (cap, "no per-item cost observed (free or unknown) — capped by config; "
                             "maxTotalChargeUsd still enforces the budget")
    return alloc


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

    budget = CostBudget(cfg["cost_control"]["max_external_usd"])
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
        paths = deliver(ranked, cfg, fx, meta, audit_rows, layers, K.OUTPUTS, None, suffix="_REAL", http=http)
        log.section("Gate 9 — deliverables (rebuilt)", [str(p.relative_to(K.ROOT)) for p in paths])
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
        res = collect(name, cfg, http, budget, "validate", auth)
        val_results[name] = res
        cov[name] = coverage(res.listings)
        statuses[name] = source_status(res, cov[name])
        save_json(K.RAW / f"{name}_validation_{res.started_at[:19].replace(':', '')}.json", res.raw_records)
    vrows = [validation_row(n, r) for n, r in val_results.items()]
    details = []
    for n, r in val_results.items():
        if r.audit.get("actor_input") is not None:
            details.append(f"{n}: actor input sent = {json.dumps(r.audit['actor_input'], ensure_ascii=False)}")
            details.append(f"{n}: actor input schema properties = {r.audit.get('input_properties')}")
            details.append(f"{n}: pricing = {r.audit.get('pricing')}")
        if r.audit.get("dataset_fields"):
            details.append(f"{n}: dataset fields (non-empty count) = {', '.join(r.audit['dataset_fields'])}")
        if r.notes:
            details.append(f"{n}: notes = {'; '.join(r.notes)}")
    log.section("Gates 2–3 — validation run (10–20 records/source)", md_table(vrows) + [""] + details)
    audit_rows = build_audit_rows(val_results, cov, statuses)
    write_source_audit_md(audit_rows, probes, now_iso())
    if mode == "validate":
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
    paths = deliver(ranked, cfg, fx, meta, audit_rows, layers, K.OUTPUTS, None, suffix="_REAL", http=http)
    log.section("Gate 9 — deliverables", [str(p.relative_to(K.ROOT)) for p in paths])
    qa_lines, ok = final_qa(ranked, paths, cfg, token, http)
    log.section("Gate 10 — final QA", qa_lines + [f"total external cost: USD {budget.spent:.3f}"])
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
    log.section("Demo deliverables", [str(p) for p in paths])
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
