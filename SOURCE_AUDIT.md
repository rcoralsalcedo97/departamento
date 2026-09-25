# SOURCE_AUDIT

Research date: 2026-09-24. Last automated update: 2026-09-24T19:57:13-05:00.

Status meanings: **APPROVED** = validation run returned records with ≥90% core-field coverage (URL, rent, currency, bedrooms) and ≥60% area coverage · **PARTIAL** = records returned but weaker coverage or errors · **REJECTED** = source answered but could not be used (e.g. bot challenge — never bypassed) · **PENDING** = not yet testable (environment egress blocked or not automated).

## Reachability from the run environment

| Host | Result |
|---|---|
| api.apify.com | reachable — HTTP 404 |
| urbania.pe | reachable — HTTP 403 |
| www.urbania.pe | reachable — HTTP 301 |
| adondevivir.com | reachable — HTTP 301 |
| www.adondevivir.com | reachable — HTTP 403 |
| inmuebles.mercadolibre.com.pe | reachable — HTTP 403 |
| departamento.mercadolibre.com.pe | reachable — HTTP 403 |
| overpass-api.de | UNREACHABLE — ConnectError: [Errno 104] Connection reset by peer |
| nominatim.openstreetmap.org | reachable — HTTP 200 |
| estadisticas.bcrp.gob.pe | reachable — HTTP 200 |
| www.sunat.gob.pe | reachable — HTTP 200 |

## Urbania — APPROVED

- **Method:** Apify actor scrapers_lat/urbania-scraper (CLOUD_CREDENTIAL), one run per bedroom segment
- **Target search URL:** https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima
- **Records collected:** 10
- **Public access:** Public search and detail pages, no login
- **Pagination:** Handled by actor (direct: ?page=N)
- **Detail pages:** Paid Apify plans only ('details' event). On the FREE plan the actor returns list-level output only — confirmed in validation (details events = 0)
- **Contact data:** Detail pages only (paid plan): agentPhone / agentWhatsapp. Free plan: none — contact via listing
- **Coordinates:** Detail pages only (paid plan). Free plan: none — geocoded only from specific address text · observed 0%
- **Publication date:** Detail pages only (paid plan: publishDate). Free plan: none · observed 0%
- **Maintenance fee:** Expected when advertiser publishes 'Mantenimiento' · observed 90%
- **Completeness:** URL 100%, rent 100%, currency 100%, bedrooms 100%, area 100%, maintenance 90%, coordinates 0%, address 0%, publication date 0%, contact 0%, description 100%, images 100%
- **Limitations / errors:** no input for 'operation' in actor schema — filter re-applied after extraction; no input for 'property_type' in actor schema — filter re-applied after extraction | Navent platform uses bot protection; direct scraping not attempted beyond one polite request. Actor docs: free Apify plans are capped at 10 records per run and list-level output, so collection runs one Actor run per bedroom segment. Every filter is re-applied after extraction.

## Adondevivir — APPROVED

- **Method:** Apify actor scrapers_lat/adondevivir-scraper (CLOUD_CREDENTIAL), one run per bedroom segment
- **Target search URL:** https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores.html
- **Records collected:** 10
- **Public access:** Public search and detail pages, no login
- **Pagination:** Handled by actor (direct: -pagina-N.html)
- **Detail pages:** Paid Apify plans only ('details' event). FREE plan: list-level output only (confirmed)
- **Contact data:** Detail pages only (paid plan): agentPhone / agentWhatsapp. Free plan: none — contact via listing
- **Coordinates:** Detail pages only (paid plan). Free plan: none — geocoded only from specific address text · observed 0%
- **Publication date:** Detail pages only (paid plan: publishedDate). Free plan: none · observed 0%
- **Maintenance fee:** Expected when published · observed 80%
- **Completeness:** URL 100%, rent 100%, currency 100%, bedrooms 100%, area 100%, maintenance 80%, coordinates 0%, address 0%, publication date 0%, contact 0%, description 100%, images 100%
- **Limitations / errors:** no input for 'operation' in actor schema — filter re-applied after extraction; no input for 'property_type' in actor schema — filter re-applied after extraction | Actor docs: free Apify plans are capped at 10 listings per run, list-level only. Same backend as Urbania, so many listings are cross-posted under a different posting id — grouped by de-duplication (same photo file, advertiser, description, area, price).

## Mercado Libre Inmuebles Perú — REJECTED

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
- **Limitations / errors:** AccessBlocked: inmuebles.mercadolibre.com.pe returned HTTP 200 with a bot challenge — not bypassed | Page layout changes periodically; parser supports current poly-card and legacy layouts. Reference repo rejected: no licence ('Private'), targets Mexico (MLM), relies on webdriver masking, UA rotation and residential proxy rotation.

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
