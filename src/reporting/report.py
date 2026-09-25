"""Executive report: HTML (self-contained, inline SVG) → PDF via headless Chromium.

One builder serves both languages: ``build_report_html(..., lang="hi")`` renders the *same* final,
already-ranked records with Hindi text (``i18n``). Names, addresses, URLs, IDs and numbers are
identical in both; every Top-10 row/card carries ``data-*`` attributes with its facts so the
bilingual parity check can compare the two documents exactly.
"""
from __future__ import annotations

import html
import math
from pathlib import Path

import pandas as pd

from . import common as C
from .i18n import L, code_hi, language, t

E = html.escape
SERIES = {1: "#2a78d6", 2: "#eb6834"}          # validated categorical slots 1–2 (dataviz reference palette)
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
NAVY = "#1f3a4d"
RELIABLE_PRECISION = ("EXACT", "STREET_NUMBER")

CSS = """
@page { size: A4; }
* { box-sizing: border-box; }
body { font-family: "Liberation Sans", "Helvetica Neue", Arial, sans-serif; color: #1b1b1b; font-size: 10pt;
       line-height: 1.42; margin: 0; background: #fff; }
body.hi { font-family: "Noto Sans Devanagari", "Noto Sans", "Liberation Sans", sans-serif; line-height: 1.55; }
h1 { font-size: 21pt; color: #1f3a4d; margin: 0 0 1.5mm; letter-spacing: -0.2px; }
h2 { font-size: 13pt; color: #1f3a4d; margin: 6mm 0 2.5mm; padding-bottom: 1.5mm; border-bottom: 1.5px solid #1f3a4d; }
h3 { font-size: 10.5pt; margin: 0 0 1.5mm; color: #0b0b0b; }
p { margin: 0 0 2.3mm; }
a { color: #1f5fbf; text-decoration: none; }
.sub { color: #52514e; font-size: 9pt; }
.banner { background: #fde8e7; color: #9b1c13; border: 1px solid #f3b4ae; padding: 3mm 4mm; font-weight: bold;
          margin: 0 0 4mm; border-radius: 3px; }
.tiles { display: flex; gap: 2.5mm; margin: 3mm 0; }
.tile { flex: 1; border: 1px solid #e1e0d9; border-radius: 4px; padding: 2.4mm; background: #fcfcfb; }
.tile .label { color: #52514e; font-size: 7.8pt; line-height: 1.25; }
.tile .value { font-size: 16pt; font-weight: 600; color: #0b0b0b; }
table { border-collapse: collapse; width: 100%; font-size: 8.6pt; margin: 1mm 0 3mm; }
th { text-align: left; background: #1f3a4d; color: #fff; padding: 1.5mm 1.6mm; font-weight: 600; vertical-align: top; }
td { padding: 1.3mm 1.6mm; border-bottom: 1px solid #e6e6e2; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:nth-child(even) td { background: #f7f8f9; }
table.top5 { font-size: 7.6pt; table-layout: fixed; }
table.top5 th { font-size: 7.4pt; padding: 1.3mm 1.2mm; }
table.top5 td { padding: 1.2mm 1.2mm; word-wrap: break-word; }
table.top5 .rk { font-weight: bold; font-size: 11pt; color: #1f3a4d; text-align: center; }
.card { border: 1px solid #d9dce1; border-radius: 5px; padding: 2.5mm 3.4mm; margin: 0 0 3mm; page-break-inside: avoid;
        font-size: 8.8pt; line-height: 1.36; }
body.hi .card { line-height: 1.5; }
.card .head { display: flex; justify-content: space-between; align-items: baseline; gap: 4mm; }
.rank { display: inline-block; min-width: 7.5mm; height: 7.5mm; line-height: 7.5mm; text-align: center; border-radius: 50%;
        background: #1f3a4d; color: #fff; font-weight: bold; margin-right: 2mm; }
.fit { color: #52514e; font-size: 8.6pt; white-space: nowrap; }
.facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5mm 4mm; margin: 1.2mm 0 1.5mm; font-size: 8.6pt; }
.facts div span { color: #6b6a66; display: block; font-size: 7.6pt; }
.pill { display: inline-block; padding: 0.2mm 1.8mm; border-radius: 9px; font-size: 7.8pt; font-weight: bold; }
.QUIET { background: #d8f0dd; color: #0b6b22; } .PQUIET { background: #e6f4e8; color: #2d6b3a; }
.UNCERTAIN { background: #ecebe6; color: #4a4944; } .NOISY { background: #fbd5d2; color: #9b1c13; }
.kv { margin: 0.6mm 0; } .kv b { color: #1f3a4d; }
.warn { color: #9b1c13; font-weight: bold; }
.foot { display: flex; justify-content: space-between; gap: 4mm; margin-top: 1mm; font-size: 8pt; }
td.nw, th.nw { white-space: nowrap; }
.links a { margin-right: 3.5mm; font-weight: 600; white-space: nowrap; }
a.view { white-space: nowrap; font-weight: 600; }
.muted { color: #6b6a66; }
.pb { page-break-before: always; }
ul { margin: 1mm 0 3mm 5mm; padding: 0; } li { margin-bottom: 1mm; }
figure { margin: 2mm 0 4mm; page-break-inside: avoid; } figcaption { color: #52514e; font-size: 8.3pt; margin-top: 1mm; }
.keep { page-break-inside: avoid; } tr { page-break-inside: avoid; }
.STRICT_ALL_IN { background: #d8f0dd; color: #0b6b22; } .BASE_RENT_COMPLIANT { background: #ffe8b3; color: #8a4b00; }
.STRETCH { background: #fbd5d2; color: #9b1c13; } .BORDERLINE { background: #ecebe6; color: #4a4944; }
.lead { font-size: 9.6pt; margin: 1mm 0 2mm; }
.legend { font-size: 8.2pt; color: #3a3935; }
.callout { border: 1px solid #d9dce1; border-left: 3px solid #eb6834; border-radius: 4px; padding: 2mm 3mm 0.5mm; margin: 0 0 3mm; }
.callout h3 { color: #1f3a4d; font-size: 10pt; margin: 0 0 1mm; }
table.br2t { font-size: 8pt; margin: 0.5mm 0 1mm; }
body.hi ul.meth { font-size: 9pt; line-height: 1.45; } body.hi ul.meth li { margin-bottom: 0.6mm; }
"""

NOISE_CLASS = {"LIKELY QUIET": "QUIET", "POSSIBLY QUIET": "PQUIET", "NOISE UNCERTAIN": "UNCERTAIN",
               "LIKELY NOISY": "NOISY"}
BUDGET_LABEL = {"STRICT_ALL_IN": "All-in ≤ USD 1,000", "BASE_RENT_COMPLIANT": "Rent ≤ USD 1,000 · total over/unknown",
                "STRETCH": "Stretch USD 1,001–1,100", "BORDERLINE": "Borderline — just above USD 1,100"}


def _short(text: str, limit: int = 150) -> str:
    text = str(text or "").split(" | ")[0]
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _fmt_usd(v) -> str:
    v = C.num(v)
    return f"USD {v:,.0f}" if v is not None else t("UNKNOWN")


def _nt(text) -> str:
    """Names, addresses and titles are shown exactly as published (never translated)."""
    return f'<span translate="no">{E(str(text))}</span>'


def _total(r: dict):
    if r.get("maintenance_included_in_rent") is True:
        return C.num(r.get("rent_usd"))
    return C.num(r.get("estimated_total_monthly_usd"))


def _area_text(r: dict) -> str:
    a = C.num(r.get("area_m2"))
    return f"{a:.0f} m²" if a else t("UNKNOWN")


def _noise_pill(r: dict) -> str:
    label = r.get("noise_label") or "NOISE UNCERTAIN"
    return f"<span class='pill {NOISE_CLASS.get(label, 'UNCERTAIN')}'>{E(t(label))}</span>"


def _noise_line(r: dict) -> str:
    risk = r.get("noise_risk") or "UNKNOWN"
    conf = str(r.get("noise_confidence") or "low").lower()
    return L(f"risk {risk} · confidence {conf.upper()}", f"जोखिम {t(risk) if risk != 'UNKNOWN' else 'अज्ञात'} · "
             f"विश्वसनीयता {t(conf)}")


def _quiet_score(r: dict) -> str:
    if r.get("quietness_supported") is False or r.get("noise_risk") == "UNKNOWN":
        return L("not supportable (no location, no noise wording)", "आकलन संभव नहीं (स्थान और शोर की जानकारी नहीं)")
    return f"{r.get('quietness_score_0_100')}/100"


def why_matches(r: dict) -> str:
    beds = int(C.num(r.get("bedrooms")) or 0)
    area = C.num(r.get("area_m2"))
    band = str(r.get("space_band") or "").replace("_", " ").lower()
    parts = [f"{beds}-bedroom, {area:.0f} m² ({band} for a {beds}BR)" if area else f"{beds}-bedroom (area not published)"]
    furn = {"Yes": "furnished", "Semi": "semi-furnished", "No": "unfurnished"}.get(C.furnished_text(r))
    if furn:
        parts.append(furn)
    total = _total(r)
    if total is not None and total <= 1000:
        parts.append(f"all-in ≈ USD {total:,.0f}")
    parts += [x for x in str(r.get("main_advantage") or "").split("; ")
              if x and not (area and x.startswith(f"{area:.0f} m²")) and not x.startswith("all-in")
              and x not in ("furnished", "meets all hard requirements")]
    return "; ".join(t(p) for p in parts)


def _availability(r: dict) -> str:
    status = r.get("active_status") or "UNKNOWN"
    ts = r.get("qa_checked_at") or r.get("scraped_at") or ""
    if status == "ACTIVE_CONFIRMED":
        return L(f"ACTIVE_CONFIRMED — listing re-opened successfully on {ts}; availability is never guaranteed",
                 f"ACTIVE_CONFIRMED — {ts} को विज्ञापन दोबारा सफलतापूर्वक खोला गया; उपलब्धता की गारंटी नहीं")
    if status == "LIKELY_ACTIVE":
        return L(f"LIKELY_ACTIVE — returned by the live portal search on {r.get('scraped_at')}; an automated re-check "
                 "was not possible — open the link to confirm",
                 f"LIKELY_ACTIVE — {r.get('scraped_at')} को पोर्टल की लाइव खोज में मिला; स्वचालित पुनः-जाँच संभव नहीं "
                 "हुई — पुष्टि के लिए लिंक खोलें")
    return L("UNKNOWN — availability could not be confirmed; open the link", "UNKNOWN — उपलब्धता की पुष्टि नहीं हो सकी; लिंक खोलें")


def _location_line(r: dict) -> str:
    zone = r.get("subarea") if str(r.get("subarea") or "").strip().lower() not in ("", "lima", "miraflores") else None
    where = r.get("address") or (f"{zone}, {r.get('district') or 'Miraflores'}" if zone else r.get("district")) or ""
    prec, conf = r.get("coord_precision"), r.get("geocoding_confidence")
    if r.get("coord_source") == "LISTING" and prec in RELIABLE_PRECISION:
        note = L("exact position published by the portal", "पोर्टल द्वारा प्रकाशित सटीक स्थान")
    elif conf == "HIGH":
        note = L("position from the street address in the listing (high confidence)",
                 "विज्ञापन के पते से स्थान निर्धारित (उच्च विश्वसनीयता)")
    elif conf == "MEDIUM" or prec in ("STREET_LEVEL", "APPROXIMATE"):
        note = L("street-level position only (medium confidence) — the exact building is not known",
                 "केवल सड़क-स्तर का स्थान (मध्यम विश्वसनीयता) — सटीक भवन ज्ञात नहीं")
    else:
        note = L("exact location UNKNOWN — the listing gives only the district/zone",
                 "सटीक स्थान ज्ञात नहीं — विज्ञापन में केवल ज़िला/क्षेत्र दिया है")
    return f"{_nt(where)} — {E(note)}" if where else E(note)


def _foreign_line(r: dict) -> str:
    level = r.get("foreign_tenant_friendliness") or "UNKNOWN"
    ev = str(r.get("foreign_tenant_evidence") or "")
    if level == "UNKNOWN":
        body = L("not stated in the listing — confirm passport, carné de extranjería, proof of income, guarantor (aval), "
                 "deposit and minimum term",
                 "विज्ञापन में उल्लेख नहीं — पासपोर्ट, carné de extranjería, आय का प्रमाण, गारंटर (aval), जमा राशि और "
                 "न्यूनतम अवधि की पुष्टि करें")
    else:
        body = t(ev) if ev else ""
    return f'<p class="kv"><b>{E(L("Foreign tenant.", "विदेशी किरायेदार।"))}</b> {E(code_hi(level))} — {E(body)}</p>'


def _data_attrs(rank: int, r: dict) -> str:
    """Facts used by the bilingual parity check (identical in EN and HI by construction)."""
    vals = {"rank": rank, "id": f"{r.get('source')}:{r.get('source_listing_id')}", "url": r.get("source_url"),
            "rent-usd": f"{C.num(r.get('rent_usd')):.2f}" if C.num(r.get("rent_usd")) is not None else "",
            "rent-pen": f"{C.num(r.get('rent_pen')):.2f}" if C.num(r.get("rent_pen")) is not None else "",
            "maint": C.maintenance_text(r), "total": f"{_total(r):.2f}" if _total(r) is not None else "",
            "beds": int(C.num(r.get("bedrooms")) or 0), "area": C.num(r.get("area_m2")) or "",
            "furnished": C.furnished_text(r), "noise": r.get("noise_label"), "risk": r.get("noise_risk"),
            "conf": r.get("noise_confidence"), "status": r.get("active_status"),
            "score": f"{C.num(r.get('fit_score')):.1f}", "budget": r.get("budget_class")}
    return " ".join(f'data-{k}="{E(str(v))}"' for k, v in vals.items())


# --------------------------------------------------------------------------- charts
def scatter_svg(df: pd.DataFrame, top: pd.DataFrame, budget: float) -> str:
    pts = df[df["area_m2"].notna() & df["rent_usd"].notna()]
    if pts.empty:
        return f"<p class='muted'>{E(L('Not enough data with published area to draw the rent–area chart.', 'किराया–क्षेत्रफल चार्ट के लिए पर्याप्त आँकड़े नहीं हैं।'))}</p>"
    W, H, L_, R, T, B = 700, 240, 52, 14, 24, 36
    xmax = max(40, math.ceil(pts["area_m2"].max() / 20) * 20)
    xmin = max(0, math.floor(pts["area_m2"].min() / 20) * 20)
    ymax = max(budget * 1.12, math.ceil(pts["rent_usd"].max() / 100) * 100)
    ymin = max(0, math.floor(pts["rent_usd"].min() / 100) * 100 - 100)
    sx = lambda x: L_ + (x - xmin) / (xmax - xmin) * (W - L_ - R)
    sy = lambda y: T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B)
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="rent vs area" '
           f'style="background:{SURFACE};font-family:inherit">']
    ystep = 100 if ymax - ymin <= 900 else 200
    y = ymin
    while y <= ymax:
        out.append(f'<line x1="{L_}" x2="{W - R}" y1="{sy(y):.1f}" y2="{sy(y):.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{L_ - 6}" y="{sy(y) + 3:.1f}" font-size="9" fill="{MUTED}" text-anchor="end">{y:,.0f}</text>')
        y += ystep
    x = xmin
    xstep = 10 if xmax - xmin <= 100 else 20
    while x <= xmax:
        out.append(f'<text x="{sx(x):.1f}" y="{H - B + 14}" font-size="9" fill="{MUTED}" text-anchor="middle">{x:.0f}</text>')
        x += xstep
    out.append(f'<line x1="{L_}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{AXIS}" stroke-width="1"/>')
    out.append(f'<line x1="{L_}" x2="{W - R}" y1="{sy(budget):.1f}" y2="{sy(budget):.1f}" stroke="{INK2}" stroke-width="1"/>')
    out.append(f'<text x="{W - R}" y="{sy(budget) - 4:.1f}" font-size="9" fill="{INK2}" text-anchor="end">'
               f'{E(L(f"USD {budget:,.0f} budget", f"USD {budget:,.0f} बजट"))}</text>')
    out.append(f'<text x="{(L_ + W - R) / 2}" y="{H - 4}" font-size="9.5" fill="{INK2}" text-anchor="middle">'
               f'{E(L("Floor area (m²)", "क्षेत्रफल (m²)"))}</text>')
    out.append(f'<text x="12" y="{(T + H - B) / 2}" font-size="9.5" fill="{INK2}" text-anchor="middle" '
               f'transform="rotate(-90 12 {(T + H - B) / 2})">{E(L("Monthly rent (USD)", "मासिक किराया (USD)"))}</text>')
    top_ids = {k: i + 1 for i, k in enumerate(top["_key"])} if not top.empty else {}
    for _, r in pts.iterrows():
        beds = int(r["bedrooms"]) if C.num(r["bedrooms"]) in (1, 2) else 1
        out.append(f'<circle cx="{sx(r["area_m2"]):.1f}" cy="{sy(r["rent_usd"]):.1f}" r="4" fill="{SERIES[beds]}" '
                   f'stroke="{SURFACE}" stroke-width="2"/>')
    labels: dict[tuple[int, int], list[int]] = {}      # Top-10 units at the same rent and area share one label
    for _, r in pts[pts["_key"].isin(top_ids)].iterrows():
        labels.setdefault((round(sx(r["area_m2"])), round(sy(r["rent_usd"]))), []).append(top_ids[r["_key"]])
    placed: list[tuple[float, float, float]] = []       # (x, y, width) of labels already drawn
    for (x, y), ranks in sorted(labels.items(), key=lambda kv: kv[0][1]):
        text = " ".join(f"#{k}" for k in sorted(ranks))
        w, ty = 6.5 * len(text), y - 5
        while any(abs(ty - py) < 11 and x + 6 < px + pw and px < x + 6 + w for px, py, pw in placed):
            ty += 11                                   # nudge below the label it would collide with
        placed.append((x + 6, ty, w))
        out.append(f'<text x="{x + 6}" y="{ty}" font-size="9" font-weight="bold" fill="{INK}">{text}</text>')
    lx = L_ + 8
    for beds, label in ((1, L("1 bedroom", "1 बेडरूम")), (2, L("2 bedrooms", "2 बेडरूम"))):
        out.append(f'<circle cx="{lx}" cy="{T - 10}" r="4" fill="{SERIES[beds]}"/>'
                   f'<text x="{lx + 8}" y="{T - 7}" font-size="9.5" fill="{INK2}">{E(label)}</text>')
        lx += 90
    out.append(f'<text x="{lx + 10}" y="{T - 7}" font-size="9.5" fill="{INK2}">'
               f'{E(L("#n = Top-10 rank", "#n = शीर्ष-10 क्रम"))}</text></svg>')
    return "".join(out)


def map_svg(ranked: pd.DataFrame, top: pd.DataFrame, geo: dict | None) -> str:
    """Only positions that are reliable (published exactly, or geocoded to the house number) are drawn."""
    reliable = ranked["latitude"].notna() & ranked["category"].isin(["PRIMARY", "STRETCH"]) & (
        ranked["coord_precision"].isin(RELIABLE_PRECISION) | (ranked.get("geocoding_confidence") == "HIGH"))
    pts = ranked[reliable]
    if pts.empty:
        n_approx = int((ranked["latitude"].notna() & ranked["category"].isin(["PRIMARY", "STRETCH"])).sum())
        msg = L(f"No listing in the shortlist has a reliable (building-level) position, so no map is drawn rather "
                f"than a misleading one. {n_approx} listing(s) have a street-level position only; all others give just "
                "the district or zone. Ask each landlord for the exact address.",
                f"शॉर्टलिस्ट के किसी भी अपार्टमेंट का भरोसेमंद (भवन-स्तर का) स्थान उपलब्ध नहीं है, इसलिए भ्रामक नक्शा बनाने के "
                f"बजाय नक्शा नहीं दिया गया है। {n_approx} अपार्टमेंट का केवल सड़क-स्तर का स्थान ज्ञात है; बाकी में केवल ज़िला या "
                "क्षेत्र दिया है। हर मकान-मालिक से सटीक पता पूछें।")
        return f"<p class='muted'>{E(msg)}</p>"
    boundary = (geo or {}).get("boundary_ll") or []
    roads = (geo or {}).get("road_lines_ll") or []
    lats = [p[0] for p in boundary] + list(pts["latitude"])
    lons = [p[1] for p in boundary] + list(pts["longitude"])
    pad = 0.002
    s, n, w, e = min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad
    kx = math.cos(math.radians((s + n) / 2))
    W = 700
    H = max(260, min(int(W * (n - s) / ((e - w) * kx)), 520))
    sx = lambda lon: (lon - w) / (e - w) * W
    sy = lambda lat: (n - lat) / (n - s) * H
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="map" '
           f'style="background:#f4f6f5;border:1px solid #e1e0d9;font-family:inherit">']
    if boundary:
        d = " ".join(f"{sx(lo):.1f},{sy(la):.1f}" for la, lo in boundary)
        out.append(f'<polygon points="{d}" fill="#ffffff" stroke="{NAVY}" stroke-width="1.5"/>')
    for kind, line in roads:
        d = " ".join(f"{sx(lo):.1f},{sy(la):.1f}" for la, lo in line)
        col, wdt = ("#b9b7ae", 2.2) if kind == "major" else ("#d6d4cc", 1.2)
        out.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="{wdt}"/>')
    top_keys = list(top["_key"]) if not top.empty else []
    for _, r in pts[~pts["_key"].isin(top_keys)].iterrows():
        out.append(f'<circle cx="{sx(r["longitude"]):.1f}" cy="{sy(r["latitude"]):.1f}" r="3" fill="#9aa5ad" '
                   f'stroke="#fff" stroke-width="1.5"/>')
    for i, key in enumerate(top_keys, start=1):
        r = pts[pts["_key"] == key]
        if r.empty:
            continue
        r = r.iloc[0]
        x, y = sx(r["longitude"]), sy(r["latitude"])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{NAVY}" stroke="#fff" stroke-width="2"/>'
                   f'<text x="{x:.1f}" y="{y + 3.5:.1f}" font-size="9.5" font-weight="bold" fill="#fff" '
                   f'text-anchor="middle">{i}</text>')
    ly = H - 12
    out.append(f'<text x="14" y="{ly + 2}" font-size="8" fill="{MUTED}">{E(L("Outline: Miraflores district · © OpenStreetMap contributors", "रूपरेखा: Miraflores ज़िला · © OpenStreetMap contributors"))}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- blocks
def _top5(top: pd.DataFrame) -> str:
    rows = ""
    for i, r in enumerate(C.records(top.head(5)), start=1):
        total = _total(r)
        reason = t(str(r.get("main_advantage") or "").split("; ")[0])
        rows += (f"<tr {_data_attrs(i, r)}><td class='rk'>{i}</td>"
                 f"<td><a href='{E(str(r.get('source_url')))}'>{_nt(C.property_label(r))}</a></td>"
                 f"<td class='num'>{_fmt_usd(r.get('rent_usd'))}</td>"
                 f"<td class='num'>{('≈ ' + _fmt_usd(total)) if total is not None else E(t('UNKNOWN'))}"
                 f"<br><span class='pill {E(str(r.get('budget_class')))}' style='font-size:6.6pt'>"
                 f"{E(t(BUDGET_LABEL.get(r.get('budget_class'), '')))}</span></td>"
                 f"<td class='num'>{int(C.num(r.get('bedrooms')) or 0)}</td>"
                 f"<td class='num'>{E(_area_text(r) if C.num(r.get('area_m2')) else t('Unknown'))}</td>"
                 f"<td>{E(t(C.furnished_text(r).replace('UNKNOWN', 'Unknown')))}</td>"
                 f"<td>{_noise_pill(r)}<br><span class='muted'>{E(_noise_line(r))}</span></td>"
                 f"<td>{E(reason)}</td><td>{E(t(str(r.get('main_drawback') or '')))}</td>"
                 f"<td><a class='view' href='{E(str(r.get('source_url')))}'>{E(L('View', 'देखें'))} ↗</a></td></tr>")
    if not rows:
        return f"<p class='muted'>{E(L('No budget-compliant listings available in this run.', 'इस खोज में बजट के भीतर कोई अपार्टमेंट उपलब्ध नहीं।'))}</p>"
    head = [("#", 4), (L("Property", "संपत्ति"), 14), (L("Rent", "मासिक किराया"), 8), (L("Estimated total", "अनुमानित कुल मासिक खर्च"), 11),
            (L("BR", "बेडरूम"), 5), (L("Area", "क्षेत्रफल"), 7), (L("Furnished", "सुसज्जित"), 8),
            (L("Noise risk + confidence", "शोर का जोखिम + विश्वसनीयता"), 13), (L("Why it stands out", "यह क्यों ख़ास है"), 12),
            (L("Main drawback", "मुख्य कमी"), 11), (L("View listing", "विज्ञापन देखें"), 7)]
    ths = "".join(f"<th style='width:{w}%'>{E(h)}</th>" for h, w in head)
    return f"<table class='top5'><tr>{ths}</tr>{rows}</table>"


def _card(i: int, r: dict, twins: list[int] | None = None) -> str:
    links = [f'<a href="{E(r["source_url"])}">{E(t("View listing"))} ↗</a>'] if r.get("source_url") else []
    if C.map_url(r):
        approx = r.get("coord_precision") in ("STREET_LEVEL", "APPROXIMATE") or C.num(r.get("latitude")) is None
        links.append(f'<a href="{E(C.map_url(r))}">{E(t("Map"))}{E(L(" (approx.)", " (अनुमानित)")) if approx else ""} ↗</a>')
    if C.whatsapp_url(r):
        links.append(f'<a href="{E(C.whatsapp_url(r))}">WhatsApp ↗</a>')
    total = _total(r)
    rent = _fmt_usd(r.get("rent_usd"))
    if r.get("rent_usd_basis") == "CALCULATED" and C.num(r.get("rent_pen")) is not None:
        rent += f" (S/ {C.num(r.get('rent_pen')):,.0f})"
    facts = [(L("Rent", "मासिक किराया"), rent),
             (L("Maintenance", "रखरखाव शुल्क"), t(C.maintenance_text(r))),
             (L("Est. total / month", "अनुमानित कुल मासिक खर्च"), f"≈ {_fmt_usd(total)}" if total is not None else t("UNKNOWN")),
             (L("Bedrooms · area", "बेडरूम · क्षेत्रफल"), f"{int(C.num(r.get('bedrooms')) or 0)} · {_area_text(r)}"),
             (L("Furnished", "सुसज्जित"), t(C.furnished_text(r))), (L("Floor", "मंज़िल"), t(str(C.floor_text(r)))),
             (L("Contract", "अनुबंध"), t(C.contract_text(r))), (L("Deposit", "जमा राशि"), t(C.deposit_text(r)))]
    facts_html = "".join(f"<div><span>{E(k)}</span>{E(str(v))}</div>" for k, v in facts)
    arterial = ""
    if "ON_MAJOR_ARTERIAL" in str(r.get("red_flags") or ""):
        arterial = (f'<p class="kv warn">⚠ {E(L("On a major arterial (Av. Paseo de la República / Vía Expresa or similar) — expect traffic noise unless the bedroom faces the interior.", "मुख्य सड़क पर स्थित (Av. Paseo de la República / Vía Expresa या समान) — जब तक बेडरूम भीतर की ओर न हो, ट्रैफ़िक के शोर की अपेक्षा करें।"))}</p>')
    elif "MAJOR_ARTERIAL_MENTIONED" in str(r.get("red_flags") or ""):
        arterial = (f'<p class="kv"><b>{E(L("Arterial nearby.", "पास में मुख्य सड़क।"))}</b> '
                    f'{E(L("The listing mentions a major arterial — ask how far the bedroom is from it.", "विज्ञापन में एक मुख्य सड़क का उल्लेख है — पूछें कि बेडरूम उससे कितनी दूर है।"))}</p>')
    contact = t(C.contact_text(r)) if not (r.get("agency_name") or r.get("agent_name")) else \
        f"{_nt(r.get('agency_name') or r.get('agent_name'))} · " + E(t(" · ".join(C.contact_text(r).split(" · ")[1:])))
    return f"""
<div class="card" {_data_attrs(i, r)}>
  <div class="head"><h3><span class="rank">{i}</span>{_nt(C.property_label(r))}</h3>
  <span class="fit">{E(L("Fit", "उपयुक्तता"))} {C.num(r.get('fit_score')):.0f}/100 · {_nt(C.sources_text(r))}</span></div>
  <div class="facts">{facts_html}</div>
  <p class="kv"><b>{E(L("Budget.", "बजट।"))}</b> <span class="pill {E(str(r.get('budget_class')))}">{E(t(BUDGET_LABEL.get(r.get('budget_class'), str(r.get('budget_class')))))}</span>
     {E(t(str(r.get('budget_note') or '')))}</p>
  <p class="kv"><b>{E(L("Why it stands out.", "यह क्यों ख़ास है।"))}</b> {E(why_matches(r))}</p>
  <p class="kv"><b>{E(L("Main drawback.", "मुख्य कमी।"))}</b> {E(t(str(r.get('main_drawback') or '')))}</p>
  <p class="kv"><b>{E(L("Noise.", "शोर।"))}</b> {_noise_pill(r)} {E(_noise_line(r))} · {E(L("quietness score", "शांति स्कोर"))} {E(_quiet_score(r))}</p>
  <p class="kv"><b>{E(L("Evidence.", "प्रमाण।"))}</b> {E(t(str(r.get('quietness_reason') or '')))}</p>
  {arterial}
  {_twin_note(twins)}
  <p class="kv"><b>{E(L("Location.", "स्थान।"))}</b> {_location_line(r)}</p>
  <p class="kv"><b>{E(L("Contact.", "संपर्क।"))}</b> {contact if contact.startswith("<span") else E(contact)}</p>
  {_foreign_line(r)}
  <div class="foot"><span class="muted">{E(_availability(r))}</span><span class="links">{' '.join(links)}</span></div>
</div>"""


def _twin_note(twins: list[int] | None) -> str:
    if not twins:
        return ""
    ks = ", ".join(f"#{k}" for k in twins)
    return (f'<p class="kv warn">⚠ {E(L(f"Possible duplicate of {ks}: very similar details but no shared photo or ID — it may be the same flat listed by two different agents. Ask each for the exact address before visiting both.", f"संभवतः {ks} जैसा ही अपार्टमेंट: विवरण लगभग एक जैसे, पर कोई साझा फ़ोटो या ID नहीं — यह दो अलग एजेंटों द्वारा विज्ञापित एक ही अपार्टमेंट हो सकता है। दोनों को देखने से पहले हर एजेंट से सटीक पता पूछें।"))}</p>')


def _best_2br(primary: pd.DataFrame) -> str:
    """The three strongest collected 2-bedroom options, in their existing rank order — informational only."""
    two = primary[primary["bedrooms"] == 2].sort_values("rank_in_category").head(3)
    if two.empty:
        return ""
    rows = ""
    for r in C.records(two):
        total = _total(r)
        url = E(str(r.get("source_url")))
        key = f"{r.get('source')}:{r.get('source_listing_id')}"
        rows += (f"<tr class='br2' data-id=\"{E(key)}\" "
                 f"data-url=\"{url}\" data-rank=\"{r.get('rank_in_category')}\">"
                 f"<td><a href='{url}'>{_nt(C.property_label(r))}</a></td>"
                 f"<td class='num nw'>{_fmt_usd(r.get('rent_usd'))}</td>"
                 f"<td class='num nw'>{('≈ ' + _fmt_usd(total)) if total is not None else E(t('Unknown'))}</td>"
                 f"<td class='num nw'>{E(_area_text(r))}</td>"
                 f"<td>{E(t(C.furnished_text(r).replace('UNKNOWN', 'Unknown')))}</td>"
                 f"<td>{_noise_pill(r)} <span class='muted'>{E(L('confidence', 'विश्वसनीयता'))} "
                 f"{E(t(str(r.get('noise_confidence') or 'low').lower()))}</span></td>"
                 f"<td><a class='view' href='{url}'>{E(L('View', 'देखें'))} ↗</a></td></tr>")
    head = "".join(f"<th class='{c}'>{E(h)}</th>" for h, c in (
        (L("Property", "संपत्ति"), ""), (L("Rent", "मासिक किराया"), "num nw"), (L("Estimated total", "अनुमानित कुल मासिक खर्च"), "num"),
        (L("Area", "क्षेत्रफल"), "num"), (L("Furnished", "सुसज्जित"), ""), (L("Noise category · confidence", "शोर श्रेणी · विश्वसनीयता"), ""),
        (L("Listing", "विज्ञापन"), "")))
    note = L("Informational only — these are the highest-ranked 2-bedroom listings collected; the Top 10 ranking above is unchanged.",
             "केवल जानकारी के लिए — ये एकत्रित 2 बेडरूम विज्ञापनों में सबसे ऊँचे क्रम वाले हैं; ऊपर का शीर्ष-10 क्रम नहीं बदला गया है।")
    return (f"<section class='keep callout'><h3>{E(L('BEST 2-BEDROOM OPTIONS', '2 बेडरूम के अच्छे विकल्प'))}</h3>"
            f"<table class='br2t'><tr>{head}</tr>{rows}</table><p class='sub'>{E(note)}</p></section>")


def _mini_table(rows: pd.DataFrame, cols: list[tuple[str, callable, bool]]) -> str:
    if rows.empty:
        return f"<p class='muted'>{E(L('No qualifying listings.', 'कोई उपयुक्त अपार्टमेंट नहीं।'))}</p>"
    head = "".join(f"<th class='{'num nw' if n else ''}'>{E(h)}</th>" for h, _, n in cols)
    body = ""
    for r in C.records(rows):
        body += "<tr>" + "".join(f"<td class='{'num nw' if n else ''}'>{f(r)}</td>" for _, f, n in cols) + "</tr>"
    return f"<table><tr>{head}</tr>{body}</table>"


# --------------------------------------------------------------------------- document
def build_report_html(ranked: pd.DataFrame, meta: dict, audit_rows: list[dict], geo: dict | None,
                      banner: str | None = None, thumbs: dict | None = None, lang: str = "en") -> str:
    with language(lang):
        return _build(ranked, meta, audit_rows, geo, banner)


def _build(ranked: pd.DataFrame, meta: dict, audit_rows: list[dict], geo: dict | None, banner: str | None) -> str:
    ranked = ranked.copy()
    for col in ("noise_label", "geocoding_confidence", "quietness_supported"):
        if col not in ranked:
            ranked[col] = None
    ranked["_key"] = ranked["source"].astype(str) + ":" + ranked["source_listing_id"].astype(str)
    primary = ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category")
    top = primary.head(meta["top_n"])
    stretch = ranked[ranked["category"] == "STRETCH"].sort_values("rank_in_category")
    border = ranked[ranked["category"] == "BORDERLINE"].sort_values("rank_in_category")
    in_scope = ranked[ranked["category"].isin(["PRIMARY", "STRETCH"])]
    lang = "hi" if L("en", "hi") == "hi" else "en"

    bc = primary["budget_class"].value_counts().to_dict() if "budget_class" in primary else {}
    tiles = "".join(f"<div class='tile'><div class='label'>{E(k)}</div><div class='value'>{v}</div></div>" for k, v in (
        (L("Unique listings screened", "जाँचे गए अद्वितीय अपार्टमेंट"), f"{meta['n_unique']:,}"),
        (code_hi("STRICT_ALL_IN"), f"{bc.get('STRICT_ALL_IN', 0):,}"),
        (code_hi("BASE_RENT_COMPLIANT"), f"{bc.get('BASE_RENT_COMPLIANT', 0):,}"),
        (code_hi("STRETCH"), f"{meta['n_stretch']:,}"),
        (code_hi("BORDERLINE"), f"{meta.get('n_borderline', 0):,}")))

    link = lambda r: (f"<a href='{E(r['source_url'])}'>{_nt(C.property_label(r))}</a>" if r.get("source_url")
                      else _nt(C.property_label(r)))
    # quiet-space: evidence first (category), then space; never ranks an unsupported score as "quiet"
    order = {"LIKELY QUIET": 0, "POSSIBLY QUIET": 1, "NOISE UNCERTAIN": 2, "LIKELY NOISY": 3}
    quiet_space = primary.assign(_o=primary["noise_label"].map(order).fillna(2)) \
        .sort_values(["_o", "pts_space"], ascending=[True, False]).head(5)
    value = primary[primary["value_band"].isin(["EXCELLENT_VALUE", "GOOD_VALUE"])
                    & (primary["noise_label"] != "LIKELY NOISY")].sort_values("rent_usd_per_m2").head(5)
    qs_table = _mini_table(quiet_space, [
        (L("Property", "संपत्ति"), link, False), (L("Noise category", "शोर श्रेणी"), lambda r: _noise_pill(r), False),
        (L("Confidence", "विश्वसनीयता"), lambda r: E(t(str(r.get("noise_confidence") or "low").lower())), False),
        (L("Area", "क्षेत्रफल"), lambda r: E(_area_text(r)), True),
        (L("Est. total", "अनुमानित कुल खर्च"), lambda r: E(t(str(r["estimated_total_text"]))), False)])
    val_table = _mini_table(value, [
        (L("Property", "संपत्ति"), link, False), ("USD/m²", lambda r: f"{r['rent_usd_per_m2']:.1f}", True),
        (L("Value band", "मूल्य श्रेणी"), lambda r: E(code_hi(str(r["value_band"]))), False),
        (L("Noise category", "शोर श्रेणी"), lambda r: _noise_pill(r), False)])
    stretch_table = _mini_table(stretch.head(5), [
        (L("Property", "संपत्ति"), link, False), (L("Rent", "मासिक किराया"), lambda r: _fmt_usd(r["rent_usd"]), True),
        (L("Est. total", "अनुमानित कुल खर्च"), lambda r: _fmt_usd(_total(r)), True),
        (L("Fit", "उपयुक्तता"), lambda r: f"{r['fit_score']:.0f}", True),
        (L("Why consider it", "क्यों विचार करें"), lambda r: E(t(str(r["main_advantage"]))), False)])
    border_table = _mini_table(border, [
        (L("Property", "संपत्ति"), link, False),
        (L("Published", "प्रकाशित"), lambda r: E(" / ".join(x for x in (
            f"S/ {C.num(r.get('rent_pen_published')):,.0f}" if C.num(r.get("rent_pen_published")) else "",
            f"USD {C.num(r.get('rent_usd_published')):,.0f}" if C.num(r.get("rent_usd_published")) else "") if x)), True),
        (L("Normalised USD", "सामान्यीकृत USD"), lambda r: f"USD {C.num(r['rent_usd']):,.2f}", True),
        (L("Why it is borderline", "सीमा-रेखा पर क्यों"), lambda r: E(t(str(r.get("budget_note") or ""))), False)])

    # foreign-tenant practicality
    ft = in_scope["foreign_tenant_friendliness"].fillna("UNKNOWN").value_counts().to_dict()
    ft_rows = "".join(f"<tr><td>{E(code_hi(k))}</td><td class='num'>{ft.get(k, 0)}</td><td>{E(d)}</td></tr>" for k, d in (
        ("HIGH", L("the listing explicitly welcomes foreigners, passports or corporate leases",
                   "विज्ञापन स्पष्ट रूप से विदेशियों, पासपोर्ट या कंपनी-अनुबंध का स्वागत करता है")),
        ("MEDIUM", L("practical signals only (temporary stays, no guarantor, English listing, furnished + utilities)",
                     "केवल व्यावहारिक संकेत (अस्थायी अवधि, गारंटर नहीं, अंग्रेज़ी विज्ञापन, सुसज्जित + सेवाएँ शामिल)")),
        ("POTENTIAL_FRICTION", L("asks for a Peruvian guarantor, carné de extranjería or DNI, or excludes foreigners",
                                 "पेरू के गारंटर, carné de extranjería या DNI की माँग, या विदेशियों को अस्वीकार")),
        ("UNKNOWN", L("the listing says nothing about it — the normal case, not a penalty",
                      "विज्ञापन में इस बारे में कुछ नहीं — यह सामान्य है, इसका कोई नकारात्मक अंक नहीं"))))

    # lease observations — computed, never assumed
    obs = []
    mc = in_scope["minimum_contract_months"].dropna()
    if len(mc):
        obs.append(L(f"Minimum term stated in {len(mc)} of {len(in_scope)} listings; most common: {int(mc.mode().iloc[0])} months.",
                     f"{len(in_scope)} में से {len(mc)} विज्ञापनों में न्यूनतम अवधि दी गई है; सबसे आम: {int(mc.mode().iloc[0])} माह।"))
    else:
        obs.append(L("No listing states a minimum term in its list data — ask every landlord (12 months is common in Lima).",
                     "किसी भी विज्ञापन में न्यूनतम अवधि नहीं दी गई है — हर मकान-मालिक से पूछें (Lima में 12 माह आम है)।"))
    dep = in_scope["deposit_months"].dropna()
    if len(dep):
        obs.append(L(f"Deposit stated in {len(dep)} listings; typical {dep.median():g} month(s).",
                     f"{len(dep)} विज्ञापनों में जमा राशि दी गई है; सामान्यतः {dep.median():g} माह।"))
    else:
        obs.append(L("No listing states the deposit — expect 1–2 months' deposit plus 1 month in advance, and confirm.",
                     "किसी विज्ञापन में जमा राशि नहीं दी गई — आम तौर पर 1–2 माह की जमा राशि और 1 माह अग्रिम होता है; पुष्टि करें।"))
    m_known = int(in_scope["maintenance_usd"].notna().sum() + (in_scope["maintenance_included_in_rent"] == True).sum())  # noqa: E712
    obs.append(L(f"Maintenance fee published in {m_known} of {len(in_scope)} listings — where it is missing, the true monthly cost is higher than the rent shown.",
                 f"{len(in_scope)} में से {m_known} विज्ञापनों में रखरखाव शुल्क प्रकाशित है — जहाँ नहीं है, वहाँ वास्तविक मासिक खर्च दिखाए गए किराये से अधिक होगा।"))
    conv = int((in_scope["rent_usd_basis"] == "CALCULATED").sum())
    obs.append(L(f"{conv} of {len(in_scope)} listings are priced in soles; their USD figures use the single rate S/ {meta['fx_rate']:.3f} per USD and will move with the exchange rate.",
                 f"{len(in_scope)} में से {conv} विज्ञापनों का किराया सोल (S/) में है; इनके USD आँकड़े एक ही दर S/ {meta['fx_rate']:.3f} प्रति USD से निकाले गए हैं और विनिमय दर के साथ बदलेंगे।"))
    mism = int(in_scope["red_flags"].astype(str).str.contains("CURRENCY_CONVERSION_MISMATCH").sum())
    if mism:
        obs.append(L(f"{mism} listing(s) show a portal USD figure more than {meta.get('fx_flag_pct', 5)}% away from S/ ÷ rate (CURRENCY_CONVERSION_MISMATCH): agree the currency and amount in writing.",
                     f"{mism} विज्ञापनों में पोर्टल का USD आँकड़ा S/ ÷ दर से {meta.get('fx_flag_pct', 5)}% से अधिक अलग है (CURRENCY_CONVERSION_MISMATCH): मुद्रा और राशि लिखित में तय करें।"))

    src_rows = "".join(
        f"<tr><td>{E(t(a['Source'], record=False))}</td><td>{E(code_hi(str(a['Status'])))}</td>"
        f"<td class='num'>{E(str(a['Records collected']))}</td></tr>"
        for a in audit_rows if not str(a["Status"]).startswith("PENDING (not automated"))

    gid_rank = {r["duplicate_group_id"]: k for k, r in enumerate(C.records(top), start=1)}
    twins = lambda r: sorted(gid_rank[g] for g in str(r.get("possible_duplicate_of") or "").split("; ") if g in gid_rank)
    cards = "".join(_card(i, r, twins(r)) for i, r in enumerate(C.records(top), start=1)) or \
        f"<p class='muted'>{E(L('No budget-compliant listings available in this run.', 'इस खोज में बजट के भीतर कोई अपार्टमेंट उपलब्ध नहीं।'))}</p>"
    n_geo = int(ranked["latitude"].notna().sum())
    n_high = int(((ranked.get("geocoding_confidence") == "HIGH") | (ranked["coord_source"] == "LISTING")).sum())

    checklist = [
        L("<b>Noise, in person, three times:</b> weekday rush hour (7:30–9:00 or 18:00–20:00), a weekday evening, and a Friday or Saturday night after 23:00. Stand in the bedroom with the windows closed.",
          "<b>शोर की जाँच स्वयं, तीन बार करें:</b> सप्ताह के दिन भीड़ के समय (7:30–9:00 या 18:00–20:00), किसी शाम, और शुक्रवार या शनिवार रात 23:00 के बाद। खिड़कियाँ बंद करके बेडरूम में खड़े होकर सुनें।"),
        L("Check which rooms face the street and which face the interior; ask whether the windows are double-glazed.",
          "देखें कि कौन-से कमरे सड़क की ओर हैं और कौन-से भीतर की ओर; पूछें कि खिड़कियाँ डबल-ग्लेज़्ड हैं या नहीं।"),
        L("Confirm the final rent, the maintenance fee and what is included (water, gas, electricity, internet, arbitrios).",
          "अंतिम किराया, रखरखाव शुल्क और उसमें क्या शामिल है (पानी, गैस, बिजली, इंटरनेट, arbitrios) — इनकी पुष्टि करें।"),
        L("Confirm the minimum term, deposit and advance months, and the penalty for leaving early. Ask for the contract draft in advance.",
          "न्यूनतम अवधि, जमा राशि व अग्रिम के महीने, और जल्दी छोड़ने पर लगने वाले दंड की पुष्टि करें। अनुबंध का मसौदा पहले से माँगें।"),
        L("Foreign-tenant documents: passport accepted? carné de extranjería required? proof of income? guarantor (aval)?",
          "विदेशी किरायेदार के दस्तावेज़: क्या पासपोर्ट मान्य है? क्या carné de extranjería ज़रूरी है? आय का प्रमाण? गारंटर (aval)?"),
        L("Verify the owner or agent (property registry record, <i>partida registral</i>, SUNARP) and never pay a deposit before visiting.",
          "मालिक या एजेंट की पुष्टि करें (संपत्ति रजिस्ट्री रिकॉर्ड, <i>partida registral</i>, SUNARP) और देखे बिना कभी जमा राशि न दें।"),
        L("Photograph the inventory and any existing damage at move-in and attach it to the contract.",
          "रहने आते समय सामान की सूची और मौजूदा नुकसान की तस्वीरें लें और उन्हें अनुबंध के साथ संलग्न करें।"),
        L("Test water pressure, hot water, mobile signal and internet availability in the unit.",
          "पानी का दबाव, गर्म पानी, मोबाइल सिग्नल और इंटरनेट की उपलब्धता जाँचें।"),
    ]
    ml = next((a for a in audit_rows if str(a.get("Source", "")).startswith("Mercado Libre")), None)
    ml_n = int(C.num(ml.get("Records collected")) or 0) if ml else 0
    if ml is None:
        ml_en, ml_hi = "", ""
    elif ml_n:
        ml_en = f"Mercado Libre: {ml_n} records collected by polite direct requests."
        ml_hi = f"Mercado Libre: सामान्य सीधे अनुरोधों से {ml_n} रिकॉर्ड एकत्र किए गए।"
    else:
        ml_en = "Mercado Libre was not usable in this run (bot challenge; never bypassed)."
        ml_hi = "Mercado Libre इस खोज में उपयोग योग्य नहीं था (बॉट-जाँच; इसे कभी दरकिनार नहीं किया गया)।"
    methodology = [
        L(f"<b>Collection.</b> Live searches on Urbania and Adondevivir (via Apify, free plan: at most 10 records per search, list-level data only — no detail pages), one search per bedroom count (1 and 2 bedrooms), rent ≤ USD 1,150 at query time. Every record is re-validated afterwards. {ml_en} {meta['n_raw']} records collected; {meta['n_unique']} unique properties after merging cross-posts.",
          f"<b>संग्रह।</b> Urbania और Adondevivir पर लाइव खोज (Apify के माध्यम से, निःशुल्क प्लान: प्रति खोज अधिकतम 10 रिकॉर्ड, केवल सूची-स्तर की जानकारी — विवरण पेज नहीं), बेडरूम की संख्या (1 और 2) के अनुसार अलग-अलग खोज, खोज के समय किराया ≤ USD 1,150। हर रिकॉर्ड की बाद में दोबारा जाँच की गई। {ml_hi} कुल {meta['n_raw']} रिकॉर्ड; दोहराव हटाने के बाद {meta['n_unique']} अद्वितीय अपार्टमेंट।"),
        L(f"<b>Currency.</b> One reference rate for every conversion: 1 USD = S/ {meta['fx_rate']:.3f} ({E(meta['fx_source'])}). Listings priced in soles are converted with it; the portal's own USD figure is kept separately and flagged when it differs by more than 5%.",
          f"<b>मुद्रा।</b> हर रूपांतरण के लिए एक ही संदर्भ दर: 1 USD = S/ {meta['fx_rate']:.3f} ({E(meta['fx_source'])})। सोल में दिए गए किराये इसी दर से बदले गए हैं; पोर्टल का अपना USD आँकड़ा अलग से रखा गया है और 5% से अधिक अंतर होने पर चिह्नित किया गया है।"),
        L("<b>Budget classes.</b> STRICT_ALL_IN = rent + known maintenance ≤ USD 1,000 · BASE_RENT_COMPLIANT = rent ≤ USD 1,000 but the total is higher or unknown · STRETCH = rent USD 1,001–1,100 · BORDERLINE = at most 1% (USD 11) above USD 1,100 after currency conversion — shown for transparency, never budget-compliant.",
          "<b>बजट श्रेणियाँ।</b> STRICT_ALL_IN = किराया + ज्ञात रखरखाव शुल्क ≤ USD 1,000 · BASE_RENT_COMPLIANT = किराया ≤ USD 1,000, पर कुल खर्च अधिक या अज्ञात · STRETCH = किराया USD 1,001–1,100 · BORDERLINE = मुद्रा-रूपांतरण के बाद USD 1,100 से अधिकतम 1% (USD 11) ऊपर — पारदर्शिता के लिए दिखाया गया, बजट के भीतर नहीं माना गया।"),
        L("<b>Noise.</b> Where a reliable position exists, distance to major roads, nightclubs and bar clusters (OpenStreetMap) is combined with listing text. Without a position, only listing text is used and confidence is LOW. Categories: LIKELY QUIET (low risk, medium/high confidence) · POSSIBLY QUIET (positive listing wording only) · NOISE UNCERTAIN (no or mixed evidence) · LIKELY NOISY (on a major arterial, faces an avenue, or high risk with reliable location). Low-confidence evidence never pushes an otherwise good apartment down the ranking.",
          "<b>शोर।</b> जहाँ भरोसेमंद स्थान उपलब्ध है, वहाँ मुख्य सड़कों, नाइटक्लब और बार से दूरी (OpenStreetMap) को विज्ञापन के विवरण के साथ जोड़ा गया है। स्थान न होने पर केवल विज्ञापन का विवरण उपयोग हुआ है और विश्वसनीयता कम है। श्रेणियाँ: संभवतः शांत (कम जोखिम, मध्यम/उच्च विश्वसनीयता) · शायद शांत (केवल विज्ञापन में सकारात्मक उल्लेख) · शोर अनिश्चित (प्रमाण नहीं या मिश्रित) · संभवतः शोरगुल वाला (मुख्य सड़क पर, एवेन्यू की ओर, या भरोसेमंद स्थान के साथ अधिक जोखिम)। कम विश्वसनीयता वाला प्रमाण किसी अच्छे अपार्टमेंट को रैंकिंग में नीचे नहीं धकेलता।"),
        L(f"<b>Location.</b> The free plan returns no coordinates. Positions were derived only from a specific street address written in the listing (street + number, or street + block); district or zone names alone were never geocoded. {n_geo} of {len(ranked)} unique properties have a position, {n_high} of them building-level.",
          f"<b>स्थान।</b> निःशुल्क प्लान में निर्देशांक नहीं मिलते। स्थान केवल तभी निकाला गया जब विज्ञापन में स्पष्ट पता (सड़क + नंबर, या सड़क + ब्लॉक) लिखा था; केवल ज़िले या क्षेत्र के नाम से कभी स्थान नहीं निकाला गया। {len(ranked)} में से {n_geo} अपार्टमेंट का स्थान ज्ञात है, जिनमें से {n_high} भवन-स्तर का।"),
        L("<b>De-duplication.</b> The same flat posted on both portals is merged only with an identity anchor (the same photo file, ID or address) plus matching details; matching price, area and maintenance alone never merge two listings.",
          "<b>दोहराव हटाना।</b> दोनों पोर्टलों पर डाला गया एक ही अपार्टमेंट तभी जोड़ा गया जब पहचान का ठोस आधार (एक ही फ़ोटो फ़ाइल, ID या पता) और मिलते-जुलते विवरण हों; केवल किराया, क्षेत्रफल और रखरखाव शुल्क का मेल कभी दो विज्ञापनों को नहीं जोड़ता।"),
        L("<b>Limits.</b> Advertiser-reported data; no phone numbers, publication dates or exact addresses on the free plan (contact via each listing); availability changes daily and is never guaranteed. Scores rank options — they do not replace a visit.",
          "<b>सीमाएँ।</b> जानकारी विज्ञापनदाताओं द्वारा दी गई है; निःशुल्क प्लान में फ़ोन नंबर, प्रकाशन तिथि या सटीक पते नहीं मिलते (हर विज्ञापन के माध्यम से संपर्क करें); उपलब्धता रोज़ बदलती है और इसकी गारंटी नहीं है। स्कोर केवल विकल्पों को क्रम देते हैं — ये स्वयं जाकर देखने का विकल्प नहीं हैं।"),
    ]
    workbook = "Miraflores_Rental_Shortlist_HI.xlsx" if lang == "hi" else "Miraflores_Rental_Shortlist_EN.xlsx"

    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<title>{E(L("Miraflores Rental Shortlist", "Miraflores किराया शॉर्टलिस्ट"))}</title><style>{CSS}</style></head><body class="{lang}">
{f'<div class="banner">{E(banner)}</div>' if banner else ''}
<h1>{E(L("Miraflores Rental Shortlist", "Miraflores किराया शॉर्टलिस्ट"))}</h1>
<p class="sub">{E(L(f"Executive report · generated {meta['generated_at']} · 1 USD = S/ {meta['fx_rate']:.3f} (BCRP) · prepared for a couple living in Lima",
                     f"कार्यकारी रिपोर्ट · तैयार: {meta['generated_at']} · 1 USD = S/ {meta['fx_rate']:.3f} (BCRP) · Lima में रह रहे एक दंपति के लिए"))}</p>
<h2 style="margin-top:3mm">{E(L("TOP 5 — CONTACT THESE FIRST", "शीर्ष 5 — सबसे पहले इनसे संपर्क करें"))}</h2>
<p class="lead">{E(L("The five strongest matches: 1–2 bedrooms, inside Miraflores, rent at or below USD 1,000, ranked for quiet, space and value. Green budget badges mean the all-in monthly cost (rent + maintenance) is within USD 1,000.",
                      "पाँच सबसे उपयुक्त विकल्प: 1–2 बेडरूम, Miraflores के भीतर, मासिक किराया USD 1,000 या उससे कम — शांत वातावरण, जगह और मूल्य के आधार पर क्रमबद्ध। हरा बजट-चिह्न का अर्थ है कि कुल मासिक खर्च (किराया + रखरखाव शुल्क) USD 1,000 के भीतर है।"))}</p>
{_top5(top)}
<div class="tiles">{tiles}</div>
{_best_2br(primary)}
<p class="legend">{L("<b>Noise categories:</b> LIKELY QUIET · POSSIBLY QUIET · NOISE UNCERTAIN · LIKELY NOISY — always shown with the confidence of the evidence. Most listings give no exact location, so most noise estimates are based on listing text and have LOW confidence: check noise in person.",
                     "<b>शोर की श्रेणियाँ:</b> संभवतः शांत · शायद शांत · शोर अनिश्चित · संभवतः शोरगुल वाला — हमेशा प्रमाण की विश्वसनीयता के साथ। अधिकांश विज्ञापनों में सटीक स्थान नहीं है, इसलिए अधिकांश अनुमान केवल विज्ञापन के विवरण पर आधारित हैं और उनकी विश्वसनीयता कम है: शोर की जाँच स्वयं करें।")}</p>
<p class="legend">{L("<b>Availability:</b> ACTIVE_CONFIRMED = listing re-opened successfully just before this report · LIKELY_ACTIVE = seen in the live search, automated re-check not possible · UNKNOWN = could not be confirmed. Availability is never guaranteed.",
                     "<b>उपलब्धता:</b> ACTIVE_CONFIRMED = रिपोर्ट से ठीक पहले विज्ञापन सफलतापूर्वक दोबारा खोला गया · LIKELY_ACTIVE = लाइव खोज में मिला, स्वचालित पुनः-जाँच संभव नहीं · UNKNOWN = पुष्टि नहीं हो सकी। उपलब्धता की कोई गारंटी नहीं।")}</p>

<h2 class="pb">{E(L("1 · Top 10 in detail", "1 · शीर्ष 10 — विस्तार से"))}</h2>
{cards}

<section class="keep"><h2>{E(L("2 · Best quiet-space candidates", "2 · शांत वातावरण और जगह के लिहाज़ से सर्वश्रेष्ठ"))}</h2>
<p class="sub">{E(L("Ordered by the strength of the quiet evidence first, then by space. Confirm noise in person.", "पहले शांत वातावरण के प्रमाण की मज़बूती के आधार पर, फिर जगह के आधार पर क्रमबद्ध। शोर की पुष्टि स्वयं करें।"))}</p>
{qs_table}</section>
<section class="keep"><h2>{E(L("3 · Best value candidates", "3 · सर्वश्रेष्ठ मूल्य वाले विकल्प"))}</h2>
<p class="sub">{E(L("Lowest rent per m² within their bedroom group (relative to this sample), excluding LIKELY NOISY units.", "अपने बेडरूम-समूह में प्रति m² सबसे कम किराया (इसी नमूने की तुलना में), संभवतः शोरगुल वाले अपार्टमेंट छोड़कर।"))}</p>
{val_table}</section>

<section class="keep"><h2>{E(L("4 · Budget, stretch and borderline", "4 · बजट, स्ट्रेच और सीमा-रेखा वाले मामले"))}</h2>
<p>{L("Budget-compliant means rent ≤ USD 1,000 (STRICT_ALL_IN when rent + maintenance is also ≤ USD 1,000; BASE_RENT_COMPLIANT when the total is higher or maintenance is not published). STRETCH listings (USD 1,001–1,100) are shown separately and only make sense if the rent is negotiable.",
      "बजट के भीतर का अर्थ है किराया ≤ USD 1,000। STRICT_ALL_IN: किराया + रखरखाव शुल्क भी ≤ USD 1,000; BASE_RENT_COMPLIANT: कुल खर्च अधिक है या रखरखाव शुल्क प्रकाशित नहीं है। STRETCH अपार्टमेंट (USD 1,001–1,100) अलग दिखाए गए हैं और केवल तभी उपयुक्त हैं जब किराये पर मोलभाव हो सके।")}</p>
{stretch_table}
<p>{L("<b>BORDERLINE</b> listings are at most 1% (USD 11) above the USD 1,100 stretch ceiling only because a soles price was converted at the reference rate (for example, a published USD 1,100 that normalises to USD 1,104.87). They are listed for transparency and are <b>not</b> budget-compliant and not normal stretch.",
      "<b>BORDERLINE</b> अपार्टमेंट USD 1,100 की स्ट्रेच सीमा से अधिकतम 1% (USD 11) ऊपर हैं, और वह भी केवल इसलिए कि सोल में दिया किराया संदर्भ दर से बदला गया (उदाहरण: प्रकाशित USD 1,100 जो सामान्यीकरण के बाद USD 1,104.87 बनता है)। ये पारदर्शिता के लिए दिखाए गए हैं और बजट के भीतर <b>नहीं</b> हैं, न ही सामान्य स्ट्रेच।")}</p>
{border_table}</section>

<section class="keep"><h2>{E(L("5 · Foreign-tenant practicality", "5 · विदेशी किरायेदार के लिए व्यावहारिकता"))}</h2>
<table><tr><th style="width:22%">{E(L("Level", "स्तर"))}</th><th class="num" style="width:10%">{E(L("Listings", "अपार्टमेंट"))}</th><th>{E(L("Meaning", "अर्थ"))}</th></tr>{ft_rows}</table>
<p>{E(L("Where a listing does not state its requirements, confirm before visiting: passport acceptance; whether a carné de extranjería is required; proof of income; guarantor (aval); deposit; and minimum lease period. UNKNOWN is never scored as a negative.",
         "जहाँ विज्ञापन में शर्तें नहीं दी गई हैं, वहाँ देखने जाने से पहले पुष्टि करें: क्या पासपोर्ट मान्य है; क्या carné de extranjería ज़रूरी है; आय का प्रमाण; गारंटर (aval); जमा राशि; और न्यूनतम किराया अवधि। UNKNOWN को कभी नकारात्मक अंक नहीं दिए गए।"))}</p></section>

<section class="keep"><h2>{E(L("6 · Map", "6 · नक्शा"))}</h2>
<figure>{map_svg(ranked, top, geo)}
<figcaption>{E(L("Only building-level positions are drawn. Street-level and district-only locations are not shown as points.", "केवल भवन-स्तर के स्थान दिखाए गए हैं; सड़क-स्तर और केवल ज़िले वाले स्थान बिंदु के रूप में नहीं दिखाए गए।"))}</figcaption></figure></section>

<section class="keep"><h2>{E(L("7 · Lease observations", "7 · अनुबंध से जुड़ी बातें"))}</h2>
<ul>{''.join(f'<li>{E(o)}</li>' for o in obs)}</ul></section>

<section class="keep"><h2>{E(L("8 · Verification checklist before signing", "8 · अनुबंध पर हस्ताक्षर से पहले जाँच-सूची"))}</h2>
<ul>{''.join(f'<li>{c}</li>' for c in checklist)}</ul></section>

<section class="keep"><h2>{E(L("9 · Sources, market snapshot and methodology", "9 · स्रोत, बाज़ार की झलक और कार्यप्रणाली"))}</h2>
<table><tr><th>{E(L("Source", "स्रोत"))}</th><th style="width:30%">{E(L("Status", "स्थिति"))}</th><th class="num">{E(L("Records", "रिकॉर्ड"))}</th></tr>{src_rows}</table></section>
<figure>{scatter_svg(in_scope, top, meta['budget'])}
<figcaption>{E(L("Each dot is one unique listing (cross-posts merged). Relative to this sample only — not an official valuation.", "हर बिंदु एक अद्वितीय अपार्टमेंट है (दोहराव जोड़े गए)। केवल इसी नमूने की तुलना — आधिकारिक मूल्यांकन नहीं।"))}</figcaption></figure>
<ul class="meth">{''.join(f'<li>{m}</li>' for m in methodology)}</ul>
<p class="sub">{E(L(f"Full field-level data, duplicate groups, red flags and the source audit: {workbook}.", f"पूरे आँकड़े, डुप्लिकेट समूह, चेतावनी संकेत और स्रोत ऑडिट: {workbook}।"))}</p>
</body></html>"""


def html_to_pdf(html_path: Path, pdf_path: Path, banner: str | None = None, lang: str = "en") -> None:
    from playwright.sync_api import sync_playwright
    title = "Miraflores किराया शॉर्टलिस्ट" if lang == "hi" else "Miraflores Rental Shortlist"
    footer_left = (f"<b style='color:#9b1c13'>{E(banner)}</b>" if banner else E(title))
    font = "Noto Sans Devanagari,Noto Sans,Liberation Sans" if lang == "hi" else "Liberation Sans,Arial"
    exe = None
    for cand in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome")):
        exe = str(cand)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(pdf_path), format="A4", print_background=True,
                 display_header_footer=True,
                 header_template="<span></span>",
                 footer_template=(f"<div style='font-size:7.5pt;color:#898781;width:100%;padding:0 14mm;"
                                  f"display:flex;justify-content:space-between;font-family:{font}'>"
                                  f"<span>{footer_left}</span>"
                                  "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>"),
                 margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        browser.close()
