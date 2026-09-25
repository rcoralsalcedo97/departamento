"""Mercado Libre Inmuebles Perú — polite direct HTML collection.

Written from scratch (the GadielRP reference repo was audited and NOT reused: no licence,
Mexico-only, and built on anti-detection/proxy rotation). This collector:
  * checks robots.txt before every URL,
  * waits ≥ request_delay_s between requests,
  * never logs in, never solves CAPTCHAs, stops at the first challenge,
  * does not collect phone numbers (Mercado Libre hides them behind login).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from ..http_client import AccessBlocked, NetworkBlocked, PoliteClient, RobotsDisallowed
from ..models import Listing
from ..normalize.text_signals import fold, parse_money, relative_date_days, strip_html
from .base import SourceResult, now_iso, to_float, to_int

PAGE_SIZE = 48


def page_url(search_url: str, page: int) -> str:
    if page == 1:
        return search_url
    return search_url.rstrip("/") + f"/_Desde_{(page - 1) * PAGE_SIZE + 1}_NoIndex_True"


def listing_id_from_url(url: str) -> str | None:
    m = re.search(r"(MPE)-?(\d{6,})", url or "")
    return f"MPE{m.group(2)}" if m else None


def _attr_values(texts: list[str]) -> dict:
    out: dict = {}
    for t in texts:
        f = fold(t)
        n = to_float(f)
        if n is None:
            continue
        if re.search(r"dormitorio|dorm|habitaci", f):
            out.setdefault("bedrooms", int(n))
        elif re.search(r"bano", f):
            out.setdefault("bathrooms", n)
        elif re.search(r"m2|m²", f) and re.search(r"cubierto|construid|techad", f):
            out.setdefault("built_area_m2", n)
        elif re.search(r"m2|m²", f):
            out.setdefault("total_area_m2", n)
        elif re.search(r"estacionamiento|cochera", f):
            out.setdefault("parking_spaces", int(n))
    return out


def parse_search_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.ui-search-layout__item") or soup.select("div.poly-card")
    out = []
    for c in cards:
        a = c.select_one("a.poly-component__title, h2 a, a.ui-search-link, a.ui-search-item__group__element")
        if not a or not a.get("href"):
            continue
        url = a["href"].split("#")[0]
        title = a.get_text(" ", strip=True) or (c.select_one("h2") or a).get_text(" ", strip=True)
        money = c.select_one(".poly-price__current .andes-money-amount, .andes-money-amount")
        amount, currency = None, None
        if money:
            sym = money.select_one(".andes-money-amount__currency-symbol")
            frac = money.select_one(".andes-money-amount__fraction")
            amount, currency = parse_money(f"{sym.get_text() if sym else ''} {frac.get_text() if frac else ''}")
        attrs = [li.get_text(" ", strip=True) for li in
                 c.select(".poly-attributes_list__item, .poly-attributes-list__item, "
                          ".ui-search-card-attributes__attribute")]
        loc = c.select_one(".poly-component__location, .ui-search-item__location, .ui-search-item__group__element--location")
        rec = {
            "url": url, "id": listing_id_from_url(url), "title": title,
            "price": amount, "currency": currency, "attributes": attrs,
            "location": loc.get_text(" ", strip=True) if loc else None,
        }
        rec.update(_attr_values(attrs))
        out.append(rec)
    return out


SPEC_MAP = [
    ("total_area_m2", r"superficie total|area total"),
    ("built_area_m2", r"superficie (cubierta|construida|techada)|area (construida|techada)"),
    ("bedrooms", r"^dormitorios?$|^habitaciones$|^recamaras$"),
    ("bathrooms", r"^banos?$"),
    ("parking_spaces", r"estacionamientos?|cocheras?"),
    ("floor", r"(numero de )?piso de la unidad|^piso$"),
    ("total_floors", r"cantidad de pisos|pisos del edificio"),
    ("maintenance", r"mantenimiento|gastos comunes|expensas"),
    ("furnished", r"^amoblado|amueblado"),
    ("elevator", r"ascensor"),
    ("security_24h", r"seguridad|vigilancia|conserje|porter"),
    ("gym", r"gimnasio"),
    ("pool", r"piscina"),
    ("laundry", r"lavander"),
    ("balcony", r"balcon"),
    ("terrace", r"terraza"),
    ("pets_allowed", r"mascotas"),
    ("orientation", r"disposicion|orientacion"),
]


def parse_detail_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {"specs": {}}
    for row in soup.select("tr.andes-table__row, .ui-vpp-striped-specs__row"):
        th, td = row.select_one("th, .andes-table__header"), row.select_one("td, .andes-table__column")
        if th and td:
            out["specs"][th.get_text(" ", strip=True)] = td.get_text(" ", strip=True)
    for kv in soup.select(".ui-vpp-highlighted-specs__key-value, .ui-pdp-highlighted-specs-res__icon-label"):
        text = kv.get_text(" ", strip=True)
        if ":" in text:
            k, v = text.split(":", 1)
            out["specs"].setdefault(k.strip(), v.strip())
    desc = soup.select_one(".ui-pdp-description__content, [data-testid='content']")
    out["description"] = desc.get_text("\n", strip=True) if desc else None
    loc = soup.select_one(".ui-vip-location__subtitle p, .ui-vip-location p, .ui-pdp-media__title")
    out["address"] = loc.get_text(" ", strip=True) if loc else None
    html_text = soup.get_text(" ", strip=True)
    out["published_text"] = next(iter(re.findall(r"Publicado hace [^|·\n]{1,30}", html_text)), None)
    m_lat = re.search(r'"latitude"\s*:\s*(-?\d+\.\d+)', html)
    m_lon = re.search(r'"longitude"\s*:\s*(-?\d+\.\d+)', html)
    if not (m_lat and m_lon):
        m = re.search(r"staticmap[^\"']*?center=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)", html)
        if m:
            out["lat"], out["lon"] = float(m.group(1)), float(m.group(2))
    else:
        out["lat"], out["lon"] = float(m_lat.group(1)), float(m_lon.group(1))
    seller = soup.select_one(".ui-pdp-seller__header__title, .ui-vip-profile-info__info-link h3, "
                             ".ui-seller-data-header__title")
    out["seller"] = seller.get_text(" ", strip=True) if seller else None
    out["image_count"] = len(soup.select("figure.ui-pdp-gallery__figure")) or None
    img = soup.select_one("figure.ui-pdp-gallery__figure img")
    out["main_image"] = (img.get("data-zoom") or img.get("src")) if img else None
    low = fold(html_text[:20000])
    out["inactive"] = any(t in low for t in ("publicacion finalizada", "publicacion pausada",
                                              "esta publicacion ya no esta disponible", "ya no esta disponible"))
    ld = soup.find("script", type="application/ld+json")
    if ld:
        try:
            out["ld"] = json.loads(ld.string or "{}")
        except json.JSONDecodeError:
            pass
    return out


def to_listing(card: dict, detail: dict | None, scraped_at: str) -> Listing:
    detail = detail or {}
    specs = {fold(k): v for k, v in (detail.get("specs") or {}).items()}

    def spec(field: str):
        for f, rx in SPEC_MAP:
            if f == field:
                for k, v in specs.items():
                    if re.search(rx, k):
                        return v
        return None

    def spec_bool(field: str) -> bool | None:
        v = spec(field)
        if v is None:
            return None
        fv = fold(str(v))
        return True if fv.startswith("si") else False if fv.startswith("no") else None

    maint_amt, maint_cur = parse_money(spec("maintenance"))
    lat, lon = detail.get("lat"), detail.get("lon")
    scraped_dt = datetime.fromisoformat(scraped_at)
    pub_days = relative_date_days(detail.get("published_text"))
    orient = fold(str(spec("orientation") or ""))
    lst = Listing(
        source="mercadolibre",
        source_listing_id=card.get("id"),
        source_url=card.get("url"),
        scraped_at=scraped_at,
        publication_date=(scraped_dt - timedelta(days=pub_days)).date().isoformat() if pub_days is not None else None,
        active_status="INACTIVE" if detail.get("inactive") else "LIKELY_ACTIVE",
        active_evidence=("detail page says the publication is finished/paused" if detail.get("inactive")
                         else f"returned by a live Mercado Libre search at {scraped_at}"),
        title=card.get("title"),
        description=strip_html(detail.get("description")) or None,
        district=card.get("location"),
        address=detail.get("address") or card.get("location"),
        latitude=lat, longitude=lon,
        coord_source="LISTING" if lat is not None else None,
        coord_precision="UNSPECIFIED" if lat is not None else None,
        rent_original=card.get("price"),
        rent_currency=card.get("currency"),
        maintenance_fee=maint_amt,
        maintenance_currency=(maint_cur or "PEN") if maint_amt else None,
        bedrooms=to_int(spec("bedrooms")) if spec("bedrooms") else card.get("bedrooms"),
        bathrooms=to_float(spec("bathrooms")) if spec("bathrooms") else card.get("bathrooms"),
        total_area_m2=to_float(spec("total_area_m2")) or card.get("total_area_m2"),
        built_area_m2=to_float(spec("built_area_m2")) or card.get("built_area_m2"),
        floor=to_int(spec("floor")),
        total_floors=to_int(spec("total_floors")),
        parking_spaces=to_int(spec("parking_spaces")) if spec("parking_spaces") else card.get("parking_spaces"),
        furnished=spec_bool("furnished"),
        elevator=spec_bool("elevator"),
        security_24h=spec_bool("security_24h"),
        gym=spec_bool("gym"),
        pool=spec_bool("pool"),
        laundry=spec_bool("laundry"),
        balcony=spec_bool("balcony"),
        terrace=spec_bool("terrace"),
        pets_allowed=spec_bool("pets_allowed"),
        interior_view=True if "contrafrente" in orient or "interior" in orient else None,
        exterior_view=True if "frente" in orient and "contra" not in orient else None,
        agency_name=detail.get("seller"),
        main_image_url=detail.get("main_image"),
        image_count=detail.get("image_count"),
        amenities=[f"{k}: {v}" for k, v in (detail.get("specs") or {}).items()],
    )
    if maint_amt and not maint_cur:
        lst.text_signals.append("maintenance currency not stated — assumed PEN")
    return lst


def collect_mercadolibre(scfg: dict, cfg: dict, http: PoliteClient, mode: str) -> SourceResult:
    res = SourceResult(source="mercadolibre", method="direct HTML (robots.txt respected)")
    delay = float(scfg.get("request_delay_s", 2.5))
    # validation sample: the same size as one portal's two bedroom segments together (free source, no cost)
    max_items = 2 * cfg["cost_control"]["validation_items_per_segment"] if mode == "validate" else 10_000
    pages = 1 if mode == "validate" else int(scfg["max_pages"])
    max_details = min(max_items, int(scfg["max_details"]))
    scraped = now_iso()
    cards: list[dict] = []
    try:
        for page in range(1, pages + 1):
            resp = http.get_html(page_url(scfg["search_url"], page), delay=delay)
            if resp.status_code != 200:
                res.errors.append(f"search page {page}: HTTP {resp.status_code}")
                break
            found = parse_search_html(resp.text)
            res.audit.setdefault("pages_ok", 0)
            res.audit["pages_ok"] += 1
            if not found:
                res.notes.append(f"search page {page}: no result cards recognised")
                break
            cards.extend(found)
            if len(cards) >= max_items or len(found) < PAGE_SIZE:
                break
        cards = cards[:max_items]
        # detail pages only for records that could pass the budget gate (saves requests)
        ceiling = cfg["budget"]["query_max_rent"]
        rate_guess = cfg["fx"]["fallback"]["usd_pen"]
        details_done = 0
        for card in cards:
            price_usd = card.get("price") if card.get("currency") == "USD" else \
                (card["price"] / rate_guess if card.get("price") else None)
            detail = None
            if scfg.get("fetch_details") and details_done < max_details and (price_usd is None or price_usd <= ceiling):
                try:
                    d = http.get_html(card["url"], delay=delay)
                    if d.status_code == 200:
                        detail = parse_detail_html(d.text)
                        details_done += 1
                    elif d.status_code in (404, 410):
                        detail = {"inactive": True}
                except RobotsDisallowed:
                    res.notes.append("robots.txt disallows detail pages — card data only")
                    scfg = {**scfg, "fetch_details": False}
            card["_detail"] = detail
            res.raw_records.append(card)
            res.listings.append(to_listing(card, detail, scraped))
        res.audit["details_fetched"] = details_done
    except (AccessBlocked, NetworkBlocked, RobotsDisallowed) as exc:
        res.errors.append(f"{type(exc).__name__}: {exc} — not bypassed")
    if res.listings and not res.errors:
        return res.finish("SUCCESS")
    return res.finish("PARTIAL" if res.listings else "FAILED")
