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

