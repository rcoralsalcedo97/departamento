"""Hard gates, 100-point fit score, value bands, red flags and plain-English summaries."""
from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd

from ..normalize.text_signals import fold
from ..normalize.foreign_tenant import assess_foreign_tenant
from .noise import assess_noise

APARTMENT_WORDS = ("departamento", "depa", "apartment", "flat", "penthouse", "duplex", "dúplex", "loft",
                   "apartamento", "dpto")
NON_APARTMENT_WORDS = ("casa", "house", "oficina", "office", "local", "terreno", "habitación", "habitacion",
                       "cuarto", "room", "cochera", "depósito", "deposito")


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def clean_row(row: dict) -> dict:
    """pandas turns missing values into NaN; downstream logic expects None."""
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}


def area_of(row) -> tuple[float | None, str | None]:
    built, total = _num(row.get("built_area_m2")), _num(row.get("total_area_m2"))
    if built and 12 <= built <= 400:
        return built, "built"
    if total and 12 <= total <= 400:
        return total, "total"
    return None, None


def space_band(beds: int | None, area: float | None, cfg: dict) -> str:
    if beds not in (1, 2) or area is None:
        return "UNKNOWN"
    b = cfg["space_bands"][beds]
    if area >= b["very_spacious_from"]:
        return "VERY_SPACIOUS"
    if area >= b["good_from"]:
        return "GOOD"
    if area >= b["acceptable_from"]:
        return "ACCEPTABLE"
    return "SMALL"


# --------------------------------------------------------------------------- gates
DEMO_FIELD_RX = re.compile(r"\bdemo\b|\(demo|ejemplo|synthetic|sint[eé]tic|\bfake\b|lorem ipsum", re.I)
DEMO_TEXT_RX = re.compile(r"\(demo|synthetic|lorem ipsum|fake listing", re.I)   # "por ejemplo" is normal Spanish
DEMO_HOSTS = ("example.com", "example.org", "example.net", "localhost")


def integrity_issues(row: dict) -> list[str]:
    """Production data-integrity guard: a record must look like a real, reachable portal listing."""
    issues = []
    url = str(row.get("source_url") or "")
    if not url.startswith("http"):
        issues.append("no listing URL")
    elif any(h in url.lower() for h in DEMO_HOSTS):
        issues.append("demo/example URL")
    for field in ("title", "address", "agency_name", "agent_name", "source_listing_id", "source_url"):
        if DEMO_FIELD_RX.search(str(row.get(field) or "")):
            issues.append(f"demo marker in {field}")
            break
    if DEMO_TEXT_RX.search(str(row.get("description") or "")):
        issues.append("demo marker in description")
    if row.get("rent_usd") is None:
        issues.append("rent missing")
    return issues


def classify(row: dict, cfg: dict) -> tuple[str, list[str], list[str]]:
    """Return (category, exclusion_reasons, gate_flags). Category ∈ PRIMARY, STRETCH, NEAR_MISS_CANDIDATE, EXCLUDED."""
    reasons, flags = [], []
    if cfg.get("_production"):
        reasons += [f"INTEGRITY: {x}" for x in integrity_issues(row)]
    op = fold(str(row.get("operation") or ""))
    if op and not any(k in op for k in ("alquiler", "rent", "arriendo")):
        reasons.append(f"operation is '{row.get('operation')}', not rent")
    ptype = fold(str(row.get("property_type") or ""))
    if ptype and any(w in ptype for w in NON_APARTMENT_WORDS) and not any(w in ptype for w in APARTMENT_WORDS):
        reasons.append(f"property type '{row.get('property_type')}' is not an apartment")
    if row.get("shared_room_text") is True:
        reasons.append("room in a shared flat, not a whole unit")
    if row.get("active_status") == "INACTIVE":
        reasons.append("listing inactive")

    beds = _num(row.get("bedrooms"))
    if beds is None:
        reasons.append("bedroom count unknown")
    elif beds == 0:
        reasons.append("studio (0 bedrooms)")
    elif beds > cfg["bedrooms"]["max"] or beds < cfg["bedrooms"]["min"]:
        reasons.append(f"{beds:.0f} bedrooms")
    if row.get("studio_text") is True and beds == 1:
        flags.append("STUDIO_WORDING")

    rent = _num(row.get("rent_usd"))
    if rent is None:
        reasons.append("rent unknown")

    # district: precise coordinates beat free text, but disagreements are always flagged
    target = cfg["location"]["district"]
    text_in = fold(str(row.get("district") or "")) == fold(target)
    geo_in = row.get("inside_district_polygon")
    precision = row.get("coord_precision")
    if geo_in is None or (isinstance(geo_in, float) and math.isnan(geo_in)):
        in_district = text_in
        if not text_in and row.get("district"):
            reasons_district = f"district text '{row.get('district')}'"
        else:
            reasons_district = "district not stated" if not row.get("district") else None
    else:
        geo_in = bool(geo_in)
        if precision in ("APPROXIMATE", "STREET_LEVEL"):
            in_district = text_in or (geo_in and not row.get("district"))
        else:
            in_district = geo_in
        if geo_in != text_in and row.get("district"):
            flags.append("DISTRICT_MISMATCH")
        reasons_district = None if in_district else \
            f"outside {target} ({_num(row.get('dist_outside_district_m')) or 0:.0f} m beyond the boundary)"

    if reasons:
        return "EXCLUDED", reasons, flags
    if not in_district:
        near = cfg["near_misses"]
        dist = _num(row.get("dist_outside_district_m"))
        if dist is not None and dist <= near["max_distance_outside_m"] and rent <= cfg["budget"]["target_max_rent"]:
            return "NEAR_MISS_CANDIDATE", [reasons_district or "outside district"], flags
        return "EXCLUDED", [reasons_district or "outside district"], flags
    if rent <= cfg["budget"]["target_max_rent"]:
        return "PRIMARY", [], flags
    if rent <= cfg["budget"]["stretch_max_rent"]:
        return "STRETCH", [], flags
    return "EXCLUDED", [f"rent USD {rent:.0f} above stretch ceiling"], flags


# --------------------------------------------------------------------------- budget classes
def budget_class(row: dict, cfg: dict) -> tuple[str, str]:
    """STRICT_ALL_IN (rent + known maintenance ≤ target) · BASE_RENT_COMPLIANT (rent ≤ target, total over or
    unknown) · STRETCH (rent in the stretch band) · OVER_BUDGET. Never presented as equivalent."""
    rent = _num(row.get("rent_usd"))
    if rent is None:
        return "UNKNOWN", "rent unknown"
    tgt, stretch = cfg["budget"]["target_max_rent"], cfg["budget"]["stretch_max_rent"]
    total = _num(row.get("estimated_total_monthly_usd"))
    if row.get("maintenance_included_in_rent") is True:
        total = rent
    if rent <= tgt:
        if total is not None and total <= cfg["budget"]["target_max_total"]:
            return "STRICT_ALL_IN", f"all-in ≈ USD {total:,.0f}"
        if total is not None:
            return "BASE_RENT_COMPLIANT", f"rent within budget but total ≈ USD {total:,.0f} (over USD {tgt:,.0f})"
        return "BASE_RENT_COMPLIANT", "rent within budget; maintenance not published — total unknown"
    if rent <= stretch:
        return "STRETCH", f"rent USD {rent:,.0f} (stretch)"
    return "OVER_BUDGET", f"rent USD {rent:,.0f}"


# --------------------------------------------------------------------------- components
def budget_points(row, cfg) -> float:
    w = cfg["scoring"]["budget"]
    rent = _num(row.get("rent_usd"))
    if rent is None:
        return 0.0
    tgt, stretch = cfg["budget"]["target_max_rent"], cfg["budget"]["stretch_max_rent"]
    total = _num(row.get("estimated_total_monthly_usd"))
    if rent > tgt:
        return round(w * 0.2, 2) if rent <= stretch else 0.0
    if total is not None:
        if total <= cfg["budget"]["target_max_total"]:
            frac = 0.7 + 0.3 * min(1.0, (tgt - total) / 300)
        elif total <= stretch:
            frac = 0.5
        else:
            frac = 0.3
    else:   # maintenance unknown — rent-only, capped below a fully known total
        frac = 0.6 + 0.3 * min(1.0, (tgt - rent) / 300)
    return round(w * frac, 2)


def space_points(row, cfg) -> tuple[float, str, float | None, str | None]:
    w = cfg["scoring"]["space"]
    beds = _num(row.get("bedrooms"))
    area, basis = area_of(row)
    band = space_band(int(beds) if beds else None, area, cfg)
    base = {"VERY_SPACIOUS": 0.95, "GOOD": 0.8, "ACCEPTABLE": 0.55, "SMALL": 0.3, "UNKNOWN": 0.35}[band]
    if band == "SMALL" and area is not None:
        small_th = cfg["space_bands"][int(beds)]["small_below"]
        if area < cfg["red_flags"]["very_small_area_factor"] * small_th:
            base = 0.15
    bonus = 0.0
    if (_num(row.get("bathrooms")) or 0) >= 2:
        bonus += 0.05
    if row.get("balcony") is True or row.get("terrace") is True:
        bonus += 0.05
    if row.get("study") is True:
        bonus += 0.05
    if row.get("laundry") is True:
        bonus += 0.025
    if row.get("walk_in_closet") is True:
        bonus += 0.025
    return round(w * min(1.0, base + bonus), 2), band, area, basis


def location_points(row, cfg) -> tuple[float, str]:
    w = cfg["scoring"]["location"]
    lv = cfg["livability"]
    if _num(row.get("dist_supermarket_m")) is None and _num(row.get("dist_park_m")) is None:
        return round(w * 0.5, 2), "location data unavailable (neutral score)"
    parts, notes = 0.0, []
    for key, limit, weight, label in (("supermarket", lv["supermarket_m"], 0.3, "supermarket"),
                                      ("pharmacy", lv["pharmacy_m"], 0.2, "pharmacy"),
                                      ("park", lv["park_m"], 0.2, "park"),
                                      ("cafe", lv["cafe_m"], 0.1, "café"),
                                      ("transit", lv["transit_m"], 0.1, "bus/Metropolitano stop"),
                                      ("malecon", lv["malecon_m"], 0.1, "Malecón")):
        d = _num(row.get(f"dist_{key}_m"))
        if d is None:
            continue
        if d <= limit:
            parts += weight
            notes.append(f"{label} {d:.0f} m")
        elif d <= limit * 1.6:
            parts += weight / 2
    return round(w * parts, 2), ", ".join(notes)


def furnishing_points(row, cfg) -> float:
    w = cfg["scoring"]["furnishing"]
    if row.get("furnished") is True:
        return float(w)
    if row.get("semi_furnished") is True:
        return round(w * 0.6, 2)
    if row.get("furnished") is False:
        return round(w * 0.2, 2)
    return round(w * 0.35, 2)


def building_points(row, cfg) -> float:
    w = cfg["scoring"]["building"]
    frac = 0.0
    frac += 0.35 if row.get("security_24h") is True else 0
    frac += 0.2 if row.get("elevator") is True else 0
    frac += 0.15 if row.get("laundry") is True else 0
    frac += 0.15 if row.get("parking_included") is True or (_num(row.get("parking_spaces")) or 0) > 0 else 0
    frac += 0.15 if any(row.get(k) is True for k in ("gym", "pool", "coworking", "common_areas")) else 0
    return round(w * min(1.0, frac), 2)


def days_since(d) -> int | None:
    if not isinstance(d, str) or not re.match(r"\d{4}-\d{2}-\d{2}", d):
        return None
    return (date.today() - date.fromisoformat(d[:10])).days


def quality_points(row, cfg) -> float:
    w = cfg["scoring"]["listing_quality"]
    frac = {"ACTIVE_CONFIRMED": 0.3, "LIKELY_ACTIVE": 0.25, "UNKNOWN": 0.1}.get(row.get("active_status"), 0)
    age = days_since(row.get("publication_date"))
    frac += 0.2 if age is not None and age <= 30 else 0.1 if age is not None and age <= 90 else 0
    imgs = _num(row.get("image_count")) or 0
    frac += 0.1 if imgs >= 8 else 0.05 if imgs >= 3 else 0
    frac += 0.1 if _num(row.get("latitude")) is not None else 0
    frac += 0.1 if (row.get("phone") or row.get("whatsapp") or row.get("agency_name")) else 0
    frac += 0.1 if len(str(row.get("description") or "")) >= 300 else 0
    frac += 0.1 if (_num(row.get("number_of_sources")) or 1) >= 2 else 0
    return round(w * min(1.0, frac), 2)


# --------------------------------------------------------------------------- flags
def red_flags(row, cfg, extra: list[str]) -> list[str]:
    f = set(extra)
    rent = _num(row.get("rent_usd"))
    total = _num(row.get("estimated_total_monthly_usd"))
    tgt = cfg["budget"]["target_max_rent"]
    if rent is not None and rent > tgt:
        f.add("PRICE_OVER_BUDGET")
    if total is not None and total > cfg["budget"]["target_max_total"]:
        f.add("TOTAL_COST_OVER_BUDGET")
    if _num(row.get("maintenance_usd")) is None and row.get("maintenance_included_in_rent") is not True:
        f.add("UNKNOWN_MAINTENANCE")
    area, _ = area_of(row)
    beds = _num(row.get("bedrooms"))
    if area is not None and beds in (1, 2):
        if area < cfg["red_flags"]["very_small_area_factor"] * cfg["space_bands"][int(beds)]["small_below"]:
            f.add("VERY_SMALL_AREA")
    if area is None:
        f.add("AREA_UNKNOWN")
    if not row.get("publication_date"):
        f.add("NO_PUBLICATION_DATE")
    if row.get("active_status") in ("UNKNOWN", None):
        f.add("UNKNOWN_ACTIVE_STATUS")
    dep = _num(row.get("deposit_months"))
    if dep is not None and dep >= cfg["red_flags"]["very_high_deposit_months"]:
        f.add("VERY_HIGH_DEPOSIT")
    mc = _num(row.get("minimum_contract_months"))
    if mc is not None and mc >= cfg["red_flags"]["long_min_contract_months"]:
        f.add("LONG_MINIMUM_CONTRACT")
    if row.get("furnished") is False and row.get("semi_furnished") is not True:
        f.add("NO_FURNITURE")
    if row.get("possible_duplicate_of"):
        f.add("POSSIBLE_DUPLICATE")
    if row.get("dup_inconsistencies"):
        f.add("DUPLICATE_DATA_CONFLICT")
    if not (row.get("phone") or row.get("whatsapp")):
        f.add("INCOMPLETE_CONTACT")
    addr = row.get("address")
    if not isinstance(addr, str) or not re.search(r"\d", addr):
        f.add("INCOMPLETE_ADDRESS")
    if row.get("coord_precision") in ("APPROXIMATE", "STREET_LEVEL"):
        f.add("APPROXIMATE_LOCATION")
    if _num(row.get("latitude")) is None:
        f.add("NO_COORDINATES")
    built, total_a = _num(row.get("built_area_m2")), _num(row.get("total_area_m2"))
    if built and total_a and built > total_a * 1.05:
        f.add("AREA_INCONSISTENT")
    m = re.search(r"(\d)\s*(dormitorio|dorm|habitaci|bedroom)", fold(str(row.get("title") or "")))
    if m and beds is not None and int(m.group(1)) != int(beds):
        f.add("BEDROOM_TITLE_MISMATCH")
    if row.get("short_term_text") is True:
        f.add("SHORT_TERM_WORDING")
    if row.get("rent_usd_basis") == "CALCULATED":
        f.add("PRICE_CONVERTED_FROM_PEN")
    return sorted(f)


# --------------------------------------------------------------------------- narrative
def money(v) -> str:
    v = _num(v)
    return f"USD {v:,.0f}" if v is not None else "UNKNOWN"


def total_text(row) -> str:
    rent = _num(row.get("rent_usd"))
    if rent is None:
        return "UNKNOWN"
    if row.get("maintenance_included_in_rent") is True:
        return f"{money(rent)} (maintenance included in rent)"
    m_usd, m_pen = _num(row.get("maintenance_usd")), _num(row.get("maintenance_pen"))
    total = _num(row.get("estimated_total_monthly_usd"))
    if total is not None:
        if row.get("maintenance_currency") == "PEN" and m_pen is not None:
            return f"≈ {money(total)} ({money(rent)} rent + S/ {m_pen:,.0f} maintenance)"
        return f"≈ {money(total)} ({money(rent)} rent + {money(m_usd)} maintenance)"
    return f"{money(rent)} rent + maintenance UNKNOWN"


def advantages(row) -> list[str]:
    out = []
    area, basis = _num(row.get("area_m2")), row.get("area_basis")
    beds = int(_num(row.get("bedrooms")) or 0)
    band = row.get("space_band")
    if area and band in ("VERY_SPACIOUS", "GOOD"):
        out.append(f"{area:.0f} m² {'built ' if basis == 'built' else ''}area — {band.replace('_', ' ').lower()} for a {beds}-bedroom")
    if row.get("noise_risk") == "LOW" and row.get("noise_confidence") != "LOW":
        out.append(f"low estimated noise ({row.get('quietness_score_0_100')}/100)")
    if row.get("interior_view") is True:
        out.append("interior-facing")
    if row.get("acoustic_windows") is True:
        out.append("acoustic/double-glazed windows")
    vb = row.get("value_band")
    if vb in ("EXCELLENT_VALUE", "GOOD_VALUE") and _num(row.get("rent_usd_per_m2")):
        out.append(f"USD {row['rent_usd_per_m2']:.1f}/m² ({vb.replace('_', ' ').lower()} vs other {beds}BR in sample)")
    total = _num(row.get("estimated_total_monthly_usd"))
    if total is not None and total <= 850:
        out.append(f"all-in ≈ {money(total)}/month")
    if row.get("furnished") is True:
        out.append("furnished")
    if row.get("security_24h") is True:
        out.append("building security/controlled access")
    if row.get("balcony") is True or row.get("terrace") is True:
        out.append("balcony/terrace")
    return out


DRAWBACK_TEXT = [
    ("HIGH_NOISE_RISK", lambda r: f"high estimated noise: {str(r.get('quietness_reason') or '').split(';')[0]}"),
    ("DIRECT_MAJOR_AVENUE", lambda r: (f"only {_num(r.get('dist_major_road_m')):.0f} m from "
                                      f"{r.get('major_road_name') or 'a major avenue'}")
     if (_num(r.get("dist_major_road_m")) or 999) <= 50 else "listing says the unit faces an avenue"),
    ("NIGHTLIFE_PROXIMITY", lambda r: "bars/nightlife nearby — check at night"),
    ("TOTAL_COST_OVER_BUDGET", lambda r: f"rent + maintenance {total_text(r)} exceeds USD 1,000"),
    ("VERY_SMALL_AREA", lambda r: f"only {_num(r.get('area_m2')) or 0:.0f} m²"),
    ("LONG_MINIMUM_CONTRACT", lambda r: f"minimum contract {_num(r.get('minimum_contract_months')) or 0:.0f} months"),
    ("VERY_HIGH_DEPOSIT", lambda r: f"{_num(r.get('deposit_months')) or 0:.0f} months' deposit"),
    ("UNKNOWN_MAINTENANCE", lambda r: "maintenance fee not published — confirm before visiting"),
    ("AREA_UNKNOWN", lambda r: "floor area not published"),
    ("NO_FURNITURE", lambda r: "unfurnished"),
    ("APPROXIMATE_LOCATION", lambda r: "portal shows an approximate location only"),
    ("NO_COORDINATES", lambda r: "no map location — noise estimate is text-only"),
    ("DUPLICATE_DATA_CONFLICT", lambda r: f"portals disagree: {r.get('dup_inconsistencies')}"),
    ("INCOMPLETE_CONTACT", lambda r: "no direct phone/WhatsApp — contact via portal"),
    ("NO_PUBLICATION_DATE", lambda r: "publication date unknown"),
]


def main_drawback(row) -> str:
    flags = set(str(row.get("red_flags") or "").split("; "))
    for flag, fn in DRAWBACK_TEXT:
        if flag in flags:
            return fn(row)
    if row.get("noise_risk") == "MEDIUM":
        return "moderate estimated noise — visit at rush hour and at night"
    return "no major drawback identified from listing data"


# --------------------------------------------------------------------------- orchestration
def score_all(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = df.copy()
    rows = []
    for _, r in df.iterrows():
        row = clean_row(r.to_dict())
        cat, excl, gate_flags = classify(row, cfg)
        noise = assess_noise(row, cfg)
        row.update({k: v for k, v in noise.items() if not k.startswith("_")})
        sp, band, area, basis = space_points(row, cfg)
        loc, loc_notes = location_points(row, cfg)
        comp = {
            "pts_quietness": round(cfg["scoring"]["quietness"] * noise["quietness_score_0_100"] / 100, 2),
            "pts_budget": budget_points(row, cfg),
            "pts_space": sp,
            "pts_location": loc,
            "pts_furnishing": furnishing_points(row, cfg),
            "pts_building": building_points(row, cfg),
            "pts_listing_quality": quality_points(row, cfg),
        }
        row.update(comp)
        row.update({"category": cat, "exclusion_reason": "; ".join(excl), "space_band": band,
                    "area_m2": area, "area_basis": basis, "location_notes": loc_notes,
                    "fit_score": round(sum(comp.values()), 1)})
        row["budget_class"], row["budget_note"] = budget_class(row, cfg)
        row["foreign_tenant_friendliness"], row["foreign_tenant_evidence"] = assess_foreign_tenant(
            row.get("title"), row.get("description"), row.get("furnished"), row.get("minimum_contract_months"))
        row["red_flags"] = "; ".join(red_flags(row, cfg, gate_flags + noise["_noise_flags"]))
        rows.append(row)
    out = pd.DataFrame(rows)

    # near misses need an exceptionally strong reason
    nm = cfg["near_misses"]
    weak = (out["category"] == "NEAR_MISS_CANDIDATE") & (out["fit_score"] < nm["min_fit_score"])
    out.loc[weak, "exclusion_reason"] = out.loc[weak, "exclusion_reason"] + "; fit below near-miss bar"
    out.loc[weak, "category"] = "EXCLUDED"
    out.loc[out["category"] == "NEAR_MISS_CANDIDATE", "category"] = "NEAR_MISS"

    # value analysis — relative to this sample, by bedroom count, Miraflores in-scope only
    out["rent_usd_per_m2"] = [
        round(r / a, 2) if _num(r) and _num(a) else None for r, a in zip(out["rent_usd"], out["area_m2"])]
    out["value_band"] = "INSUFFICIENT_DATA"
    scope = out["category"].isin(["PRIMARY", "STRETCH"]) & out["rent_usd_per_m2"].notna()
    for beds, grp in out[scope].groupby("bedrooms"):
        if len(grp) < cfg["value_analysis"]["min_group_size"]:
            out.loc[grp.index, "value_band"] = "INSUFFICIENT_SAMPLE"
            continue
        pct = grp["rent_usd_per_m2"].rank(pct=True)
        out.loc[grp.index, "value_percentile"] = (pct * 100).round()
        out.loc[grp.index, "value_band"] = pd.cut(
            pct, [0, 0.25, 0.5, 0.75, 1.0001],
            labels=["EXCELLENT_VALUE", "GOOD_VALUE", "FAIR_VALUE", "EXPENSIVE_RELATIVE_TO_SAMPLE"]).astype(str)

    recs = [clean_row(r) for r in out.to_dict("records")]
    out["main_advantage"] = [("; ".join(advantages(r)[:3]) or "meets all hard requirements") for r in recs]
    out["main_drawback"] = [main_drawback(r) for r in recs]
    out["estimated_total_text"] = [total_text(r) for r in recs]
    return out


def rank(df: pd.DataFrame, strict_margin: float = 5.0) -> pd.DataFrame:
    """Canonical records only; hard gates first, then fit score, then lower total cost.

    STRICT_ALL_IN units get ``strict_margin`` extra ranking points (not fit points), so a
    BASE_RENT_COMPLIANT unit only outranks one when its fit is clearly superior."""
    canon = df[df["is_canonical"]].copy()
    total = canon["estimated_total_monthly_usd"] if "estimated_total_monthly_usd" in canon else canon["rent_usd"]
    canon["_cost"] = total.fillna(canon["rent_usd"])
    order = {"PRIMARY": 0, "STRETCH": 1, "NEAR_MISS": 2, "EXCLUDED": 3}
    canon["_cat"] = canon["category"].map(order)
    # Quiet is the client's first priority: a unit with HIGH estimated noise (and a location good enough to
    # trust that estimate) ranks after every LOW/MEDIUM unit in its category, whatever its fit score.
    canon["_loud"] = ((canon["noise_risk"] == "HIGH") & canon["noise_confidence"].isin(["HIGH", "MEDIUM"])).astype(int)
    strict = canon["budget_class"] == "STRICT_ALL_IN" if "budget_class" in canon else False
    canon["_strict"] = strict.astype(int) if strict is not False else 0
    canon["_rank_score"] = canon["fit_score"] + canon["_strict"] * strict_margin
    # ties go to the known all-in cost, then to the cheaper unit
    canon = canon.sort_values(["_cat", "_loud", "_rank_score", "_strict", "_cost"],
                              ascending=[True, True, False, False, True])
    canon["rank_in_category"] = canon.groupby("category").cumcount() + 1
    return canon.drop(columns=["_cost", "_cat", "_loud", "_rank_score", "_strict"])
