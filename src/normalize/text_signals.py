"""Spanish (and some English) listing-text feature extraction.

Every detected feature returns the phrase that triggered it, so downstream reports can
cite evidence instead of asserting. Negations ("sin amoblar", "no mascotas") win over
positive matches.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

NUM_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "dieciocho": 18, "veinticuatro": 24,
}
ORDINAL_FLOORS = {
    "primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4,
    "quinto": 5, "sexto": 6, "septimo": 7, "sétimo": 7, "setimo": 7, "octavo": 8,
    "noveno": 9, "decimo": 10, "décimo": 10,
}


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def fold(text: str) -> str:
    """Lower-case and strip accents so patterns can be written without them."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _num(token: str) -> float | None:
    token = fold(token.strip())
    if token in NUM_WORDS:
        return float(NUM_WORDS[token])
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


# (feature, positive patterns, negative patterns). Patterns run on folded text.
BOOL_FEATURES: list[tuple[str, list[str], list[str]]] = [
    ("semi_furnished", [r"semiamo(b|u)?blad", r"semiamueblad", r"parcialmente amo(b|u)?blad",
                         r"semifurnished", r"partly furnished"], []),
    ("furnished", [r"\bamoblad[oa]s?\b", r"\bamueblad[oa]s?\b", r"\bfully furnished\b", r"\bfurnished\b"],
     [r"sin amoblar", r"sin amueblar", r"no (esta |viene )?amoblado", r"no (esta |viene )?amueblado",
      r"sin muebles", r"\bunfurnished\b", r"no incluye muebles", r"se entrega vacio"]),
    ("balcony", [r"\bbalcon", r"\bbalcony\b"], [r"sin balcon"]),
    ("terrace", [r"\bterraza\b(?! (comun|compartida|del edificio|en azotea del edificio))", r"\bterrace\b"],
     [r"sin terraza"]),
    ("laundry", [r"lavanderia", r"zona de lavado", r"area de lavado", r"cuarto de lavado", r"patio de lavado",
                  r"lavadora", r"\blaundry\b", r"washer"], [r"sin lavanderia"]),
    ("interior_view", [r"vista (al |hacia el |a )?interior", r"vista interna", r"contra ?frente", r"da al interior",
                        r"hacia el interior", r"no da a la calle", r"interior[- ]facing", r"\binterior view\b"], []),
    ("exterior_view", [r"vista (a la |hacia la )?calle", r"vista exterior", r"vista al (parque|mar|malecon)",
                        r"frente al (parque|mar|malecon)", r"vista a(l)? (la )?avenida", r"\bexterior view\b",
                        r"ocean view", r"park view"], []),
    ("avenue_view", [r"vista a(l)? (la )?av(enida|\.)?\s", r"frente a (la )?av(enida|\.)", r"con vista a av",
                      r"da a (la )?avenida", r"sobre (la )?avenida", r"facing (the )?avenue"], []),
    ("acoustic_windows", [r"ventanas? acustic", r"antirruido", r"anti[\s-]?ruido", r"doble vidrio",
                           r"termopanel", r"insonoriz", r"aislamiento acustico", r"vidrio (doble|laminado)",
                           r"double[- ]glazed", r"soundproof"], []),
    ("quiet_claim", [r"calle tranquila", r"zona tranquila", r"muy tranquil", r"silencios", r"zona residencial",
                      r"ambiente tranquilo", r"\bquiet\b"], []),
    ("elevator", [r"ascensor", r"elevador", r"\belevator\b", r"\blift\b"], [r"sin ascensor", r"no tiene ascensor"]),
    ("security_24h", [r"vigilancia 24", r"seguridad 24", r"porter(o|ia)", r"conserje", r"recepcion 24",
                       r"control de acceso", r"vigilancia", r"24/7 security", r"24h security", r"doorman",
                       r"guardiania", r"agente de seguridad"], []),
    ("gym", [r"gimnasio", r"\bgym\b"], []),
    ("pool", [r"piscina", r"\bpool\b"], []),
    ("coworking", [r"co-?working", r"sala de trabajo", r"business center"], []),
    ("common_areas", [r"zona de parrilla", r"\bparrilla", r"\bbbq\b", r"\bsum\b", r"sala de usos multiples",
                       r"areas? comunes", r"azotea", r"roof ?top", r"terraza comun", r"lounge", r"sala de juegos"], []),
    ("pets_allowed", [r"acepta(n)? mascotas", r"pet[\s-]?friendly", r"se aceptan mascotas", r"mascotas permitidas",
                       r"admite mascotas", r"pets allowed"],
     [r"no (se )?(aceptan|acepta|admite|admiten|permite|permiten) mascotas", r"sin mascotas", r"no mascotas",
      r"no pets", r"mascotas no"]),
    ("parking_included", [r"incluye (un |1 )?(estacionamiento|cochera)", r"con (estacionamiento|cochera)",
                           r"(1|un|una|dos|2) (estacionamiento|cochera)s?", r"parking (included|space)"],
     [r"sin (estacionamiento|cochera)", r"no (incluye|tiene) (estacionamiento|cochera)",
      r"estacionamiento (no incluido|adicional|opcional|se alquila aparte|aparte)"]),
    ("study", [r"(con|y|\+) estudio\b", r"home office", r"sala de estudio", r"ambiente (de|para) estudio",
                r"\bescritorio\b", r"\bstudy room\b", r"\boffice space\b"], []),
    ("walk_in_closet", [r"walk[\s-]?in", r"vestidor", r"closets? amplio", r"amplios? closets?"], []),
    ("internet_included", [r"internet incluido", r"incluye internet", r"wifi incluido", r"incluye wifi",
                            r"internet included", r"(internet|wifi) y (cable|tv)", r"servicios incluidos"], []),
    ("maintenance_included", [r"mantenimiento incluido", r"incluye (el )?mantenimiento", r"incl(uye|\.)? mant",
                               r"maintenance included"],
     [r"no incluye (el )?mantenimiento", r"mas mantenimiento", r"\+ ?mantenimiento", r"mantenimiento aparte"]),
    ("studio_text", [r"monoambiente", r"tipo estudio", r"departamento estudio", r"\bflat estudio\b",
                      r"\bstudio apartment\b", r"\bmini ?depa", r"\bloft\b"], []),
    ("short_term", [r"temporal", r"por dias", r"por semanas", r"airbnb", r"corta estancia", r"short[- ]term"], []),
    ("shared", [r"habitacion en departamento compartido", r"cuarto compartido", r"se alquila (una )?habitacion",
                 r"alquilo (una )?habitacion", r"room for rent"], []),
]

_COMPILED = [(name, [re.compile(p) for p in pos], [re.compile(n) for n in neg]) for name, pos, neg in BOOL_FEATURES]


def _snippet(text: str, m: re.Match, pad: int = 25) -> str:
    return text[max(0, m.start() - pad): m.end() + pad].strip()


def extract_signals(*texts: str | None) -> dict[str, Any]:
    """Return {feature: True/False} for features found, plus 'evidence' and parsed numbers."""
    raw = " \n ".join(strip_html(t) for t in texts if t)
    text = fold(raw)
    # glue "semi amoblado" / "semi-amueblado" / "semi furnished" into one token so the plain
    # furnished patterns cannot match inside them
    text = re.sub(r"\bsemi[\s-]+(amo|amue|furn)", r"semi\1", text)
    out: dict[str, Any] = {"evidence": []}
    for name, pos, neg in _COMPILED:
        neg_hit = next((m for p in neg for m in [p.search(text)] if m), None)
        if neg_hit:
            out[name] = False
            out["evidence"].append(f"{name}=False: …{_snippet(text, neg_hit)}…")
            continue
        pos_hit = next((m for p in pos for m in [p.search(text)] if m), None)
        if pos_hit:
            out[name] = True
            out["evidence"].append(f"{name}: …{_snippet(text, pos_hit)}…")
    if out.get("semi_furnished") and out.get("furnished") is None:
        out["furnished"] = False

    num = r"(\d{1,2}|un|uno|una|dos|tres|cuatro|seis|doce|dieciocho|veinticuatro)"
    m = re.search(rf"(contrato|plazo|alquiler|arrendamiento)[^.\n]{{0,25}}?(minimo|min\.?)?[^.\n]{{0,10}}?{num}\s*(anos?|mes(?:es)?)\b", text) \
        or re.search(rf"minimo (de )?{num}\s*(anos?|mes(?:es)?)\b", text)
    if m:
        qty = _num(m.group(m.lastindex - 1))
        unit = m.group(m.lastindex)
        if qty:
            out["minimum_contract_months"] = int(qty * 12 if unit.startswith("ano") else qty)
            out["evidence"].append(f"contract: …{_snippet(text, m)}…")

    m = re.search(rf"{num}\s*mes(?:es)?\s*(de )?garantia", text) \
        or re.search(rf"garantia[:\s]*(de )?{num}\s*mes(?:es)?", text)
    if m:
        groups = [g for g in m.groups() if g]
        qty = next((_num(g) for g in groups if _num(g) is not None), None)
        if qty is not None and qty <= 12:
            out["deposit_months"] = qty
            out["evidence"].append(f"deposit: …{_snippet(text, m)}…")

    m = re.search(rf"{num}\s*mes(?:es)?\s*(de )?adelanto", text) \
        or re.search(rf"adelanto[:\s]*(de )?{num}\s*mes(?:es)?", text)
    if m:
        groups = [g for g in m.groups() if g]
        qty = next((_num(g) for g in groups if _num(g) is not None), None)
        if qty is not None and qty <= 12:
            out["advance_months"] = qty
            out["evidence"].append(f"advance: …{_snippet(text, m)}…")

    m = re.search(r"(?:\b|^)(\d{1,2})\s*(?:°|º|er|do|ro|to|vo|mo|no)?\s*piso\b", text) \
        or re.search(r"\bpiso\s*(?:n[°º.]?\s*)?(\d{1,2})\b", text)
    if m:
        out["floor"] = int(m.group(1))
    else:
        m = re.search(r"\b(" + "|".join(ORDINAL_FLOORS) + r")\s+piso\b", text)
        if m:
            out["floor"] = ORDINAL_FLOORS[m.group(1)]

    m = re.search(r"mantenimiento[^\d\n]{0,25}?(s/\.?|us\$|usd|\$|soles|dolares)?\s*([\d][\d.,]*)\s*(soles|dolares|usd|pen)?", text)
    if m and not out.get("maintenance_included"):
        amount = parse_amount(m.group(2))
        cur_token = (m.group(1) or m.group(3) or "").strip()
        currency = "USD" if cur_token in ("us$", "usd", "$", "dolares") else ("PEN" if cur_token else None)
        if amount and 30 <= amount <= 2500:
            out["maintenance_text_amount"] = amount
            out["maintenance_text_currency"] = currency or "PEN"   # Lima maintenance is almost always quoted in soles
            out["maintenance_text_currency_assumed"] = currency is None
            out["evidence"].append(f"maintenance: …{_snippet(text, m)}…")

    utils = re.findall(r"incluye[n]?\s+((?:agua|luz|gas|internet|wifi|cable|mantenimiento|servicios|arbitrios)"
                       r"(?:\s*(?:,|y|e)\s*(?:agua|luz|gas|internet|wifi|cable|mantenimiento|servicios|arbitrios))*)", text)
    if utils:
        out["utilities_included"] = "; ".join(sorted(set(utils)))
    return out


def parse_amount(token: str | None) -> float | None:
    """Parse '3.500', '3,500', '1.250,50', '950' → float."""
    if token is None:
        return None
    if isinstance(token, (int, float)):
        return float(token)
    s = re.sub(r"[^\d.,]", "", str(token))
    if not s:
        return None
    if "," in s and "." in s:
        # the last separator is the decimal one
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", "") if len(parts[-1]) == 3 else s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 and len(parts) >= 2:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_money(text: str | None) -> tuple[float | None, str | None]:
    """'USD 950' / 'US$ 1,000' / 'S/ 3.200' / 'S/. 350' → (amount, 'USD'|'PEN')."""
    if not text:
        return None, None
    t = fold(str(text))
    currency = None
    if re.search(r"us\$|usd|u\$s|\bdolar|\$", t) and not re.search(r"s/", t):
        currency = "USD"
    if re.search(r"s/|\bpen\b|\bsol(es)?\b", t):
        currency = "PEN"
    m = re.search(r"\d[\d.,]*", t)
    return (parse_amount(m.group(0)) if m else None), currency


def relative_date_days(text: str | None) -> int | None:
    """'Publicado hace 3 días' → 3; 'hoy' → 0; 'ayer' → 1; 'hace 2 meses' → 60."""
    if not text:
        return None
    t = fold(text)
    if re.search(r"\bhoy\b|hace (\d+ )?(minutos?|horas?)", t):
        return 0
    if "ayer" in t:
        return 1
    m = re.search(r"hace\s+(mas de\s+)?(\d+|un|una|dos|tres)\s+(dias?|semanas?|mes(es)?|anos?)", t)
    if not m:
        return None
    qty = _num(m.group(2)) or 0
    unit = m.group(3)
    factor = 1 if unit.startswith("dia") else 7 if unit.startswith("semana") else 30 if unit.startswith("mes") else 365
    return int(qty * factor)
