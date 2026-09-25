"""Urbania + Adondevivir (both run on the Navent platform).

Primary path: Apify actors scrapers_lat/urbania-scraper and scrapers_lat/adondevivir-scraper.
Fallback (no token): one polite fetch of the public search page. Any bot challenge stops
the source immediately — nothing is bypassed.

The mapper is intentionally tolerant: actor output field names are not formally
documented, so every field is looked up through several aliases (flat actor fields and
Navent-native nested structures). Gate 2 prints field coverage so gaps are visible.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http_client import AccessBlocked, NetworkBlocked, PoliteClient, RobotsDisallowed
from ..models import Listing
from ..normalize.text_signals import fold, parse_money, relative_date_days, strip_html
from .apify_client import (ApifyAuth, ApifyClient, ApifyError, BudgetStop, build_actor_input, dataset_fields,
                           paid_run)
from .base import (CostBudget, SourceResult, iter_label_values, now_iso, pick, to_bool, to_float,
                   to_int)

USD_TOKENS = ("usd", "us$", "u$s", "$", "dolar", "dólar", "dolares", "dólares", "us")
PEN_TOKENS = ("pen", "s/", "s/.", "sol", "soles", "nuevos soles")
LIMA_LAT = (-12.30, -11.80)
LIMA_LON = (-77.25, -76.80)


def norm_currency(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = pick(value, "code", "symbol", "name", "id")
    s = str(value).strip().lower()
    if s in ("2", "6"):              # Navent currencyId codes seen in URLs: 6=PEN, 2=USD
        return "USD" if s == "2" else "PEN"
    if any(tok == s or s.startswith(tok) for tok in PEN_TOKENS):
        return "PEN"
    if any(tok == s or s.startswith(tok) for tok in USD_TOKENS):
        return "USD"
    return None


# --------------------------------------------------------------------------- mapper
def _prices(rec: dict) -> tuple[float | None, str | None, dict[str, float]]:
    """Return (amount, currency, {currency: amount} of all *published* prices)."""
    published: dict[str, float] = {}
    for op in rec.get("priceOperationTypes") or []:
        for p in (op or {}).get("prices") or []:
            cur, amt = norm_currency(p.get("currency")), to_float(p.get("amount"))
            if cur and amt:
                published.setdefault(cur, amt)
    for p in rec.get("prices") or [] if isinstance(rec.get("prices"), list) else []:
        if isinstance(p, dict):
            cur, amt = norm_currency(p.get("currency")), to_float(p.get("amount") or p.get("value"))
            if cur and amt:
                published.setdefault(cur, amt)
    if published:
        first = next(iter(published))
        return published[first], first, published

    raw_price = pick(rec, "price", "priceAmount", "price.amount", "price.value", "rent", "monthlyPrice")
    cur = norm_currency(pick(rec, "currency", "priceCurrency", "price.currency", "currencyCode"))
    if isinstance(raw_price, str):
        amt, cur_from_text = parse_money(raw_price)
        cur = cur or cur_from_text
    else:
        amt = to_float(raw_price)
    usd_flat = to_float(pick(rec, "priceUSD", "priceUsd", "price_usd", "usdPrice", "priceInUsd"))
    pen_flat = to_float(pick(rec, "pricePEN", "pricePen", "price_pen", "penPrice", "priceInPen"))
    if amt and cur:
        published = {cur: amt}
        for c, v in (("USD", usd_flat), ("PEN", pen_flat)):   # the portal's figure in the other currency
            if v and c not in published:
                published[c] = v
        return amt, cur, published
    # only converted flat fields: pick the one that looks like a round, human-typed figure
    if usd_flat or pen_flat:
        candidates = [(c, v) for c, v in (("USD", usd_flat), ("PEN", pen_flat)) if v]
        round_ones = [(c, v) for c, v in candidates if v % 10 == 0]
        cur, amt = (round_ones or candidates)[0]
        return amt, cur, {cur: amt}
    return amt, cur, ({cur: amt} if amt and cur else {})


def _expenses(rec: dict) -> tuple[float | None, str | None, bool]:
    raw = pick(rec, "expenses", "maintenance", "maintenanceFee", "expensas", "commonExpenses",
               "maintenanceCost", "hoa", "gastosComunes")
    cur = norm_currency(pick(rec, "expensesCurrency", "maintenanceCurrency", "expenses.currency"))
    if isinstance(raw, dict):
        cur = cur or norm_currency(raw.get("currency"))
        raw = raw.get("amount") or raw.get("value")
    if isinstance(raw, str):
        amt, cur_t = parse_money(raw)
        cur = cur or cur_t
    else:
        amt = to_float(raw)
    if amt is None or amt <= 0:
        return None, None, False
    assumed = cur is None
    return amt, cur or "PEN", assumed


FEATURE_RULES = [
    ("bedrooms", re.compile(r"dormitorio|dorm\b|dorm\.|habitaci|recamara|bedroom")),
    ("half_bath", re.compile(r"medio bano|medios banos|toilette|half bath")),
    ("bathrooms", re.compile(r"bano|bath")),
    ("total_area_m2", re.compile(r"(area|superficie|sup\.?)\s*total|m2 tot|m² tot|tot\.|total area")),
    ("built_area_m2", re.compile(r"techad|construid|cubiert|covered|built|m2 cub|m² cub|cub\.")),
    ("parking_spaces", re.compile(r"estacionamiento|cochera|parking|garage|estac\.")),
    ("total_floors", re.compile(r"(cantidad|numero|n°) de pisos|pisos del edificio|total floors")),
    ("floor", re.compile(r"^piso\b|numero de piso|piso de la unidad|ubicacion en piso|\bfloor\b")),
]


def _features(rec: dict) -> dict:
    out: dict = {}
    sources = [pick(rec, "mainFeatures"), pick(rec, "features"), pick(rec, "characteristics"),
               pick(rec, "attributes"), pick(rec, "specs"), pick(rec, "details")]
    for src in sources:
        if not src:
            continue
        for label, value in iter_label_values(src):
            lab = fold(str(label))
            val_is_label = value == label
            for field, rx in FEATURE_RULES:
                if field in out or not rx.search(lab):
                    continue
                num = to_float(value if not val_is_label else lab)
                if field in ("total_area_m2", "built_area_m2") and val_is_label and "m" not in lab:
                    continue
                if num is not None:
                    out[field] = num
                break
    return out


def _amenities(rec: dict) -> list[str]:
    out: list[str] = []
    for key in ("amenities", "generalFeatures", "services", "extras", "facilities", "amenitiesList",
                "features", "characteristics"):
        val = pick(rec, key)
        if not val:
            continue
        for label, value in iter_label_values(val):
            if value in (None, True, "true", "Sí", "Si", "si", "sí", 1) or value == label:
                lab = str(label).strip()
                if lab and not re.match(r"^\d", lab):
                    out.append(lab)
    return list(dict.fromkeys(out))


def _images(rec: dict) -> tuple[str | None, int | None, list[str]]:
    imgs = pick(rec, "images", "pictures", "photos", "visiblePictures.pictures", "gallery", "imageUrls",
                "imagesUrls")
    urls: list[str] = []
    if isinstance(imgs, list):
        for it in imgs:
            if isinstance(it, str):
                urls.append(it)
            elif isinstance(it, dict):
                u = pick(it, "url", "url730x532", "resizeUrl1200x1200", "src", "href", "original", "large")
                if isinstance(u, str):
                    urls.append(u)
    main = pick(rec, "mainImage", "mainImageUrl", "imageUrl", "thumbnail", "coverImage", "image") or \
        (urls[0] if urls else None)
    if isinstance(main, dict):
        main = pick(main, "url", "src")
    if isinstance(main, str) and main not in urls:
        urls.append(main)
    count = to_int(pick(rec, "picturesCount", "imageCount", "imagesCount", "photoCount")) or (len(urls) or None)
    keys = []
    for u in urls:
        m = re.search(r"/([0-9a-f]{12,}|\d{7,})[^/]*\.(jpe?g|png|webp)", u, re.I)
        if m:
            keys.append(m.group(1))
    return (main if isinstance(main, str) else None), count, keys


def _date(value, scraped_at: datetime) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and value > 1e9:          # epoch (s or ms)
        ts = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(ts).date().isoformat()
    s = str(value)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    days = relative_date_days(s)
    if days is not None:
        return (scraped_at - timedelta(days=days)).date().isoformat()
    return None


def _coords(rec: dict) -> tuple[float | None, float | None, str | None]:
    lat = to_float(pick(rec, "latitude", "lat", "geolocation.latitude", "geoLocation.latitude",
                        "location.latitude", "location.lat", "coordinates.latitude", "coordinates.lat",
                        "postingLocation.postingGeolocation.geolocation.latitude", "geo.lat", "geo.latitude",
                        "mapLocation.lat"))
    lon = to_float(pick(rec, "longitude", "lng", "lon", "geolocation.longitude", "geoLocation.longitude",
                        "location.longitude", "location.lng", "location.lon", "coordinates.longitude",
                        "coordinates.lng", "postingLocation.postingGeolocation.geolocation.longitude",
                        "geo.lng", "geo.lon", "geo.longitude", "mapLocation.lng"))
    if lat is None or lon is None:
        return None, None, None
    if not (LIMA_LAT[0] <= lat <= LIMA_LAT[1] and LIMA_LON[0] <= lon <= LIMA_LON[1]):
        return None, None, None
    exact = pick(rec, "showExactLocation", "exactLocation", "postingLocation.postingGeolocation.showExactLocation")
    approx = pick(rec, "isApproximate", "approximateLocation", "locationIsApproximate")
    precision = "EXACT" if to_bool(exact) is True or to_bool(approx) is False else \
        "APPROXIMATE" if to_bool(exact) is False or to_bool(approx) is True else "UNSPECIFIED"
    return lat, lon, precision


def _advertiser_key(rec: dict) -> str | None:
    """Stable advertiser identity for dedupe. The publisher logo path is present on both portals' list
    output (Navent reuses one path per advertiser); the publisher id is used when there is no logo."""
    logo = pick(rec, "publisherLogo", "publisher.logo")
    if isinstance(logo, str):
        m = re.search(r"/empresas/((?:\d+/)+)", logo)
        if m:
            return "logo:" + m.group(1).replace("/", "")
    pid = pick(rec, "publisherId", "publisher.publisherId", "publisher.id")
    return f"id:{pid}" if pid else None


def _location_text(rec: dict) -> tuple[str | None, str | None, str | None]:
    address = pick(rec, "address", "postingLocation.address.name", "location.address", "street",
                   "fullAddress", "addressLine")
    if isinstance(address, dict):
        address = pick(address, "name", "street", "value")
    district = pick(rec, "district", "neighborhood", "neighbourhood", "postingLocation.location.name",
                    "location.name", "locationName", "location.district", "comuna", "barrio")
    if isinstance(district, dict):
        district = pick(district, "name")
    parent = pick(rec, "city", "postingLocation.location.parent.name", "location.city", "province", "zone",
                  "locationText", "fullLocation")
    if isinstance(parent, dict):
        parent = pick(parent, "name")
    loc = rec.get("location")
    if isinstance(loc, str) and loc.strip():
        # Navent list output: "Miraflores, Lima" (district, city) or "San Antonio, Miraflores" (zone, district)
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        if len(parts) >= 2 and fold(parts[-1]) in ("lima", "peru", "lima metropolitana"):
            parts = parts[:-1]
            parent = parent or "Lima"
        if not district:
            district = parts[-1]
        if len(parts) >= 2:
            parent = parts[0]      # neighbourhood / zone within the district
    return (str(address) if address else None), (str(district) if district else None), \
        (str(parent) if parent else None)


def map_navent_record(rec: dict, source: str, base_url: str, scraped_at: str | None = None) -> Listing:
    scraped_at = scraped_at or now_iso()
    scraped_dt = datetime.fromisoformat(scraped_at)
    url = pick(rec, "url", "link", "detailUrl", "postingUrl", "permalink", "listingUrl", "href")
    if isinstance(url, str) and url.startswith("/"):
        url = urljoin(base_url, url)
    lid = pick(rec, "id", "postingId", "listingId", "propertyId", "postingCode", "code")
    if lid is None and isinstance(url, str):
        m = re.search(r"-(\d{6,})\.html", url) or re.search(r"(\d{8,})", url)
        lid = m.group(1) if m else None

    amount, currency, published = _prices(rec)
    exp_amt, exp_cur, exp_assumed = _expenses(rec)
    feats = _features(rec)
    lat, lon, precision = _coords(rec)
    address, district, parent = _location_text(rec)
    main_img, img_count, img_keys = _images(rec)

    bedrooms = to_int(pick(rec, "bedrooms", "dormitorios", "bedroomsCount", "bedroom", "numBedrooms"))
    if bedrooms is None:
        bedrooms = to_int(feats.get("bedrooms")) if feats.get("bedrooms") is not None else \
            to_int(pick(rec, "rooms"))
    baths = to_float(pick(rec, "bathrooms", "baths", "banos", "bathroomsCount"))
    if baths is None and feats.get("bathrooms") is not None:
        baths = feats["bathrooms"] + 0.5 * feats.get("half_bath", 0)

    status_raw = pick(rec, "status", "postingStatus", "isActive", "active", "available")
    status_txt = fold(str(status_raw)) if status_raw is not None else ""
    if status_raw is False or any(t in status_txt for t in ("finaliz", "offline", "paused", "pausad",
                                                             "inactive", "alquilad", "rented", "sold")):
        active, evidence = "INACTIVE", f"source status = {status_raw}"
    else:
        active, evidence = "LIKELY_ACTIVE", f"returned by a live {source} search at {scraped_at}"

    desc = pick(rec, "description", "descriptionNormalized", "fullDescription", "text", "body")
    lst = Listing(
        source=source,
        source_listing_id=str(lid) if lid is not None else None,
        source_url=url if isinstance(url, str) else None,
        search_segment=rec.get("_search_segment"),
        scraped_at=scraped_at,
        publication_date=_date(pick(rec, "publicationDate", "publishedAt", "publishDate", "published",
                                    "publishedDate", "createdAt", "created", "datePublished", "publishedText",
                                    "publicationDateText", "antiquity"), scraped_dt),
        last_updated_date=_date(pick(rec, "modifiedDate", "updatedAt", "lastUpdate", "modified",
                                     "lastModified", "updated"), scraped_dt),
        active_status=active,
        active_evidence=evidence,
        title=strip_html(pick(rec, "title", "generatedTitle", "name", "headline")) or None,
        description=strip_html(desc) or None,
        district=district,
        subarea=parent,
        address=address,
        latitude=lat, longitude=lon,
        coord_source="LISTING" if lat is not None else None,
        coord_precision=precision,
        rent_original=amount,
        rent_currency=currency,
        rent_usd=published.get("USD"),
        rent_usd_basis="PUBLISHED" if "USD" in published else None,
        rent_pen=published.get("PEN"),
        rent_pen_basis="PUBLISHED" if "PEN" in published else None,
        rent_usd_published=published.get("USD"),
        rent_pen_published=published.get("PEN"),
        maintenance_fee=exp_amt,
        maintenance_currency=exp_cur,
        property_type=str(pick(rec, "propertyType", "realEstateType.name", "property_type", "type",
                               "category") or "") or None,
        operation=str(pick(rec, "operationType", "operation", "priceOperationTypes.0.operationType.name",
                           "transaction") or "") or None,
        bedrooms=bedrooms,
        bathrooms=baths,
        total_area_m2=to_float(pick(rec, "totalArea", "totalAreaM2", "total_area", "areaTotal", "totalSurface",
                                    "surfaceTotal", "area", "surface", "m2Total")) or feats.get("total_area_m2"),
        built_area_m2=to_float(pick(rec, "coveredArea", "builtArea", "builtAreaM2", "covered_area", "roofedArea",
                                    "areaTechada", "coveredSurface", "surfaceCovered")) or feats.get("built_area_m2"),
        floor=to_int(pick(rec, "floor", "piso", "unitFloor")) if pick(rec, "floor", "piso", "unitFloor") is not None
        else to_int(feats.get("floor")),
        total_floors=to_int(pick(rec, "totalFloors", "floors", "buildingFloors")) or to_int(feats.get("total_floors")),
        parking_spaces=to_int(pick(rec, "parking", "parkingSpaces", "garages", "parkingLots", "estacionamientos"))
        if pick(rec, "parking", "parkingSpaces", "garages", "parkingLots", "estacionamientos") is not None
        else to_int(feats.get("parking_spaces")),
        agent_name=str(pick(rec, "contactName", "agent.name", "agentName", "contact.name") or "") or None,
        agency_name=str(pick(rec, "publisher.name", "publisherName", "agencyName", "agency.name",
                             "advertiser.name", "advertiserName", "realEstate.name", "inmobiliaria") or "") or None,
        advertiser_key=_advertiser_key(rec),
        phone=str(pick(rec, "phone", "agentPhone", "phones.0", "publisher.phone", "contact.phone", "phoneNumber",
                       "telephone", "mobile", "cellPhone") or "") or None,
        whatsapp=str(pick(rec, "whatsapp", "whatsApp", "agentWhatsapp", "whatsappNumber", "publisher.whatsapp",
                          "contact.whatsapp", "publisher.whatsApp") or "") or None,
        main_image_url=main_img,
        image_count=img_count,
        image_keys=img_keys,
        amenities=_amenities(rec),
    )
    if exp_assumed:
        lst.text_signals.append("maintenance currency not provided by source — assumed PEN")
    furnished = to_bool(pick(rec, "furnished", "isFurnished", "amoblado"))
    if furnished is not None:
        lst.furnished = furnished
    return lst


# --------------------------------------------------------------------------- direct fallback
def parse_navent_search_html(html: str, base_url: str) -> list[dict]:
    """Parse public Navent search cards (data-qa attributes). Returns raw dicts for the mapper."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('[data-qa="posting PROPERTY"], [data-qa="posting DEVELOPMENT"], div[data-id][data-to-posting]')
    out = []
    for c in cards:
        def txt(sel: str) -> str | None:
            el = c.select_one(sel)
            return el.get_text(" ", strip=True) if el else None
        feats = [s.get_text(" ", strip=True) for s in c.select('[data-qa="POSTING_CARD_FEATURES"] span')]
        pub = c.select_one('[data-qa="POSTING_CARD_PUBLISHER"] img')
        rec = {
            "id": c.get("data-id"),
            "url": c.get("data-to-posting"),
            "price": txt('[data-qa="POSTING_CARD_PRICE"]'),
            "expenses": txt('[data-qa="expensas"], [data-qa="POSTING_CARD_EXPENSES"]'),
            "features": feats,
            "address": txt('[class*="LocationAddress"], [class*="location-address"], .postingAddress'),
            "district": txt('[data-qa="POSTING_CARD_LOCATION"]'),
            "description": txt('[data-qa="POSTING_CARD_DESCRIPTION"]'),
            "title": txt('[data-qa="POSTING_CARD_TITLE"], h2 a, h3 a'),
            "publisherName": pub.get("alt") if pub else None,
            "publishedText": txt('[data-qa="POSTING_CARD_DATE"], [class*="Antiquity"]'),
        }
        if rec["url"] or rec["id"]:
            out.append(rec)
    return out


def _page_url(url: str, page: int) -> str:
    if page == 1:
        return url
    if url.endswith(".html"):
        return url[:-5] + f"-pagina-{page}.html"
    return url + ("&" if "?" in url else "?") + f"page={page}"


# --------------------------------------------------------------------------- collector
def segment_urls(scfg: dict) -> list[tuple[int, str]]:
    return [(int(seg["bedrooms"]), url) for seg in scfg["segments"] for url in seg["start_urls"]]


def _segment_intent(cfg: dict, bedrooms: int, url: str) -> dict:
    max_price = cfg["budget"]["query_max_rent"]
    return {"start_urls": [url], "max_price": max_price, "currency": "USD", "min_bedrooms": bedrooms,
            "max_bedrooms": bedrooms, "operation": "rent", "property_type": "apartment", "with_details": True,
            # sent verbatim only if the actor's input schema cannot be read
            "raw_input": {"startUrls": [{"url": url}], "withDetails": True, "priceCurrency": "USD",
                          "maxPrice": max_price, "minBedrooms": bedrooms, "maxBedrooms": bedrooms}}


def collect_navent(name: str, scfg: dict, cfg: dict, http: PoliteClient, budget: CostBudget,
                   mode: str, auth: ApifyAuth | None, max_items: int | None = None) -> SourceResult:
    """``max_items`` is per bedroom segment. Each segment (and each of its start URLs) is its own Actor
    run, so the 1-bedroom search can never use up the records meant for the 2-bedroom search."""
    base_url = scfg["base_url"]
    if max_items is None:
        max_items = cfg["cost_control"]["validation_items_per_segment"] if mode == "validate" \
            else scfg["full_max_items_per_segment"]

    if auth is not None and auth.available:
        res = SourceResult(source=name, method=f"Apify actor {scfg['actor_id']} ({auth.method}), "
                                               f"one run per bedroom segment")
        try:
            client = ApifyClient(auth, http)
            info = client.actor_info(scfg["actor_id"])
            stats = info.get("stats") or {}
            res.audit.update({"actor_title": info.get("title"), "actor_modified": info.get("modifiedAt"),
                              "actor_last_run": stats.get("lastRunStartedAt"),
                              "actor_total_runs": stats.get("totalRuns"), "segments": []})
            try:
                props = client.input_schema(scfg["actor_id"], info)
                res.audit["input_schema"] = "retrieved" if props else "not published by the actor"
            except ApifyError as exc:
                props = None
                res.audit["input_schema"] = f"unavailable ({exc})"
                res.notes.append(f"input schema unavailable ({exc})")
            res.audit["input_properties"] = sorted(props) if props else []
        except NetworkBlocked as exc:
            res.errors.append(f"api.apify.com unreachable from this environment: {exc}")
            return res.finish("FAILED")
        except ApifyError as exc:
            res.errors.append(str(exc))
            return res.finish("FAILED")

        scraped = now_iso()
        stop = False
        for seg in scfg["segments"]:
            beds = int(seg["bedrooms"])
            urls = seg["start_urls"][:1] if mode == "validate" else seg["start_urls"]
            seg_audit = {"bedrooms": beds, "runs": []}
            got: list[dict] = []
            for url in urls:
                want = min(max_items - len(got), int(cfg["cost_control"]["apify_max_items_per_run"]))
                if want <= 0 or stop:
                    break
                intent = _segment_intent(cfg, beds, url)
                if not props or not _prop_present(props, "start_urls"):
                    intent["location"] = cfg["location"]["district"]
                run_input, notes = build_actor_input(props, intent, want)
                res.notes.extend(n for n in notes if n not in res.notes)
                label = f"{name} {beds}BR"
                try:
                    run, items, cost, basis = paid_run(client, budget, scfg["actor_id"], info, run_input, want,
                                                       label, cfg["cost_control"]["unknown_pricing_run_usd"])
                except BudgetStop as exc:
                    res.errors.append(f"{exc} (ask before spending more)")
                    stop = True
                    break
                except (ApifyError, NetworkBlocked) as exc:
                    res.errors.append(f"{label}: {exc}")
                    continue
                res.cost_usd += cost
                seg_audit["runs"].append({"run_id": run.get("id"), "status": run.get("status"), "requested": want,
                                          "items": len(items), "cost_usd": round(cost, 4), "cost_basis": basis,
                                          "input": run_input})
                if want > 10 and len(items) == 10:
                    res.notes.append(f"{label}: exactly 10 of {want} records returned — the free Apify plan "
                                     "caps every run at 10 records")
                if run.get("status") != "SUCCEEDED":
                    res.errors.append(f"{label}: actor run ended with status {run.get('status')}")
                for it in items:
                    it["_search_segment"] = f"{beds}BR"
                got.extend(items)
            res.audit["segments"].append(seg_audit)
            res.raw_records.extend(got)
            if stop:
                break
        res.audit["dataset_fields"] = dataset_fields(res.raw_records)
        res.listings = [map_navent_record(it, name, base_url, scraped) for it in res.raw_records]
        if not res.raw_records:
            return res.finish("FAILED")
        return res.finish("PARTIAL" if res.errors else "SUCCESS")

    # ---- Apify not available: no paid call; one polite direct attempt, stop on any challenge
    res = SourceResult(source=name, method="direct HTML (Apify not available — local fallback)")
    if auth is not None:
        res.notes.append(f"Apify not used: {auth.reason or auth.method}. No paid call was made.")
    scraped = now_iso()
    pages = 1 if mode == "validate" else int(scfg.get("direct_max_pages", 10))
    try:
        for _, url in segment_urls(scfg):
            for page in range(1, pages + 1):
                resp = http.get_html(_page_url(url, page))
                if resp.status_code != 200:
                    res.errors.append(f"{url} page {page}: HTTP {resp.status_code}")
                    break
                recs = parse_navent_search_html(resp.text, base_url)
                if not recs:
                    res.notes.append(f"{url} page {page}: no listing cards recognised (layout may have changed)")
                    break
                res.raw_records.extend(recs)
                if len(res.raw_records) >= max_items:
                    break
            if len(res.raw_records) >= max_items:
                break
    except (AccessBlocked, NetworkBlocked, RobotsDisallowed) as exc:
        res.errors.append(f"{type(exc).__name__}: {exc} — not bypassed")
    res.raw_records = res.raw_records[:max_items]
    res.listings = [map_navent_record(r, name, base_url, scraped) for r in res.raw_records]
    return res.finish("PARTIAL" if res.listings else "FAILED")


def _prop_present(props: dict, key: str) -> bool:
    from .apify_client import _prop
    return _prop(props, key) is not None
