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

