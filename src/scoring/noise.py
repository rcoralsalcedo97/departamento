"""Quietness / noise-risk estimate.

Combines geospatial exposure (distance to major roads and arterials, nightclubs, bar and
restaurant clusters) with listing-text evidence (interior-facing, acoustic windows, avenue
view, floor). This is an *estimate*; the report always recommends checking noise in person.
"""
from __future__ import annotations

import math
import re

from ..normalize.text_signals import fold

# Major arterials in and around Miraflores (heavy traffic). Paseo de la República *is* the Vía Expresa.
ARTERIAL_RX = re.compile(
    r"paseo de la republica|via expresa|\b(?:av(?:enida)?\.?\s+)(?:"
    r"arequipa|(?:alfredo\s+)?benavides|angamos|(?:jose\s+)?larco|(?:jose\s+)?pardo|ricardo palma|diagonal|"
    r"(?:republica de\s+)?panama|(?:del\s+)?ejercito|comandante espinar|(?:la\s+)?aramburu|santa cruz|armendariz|"
    r"petit thouars|reducto|28 de julio)\b|circuito de playas|costa verde")
NOISE_LABELS = ("LIKELY QUIET", "POSSIBLY QUIET", "NOISE UNCERTAIN", "LIKELY NOISY")


def arterial_evidence(row: dict) -> tuple[str | None, str | None]:
    """(street the unit is ON, arterial merely MENTIONED) from the listing's own address/title/description."""
    from ..geospatial.geocode import address_evidence
    ev = address_evidence(row.get("address"), row.get("title"), row.get("description"))
    on = ev["street"] if ev and ARTERIAL_RX.search(fold(ev["street"])) else None
    if on is None and isinstance(row.get("address"), str) and ARTERIAL_RX.search(fold(row["address"])):
        on = row["address"]
    blob = fold(" ".join(str(row.get(k) or "") for k in ("title", "description")))
    m = ARTERIAL_RX.search(blob)
    return on, (m.group(0) if m else None)


def noise_label(risk: str, conf: str, on_arterial: bool, avenue_view: bool, interior: bool,
                positive_text: bool = False) -> str:
    """Plain-language category that never claims more than the evidence supports."""
    if avenue_view or (on_arterial and not interior):
        return "LIKELY NOISY"
    if risk == "HIGH" and conf in ("HIGH", "MEDIUM"):
        return "LIKELY NOISY"
    if risk == "LOW" and conf in ("HIGH", "MEDIUM"):
        return "LIKELY QUIET"
    if risk == "LOW" or (conf == "LOW" and risk != "HIGH" and positive_text):
        return "POSSIBLY QUIET"          # positive listing wording (interior-facing, acoustic windows) only
    return "NOISE UNCERTAIN"


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def assess_noise(row: dict, cfg: dict) -> dict:
    nm = cfg["noise_model"]
    base = float(nm["baseline"])
    geo_delta, text_delta = 0.0, 0.0
    reasons: list[str] = []
    flags: set[str] = set()
    geo_ok = _num(row.get("dist_major_road_m")) is not None

    if geo_ok:
        d, name = _num(row["dist_major_road_m"]), row.get("major_road_name") or "major road"
        m = nm["major_road"]
        if d <= m["strong_m"]:
            geo_delta -= m["strong_penalty"]
            reasons.append(f"{d:.0f} m from {name} (major road)")
            flags.add("DIRECT_MAJOR_AVENUE")
        elif d <= m["moderate_m"]:
            geo_delta -= m["moderate_penalty"]
            reasons.append(f"{d:.0f} m from {name} (major road)")
        elif d <= m["mild_m"]:
            geo_delta -= m["mild_penalty"]
            reasons.append(f"{d:.0f} m from {name}")
        else:
            reasons.append(f"nearest major road ({name}) {d:.0f} m away")

        d2 = _num(row.get("dist_arterial_road_m"))
        if d2 is not None:
            a = nm["arterial_road"]
            name2 = row.get("arterial_road_name") or "arterial"
            if d2 <= a["strong_m"]:
                geo_delta -= a["strong_penalty"]
                reasons.append(f"fronts/adjacent to {name2} ({d2:.0f} m)")
            elif d2 <= a["moderate_m"]:
                geo_delta -= a["moderate_penalty"]
                reasons.append(f"{d2:.0f} m from {name2}")

        dn = _num(row.get("dist_nightclub_m"))
        n = nm["nightclub"]
        if dn is not None and dn <= n["strong_m"]:
            geo_delta -= n["strong_penalty"]
            reasons.append(f"nightclub '{row.get('nightclub_name')}' {dn:.0f} m away")
            flags.add("NIGHTLIFE_PROXIMITY")
        elif dn is not None and dn <= n["moderate_m"]:
            geo_delta -= n["moderate_penalty"]
            reasons.append(f"nightclub '{row.get('nightclub_name')}' {dn:.0f} m away")
            flags.add("NIGHTLIFE_PROXIMITY")
        elif dn is not None and dn <= n["mild_m"]:
            geo_delta -= n["mild_penalty"]
            reasons.append(f"nightclub {dn:.0f} m away")
        else:
            reasons.append(f"no nightclub mapped within {n['mild_m']} m")

        bars = int(_num(row.get("bars_within_m")) or 0)
        b = nm["bar_cluster"]
        if bars >= b["many_threshold"]:
            geo_delta -= b["many_penalty"]
            reasons.append(f"{bars} bars/pubs within {b['radius_m']} m")
            flags.add("NIGHTLIFE_PROXIMITY")
        elif bars > 0:
            geo_delta -= b["few_penalty"]
            reasons.append(f"{bars} bar(s) within {b['radius_m']} m")
        rests = int(_num(row.get("restaurants_within_m")) or 0)
        r = nm["restaurant_cluster"]
        if rests >= r["threshold"]:
            geo_delta -= r["penalty"]
            reasons.append(f"{rests} restaurants within {r['radius_m']} m (busy frontage)")

    t = nm["text_signals"]
    if row.get("interior_view") is True:
        text_delta += t["interior_view"]
        reasons.append("listing says interior-facing / contrafrente")
    if row.get("acoustic_windows") is True:
        text_delta += t["acoustic_windows"]
        reasons.append("acoustic / double-glazed windows mentioned")
    if row.get("avenue_view") is True:
        text_delta += t["avenue_view"]
        reasons.append("listing says it faces an avenue")
        flags.add("DIRECT_MAJOR_AVENUE")
    elif row.get("exterior_view") is True and geo_ok and (_num(row.get("dist_major_road_m")) or 999) <= 150:
        text_delta -= 4
        reasons.append("street-facing unit near a major road")
    on_arterial, mentioned = arterial_evidence(row)
    if on_arterial:
        flags.add("ON_MAJOR_ARTERIAL")
        if row.get("interior_view") is not True:
            text_delta += t["avenue_view"]
        reasons.append(f"listing address is on {on_arterial} — a major arterial"
                       + (" (Vía Expresa)" if "republica" in fold(on_arterial) else ""))
    elif mentioned:
        flags.add("MAJOR_ARTERIAL_MENTIONED")
        reasons.append(f"listing mentions '{mentioned}' (major arterial) — check the distance")
    if row.get("quiet_claim") is True:
        text_delta += t["quiet_street_claim"]
        reasons.append("seller describes the street as quiet (unverified claim)")
    floor = _num(row.get("floor"))
    if floor is not None and floor >= t["high_floor_min"]:
        text_delta += t["high_floor_bonus"]
        reasons.append(f"high floor ({floor:.0f})")

    if geo_ok:
        score = base + geo_delta + text_delta
    else:
        # no coordinates: shrink towards neutral and make uncertainty explicit
        score = 50 + 0.6 * text_delta
        reasons.insert(0, "no usable coordinates — text evidence only")
    score = max(0.0, min(100.0, score))

    th = nm["risk_thresholds"]
    risk = "LOW" if score >= th["low_from"] else "MEDIUM" if score >= th["medium_from"] else "HIGH"
    supported = geo_ok or text_delta != 0
    if not supported:
        risk = "UNKNOWN"      # no location and no noise wording: the exposure is genuinely unknown
        reasons = [r for r in reasons if not r.startswith("no usable coordinates")]
        reasons.insert(0, "no map location and no noise-related wording in the listing — street exposure unknown")
    precision = row.get("coord_precision")
    orientation_known = any(row.get(k) is True for k in ("interior_view", "exterior_view", "avenue_view"))
    if not geo_ok:
        conf = "LOW"
    elif precision in ("APPROXIMATE", "STREET_LEVEL"):
        conf = "LOW"
    elif precision in ("EXACT", "STREET_NUMBER") and orientation_known:
        conf = "HIGH"
    else:
        conf = "MEDIUM"
    if risk == "HIGH":
        flags.add("HIGH_NOISE_RISK")
    if precision in ("APPROXIMATE", "STREET_LEVEL"):
        reasons.append("portal location is approximate")

    reason = "; ".join(reasons[:6])
    reason = reason[0].upper() + reason[1:] + f". Quietness estimate: {conf.lower()} confidence."
    label = noise_label(risk, conf, bool(on_arterial), row.get("avenue_view") is True, row.get("interior_view") is True,
                        row.get("interior_view") is True or row.get("acoustic_windows") is True)
    # the numeric score stays neutral (50) inside the fit score, but is only *shown* where it is supportable
    return {"quietness_score_0_100": round(score), "quietness_supported": supported, "noise_risk": risk,
            "noise_confidence": conf, "noise_label": label, "quietness_reason": reason, "_noise_flags": sorted(flags)}
