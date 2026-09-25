"""Evidence-based geocoding (OSM Nominatim) for listings without published coordinates.

Only *specific* location evidence written in the listing itself is geocoded:
  * street + number   ("Calle Schell 345", "Av. José Pardo N° 620")      → query the address
  * street + block    ("Av. Pardo cuadra 5", "cuadra 3 de la calle Berlín") → query the street
The address field is read first, then the title, then the description. Proximity phrases
("a 2 cuadras de Av. Larco", "cerca al Parque Kennedy") are not the unit's address and are
ignored. District or neighbourhood names alone ("Miraflores, Lima", "San Antonio") are never
geocoded — those listings keep UNKNOWN coordinates.

Confidence: HIGH = Nominatim matched the house number (coord_precision STREET_NUMBER);
MEDIUM = only the street was matched (coord_precision STREET_LEVEL — a point somewhere on that
street, so the noise model treats it as low confidence and never demotes on it).
Policy-compliant: ≤ 1 request/s, identifying User-Agent, results cached, bounded to the Miraflores bbox.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from rapidfuzz import fuzz

from ..normalize.text_signals import fold

NOMINATIM = "https://nominatim.openstreetmap.org/search"

_STREET_TYPE = r"(?P<type>av(?:enida)?\.?|calle|ca\.|jr\.?|jir[oó]n|pasaje|psje\.?|pje\.?|malec[oó]n|alameda|prolongaci[oó]n|prol\.)"
_WORD = r"(?:\d{1,2}\s+de|[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'][A-Za-zÁÉÍÓÚÜÑáéíóúüñ'\.]*)"
_NAME = rf"(?P<name>{_WORD}(?:\s+{_WORD}){{0,4}}?)"
_NOT_AN_ADDRESS_NUMBER = (r"(?!\s*(?:m2|m²|mts?\b|metros|m\b|soles|s/|usd|us\$|d[oó]lares|cuadras?|min\b|minutos|km|"
                          r"pisos\b|dorm|hab|horas|hrs|h\b|a[nñ]os|%))")
STREET_NUMBER_RX = re.compile(
    rf"\b{_STREET_TYPE}\s+{_NAME}\s*,?\s*(?:n[°º\.o]?\s*|nro\.?\s*|#\s*)?(?P<num>\d{{2,4}})\b{_NOT_AN_ADDRESS_NUMBER}", re.I)
STREET_BLOCK_RX = re.compile(
    rf"\b{_STREET_TYPE}\s+{_NAME}\s*,?\s*(?:cuadra|cdra\.?|cda\.?)\s*(?P<num>\d{{1,2}})\b", re.I)
# name last, no number after it to anchor on: continue only through Capitalised words and de/la connectors
_TAIL_NAME = (r"(?P<name>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'][\wÁÉÍÓÚÜÑáéíóúüñ'\.]*"
              r"(?:\s+(?:(?:de|del|la|las|los)\s+){0,2}(?-i:[A-ZÁÉÍÓÚÜÑ][\wÁÉÍÓÚÜÑáéíóúüñ'\.]*)){0,4})")
BLOCK_FIRST_RX = re.compile(
    rf"\b(?:cuadra|cdra\.?|cda\.?)\s*(?P<num>\d{{1,2}})\s+de\s+(?:la\s+|el\s+)?{_STREET_TYPE}\s+{_TAIL_NAME}"
    r"(?=[\s,\.;:\)]|$)", re.I)
# the phrase just before a street mention that makes it a *reference point*, not the unit's address
PROXIMITY_RX = re.compile(r"(?:a\s+(?:\d+|una|media|dos|tres|cuatro|cinco|pocas)\s+cuadras?\s+(?:de|del)|cerca\s+(?:de|a|al|del)|"
                          r"a\s+pasos\s+(?:de|del)|frente\s+(?:a|al)|junto\s+(?:a|al)|a\s+\d+\s+min(?:utos)?\s+(?:de|del)|"
                          r"a\s+minutos\s+(?:de|del)|pr[oó]ximo\s+(?:a|al)|colindante\s+(?:a|con)|entre|esquina\s+(?:con|de))"
                          r"\s*(?:la\s+|el\s+)?$", re.I)
NOT_STREET_NAMES = {"tranquila", "principal", "interior", "privada", "residencial", "comercial", "cerrada", "exclusiva",
                    "segura", "arborizada", "centrica", "céntrica", "peatonal", "muy", "super", "con", "sin", "de"}
TYPE_CANON = {"av": "Avenida", "avenida": "Avenida", "calle": "Calle", "ca": "Calle", "jr": "Jirón", "jiron": "Jirón",
              "pasaje": "Pasaje", "psje": "Pasaje", "pje": "Pasaje", "malecon": "Malecón", "alameda": "Alameda",
              "prolongacion": "Prolongación", "prol": "Prolongación"}


def _street(m: re.Match) -> str | None:
    name = re.sub(r"\s+", " ", m.group("name")).strip(" .,")
    if not name or fold(name.split()[0]) in NOT_STREET_NAMES:
        return None
    typ = TYPE_CANON.get(fold(m.group("type")).rstrip("."), m.group("type"))
    return f"{typ} {name}"


def _proximity(text: str, start: int) -> bool:
    return bool(PROXIMITY_RX.search(text[max(0, start - 40):start]))


def address_evidence(address: str | None, title: str | None, description: str | None) -> dict | None:
    """First specific address found in the listing: {kind, street, number, text, field} or None."""
    for field, text in (("address", address), ("title", title), ("description", description)):
        if not isinstance(text, str) or not text.strip():
            continue
        for m in STREET_NUMBER_RX.finditer(text):
            street = _street(m)
            if street and not _proximity(text, m.start()):
                return {"kind": "STREET_NUMBER", "street": street, "number": m.group("num"),
                        "text": m.group(0).strip(), "field": field}
        for rx in (STREET_BLOCK_RX, BLOCK_FIRST_RX):
            for m in rx.finditer(text):
                street = _street(m)
                if street and not _proximity(text, m.start()):
                    return {"kind": "STREET_BLOCK", "street": street, "number": m.group("num"),
                            "text": m.group(0).strip(), "field": field}
    return None


def geocodable(address: str | None) -> bool:
    return address_evidence(address, None, None) is not None


def _judge(hit: dict, ev: dict) -> tuple[str, str] | None:
    """(geocoding_confidence, coord_precision) for a Nominatim hit, or None if it does not match the evidence."""
    road = fold(str((hit.get("address") or {}).get("road") or hit.get("name") or ""))
    wanted = fold(ev["street"].split(" ", 1)[-1])
    if not road or fuzz.partial_ratio(wanted, road) < 80:
        return None
    house = str((hit.get("address") or {}).get("house_number") or "")
    if ev["kind"] == "STREET_NUMBER" and house and re.sub(r"\D", "", house.split(";")[0]) == ev["number"]:
        return "HIGH", "STREET_NUMBER"
    return "MEDIUM", "STREET_LEVEL"


def geocode_missing(df, cfg: dict, http, cache_path: Path, max_queries: int = 150) -> tuple[int, list[str]]:
    """Fill coordinates only from specific address evidence. Returns (Nominatim queries made, errors)."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    s, w, n, e = cfg["location"]["bbox"]
    district = cfg["location"]["district"]
    done, errors = 0, []
    for col in ("geocoding_confidence", "address_evidence"):
        if col not in df.columns:
            df[col] = None
    for i, row in df.iterrows():
        lat = row.get("latitude")
        if lat is not None and lat == lat:          # has coordinates (not NaN)
            continue
        ev = address_evidence(row.get("address"), row.get("title"), row.get("description"))
        if ev is None:
            continue
        df.at[i, "address_evidence"] = f"{ev['kind']} from {ev['field']}: “{ev['text']}”"
        street_q = f"{ev['street']} {ev['number']}" if ev["kind"] == "STREET_NUMBER" else ev["street"]
        q = f"{street_q}, {district}, Lima, Peru"
        if q not in cache:
            if done >= max_queries:
                break
            try:
                r = http.request_json("GET", NOMINATIM, params={
                    "q": q, "format": "jsonv2", "limit": 3, "countrycodes": "pe", "addressdetails": 1,
                    "viewbox": f"{w},{n},{e},{s}", "bounded": 1})
                cache[q] = r.json() if r.status_code == 200 else []
                done += 1
                time.sleep(1.1)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
                break
        for hit in cache.get(q) or []:
            verdict = _judge(hit, ev)
            if verdict is None:
                continue
            conf, precision = verdict
            df.at[i, "latitude"], df.at[i, "longitude"] = float(hit["lat"]), float(hit["lon"])
            df.at[i, "coord_source"] = "GEOCODED_ADDRESS" if ev["field"] == "address" else "GEOCODED_TEXT"
            df.at[i, "coord_precision"] = precision
            df.at[i, "geocoding_confidence"] = conf
            break
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return done, errors
