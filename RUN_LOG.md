# RUN_LOG

Every pipeline run appends a section below: sources attempted, what failed and why, counts, cost, exchange rate,
assumptions and checks. Nothing is removed.

---

## Session notes 2026-09-24 (manual research & checks, before the first automated run)

- **Environment (Gate 0):** Python 3.11.15; Chromium preinstalled (used only to print the PDF). `APIFY_TOKEN` /
  `APIFY_API_TOKEN` **not set**. No Apify MCP server configured. No Google Maps key.
- **Egress policy of the build environment denies every data host** (HTTP 403 at the proxy): `api.apify.com`,
  `apify.com`, `urbania.pe`, `www.adondevivir.com`, `inmuebles.mercadolibre.com.pe`, `listado.mercadolibre.com.pe`,
  `api.mercadolibre.com`, `overpass-api.de`, `overpass.kumi.systems`, `nominatim.openstreetmap.org`,
  `estadisticas.bcrp.gob.pe`, `open.er-api.com`, `www.sunat.gob.pe`, `www.properati.com.pe`, `babilonia.pe`,
  `www.infocasas.com.pe`, `www.laencontre.com.pe`, `casas.mitula.pe`, `www.remax.pe`, `www.fazwaz.com.pe`,
  `ubicasa.pe`. The same hosts were also refused through the WebFetch tool. Nothing was routed around the policy.
- **What did work:** web *search* (titles/URLs only) — used for source discovery (Gate 1) and the exchange-rate
  fallback; PyPI (dependencies); anonymous git read of public GitHub repos (reference-repo audit).
- **Source discovery (web search):** Urbania 859 Miraflores rentals; Adondevivir 821; Ubicasa 651; FazWaz 437;
  Properati 294; LaEncontre 293 (search-index counts, Sep 2026, unverified).
- **Apify actors:** actor pages unreachable; from search snippets — urbania-scraper supports minPrice/maxPrice/
  priceCurrency, minAreaM2/maxAreaM2, minBedrooms/maxBedrooms/minBathrooms and returns phone numbers;
  adondevivir-scraper takes startUrls, returns USD+PEN prices, phone/WhatsApp, and caps free-tier runs at 10 items.
  A `withDetails` flag is **not** confirmed in the Urbania actor docs — the pipeline drops undeclared inputs at run time.
- **Exchange-rate fallback:** SUNAT 24-Sep-2026 compra 3.380 / venta 3.385 (press reports via web search). The live
  BCRP series PD04640PD is always tried first.
- **Reference repo audit:** GadielRP/mercadolibre-real-estate-scraper — rejected for reuse (see SOURCE_AUDIT.md appendix).
- **Offline verification:** full pipeline executed end-to-end on SYNTHETIC fixtures (`--mode demo`) → 7-sheet
  workbook, 8-page PDF, contact templates in `docs/preview/`; 28 unit/integration tests pass. The synthetic run caught
  and fixed: NaN read as text, title text overriding the district field ("Límite Miraflores" in Surquillo), fuzzy
  address matches merging different units, and a loud unit reaching the Top 10.
- **External cost this session:** USD 0.00.

---

## Run 2026-09-24T17:44:10-05:00 — mode `full`

Finished: 2026-09-24T17:44:13-05:00


### Gate 0 — environment & credentials

- APIFY token: NOT SET — add APIFY_TOKEN to .env
- Google Maps key: not set (not required)
- api.apify.com: UNREACHABLE — blocked by egress proxy (403 Forbidden)
- urbania.pe: UNREACHABLE — blocked by egress proxy (403 Forbidden)
- www.adondevivir.com: UNREACHABLE — blocked by egress proxy (403 Forbidden)
- inmuebles.mercadolibre.com.pe: UNREACHABLE — blocked by egress proxy (403 Forbidden)
- overpass-api.de: UNREACHABLE — blocked by egress proxy (403 Forbidden)
- nominatim.openstreetmap.org: UNREACHABLE — blocked by egress proxy (403 Forbidden)
- estadisticas.bcrp.gob.pe: UNREACHABLE — blocked by egress proxy (403 Forbidden)


### Exchange rate

- 1 USD = S/ 3.385 — FALLBACK: SUNAT tipo de cambio venta 24-Sep-2026 (as reported by La República / América TV, obtained via web search) — 2026-09-24T12:00:00-05:00
- live fetch failed (NetworkBlocked: estadisticas.bcrp.gob.pe: ProxyError: 403 Forbidden); documented fallback used


### Gates 1–3 — source audit & validation run (10–20 records/source)

- urbania: PENDING (environment egress blocked) · 0 records · cost USD 0.00 · no records · errors: NetworkBlocked: urbania.pe: ProxyError: 403 Forbidden — not bypassed · notes: APIFY_TOKEN not set — trying one polite direct request; set the token for full coverage
- adondevivir: PENDING (environment egress blocked) · 0 records · cost USD 0.00 · no records · errors: NetworkBlocked: www.adondevivir.com: ProxyError: 403 Forbidden — not bypassed · notes: APIFY_TOKEN not set — trying one polite direct request; set the token for full coverage
- mercadolibre: PENDING (environment egress blocked) · 0 records · cost USD 0.00 · no records · errors: NetworkBlocked: inmuebles.mercadolibre.com.pe: ProxyError: 403 Forbidden — not bypassed
- manual: SKIPPED · 0 records · cost USD 0.00 · no records · notes: no manual files present


### Gate 4 — full collection

- urbania: FAILED · 0 records · cost USD 0.00 · errors: NetworkBlocked: urbania.pe: ProxyError: 403 Forbidden — not bypassed
- adondevivir: FAILED · 0 records · cost USD 0.00 · errors: NetworkBlocked: www.adondevivir.com: ProxyError: 403 Forbidden — not bypassed
- mercadolibre: FAILED · 0 records · cost USD 0.00 · errors: NetworkBlocked: inmuebles.mercadolibre.com.pe: ProxyError: 403 Forbidden — not bypassed
- manual: SKIPPED · 0 records · cost USD 0.00
- total records: 0
- external cost this run: USD 0.00 (cap USD 5.00)


### STOPPED — no listings collected

- No source returned listings, so no client deliverable was produced (an empty shortlist would be misleading). Fix the blockers above and re-run: python -m src.pipeline --mode full


---

## Run 2026-09-24T18:28:08-05:00 — mode `preflight`

Finished: 2026-09-24T18:28:12-05:00


### Gate 0 — network preflight (one small request per host)

- FAIL  api.apify.com — blocked by egress proxy (403 Forbidden)
- FAIL  urbania.pe — blocked by egress proxy (403 Forbidden)
- FAIL  www.urbania.pe — blocked by egress proxy (403 Forbidden)
- FAIL  adondevivir.com — blocked by egress proxy (403 Forbidden)
- FAIL  www.adondevivir.com — blocked by egress proxy (403 Forbidden)
- FAIL  inmuebles.mercadolibre.com.pe — blocked by egress proxy (403 Forbidden)
- FAIL  departamento.mercadolibre.com.pe — blocked by egress proxy (403 Forbidden)
- FAIL  overpass-api.de — blocked by egress proxy (403 Forbidden)
- FAIL  nominatim.openstreetmap.org — blocked by egress proxy (403 Forbidden)
- FAIL  estadisticas.bcrp.gob.pe — blocked by egress proxy (403 Forbidden)
- FAIL  www.sunat.gob.pe — blocked by egress proxy (403 Forbidden)


### Apify authentication

- Apify authentication: NOT AVAILABLE
- Method: ENVIRONMENT_VARIABLE
- Detail: api.apify.com is unreachable from this environment (network egress policy) — allow api.apify.com


---

## Session notes 2026-09-24 (second pass — preparing the REAL run)

- Apify credential supplied by the user: stored only in the git-ignored `.env` (mode 600); never printed, logged or
  committed. It was pasted into chat, so rotating it after the live run is recommended.
- Network re-tested after the user's allowlist change: **all 11 hosts still FAIL** at the egress proxy in this
  session (see preflight above). Environment settings apply to *new* sessions — the live run needs a new session.
- No paid Apify call was made (authentication resolves to NOT AVAILABLE because api.apify.com is unreachable).
  External cost this pass: USD 0.00.
- Portal filter URL grammar verified from the search index: Urbania `?bedroomsNumber=N&priceMax=1150&currencyId=2`;
  Adondevivir `…-con-1-dormitorio.html` / `…-con-2-dormitorios.html`.
- Implemented: per-host PASS/FAIL preflight; Apify auth resolver (CLOUD_CREDENTIAL → ENVIRONMENT_VARIABLE → NONE);
  schema-adaptive actor input + dataset-field logging; validation table; cost-per-item sizing of the full run;
  STRICT_ALL_IN / BASE_RENT_COMPLIANT / STRETCH classes with a 5-point all-in preference; no noise demotion at LOW
  confidence; FOREIGN_TENANT_FRIENDLINESS; production integrity guard (demo/example markers rejected); Top-10 live
  re-check with field comparison; CLIENT_TOP_PICKS sheet; page-1 Top 5 with thumbnails; `_REAL` file names;
  automated Gate-10 QA (renders, clipping/overlap, links, demo/secret scans, hard rules).
- Offline verification on synthetic data (scratch folder, `docs/preview/` left untouched): Gate-10 QA all PASS after
  fixing clipped cells in EXECUTIVE_SHORTLIST found by the new clipping check; 36 tests pass.

---

## Run 2026-09-24T19:23:43-05:00 — mode `preflight`

Finished: 2026-09-24T19:23:51-05:00


### Gate 0 — network preflight (one small request per host)

- PASS  api.apify.com — HTTP 404
- PASS  urbania.pe — HTTP 403
- PASS  www.urbania.pe — HTTP 301
- PASS  adondevivir.com — HTTP 301
- PASS  www.adondevivir.com — HTTP 403
- PASS  inmuebles.mercadolibre.com.pe — HTTP 403
- PASS  departamento.mercadolibre.com.pe — HTTP 403
- PASS  overpass-api.de — HTTP 406
- PASS  nominatim.openstreetmap.org — HTTP 200
- PASS  estadisticas.bcrp.gob.pe — HTTP 200
- PASS  www.sunat.gob.pe — HTTP 200


### Apify authentication

- Apify authentication: AVAILABLE
- Method: CLOUD_CREDENTIAL
- Detail: Authorization injected by the execution environment


---

## Run 2026-09-24T19:30:53-05:00 — mode `validate`

Finished: 2026-09-24T19:31:58-05:00


### Gate 0 — network preflight (one small request per host)

- PASS  api.apify.com — HTTP 404
- PASS  urbania.pe — HTTP 403
- PASS  www.urbania.pe — HTTP 301
- PASS  adondevivir.com — HTTP 301
- PASS  www.adondevivir.com — HTTP 403
- PASS  inmuebles.mercadolibre.com.pe — HTTP 403
- PASS  departamento.mercadolibre.com.pe — HTTP 403
- PASS  overpass-api.de — HTTP 406
- PASS  nominatim.openstreetmap.org — HTTP 200
- PASS  estadisticas.bcrp.gob.pe — HTTP 200
- PASS  www.sunat.gob.pe — HTTP 200


### Apify authentication

- Apify authentication: AVAILABLE
- Method: CLOUD_CREDENTIAL
- Detail: Authorization injected by the execution environment


### Exchange rate

- 1 USD = S/ 3.385 — BCRP series PD04640PD (SBS sell rate), period 23.Set.26 — https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json/2026-09-11/2026-09-25/ing — 2026-09-24T19:31:01-05:00


### Gates 2–3 — validation run (10–20 records/source)

| SOURCE | ACTOR / METHOD | RECORDS | VALID RENT % | VALID BEDROOMS % | VALID AREA % | MAINTENANCE % | COORDINATES % | CONTACT % | DATE % | ERRORS | COST |
|---|---|---|---|---|---|---|---|---|---|---|---|
| urbania | Apify actor scrapers_lat/urbania-scraper (CLOUD_CREDENTIAL) | 10 | 100% | 100% | 0% | 90% | 0% | 0% | 0% | — | USD 0.010 |
| adondevivir | Apify actor scrapers_lat/adondevivir-scraper (CLOUD_CREDENTIAL) | 10 | 100% | 100% | 0% | 90% | 0% | 0% | 0% | — | USD 0.000 |
| mercadolibre | direct HTML (robots.txt respected) | 0 | — | — | — | — | — | — | — | AccessBlocked: inmuebles.mercadolibre.com.pe returned HTTP 200 with a bot challenge — not bypassed | USD 0.000 |
| manual | file import from /home/user/departamento/data/manual | 0 | — | — | — | — | — | — | — | — | USD 0.000 |
- 
- urbania: actor input sent = {"startUrls": ["https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima?bedroomsNumber=1&priceMax=1150&currencyId=2", "https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima?bedroomsNumber=2&priceMax=1150&currencyId=2"], "maxPrice": 1150, "priceCurrency": "USD", "minBedrooms": 1, "maxBedrooms": 2, "withDetails": true, "maxListings": 15}
- urbania: actor input schema properties = ['maxAreaM2', 'maxBedrooms', 'maxListings', 'maxPrice', 'minAreaM2', 'minBathrooms', 'minBedrooms', 'minPrice', 'priceCurrency', 'startUrl', 'startUrls', 'withDetails']
- urbania: pricing = PAY_PER_EVENT: result=$0.0000, details=$0.0000, apify-actor-start=$0.0000
- urbania: dataset fields (non-empty count) = imageUrl(10), title(10), price(10), currency(10), priceUsd(10), pricePen(10), operationType(10), propertyType(10), bedrooms(10), bathrooms(10), totalAreaM2(10), location(10), description(10), publisherLogo(10), url(10), listingId(10), observedAt(10), pricePerM2(10), pricePerM2Currency(10), maintenanceFee(9), maintenanceFeeCurrency(9)
- urbania: notes = no input for 'operation' in actor schema — filter re-applied after extraction; no input for 'property_type' in actor schema — filter re-applied after extraction; exactly 10 items returned — the actor's free-tier evaluation cap is likely active
- adondevivir: actor input sent = {"startUrls": ["https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores-con-1-dormitorio.html", "https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores-con-2-dormitorios.html"], "maxPrice": 1150, "priceCurrency": "USD", "minBedrooms": 1, "maxBedrooms": 2, "withDetails": true, "maxListings": 15}
- adondevivir: actor input schema properties = ['maxAreaM2', 'maxBedrooms', 'maxListings', 'maxPrice', 'minAreaM2', 'minBathrooms', 'minBedrooms', 'minPrice', 'priceCurrency', 'startUrl', 'startUrls', 'withAiFeatures', 'withAiListingSummary', 'withAiTranslate', 'withDetails']
- adondevivir: pricing = PAY_PER_EVENT: result=$0.0000, details=$0.0000, ai_listing_summary=$0.0000, ai_features=$0.0000, ai_translate=$0.0000
- adondevivir: dataset fields (non-empty count) = imageUrl(10), title(10), price(10), currency(10), priceUsd(10), pricePen(10), operationType(10), propertyType(10), isDevelopment(10), bedrooms(10), bathrooms(10), totalAreaM2(10), location(10), description(10), publisherLogo(10), url(10), listingId(10), observedAt(10), pricePerM2(10), pricePerM2Currency(10), maintenanceFee(9), maintenanceFeeCurrency(9)
- adondevivir: notes = no input for 'operation' in actor schema — filter re-applied after extraction; no input for 'property_type' in actor schema — filter re-applied after extraction; exactly 10 items returned — the actor's free-tier evaluation cap is likely active
- manual: notes = no manual files present


---

## Run 2026-09-24T19:54:50-05:00 — mode `validate`

Finished: 2026-09-24T19:57:17-05:00


### Gate 0 — network preflight (one small request per host)

- PASS  api.apify.com — HTTP 404
- PASS  urbania.pe — HTTP 403
- PASS  www.urbania.pe — HTTP 301
- PASS  adondevivir.com — HTTP 301
- PASS  www.adondevivir.com — HTTP 403
- PASS  inmuebles.mercadolibre.com.pe — HTTP 403
- PASS  departamento.mercadolibre.com.pe — HTTP 403
- FAIL  overpass-api.de — ConnectError: [Errno 104] Connection reset by peer
- PASS  nominatim.openstreetmap.org — HTTP 200
- PASS  estadisticas.bcrp.gob.pe — HTTP 200
- PASS  www.sunat.gob.pe — HTTP 200


### Apify authentication

- Apify authentication: AVAILABLE
- Method: CLOUD_CREDENTIAL
- Detail: Authorization injected by the execution environment


### Apify spend ledger — before this run

- 2026-09-25T00:31:42Z run MV7BZ253FVNdz6Y69 (SUCCEEDED): USD 0.080 — result 10×0.0080
- 2026-09-25T00:31:03Z run PbgbgNKQwkgQoYLGO (SUCCEEDED): USD 0.130 — result 10×0.0120 + apify-actor-start 1×0.0100
- 2026-09-25T00:29:13Z run y2LD7HIOQPbzLcmSE (SUCCEEDED): USD 0.080 — result 10×0.0080
- Project spend so far: USD 0.290 of the USD 5.00 project cap (source: Apify run records of scrapers_lat/urbania-scraper, scrapers_lat/adondevivir-scraper since 2026-09-24T00:00:00Z; each run priced as chargedEventCounts × eventPriceUsd, or usageTotalUsd if higher)
- Apify account: USD 0.299 used of USD 5.00 monthly limit (cycle 2026-09-01 → 2026-09-30)
- Usable now: USD 4.701 (the stricter of the project cap and the account allowance)


### Exchange rate

- 1 USD = S/ 3.385 — BCRP series PD04640PD (SBS sell rate), period 23.Set.26 — https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json/2026-09-11/2026-09-25/ing — 2026-09-24T19:55:06-05:00


### Gates 2–3 — validation run (per source)

| SOURCE | ACTOR / METHOD | RECORDS | VALID RENT % | VALID BEDROOMS % | VALID AREA % | MAINTENANCE % | COORDINATES % | CONTACT % | DATE % | ERRORS | COST |
|---|---|---|---|---|---|---|---|---|---|---|---|
| urbania | Apify actor scrapers_lat/urbania-scraper (CLOUD_CREDENTIAL), one run per bedroom segment | 10 | 100% | 100% | 100% | 90% | 0% | 0% | 0% | — | USD 0.020 |
| adondevivir | Apify actor scrapers_lat/adondevivir-scraper (CLOUD_CREDENTIAL), one run per bedroom segment | 10 | 100% | 100% | 100% | 80% | 0% | 0% | 0% | — | USD 0.000 |
| mercadolibre | direct HTML (robots.txt respected) | 0 | — | — | — | — | — | — | — | AccessBlocked: inmuebles.mercadolibre.com.pe returned HTTP 200 with a bot challenge — not bypassed | USD 0.000 |
| manual | file import from /home/user/departamento/data/manual | 0 | — | — | — | — | — | — | — | — | USD 0.000 |
- 
- urbania: actor input schema retrieved; properties = ['maxAreaM2', 'maxBedrooms', 'maxListings', 'maxPrice', 'minAreaM2', 'minBathrooms', 'minBedrooms', 'minPrice', 'priceCurrency', 'startUrl', 'startUrls', 'withDetails']
- urbania 1BR: run YNkRYTmmuwJ1b8tP7 SUCCEEDED · 5/5 records · USD 0.010 · input {"startUrls": ["https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima?bedroomsNumber=1&priceMax=1150&currencyId=2"], "maxPrice": 1150, "priceCurrency": "USD", "minBedrooms": 1, "maxBedrooms": 1, "withDetails": true, "maxListings": 5}
- urbania 2BR: run qa8V3EdLXMoN7IhQT SUCCEEDED · 5/5 records · USD 0.010 · input {"startUrls": ["https://urbania.pe/buscar/alquiler-de-departamentos-en-miraflores--lima--lima?bedroomsNumber=2&priceMax=1150&currencyId=2"], "maxPrice": 1150, "priceCurrency": "USD", "minBedrooms": 2, "maxBedrooms": 2, "withDetails": true, "maxListings": 5}
- urbania: dataset fields (non-empty count) = imageUrl(10), title(10), price(10), currency(10), priceUsd(10), pricePen(10), operationType(10), propertyType(10), bedrooms(10), bathrooms(10), totalAreaM2(10), location(10), description(10), publisherLogo(10), url(10), listingId(10), observedAt(10), pricePerM2(10), pricePerM2Currency(10), _search_segment(10), maintenanceFee(9), maintenanceFeeCurrency(9)
- urbania: notes = no input for 'operation' in actor schema — filter re-applied after extraction; no input for 'property_type' in actor schema — filter re-applied after extraction
- adondevivir: actor input schema retrieved; properties = ['maxAreaM2', 'maxBedrooms', 'maxListings', 'maxPrice', 'minAreaM2', 'minBathrooms', 'minBedrooms', 'minPrice', 'priceCurrency', 'startUrl', 'startUrls', 'withAiFeatures', 'withAiListingSummary', 'withAiTranslate', 'withDetails']
- adondevivir 1BR: run zqGD01MvW5Dd5pmYB SUCCEEDED · 5/5 records · USD 0.000 · input {"startUrls": ["https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores-con-1-dormitorio.html"], "maxPrice": 1150, "priceCurrency": "USD", "minBedrooms": 1, "maxBedrooms": 1, "withDetails": true, "maxListings": 5}
- adondevivir 2BR: run dz2qD2WPOpQ9uUONI SUCCEEDED · 5/5 records · USD 0.000 · input {"startUrls": ["https://www.adondevivir.com/departamentos-en-alquiler-en-miraflores-con-2-dormitorios.html"], "maxPrice": 1150, "priceCurrency": "USD", "minBedrooms": 2, "maxBedrooms": 2, "withDetails": true, "maxListings": 5}
- adondevivir: dataset fields (non-empty count) = imageUrl(10), title(10), price(10), currency(10), priceUsd(10), pricePen(10), operationType(10), propertyType(10), isDevelopment(10), bedrooms(10), bathrooms(10), totalAreaM2(10), location(10), description(10), publisherLogo(10), url(10), listingId(10), observedAt(10), pricePerM2(10), pricePerM2Currency(10), _search_segment(10), maintenanceFee(8), maintenanceFeeCurrency(8)
- adondevivir: notes = no input for 'operation' in actor schema — filter re-applied after extraction; no input for 'property_type' in actor schema — filter re-applied after extraction
- manual: notes = no manual files present


### Validation sample — per source and bedroom segment

| SOURCE | BEDROOM SEGMENT | RAW RECORDS | VALID RENT % | VALID BEDROOMS % | VALID AREA % | MAINTENANCE % | SPECIFIC ADDRESS % | COORDINATES % | USABLE URL % | UNIQUE AFTER DEDUPE | ACTUAL COST | ERRORS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| urbania | 1BR | 5 | 100% | 100% | 100% | 100% | 20% | 20% | 100% | 5 | USD 0.010 | — |
| urbania | 2BR | 5 | 100% | 100% | 100% | 100% | 0% | 0% | 100% | 5 | USD 0.010 | — |
| adondevivir | 1BR | 5 | 100% | 100% | 100% | 80% | 0% | 0% | 100% | 4 | USD 0.000 | — |
| adondevivir | 2BR | 5 | 100% | 100% | 100% | 80% | 20% | 20% | 100% | 2 | USD 0.000 | — |
| mercadolibre | all | 0 | — | — | — | — | — | — | — | 0 | USD 0.000 | AccessBlocked: inmuebles.mercadolibre.com.pe returned HTTP 200 with a bot challenge — not bypassed |
- 
- VALID BEDROOMS = bedroom count present and equal to the segment searched. UNIQUE AFTER DEDUPE = new properties this row adds (rows are counted in order, so a cross-post is credited to the first portal). ACTUAL COST = Apify run records of that segment's runs.


### Validation sample — coordinates

- all 20 records: listing-provided 0 · high-confidence geocode 0 · medium-confidence (street-level) 2 · unknown 18
- 16 unique properties: listing-provided 0 · high-confidence geocode 0 · medium-confidence (street-level) 2 · unknown 14
- Nominatim queries made: 2
- District/neighbourhood-only locations are never geocoded (coordinates stay UNKNOWN).
- urbania:151178161 → STREET_BLOCK from description: “Cdra. 61 de Av. Paseo de la República” → MEDIUM
- adondevivir:149641213 → STREET_NUMBER from description: “Av. Paseo de la República 3982” → MEDIUM


### Validation sample — currency normalisation

- Reference rate: 1 USD = S/ 3.385 — BCRP series PD04640PD (SBS sell rate), period 23.Set.26 — https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json/2026-09-11/2026-09-25/ing
- records publishing both currencies: 20; CURRENCY_CONVERSION_MISMATCH (>5%): 1
- adondevivir:150518801 (PEN-priced): published S/ 3,000 · published USD 940 · normalised USD 886.26 · published vs S/÷rate +6.1% · CURRENCY_CONVERSION_MISMATCH
- adondevivir:149641213 (PEN-priced): published S/ 3,360 · published USD 960 · normalised USD 992.61 · published vs S/÷rate -3.3%
- adondevivir:151167366 (PEN-priced): published S/ 3,110 · published USD 900 · normalised USD 918.76 · published vs S/÷rate -2.0%
- urbania:151167358 (PEN-priced): published S/ 3,110 · published USD 900 · normalised USD 918.76 · published vs S/÷rate -2.0%
- adondevivir:151159980 (PEN-priced): published S/ 2,500 · published USD 750 · normalised USD 738.55 · published vs S/÷rate +1.6%
- urbania:151159973 (PEN-priced): published S/ 2,500 · published USD 750 · normalised USD 738.55 · published vs S/÷rate +1.6%
- urbania:150634895 (PEN-priced): published S/ 3,300 · published USD 990 · normalised USD 974.89 · published vs S/÷rate +1.5%
- urbania:151111723 (PEN-priced): published S/ 2,600 · published USD 775 · normalised USD 768.09 · published vs S/÷rate +0.9%
- adondevivir:146109648 (PEN-priced): published S/ 2,452 · published USD 730 · normalised USD 724.37 · published vs S/÷rate +0.8%
- urbania:151178161 (PEN-priced): published S/ 2,300 · published USD 685 · normalised USD 679.47 · published vs S/÷rate +0.8%
- adondevivir:151122933 (PEN-priced): published S/ 2,800 · published USD 823 · normalised USD 827.18 · published vs S/÷rate -0.5%
- urbania:151124896 (PEN-priced): published S/ 2,528 · published USD 750 · normalised USD 746.82 · published vs S/÷rate +0.4%
- adondevivir:151058348 (PEN-priced): published S/ 3,373 · published USD 1,000 · normalised USD 996.45 · published vs S/÷rate +0.4%
- urbania:150439988 (PEN-priced): published S/ 3,740 · published USD 1,100 · normalised USD 1,104.87 · published vs S/÷rate -0.4%
- urbania:151011858 (PEN-priced): published S/ 2,890 · published USD 850 · normalised USD 853.77 · published vs S/÷rate -0.4%
- urbania:151058338 (PEN-priced): published S/ 3,373 · published USD 1,000 · normalised USD 996.45 · published vs S/÷rate +0.4%
- adondevivir:150439990 (PEN-priced): published S/ 3,740 · published USD 1,100 · normalised USD 1,104.87 · published vs S/÷rate -0.4%
- adondevivir:151162497 (PEN-priced): published S/ 2,600 · published USD 770 · normalised USD 768.09 · published vs S/÷rate +0.2%
- adondevivir:151127641 (PEN-priced): published S/ 3,380 · published USD 1,000 · normalised USD 998.52 · published vs S/÷rate +0.1%
- urbania:150752635 (PEN-priced): published S/ 2,200 · published USD 650 · normalised USD 649.93 · published vs S/÷rate +0.0%


### Validation sample — de-duplication

- raw records: 20 · duplicate groups (≥2 records): 4 · unique properties: 16
- G0002: urbania:150439988, adondevivir:150439990 — 1BR · 93.0 m² · USD 1,105 — evidence: ≈adondevivir:150439990 (same area, same price, same bathrooms, same maintenance, same advertiser, similar title, description 100% similar, shared photo id)
- G0007: urbania:151058338, adondevivir:151058348 — 2BR · 87.0 m² · USD 996 — evidence: ≈adondevivir:151058348 (same area, same price, same bathrooms, same maintenance, same advertiser, similar title, description 100% similar, shared photo id)
- G0009: urbania:151159973, adondevivir:151159980 — 2BR · 96.0 m² · USD 739 — evidence: ≈adondevivir:151159980 (same area, same price, same bathrooms, same maintenance, same advertiser, similar title, description 100% similar, shared photo id)
- G0010: urbania:151167358, adondevivir:151167366 — 2BR · 81.0 m² · USD 919 — evidence: ≈adondevivir:151167366 (same area, same price, same bathrooms, same maintenance, same advertiser, similar title, description 100% similar, shared photo id)
- possible duplicates kept separate (score close but no identity anchor): 2


### Validation sample — Miraflores + rent + apartment + 1–2 bedroom rules

- unique properties passing the hard rules: 16 of 16 (1BR 9, 2BR 7)
- categories (unique): PRIMARY 15, EXCLUDED 1
- exclusion reasons: rent USD 1105 above stretch ceiling (1)


### Apify spend — this run

- urbania 1BR: USD 0.010 · cumulative USD 0.300 of 5.00 · remaining USD 4.691 — ACTUAL from Apify run record YNkRYTmmuwJ1b8tP7: apify-actor-start 1×0.0100; usageTotalUsd=0.01
- urbania 2BR: USD 0.010 · cumulative USD 0.310 of 5.00 · remaining USD 4.681 — ACTUAL from Apify run record qa8V3EdLXMoN7IhQT: apify-actor-start 1×0.0100; usageTotalUsd=0.01
- adondevivir 1BR: USD 0.000 · cumulative USD 0.310 of 5.00 · remaining USD 4.681 — ACTUAL from Apify run record zqGD01MvW5Dd5pmYB: no billable events; usageTotalUsd=0.0
- adondevivir 2BR: USD 0.000 · cumulative USD 0.310 of 5.00 · remaining USD 4.681 — ACTUAL from Apify run record dz2qD2WPOpQ9uUONI: no billable events; usageTotalUsd=0.0
- This run: USD 0.020 · project cumulative: USD 0.310 of USD 5.00 · remaining: USD 4.681


---

## Run 2026-09-24T19:59:12-05:00 — mode `spend reconciliation (read-only, no Actor runs)`

Finished: 2026-09-24T19:59:16-05:00


### Correction to the validation run above

- The validation run's 'Apify spend — this run' section under-reported: it read each run record right after the run ended, when Apify had booked only the start events (USD 0.020 logged).
- Settled Apify run records for those four runs: urbania 1BR USD 0.070, urbania 2BR USD 0.070, adondevivir 1BR USD 0.040, adondevivir 2BR USD 0.040 = USD 0.220.
- Fixed in code: each run's charge is now never taken below start events + delivered records × per-record price, the record is re-read until it settles, and every run is reconciled with Apify at the end of the pipeline run.


### Apify spend ledger — before this run

- 2026-09-25T00:56:55Z run dz2qD2WPOpQ9uUONI (SUCCEEDED): USD 0.040 — result 5×0.0080
- 2026-09-25T00:55:52Z run zqGD01MvW5Dd5pmYB (SUCCEEDED): USD 0.040 — result 5×0.0080
- 2026-09-25T00:55:45Z run qa8V3EdLXMoN7IhQT (SUCCEEDED): USD 0.070 — result 5×0.0120 + apify-actor-start 1×0.0100
- 2026-09-25T00:55:07Z run YNkRYTmmuwJ1b8tP7 (SUCCEEDED): USD 0.070 — result 5×0.0120 + apify-actor-start 1×0.0100
- 2026-09-25T00:31:42Z run MV7BZ253FVNdz6Y69 (SUCCEEDED): USD 0.080 — result 10×0.0080
- 2026-09-25T00:31:03Z run PbgbgNKQwkgQoYLGO (SUCCEEDED): USD 0.130 — result 10×0.0120 + apify-actor-start 1×0.0100
- 2026-09-25T00:29:13Z run y2LD7HIOQPbzLcmSE (SUCCEEDED): USD 0.080 — result 10×0.0080
- Project spend so far: USD 0.510 of the USD 5.00 project cap (source: Apify run records of scrapers_lat/urbania-scraper, scrapers_lat/adondevivir-scraper since 2026-09-24T00:00:00Z; each run priced as chargedEventCounts × eventPriceUsd, or usageTotalUsd if higher)
- Apify account: USD 0.519 used of USD 5.00 monthly limit (cycle 2026-09-01 → 2026-09-30)
- Usable now: USD 4.481 (the stricter of the project cap and the account allowance)

