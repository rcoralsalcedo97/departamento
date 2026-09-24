"""FOREIGN_TENANT_FRIENDLINESS — evidence-based, never inferred from silence.

HIGH               listing explicitly welcomes foreigners / passports / corporate leases
MEDIUM             practical signals only (temporary stays, executives, no guarantor, English listing,
                   furnished + utilities included)
POTENTIAL_FRICTION listing explicitly asks for something a newly arrived foreigner may struggle with
                   (Peruvian guarantor/aval, carné de extranjería, DNI) or excludes foreigners
UNKNOWN            the listing says nothing relevant — the normal case, and NOT a penalty

The classification is informational: it is shown to the client but is not part of the fit score.
"""
from __future__ import annotations

import re

from .text_signals import fold, strip_html

STRONG = [
    (r"(acepta(n|mos)?|se aceptan|bienvenid[oa]s?|ideal para|apto para|perfecto para)\s+(a\s+)?extranjer", "accepts foreigners"),
    (r"\bexpats?\b|expatriad", "expat-oriented"),
    (r"pasaporte|passport", "passport mentioned"),
    (r"contrato corporativo|alquiler corporativo|a nombre de (la )?empresa|corporate (lease|rental|housing)",
     "corporate lease possible"),
    (r"foreigners? (are )?(welcome|accepted)|english (is )?spoken|se habla ingles", "foreigners welcome / English spoken"),
]
SOFT = [
    (r"alquiler temporal|temporada|corta estancia|estancia corta|por meses|short[- ]term|minimo (1|2|3|6) mes",
     "temporary / short stays offered"),
    (r"ejecutiv", "aimed at executives"),
    (r"sin aval|no (se )?requiere aval|sin garante|sin fiador", "no guarantor required"),
]
FRICTION = [
    (r"no (se )?(acepta|aceptan|aceptamos) extranjer|solo (peruanos|nacionales)", "foreigners explicitly not accepted"),
    (r"(?<!sin )(?<!no requiere )(?<!no se requiere )\b(aval|fiador|garante)\b", "guarantor (aval/fiador) requested"),
    (r"carn[eé]t? de extranjer", "carné de extranjería requested"),
    (r"(copia|presentar|requisito[s]?:?)[^.\n]{0,25}\bdni\b", "Peruvian DNI requested"),
]
NOTED = [
    (r"boletas? de pago|constancia de (ingresos|trabajo)|sustento de ingresos|recibos? por honorarios|"
     r"certificado de trabajo|proof of income|carta de trabajo", "proof of income requested"),
    (r"servicios incluidos|incluye (agua|luz|internet|wifi|servicios|gas)", "utilities included"),
]
ENGLISH = re.compile(r"\b(the|with|apartment|bedroom|fully|located|walking distance|available)\b")


def assess_foreign_tenant(title: str | None, description: str | None, furnished: bool | None,
                          min_contract_months: float | None) -> tuple[str, str]:
    raw = strip_html(" ".join(x for x in (title, description) if x))
    text = fold(raw)
    if not text:
        return "UNKNOWN", ""
    strong = [label for rx, label in STRONG if re.search(rx, text)]
    soft = [label for rx, label in SOFT if re.search(rx, text)]
    friction = [label for rx, label in FRICTION if re.search(rx, text)]
    noted = [label for rx, label in NOTED if re.search(rx, text)]
    if len(ENGLISH.findall(text)) >= 6:
        soft.append("listing written in English")
    if furnished is True:
        noted.append("furnished")
    if min_contract_months:
        noted.append(f"minimum stay {int(min_contract_months)} months")
    evidence = "; ".join(dict.fromkeys(strong + soft + friction + noted))
    if friction:
        return "POTENTIAL_FRICTION", evidence
    if strong:
        return "HIGH", evidence
    if soft or ("furnished" in noted and "utilities included" in noted):
        return "MEDIUM", evidence
    return "UNKNOWN", evidence
