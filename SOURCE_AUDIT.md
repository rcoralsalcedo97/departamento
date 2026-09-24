# SOURCE_AUDIT

Research date: 2026-09-24. Last automated update: 2026-09-24T17:44:13-05:00.

Status meanings: **APPROVED** = validation run returned records with ≥90% core-field coverage (URL, rent, currency, bedrooms) and ≥60% area coverage · **PARTIAL** = records returned but weaker coverage or errors · **REJECTED** = source answered but could not be used (e.g. bot challenge — never bypassed) · **PENDING** = not yet testable (environment egress blocked or not automated).

## Reachability from the run environment

| Host | Result |
|---|---|
| api.apify.com | UNREACHABLE — blocked by egress proxy (403 Forbidden) |
| urbania.pe | UNREACHABLE — blocked by egress proxy (403 Forbidden) |
| www.adondevivir.com | UNREACHABLE — blocked by egress proxy (403 Forbidden) |
| inmuebles.mercadolibre.com.pe | UNREACHABLE — blocked by egress proxy (403 Forbidden) |
| overpass-api.de | UNREACHABLE — blocked by egress proxy (403 Forbidden) |
| nominatim.openstreetmap.org | UNREACHABLE — blocked by egress proxy (403 Forbidden) |
| estadisticas.bcrp.gob.pe | UNREACHABLE — blocked by egress proxy (403 Forbidden) |

## Urbania — PENDING (environment egress blocked)

- **Method:** direct HTML (no APIFY_TOKEN)
- **Target search URL:** https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima
- **Records collected:** 0
- **Public access:** Public search and detail pages, no login
- **Pagination:** Handled by actor (direct: ?page=N)
- **Detail pages:** Expected via actor (docs: 'all fields exposed by listing and detail pages')
- **Contact data:** Expected: phone / WhatsApp (actor docs)
- **Coordinates:** Expected (Navent geolocation; may be approximate)
- **Publication date:** Expected (relative 'Publicado hace…')
- **Maintenance fee:** Expected when advertiser publishes 'Mantenimiento'
- **Completeness:** not measured (no records)
- **Limitations / errors:** NetworkBlocked: urbania.pe: ProxyError: 403 Forbidden — not bypassed; APIFY_TOKEN not set — trying one polite direct request; set the token for full coverage | Navent platform uses bot protection; direct scraping not attempted beyond one polite request. Actor input names partly undocumented — unknown inputs are dropped and filters re-applied after extraction.

## Adondevivir — PENDING (environment egress blocked)

- **Method:** direct HTML (no APIFY_TOKEN)
- **Target search URL:** https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores.html
- **Records collected:** 0
- **Public access:** Public search and detail pages, no login
- **Pagination:** Handled by actor (direct: -pagina-N.html)
- **Detail pages:** Expected via actor
- **Contact data:** Expected: agent phone and WhatsApp (actor docs)
- **Coordinates:** Expected (same Navent backend as Urbania)
- **Publication date:** Expected (relative)
- **Maintenance fee:** Expected when published
- **Completeness:** not measured (no records)
- **Limitations / errors:** NetworkBlocked: www.adondevivir.com: ProxyError: 403 Forbidden — not bypassed; APIFY_TOKEN not set — trying one polite direct request; set the token for full coverage | Actor docs: free-tier runs capped at 10 listings. Same backend as Urbania, so many listings are cross-posted — handled by de-duplication (shared posting ids).

## Mercado Libre Inmuebles Perú — PENDING (environment egress blocked)

- **Method:** direct HTML (robots.txt respected)
- **Target search URL:** https://inmuebles.mercadolibre.com.pe/departamentos/alquiler/lima/miraflores/
- **Records collected:** 0
- **Public access:** Public search and detail pages; phone numbers require login (not collected)
- **Pagination:** _Desde_N offsets (48/page)
- **Detail pages:** Yes — specs table, description, map centre
- **Contact data:** Seller name only; contact through Mercado Libre
- **Coordinates:** Sometimes (map on detail page)
- **Publication date:** Relative 'Publicado hace…' on detail page
- **Maintenance fee:** Sometimes (spec 'Mantenimiento' / 'Gastos comunes')
- **Completeness:** not measured (no records)
- **Limitations / errors:** NetworkBlocked: inmuebles.mercadolibre.com.pe: ProxyError: 403 Forbidden — not bypassed | Page layout changes periodically; parser supports current poly-card and legacy layouts. Reference repo rejected: no licence ('Private'), targets Mexico (MLM), relies on webdriver masking, UA rotation and residential proxy rotation.

## Manual import (agency sites, other portals) — SKIPPED

- **Method:** file import from /home/user/departamento/data/manual
- **Target search URL:** n/a
- **Records collected:** 0
- **Public access:** n/a
- **Pagination:** n/a
- **Detail pages:** n/a
- **Contact data:** as entered
- **Coordinates:** as entered
- **Publication date:** as entered
- **Maintenance fee:** as entered
- **Completeness:** not measured (no records)
- **Limitations / errors:** no manual files present | Only as good as the manual capture; active status UNKNOWN unless re-checked.

## Properati Perú — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://www.properati.com.pe/s/miraflores/departamento/alquiler
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Search index: 294 Miraflores rentals; 75 furnished; 137 with 2 bedrooms | could not be opened from this environment (egress policy); verify before relying on it

## FazWaz Perú — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://www.fazwaz.com.pe/departamento-en-alquiler/peru/lima/lima/miraflores
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Search index: 437 rental listings in Miraflores; English-friendly (relevant for foreign tenants) | could not be opened from this environment (egress policy); verify before relying on it

## Ubicasa — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://ubicasa.pe/alquiler/departamento/miraflores-lima-lima
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Search index: 651 apartments; advertises exact map location and PEN/USD prices | could not be opened from this environment (egress policy); verify before relying on it

## LaEncontre — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://www.laencontre.com.pe/alquiler/departamentos/lima/miraflores
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Search index: 293 apartments in Miraflores | could not be opened from this environment (egress policy); verify before relying on it

## Babilonia — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://babilonia.pe/inmuebles/departamentos-en-alquiler-en-lima-lima-miraflores
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Peruvian portal; count not visible in index | could not be opened from this environment (egress policy); verify before relying on it

## InfoCasas Perú — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://www.infocasas.com.pe/alquiler/departamentos/lima/miraflores/1-dormitorio
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Has 1-bedroom Miraflores filter page | could not be opened from this environment (egress policy); verify before relying on it

## RE/MAX Perú — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://www.remax.pe/departamentos-en+alquiler-miraflores-dist/
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Agency network listings; often cross-posted to Urbania/Adondevivir | could not be opened from this environment (egress policy); verify before relying on it

## Mitula Casas — PENDING (not automated this iteration)

- **Method:** not automated — use manual import
- **Target search URL:** https://casas.mitula.pe/casas/alquiler-departamentos-lima-miraflores
- **Records collected:** 0
- **Public access:** public (search index)
- **Pagination:** not tested
- **Detail pages:** not tested
- **Contact data:** not tested
- **Coordinates:** not tested
- **Publication date:** not tested
- **Maintenance fee:** not tested
- **Completeness:** not measured
- **Limitations / errors:** Aggregator of other portals — mostly duplicates; low marginal value | could not be opened from this environment (egress policy); verify before relying on it

## Appendix — audit of GadielRP/mercadolibre-real-estate-scraper (reference implementation)

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
