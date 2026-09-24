"""Researched facts about each source (Gate 1). Runtime results are merged in by the pipeline.

Facts marked "expected" come from the source's public documentation / search-index pages
(research date 2026-09-24). "Observed" values are only written after a validation run.
"""
from __future__ import annotations

RESEARCH_DATE = "2026-09-24"

REGISTRY: dict[str, dict] = {
    "urbania": {
        "source_name": "Urbania",
        "source_url": "https://urbania.pe",
        "extraction_method": "Apify actor scrapers_lat/urbania-scraper (primary); single polite direct fetch "
                             "that stops at any bot challenge (fallback without token)",
        "public_access": "Public search and detail pages, no login",
        "target_search_url": "https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima",
        "pagination": "Handled by actor (direct: ?page=N)",
        "detail_pages": "Expected via actor (docs: 'all fields exposed by listing and detail pages')",
        "contact_data": "Expected: phone / WhatsApp (actor docs)",
        "coordinates": "Expected (Navent geolocation; may be approximate)",
        "publication_date": "Expected (relative 'Publicado hace…')",
        "maintenance_fee": "Expected when advertiser publishes 'Mantenimiento'",
        "inventory_hint": "Search index (Sep 2026): 859 apartments for rent in Miraflores",
        "limitations": "Navent platform uses bot protection; direct scraping not attempted beyond one polite "
                       "request. Actor input names partly undocumented — unknown inputs are dropped and filters "
                       "re-applied after extraction.",
    },
    "adondevivir": {
        "source_name": "Adondevivir",
        "source_url": "https://www.adondevivir.com",
        "extraction_method": "Apify actor scrapers_lat/adondevivir-scraper (primary); polite direct fallback",
        "public_access": "Public search and detail pages, no login",
        "target_search_url": "https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores.html",
        "pagination": "Handled by actor (direct: -pagina-N.html)",
        "detail_pages": "Expected via actor",
        "contact_data": "Expected: agent phone and WhatsApp (actor docs)",
        "coordinates": "Expected (same Navent backend as Urbania)",
        "publication_date": "Expected (relative)",
        "maintenance_fee": "Expected when published",
        "inventory_hint": "Search index (Sep 2026): 821 apartments for rent in Miraflores",
        "limitations": "Actor docs: free-tier runs capped at 10 listings. Same backend as Urbania, so many "
                       "listings are cross-posted — handled by de-duplication (shared posting ids).",
    },
    "mercadolibre": {
        "source_name": "Mercado Libre Inmuebles Perú",
        "source_url": "https://inmuebles.mercadolibre.com.pe",
        "extraction_method": "Direct HTML (own parser, robots.txt respected, ≥2.5 s between requests). "
                             "Reference repo GadielRP/mercadolibre-real-estate-scraper audited and NOT reused.",
        "public_access": "Public search and detail pages; phone numbers require login (not collected)",
        "target_search_url": "https://inmuebles.mercadolibre.com.pe/departamentos/alquiler/lima/miraflores/",
        "pagination": "_Desde_N offsets (48/page)",
        "detail_pages": "Yes — specs table, description, map centre",
        "contact_data": "Seller name only; contact through Mercado Libre",
        "coordinates": "Sometimes (map on detail page)",
        "publication_date": "Relative 'Publicado hace…' on detail page",
        "maintenance_fee": "Sometimes (spec 'Mantenimiento' / 'Gastos comunes')",
        "inventory_hint": "Search index lists Miraflores rentals; count not published in index",
        "limitations": "Page layout changes periodically; parser supports current poly-card and legacy layouts. "
                       "Reference repo rejected: no licence ('Private'), targets Mexico (MLM), relies on "
                       "webdriver masking, UA rotation and residential proxy rotation.",
    },
    "manual": {
        "source_name": "Manual import (agency sites, other portals)",
        "source_url": "data/manual/",
        "extraction_method": "CSV/JSON import (config/manual_import_template.csv)",
        "public_access": "n/a",
        "target_search_url": "n/a",
        "pagination": "n/a", "detail_pages": "n/a", "contact_data": "as entered", "coordinates": "as entered",
        "publication_date": "as entered", "maintenance_fee": "as entered",
        "inventory_hint": "",
        "limitations": "Only as good as the manual capture; active status UNKNOWN unless re-checked.",
    },
}

# Discovered in Gate 1 but not automated in this iteration (unverifiable from this environment).
CANDIDATES: list[dict] = [
    {"source_name": "Properati Perú", "source_url": "https://www.properati.com.pe/s/miraflores/departamento/alquiler",
     "note": "Search index: 294 Miraflores rentals; 75 furnished; 137 with 2 bedrooms"},
    {"source_name": "FazWaz Perú", "source_url": "https://www.fazwaz.com.pe/departamento-en-alquiler/peru/lima/lima/miraflores",
     "note": "Search index: 437 rental listings in Miraflores; English-friendly (relevant for foreign tenants)"},
    {"source_name": "Ubicasa", "source_url": "https://ubicasa.pe/alquiler/departamento/miraflores-lima-lima",
     "note": "Search index: 651 apartments; advertises exact map location and PEN/USD prices"},
    {"source_name": "LaEncontre", "source_url": "https://www.laencontre.com.pe/alquiler/departamentos/lima/miraflores",
     "note": "Search index: 293 apartments in Miraflores"},
    {"source_name": "Babilonia", "source_url": "https://babilonia.pe/inmuebles/departamentos-en-alquiler-en-lima-lima-miraflores",
     "note": "Peruvian portal; count not visible in index"},
    {"source_name": "InfoCasas Perú", "source_url": "https://www.infocasas.com.pe/alquiler/departamentos/lima/miraflores/1-dormitorio",
     "note": "Has 1-bedroom Miraflores filter page"},
    {"source_name": "RE/MAX Perú", "source_url": "https://www.remax.pe/departamentos-en+alquiler-miraflores-dist/",
     "note": "Agency network listings; often cross-posted to Urbania/Adondevivir"},
    {"source_name": "Mitula Casas", "source_url": "https://casas.mitula.pe/casas/alquiler-departamentos-lima-miraflores",
     "note": "Aggregator of other portals — mostly duplicates; low marginal value"},
]


REFERENCE_REPO_AUDIT = """## Appendix — audit of GadielRP/mercadolibre-real-estate-scraper (reference implementation)

Inspected read-only on 2026-09-24 (shallow clone of commit c29cfdf, 2025-09-30). **No code was executed or reused.**

| Check | Finding |
|---|---|
| README | Spanish; "Sistema de Scraping Inmobiliario MercadoLibre", targets **Mercado Libre México** (`mercadolibre.com.mx`, MLM ids) — not Peru. |
| Licence | **No LICENSE file**; README badge says "License-Private". Reuse would not be permitted. |
| Dependencies | 25 pinned/unpinned packages incl. Playwright 1.49, polars, asyncpg, psycopg2, SQLAlchemy, alembic, faker — far heavier than needed. |
| Recent activity | Last commit 2025-09-30. |
| Suspicious scripts | No `subprocess`, `eval`, `exec`, network exfiltration or install hooks found. |
| Behaviour | `navigation.py` implements "stealth" browsing: hides `navigator.webdriver`, rotates user agents, rotates **residential proxies (Oxylabs)**, and a function labelled "Bypass MercadoLibre"; `deteccion_bloqueos.py` detects CAPTCHAs/blocks to route around them. |
| Verdict | **REJECTED for reuse.** Anti-detection and proxy rotation conflict with this project's rule not to bypass access controls; licence forbids reuse; wrong country. Only the general idea (search page → detail page → specs table) informed our own polite parser in `src/sources/mercadolibre.py`. |
"""
