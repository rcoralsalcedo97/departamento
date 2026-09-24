"""Turn mapped source records into consistent, analysis-ready listings."""
from __future__ import annotations

import re

from ..models import Listing
from .currency import FxRate, apply_currency
from .text_signals import extract_signals, fold

# structured value (from the portal) always wins; text only fills UNKNOWNs
TEXT_FILLABLE = [
    "furnished", "semi_furnished", "balcony", "terrace", "laundry", "interior_view", "exterior_view",
    "acoustic_windows", "elevator", "security_24h", "gym", "pool", "coworking", "common_areas",
    "pets_allowed", "study", "walk_in_closet", "avenue_view", "quiet_claim", "internet_included",
    "minimum_contract_months", "deposit_months", "advance_months", "floor", "utilities_included",
]
TEXT_RENAMES = {"studio_text": "studio_text", "short_term": "short_term_text", "shared": "shared_room_text"}


OTHER_DISTRICTS = ("san isidro", "surquillo", "barranco", "santiago de surco", "surco", "san borja", "lince",
                   "jesus maria", "magdalena", "san miguel", "chorrillos", "la victoria", "lima cercado")


def detect_district(lst: Listing, cfg: dict) -> str | None:
    """District as stated by the listing (coordinates are checked later against the OSM outline).

    The structured district field wins over free text: titles such as "Límite Miraflores" are
    common for units that are actually in Surquillo or San Isidro.
    """
    target = cfg["location"]["district"]
    excluded = cfg["location"].get("exclude_district_tokens", [])
    field = fold(" | ".join(x for x in (lst.district, lst.subarea) if x))
    if field:
        for token in excluded:
            if token in field:
                return token.title()
        if fold(target) in field:
            return target
        for other in OTHER_DISTRICTS:
            if other in field:
                if fold(target) in fold(lst.title or ""):
                    lst.text_signals.append(f"title mentions {target} but district field says '{lst.district}'")
                return other.title()
        if lst.district:
            return lst.district
    blob = fold(" | ".join(x for x in (lst.address, lst.title) if x))
    for token in excluded:
        if token in blob:
            return token.title()
    if fold(target) in blob:
        return target
    return lst.district


def normalize_listing(lst: Listing, cfg: dict, fx: FxRate) -> Listing:
    sig = extract_signals(lst.title, lst.description, " ; ".join(lst.amenities))
    for field in TEXT_FILLABLE:
        if getattr(lst, field) is None and field in sig:
            setattr(lst, field, sig[field])
    for src, dst in TEXT_RENAMES.items():
        if src in sig and getattr(lst, dst) is None:
            setattr(lst, dst, sig[src])

    if lst.parking_included is None:
        if lst.parking_spaces is not None:
            lst.parking_included = lst.parking_spaces > 0
        elif "parking_included" in sig:
            lst.parking_included = sig["parking_included"]

    # maintenance: structured > "incluido" in text > amount quoted in text
    if lst.maintenance_fee is None and lst.maintenance_included_in_rent is None:
        if sig.get("maintenance_included") is True:
            lst.maintenance_included_in_rent = True
        elif sig.get("maintenance_text_amount"):
            lst.maintenance_fee = sig["maintenance_text_amount"]
            lst.maintenance_currency = sig["maintenance_text_currency"]
            note = "maintenance amount read from description"
            if sig.get("maintenance_text_currency_assumed"):
                note += " (currency not stated — assumed PEN)"
            sig["evidence"].append(note)

    lst.text_signals = list(dict.fromkeys(lst.text_signals + sig["evidence"]))
    if lst.raw_description is None:
        lst.raw_description = lst.description

    # bedrooms: a studio is 0 unless the listing itself classifies it as 1 dormitorio
    if lst.bedrooms is None and lst.title:
        m = re.search(r"(\d)\s*(dormitorio|dorm\.?|habitaci[oó]n|hab\.?|bedroom)", lst.title, re.I)
        if m:
            lst.bedrooms = int(m.group(1))

    lst.district = detect_district(lst, cfg)
    if lst.phone:
        lst.phone = normalize_phone(lst.phone)
    if lst.whatsapp:
        lst.whatsapp = normalize_phone(lst.whatsapp)
    return apply_currency(lst, fx)


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 9 and digits.startswith("9"):       # Peruvian mobile
        digits = "51" + digits
    elif len(digits) in (7, 8) and not digits.startswith("51"):   # Lima landline
        digits = "511" + digits[-7:]
    return "+" + digits


def whatsapp_link(number: str | None) -> str | None:
    if not number:
        return None
    digits = re.sub(r"\D", "", number)
    # only mobiles can receive WhatsApp (Peru: +51 9xx xxx xxx)
    if digits.startswith("519") and len(digits) == 11:
        return f"https://wa.me/{digits}"
    return None
