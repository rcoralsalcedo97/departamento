"""Formatting helpers shared by the Excel and PDF deliverables."""
from __future__ import annotations

import math
import re
from urllib.parse import quote

SOURCE_LABELS = {"urbania": "Urbania", "adondevivir": "Adondevivir", "mercadolibre": "Mercado Libre",
                 "manual": "Manual entry"}


def records(df) -> list[dict]:
    """DataFrame → list of dicts with NaN replaced by None (so 'nan' never reaches a client document)."""
    out = []
    for r in df.to_dict("records"):
        out.append({k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()})
    return out


def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def yn(v, unknown="UNKNOWN") -> str:
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return unknown


def furnished_text(r) -> str:
    if r.get("furnished") is True:
        return "Yes"
    if r.get("semi_furnished") is True:
        return "Semi"
    if r.get("furnished") is False:
        return "No"
    return "UNKNOWN"


def parking_text(r) -> str:
    n = num(r.get("parking_spaces"))
    if n is not None:
        return f"Yes ({n:.0f})" if n > 0 else "No"
    return yn(r.get("parking_included"))


def floor_text(r):
    f = num(r.get("floor"))
    return int(f) if f is not None else "UNKNOWN"


def maintenance_text(r) -> str:
    if r.get("maintenance_included_in_rent") is True:
        return "Included in rent"
    pen, usd = num(r.get("maintenance_pen")), num(r.get("maintenance_usd"))
    if r.get("maintenance_currency") == "PEN" and pen is not None:
        return f"S/ {pen:,.0f} (≈ USD {usd:,.0f})"
    if usd is not None:
        return f"USD {usd:,.0f}"
    return "UNKNOWN"


def contract_text(r) -> str:
    m = num(r.get("minimum_contract_months"))
    return f"{m:.0f} months min." if m is not None else "UNKNOWN"


def deposit_text(r) -> str:
    d = num(r.get("deposit_months"))
    adv = num(r.get("advance_months"))
    parts = []
    if d is not None:
        parts.append(f"{d:g} month{'s' if d != 1 else ''} deposit")
    if adv is not None:
        parts.append(f"{adv:g} in advance")
    return "; ".join(parts) if parts else "UNKNOWN"


def sources_text(r) -> str:
    srcs = str(r.get("duplicate_sources") or r.get("source") or "")
    return " + ".join(SOURCE_LABELS.get(s.strip(), s.strip()) for s in srcs.split(";") if s.strip())


def property_label(r) -> str:
    beds = num(r.get("bedrooms"))
    area = num(r.get("area_m2"))
    where = r.get("address") or r.get("subarea") or r.get("district") or ""
    where = re.sub(r"\s*,?\s*(Miraflores|Lima)(,\s*Lima)*\s*$", "", str(where), flags=re.I).strip(" ,")
    head = f"{beds:.0f}BR" if beds is not None else "?BR"
    if area:
        head += f" · {area:.0f} m²"
    return f"{head} — {where}" if where else f"{head} — {str(r.get('title') or '')[:60]}"


def location_text(r) -> str:
    where = r.get("address") or r.get("subarea") or "address not published"
    notes = r.get("location_notes") or ""
    return f"{where}" + (f" · {notes}" if notes else "")


def whatsapp_url(r) -> str | None:
    digits = re.sub(r"\D", "", str(r.get("whatsapp") or r.get("phone") or ""))
    if not (digits.startswith("519") and len(digits) == 11):
        return None
    msg = (f"Hola, vi su anuncio del departamento en Miraflores ({r.get('source_url')}). "
           f"¿Sigue disponible? ¿Podría indicarme el costo de mantenimiento y las condiciones del contrato? Gracias.")
    return f"https://wa.me/{digits}?text={quote(msg)}"


def map_url(r) -> str | None:
    lat, lon = num(r.get("latitude")), num(r.get("longitude"))
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
    if r.get("address"):
        return "https://www.google.com/maps/search/?api=1&query=" + quote(f"{r['address']}, Miraflores, Lima, Peru")
    return None


def contact_text(r) -> str:
    parts = []
    who = r.get("agency_name") or r.get("agent_name")
    if who:
        parts.append(str(who))
    if r.get("whatsapp"):
        parts.append(f"WhatsApp {r['whatsapp']}")
    elif r.get("phone"):
        parts.append(f"Tel. {r['phone']}")
    if not (r.get("whatsapp") or r.get("phone")):
        # no phone published (free-plan list output has none): the listing page's own form is the contact path
        parts.append(f"Contact via listing ({sources_text(r) or 'portal'} contact form)")
    return " · ".join(parts)


def noise_text(r) -> str:
    return (f"{r.get('noise_label') or 'NOISE UNCERTAIN'} · {r.get('noise_risk') or 'UNKNOWN'} risk · "
            f"{str(r.get('noise_confidence') or 'low').lower()} confidence")


def quietness_value(r):
    """The 0–100 score only where evidence supports it (location or noise wording); otherwise a dash."""
    if r.get("quietness_supported") is False or r.get("noise_risk") == "UNKNOWN":
        return "—"
    return num(r.get("quietness_score_0_100"))
