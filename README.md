# Miraflores Rental Intelligence

A reproducible pipeline that searches public rental portals for **1–2 bedroom apartments in Miraflores
(Lima, Peru) at or below USD 1,000/month**, removes cross-portal duplicates, estimates **street/nightlife noise**
from OpenStreetMap plus listing text, scores every unit on a transparent 100-point scale, and produces a
client-ready Excel shortlist, a PDF executive report and bilingual contact templates.

> **Status (2026-09-24, second pass):** pipeline built and tested end-to-end on synthetic data (36 tests). The live
> search has **not** run yet: in this session the network policy still denies every portal, Apify, OpenStreetMap
> and the FX sources. See [What is needed to run the live search](#what-is-needed-to-run-the-live-search).

## Deliverables

| File | What it is |
|---|---|
| `outputs/Miraflores_Rental_Shortlist_REAL.xlsx` | 8 sheets: **CLIENT_TOP_PICKS** (14-column client view, fits a laptop screen), EXECUTIVE_SHORTLIST, ALL_MATCHES, STRETCH_NEGOTIABLE, NEAR_MISSES, SOURCE_AUDIT, METHODOLOGY, CONTACT_GUIDE — clickable *Open / WhatsApp / Map* links, filters, frozen panes, conditional formatting (Top 5, noise risk, budget class, over-budget, UNKNOWN) |
| `outputs/Miraflores_Rental_Executive_Report_REAL.pdf` (+ `.html`) | 6–10 page English report; page 1 answers "which apartments should we contact first?" with a Top-5 table (thumbnails when available), then requirements, sources, market snapshot, Top 10 cards, quiet-space and value picks, map, lease observations, verification checklist, methodology |
| `outputs/Contact_Templates_REAL.txt` | English + Spanish messages (full and WhatsApp-length). Nothing is ever sent automatically |
| `docs/preview/PREVIEW_SYNTHETIC_*` | Format preview built from **fake** fixtures, watermarked on every page. Not real listings |
| `SOURCE_AUDIT.md`, `RUN_LOG.md` | Source audit (regenerated each run) and an append-only log of every run, failure, cost and exchange rate |

The live `outputs/*_REAL.*` files are created only by `--mode full` on real data. The pipeline refuses to write a
client deliverable from zero listings, rejects any record with demo/synthetic markers in production mode, and never
touches `docs/preview/`.

## What is needed to run the live search

Environment settings (network access, environment variables) are read when a **session starts**, so after
changing them start a **new** Claude Code session on this branch.

1. **Network access** (environment menu → *Edit* → *Network access*) must allow:
   `api.apify.com`, `urbania.pe`, `www.urbania.pe`, `adondevivir.com`, `www.adondevivir.com`,
   `inmuebles.mercadolibre.com.pe`, `departamento.mercadolibre.com.pe`, `overpass-api.de`,
   `nominatim.openstreetmap.org`, `estadisticas.bcrp.gob.pe`, `www.sunat.gob.pe` — and, for page-1 thumbnails,
   the image CDNs `img10.naventcdn.com`, `http2.mlstatic.com` (optional; the report skips images otherwise).
2. **Apify credential** — never in chat, code or git. Either:
   - cloud: add an *API credential* for `api.apify.com` in the environment settings (detected automatically as
     `CLOUD_CREDENTIAL`), or an environment variable `APIFY_TOKEN`; or
   - local: `echo "APIFY_TOKEN=apify_api_…" > .env` (git-ignored).
   At startup the pipeline prints only `Apify authentication: AVAILABLE / NOT AVAILABLE` and the method.
3. Run (same command tomorrow — it re-collects, re-checks the Top 10 and rebuilds the files):
   ```bash
   pip install -r requirements.txt
   python -m src.pipeline --mode preflight   # PASS/FAIL per host + Apify auth status (free)
   python -m src.pipeline --mode full        # validation run → full run → QA → outputs/*_REAL.*
   ```

`--mode full` always starts with a 15-record validation run per source, prints the validation table (valid rent,
bedrooms, area, maintenance, coordinates, contact, date %, errors, cost) to `RUN_LOG.md`, and only then sizes the
paid full run from the observed cost per item, within the USD 5 cap. If Apify is unavailable, no paid call is made
and Urbania/Adondevivir get one polite direct request each (stopping at any bot challenge).

## Commands

| Command | Gates | Network | Writes |
|---|---|---|---|
| `python -m src.pipeline --mode preflight` | 0 | probes only | RUN_LOG.md |
| `python -m src.pipeline --mode validate` | 0–3 | yes (10–20 records/source) | data/raw, SOURCE_AUDIT.md, RUN_LOG.md |
| `python -m src.pipeline --mode full` | 0–10 | yes | everything incl. `outputs/` |
| `python -m src.pipeline --mode report` | 9 | no scraping | rebuilds `outputs/` from `data/processed/` (e.g. after manual QA) |
| `python -m src.pipeline --mode demo` | 5–10 on synthetic data | none | `docs/preview/` only |
| `python -m pytest -q` | — | none | — |

## Configuration

All criteria live in `config/search_config.yaml`: district and bounding box, budget (target / total / stretch /
query ceiling), bedrooms, space bands, scoring weights, every noise-model distance and penalty, livability
distances, red-flag thresholds, de-duplication tolerances, QA depth, per-source Apify inputs and item caps,
the **USD 5 cost ceiling**, and the documented exchange-rate fallback. No code edits are needed to change the search.

## How it works

```
Gate 0  preflight: credentials, reachability of every host
Gate 1  source registry (src/sources/registry.py) → SOURCE_AUDIT.md
Gate 2  validation run, 10–20 records/source (Apify maxItems + maxTotalChargeUsd caps)
Gate 3  field-coverage check → APPROVED / PARTIAL / REJECTED / PENDING per source
Gate 4  full collection for approved sources, budget-tracked
Gate 5  normalise (Spanish text signals, currency with PUBLISHED/CALCULATED provenance) → de-duplicate
Gate 6  OSM Overpass layers (roads by class, nightclubs, bars, restaurants, shops, parks, transit, Malecón,
        district outline) + Nominatim for listings with a street number but no pin
Gate 7  hard gates → 100-pt fit score → categories → value bands → red flags → plain-English summaries
Gate 8  programmatic QA of the top 30, live re-check of the Top 10, manual overrides; re-rank until stable
Gate 9  Excel + HTML/PDF + contact templates
Gate 10 automated final audit (links, district, bedrooms, budget, currency traceability, credentials scan…)
```

Key rules (full detail in the METHODOLOGY sheet):

- **Hard requirements are never overridden by score**: Miraflores only, rent, apartment, 1–2 bedrooms, rent ≤ USD 1,000.
  USD 1,001–1,100 goes to STRETCH_NEGOTIABLE; units just outside the boundary with an exceptional score go to NEAR_MISSES.
- **District**: precise coordinates are checked against the OSM district outline; the portal's district field beats
  title text ("Límite Miraflores" listings in Surquillo are caught). Disagreements are flagged.
- **Noise**: distances to motorway/trunk/primary roads, secondary arterials, nightclubs, bar and restaurant clusters,
  plus interior-facing / acoustic-window / avenue-view / floor evidence → `quietness_score_0_100`, `noise_risk`,
  `noise_confidence`, and a sentence of evidence. Units with HIGH estimated noise rank after all quieter units.
  Always confirm in person (weekday rush hour, evening, weekend night).
- **Duplicates** are grouped, never deleted. A merge needs a hard anchor (portal id, shared photo, ≤40 m, same
  numbered address); similar wording alone never merges units.
- **UNKNOWN beats a guess.** Maintenance is never imputed; totals appear only when both parts are known.
- **Budget classes are never mixed:** STRICT_ALL_IN (rent + known maintenance ≤ USD 1,000), BASE_RENT_COMPLIANT
  (rent ≤ USD 1,000, total over or unknown), STRETCH (rent USD 1,001–1,100, own sheet). All-in units get a 5-point
  ranking preference, so a rent-only unit ranks above one only with a clearly higher fit.
- **Foreign-tenant friendliness** (HIGH / MEDIUM / POTENTIAL_FRICTION / UNKNOWN) is read from listing text only
  (foreigners/passport/corporate lease welcome; guarantor, carné de extranjería or DNI requested…). Silence is
  UNKNOWN and never penalised; it is shown to the client, not scored.
- **Top-10 re-check:** each Top-10 listing is re-opened just before the report is built (direct request, or the
  same Apify actor when the portal blocks scripts); ACTIVE_CONFIRMED only when fresh data came back, and changed
  fields (rent, maintenance, area…) are updated and noted.
- **Final QA (Gate 10)** renders the workbook and every PDF page (`data/processed/qa/`), checks clipped and
  overlapping text, tests the Top-10 links, scans for demo data and credentials, and re-verifies the hard rules.
  Any FAIL gives a non-zero exit.

## Manual steps that feed back into the pipeline

- **Manual QA:** create `data/processed/manual_qa.csv` with columns `source_url,qa_status,qa_notes,checked_at`
  (`qa_status` = `VERIFIED_ACTIVE` or `INACTIVE`), then `python -m src.pipeline --mode report`.
- **Listings from other sites:** fill `config/manual_import_template.csv` and drop it in `data/manual/`.

## Responsible collection

Honest User-Agent, no rotation or proxies, ≥2 s between requests, robots.txt checked for direct HTML, no login,
no CAPTCHA solving: a challenge stops that source and is logged. Phone numbers are advertisers' business contacts
from public listings; raw payloads stay local (`data/raw/` is git-ignored). Credentials are read only from
environment variables / `.env`.

## Layout

```
config/search_config.yaml        all criteria and weights
src/pipeline.py                  gate orchestration, audit, run log
src/sources/                     apify_client, navent (Urbania+Adondevivir), mercadolibre, manual, registry
src/normalize/                   text_signals (ES/EN), currency, normalize
src/deduplicate/dedupe.py        pairwise evidence + union-find groups
src/geospatial/                  osm (Overpass + shapely distances), geocode (Nominatim)
src/scoring/                     noise model, fit score, gates, value bands, red flags
src/qa/qa.py                     programmatic + live QA, manual overrides
src/reporting/                   excel, report (HTML→PDF), contact_templates
tests/                           unit tests + offline end-to-end run on synthetic fixtures
data/{raw,normalized,processed,geo,manual}   pipeline data; outputs/ client deliverables
```
