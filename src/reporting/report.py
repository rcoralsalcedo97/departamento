"""Executive report: HTML (self-contained, inline SVG) → PDF via headless Chromium."""
from __future__ import annotations

import html
import math
from pathlib import Path

import pandas as pd

from . import common as C

E = html.escape
SERIES = {1: "#2a78d6", 2: "#eb6834"}          # validated categorical slots 1–2 (dataviz reference palette)
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
NAVY = "#1f3a4d"

CSS = """
@page { size: A4; }
* { box-sizing: border-box; }
body { font-family: "Liberation Sans", "Helvetica Neue", Arial, sans-serif; color: #1b1b1b; font-size: 10pt;
       line-height: 1.42; margin: 0; background: #fff; }
h1 { font-size: 22pt; color: #1f3a4d; margin: 0 0 2mm; letter-spacing: -0.2px; }
h2 { font-size: 13.5pt; color: #1f3a4d; margin: 7mm 0 2.5mm; padding-bottom: 1.5mm; border-bottom: 1.5px solid #1f3a4d; }
h3 { font-size: 11pt; margin: 0 0 1.5mm; color: #0b0b0b; }
p { margin: 0 0 2.5mm; }
a { color: #1f5fbf; text-decoration: none; }
.sub { color: #52514e; font-size: 9.5pt; }
.banner { background: #fde8e7; color: #9b1c13; border: 1px solid #f3b4ae; padding: 3mm 4mm; font-weight: bold;
          margin: 0 0 4mm; border-radius: 3px; }
.tiles { display: flex; gap: 3mm; margin: 4mm 0; }
.tile { flex: 1; border: 1px solid #e1e0d9; border-radius: 4px; padding: 3mm; background: #fcfcfb; }
.tile .label { color: #52514e; font-size: 8.5pt; }
.tile .value { font-size: 18pt; font-weight: 600; color: #0b0b0b; }
table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 1mm 0 3mm; }
th { text-align: left; background: #1f3a4d; color: #fff; padding: 1.6mm 2mm; font-weight: 600; }
td { padding: 1.4mm 2mm; border-bottom: 1px solid #e6e6e2; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:nth-child(even) td { background: #f7f8f9; }
.card { border: 1px solid #d9dce1; border-radius: 5px; padding: 2.6mm 3.5mm; margin: 0 0 3mm; page-break-inside: avoid;
        font-size: 9pt; line-height: 1.35; }
.card .head { display: flex; justify-content: space-between; align-items: baseline; gap: 4mm; }
.rank { display: inline-block; min-width: 8mm; height: 8mm; line-height: 8mm; text-align: center; border-radius: 50%;
        background: #1f3a4d; color: #fff; font-weight: bold; margin-right: 2mm; }
.fit { color: #52514e; font-size: 9pt; white-space: nowrap; }
.facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.6mm 4mm; margin: 1.2mm 0 1.5mm; font-size: 8.8pt; }
.facts div span { color: #6b6a66; display: block; font-size: 7.8pt; text-transform: uppercase; letter-spacing: .3px; }
.pill { display: inline-block; padding: 0.3mm 2mm; border-radius: 9px; font-size: 8.3pt; font-weight: bold; }
.LOW { background: #d8f0dd; color: #0b6b22; } .MEDIUM { background: #fff1cc; color: #7a5200; }
.HIGH { background: #fbd5d2; color: #9b1c13; }
.kv { margin: 0.6mm 0; } .kv b { color: #1f3a4d; }
.foot { display: flex; justify-content: space-between; gap: 4mm; margin-top: 1mm; font-size: 8.3pt; }
td.nw, th.nw { white-space: nowrap; }
.links a { margin-right: 4mm; font-weight: 600; }
.muted { color: #6b6a66; }
.pb { page-break-before: always; }
ul { margin: 1mm 0 3mm 5mm; padding: 0; } li { margin-bottom: 1mm; }
figure { margin: 2mm 0 4mm; page-break-inside: avoid; } figcaption { color: #52514e; font-size: 8.5pt; margin-top: 1mm; }
.two { display: flex; gap: 5mm; } .two > div { flex: 1; }
.keep { page-break-inside: avoid; } tr { page-break-inside: avoid; }
"""


def _short(text: str, limit: int = 150) -> str:
    text = str(text or "").split(" | ")[0]
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _fmt_usd(v) -> str:
    v = C.num(v)
    return f"USD {v:,.0f}" if v is not None else "UNKNOWN"


def why_matches(r: dict) -> str:
    beds = int(C.num(r.get("bedrooms")) or 0)
    area = C.num(r.get("area_m2"))
    band = str(r.get("space_band") or "").replace("_", " ").lower()
    s = f"{beds}-bedroom" + (f" with {area:.0f} m² ({band} for a {beds}BR)" if area else " (area not published)")
    furn = {"Yes": "furnished", "Semi": "semi-furnished", "No": "unfurnished"}.get(C.furnished_text(r))
    s += f", {furn}" if furn else ""
    total = C.num(r.get("estimated_total_monthly_usd"))
    if total is not None and total <= 1000:
        s += f", all-in cost within budget ({_fmt_usd(total)})"
    s += "."
    extras = [x for x in str(r.get("main_advantage") or "").split("; ")
              if x and not x.startswith(f"{area:.0f} m²" if area else "§") and not x.startswith("all-in")
              and x not in ("furnished", "meets all hard requirements")]
    if extras:
        s += " Also: " + "; ".join(extras) + "."
    return s


def _availability(r: dict) -> str:
    st = r.get("qa_status") or "NOT_CHECKED"
    ts = r.get("qa_checked_at") or r.get("scraped_at")
    if st in ("VERIFIED_ACTIVE", "ACTIVE_WITH_DIFFERENCES"):
        return f"Available when checked on {ts}" + (" (some details differed — see workbook)" if st != "VERIFIED_ACTIVE" else "")
    if st.startswith("UNVERIFIED"):
        return f"Seen in live search results on {r.get('scraped_at')}; automated re-check not possible — open the link to confirm"
    if st.startswith("PROGRAMMATIC") or st == "NOT_CHECKED":
        return f"Seen in live search results on {r.get('scraped_at')}; not re-checked"
    return f"QA: {st}"


# --------------------------------------------------------------------------- charts
def scatter_svg(df: pd.DataFrame, top: pd.DataFrame, budget: float) -> str:
    pts = df[df["area_m2"].notna() & df["rent_usd"].notna()]
    if pts.empty:
        return "<p class='muted'>Not enough data with published area to draw the rent–area chart.</p>"
    W, H, L, R, T, B = 700, 300, 52, 14, 24, 36
    xmax = max(40, math.ceil(pts["area_m2"].max() / 20) * 20)
    xmin = max(0, math.floor(pts["area_m2"].min() / 20) * 20)
    ymax = max(budget * 1.12, math.ceil(pts["rent_usd"].max() / 100) * 100)
    ymin = max(0, math.floor(pts["rent_usd"].min() / 100) * 100 - 100)
    sx = lambda x: L + (x - xmin) / (xmax - xmin) * (W - L - R)
    sy = lambda y: T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B)
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Rent versus floor area, by bedroom count" '
           f'style="background:{SURFACE};font-family:inherit">']
    ystep = 100 if ymax - ymin <= 900 else 200
    y = ymin
    while y <= ymax:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{sy(y):.1f}" y2="{sy(y):.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{L - 6}" y="{sy(y) + 3:.1f}" font-size="9" fill="{MUTED}" text-anchor="end">{y:,.0f}</text>')
        y += ystep
    x = xmin
    xstep = 10 if xmax - xmin <= 100 else 20
    while x <= xmax:
        out.append(f'<text x="{sx(x):.1f}" y="{H - B + 14}" font-size="9" fill="{MUTED}" text-anchor="middle">{x:.0f}</text>')
        x += xstep
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{AXIS}" stroke-width="1"/>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{sy(budget):.1f}" y2="{sy(budget):.1f}" stroke="{INK2}" stroke-width="1"/>')
    out.append(f'<text x="{W - R}" y="{sy(budget) - 4:.1f}" font-size="9" fill="{INK2}" text-anchor="end">'
               f'USD {budget:,.0f} budget</text>')
    out.append(f'<text x="{(L + W - R) / 2}" y="{H - 4}" font-size="9.5" fill="{INK2}" text-anchor="middle">Floor area (m²)</text>')
    out.append(f'<text x="12" y="{(T + H - B) / 2}" font-size="9.5" fill="{INK2}" text-anchor="middle" '
               f'transform="rotate(-90 12 {(T + H - B) / 2})">Monthly rent (USD)</text>')
    top_ids = {k: i + 1 for i, k in enumerate(top["_key"])} if not top.empty else {}
    for _, r in pts.iterrows():
        beds = int(r["bedrooms"]) if C.num(r["bedrooms"]) in (1, 2) else 1
        cx, cy = sx(r["area_m2"]), sy(r["rent_usd"])
        tip = E(f"{C.property_label(C.records(r.to_frame().T)[0])} · {_fmt_usd(r['rent_usd'])}")
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{SERIES[beds]}" stroke="{SURFACE}" '
                   f'stroke-width="2"><title>{tip}</title></circle>')
    for _, r in pts[pts["_key"].isin(top_ids)].iterrows():
        cx, cy = sx(r["area_m2"]), sy(r["rent_usd"])
        out.append(f'<text x="{cx + 6:.1f}" y="{cy - 5:.1f}" font-size="9" font-weight="bold" fill="{INK}">'
                   f'#{top_ids[r["_key"]]}</text>')
    # legend (two series → always present)
    lx = L + 8
    for beds, label in ((1, "1 bedroom"), (2, "2 bedrooms")):
        out.append(f'<circle cx="{lx}" cy="{T - 10}" r="4" fill="{SERIES[beds]}"/>'
                   f'<text x="{lx + 8}" y="{T - 7}" font-size="9.5" fill="{INK2}">{label}</text>')
        lx += 80
    out.append(f'<text x="{lx + 10}" y="{T - 7}" font-size="9.5" fill="{INK2}">#n = Top-10 rank</text>')
    out.append("</svg>")
    return "".join(out)


def map_svg(ranked: pd.DataFrame, top: pd.DataFrame, geo: dict | None) -> str:
    pts = ranked[ranked["latitude"].notna() & ranked["category"].isin(["PRIMARY", "STRETCH"])]
    boundary = (geo or {}).get("boundary_ll") or []
    roads = (geo or {}).get("road_lines_ll") or []
    lats = [p[0] for p in boundary] + list(pts["latitude"])
    lons = [p[1] for p in boundary] + list(pts["longitude"])
    if not lats:
        return "<p class='muted'>No coordinates available — map not drawn.</p>"
    pad = 0.002
    s, n, w, e = min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad
    kx = math.cos(math.radians((s + n) / 2))
    W = 700
    H = int(W * (n - s) / ((e - w) * kx))
    H = max(260, min(H, 520))
    sx = lambda lon: (lon - w) / (e - w) * W
    sy = lambda lat: (n - lat) / (n - s) * H
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Map of shortlisted listings" '
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
                   f'stroke="#fff" stroke-width="1.5"><title>{E(C.property_label(C.records(r.to_frame().T)[0]))}</title></circle>')
    for i, key in enumerate(top_keys, start=1):
        r = pts[pts["_key"] == key]
        if r.empty:
            continue
        r = r.iloc[0]
        x, y = sx(r["longitude"]), sy(r["latitude"])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{NAVY}" stroke="#fff" stroke-width="2">'
                   f'<title>#{i} {E(C.property_label(C.records(r.to_frame().T)[0]))}</title></circle>'
                   f'<text x="{x:.1f}" y="{y + 3.5:.1f}" font-size="9.5" font-weight="bold" fill="#fff" '
                   f'text-anchor="middle">{i}</text>')
    ly = H - 12
    out.append(f'<rect x="8" y="{ly - 30}" width="300" height="38" fill="#ffffffdd" rx="3"/>'
               f'<circle cx="20" cy="{ly - 18}" r="7" fill="{NAVY}"/><text x="32" y="{ly - 14}" font-size="9.5" fill="{INK2}">Top-10 rank</text>'
               f'<circle cx="110" cy="{ly - 18}" r="3" fill="#9aa5ad"/><text x="118" y="{ly - 14}" font-size="9.5" fill="{INK2}">other matches</text>'
               f'<line x1="200" x2="222" y1="{ly - 18}" y2="{ly - 18}" stroke="#b9b7ae" stroke-width="2.2"/>'
               f'<text x="226" y="{ly - 14}" font-size="9.5" fill="{INK2}">major road</text>'
               f'<text x="14" y="{ly + 2}" font-size="8" fill="{MUTED}">Outline: Miraflores district · © OpenStreetMap contributors</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- document
def _card(i: int, r: dict) -> str:
    risk = r.get("noise_risk") or "UNKNOWN"
    links = [f'<a href="{E(r["source_url"])}">View listing ↗</a>'] if r.get("source_url") else []
    if C.map_url(r):
        links.append(f'<a href="{E(C.map_url(r))}">Open map ↗</a>')
    if C.whatsapp_url(r):
        links.append(f'<a href="{E(C.whatsapp_url(r))}">WhatsApp ↗</a>')
    total = C.num(r.get("estimated_total_monthly_usd"))
    facts = [("Rent", _fmt_usd(r.get("rent_usd")) + (" (from S/)" if r.get("rent_usd_basis") == "CALCULATED" else "")),
             ("Maintenance", C.maintenance_text(r)),
             ("Est. total / month", f"≈ {_fmt_usd(total)}" if total is not None else
              ("= rent (maint. incl.)" if r.get("maintenance_included_in_rent") is True else "UNKNOWN")),
             ("Bedrooms · area", f"{int(C.num(r.get('bedrooms')) or 0)} BR · "
                                 + (f"{C.num(r.get('area_m2')):.0f} m²" if C.num(r.get('area_m2')) else "area UNKNOWN")),
             ("Furnished", C.furnished_text(r)), ("Floor", str(C.floor_text(r))),
             ("Contract", C.contract_text(r)), ("Deposit", C.deposit_text(r))]
    facts_html = "".join(f"<div><span>{E(k)}</span>{E(str(v))}</div>" for k, v in facts)
    return f"""
<div class="card">
  <div class="head"><h3><span class="rank">{i}</span>{E(C.property_label(r))}</h3>
  <span class="fit">Fit {C.num(r.get('fit_score')):.0f}/100 · {E(C.sources_text(r))}</span></div>
  <div class="facts">{facts_html}</div>
  <p class="kv"><b>Why it matches.</b> {E(why_matches(r))}</p>
  <p class="kv"><b>Main drawback.</b> {E(str(r.get('main_drawback') or ''))}</p>
  <p class="kv"><b>Noise.</b> <span class="pill {E(risk)}">{E(risk)} · {r.get('quietness_score_0_100')}/100</span>
     {E(str(r.get('quietness_reason') or ''))}</p>
  <p class="kv"><b>Contact.</b> {E(C.contact_text(r))}</p>
  <div class="foot"><span class="muted">{E(_availability(r))}</span><span class="links">{' '.join(links)}</span></div>
</div>"""


def _mini_table(rows: pd.DataFrame, cols: list[tuple[str, callable, bool]]) -> str:
    if rows.empty:
        return "<p class='muted'>No qualifying listings.</p>"
    head = "".join(f"<th class='{'num nw' if n else ''}'>{E(h)}</th>" for h, _, n in cols)
    body = ""
    for r in C.records(rows):
        body += "<tr>" + "".join(f"<td class='{'num nw' if n else ''}'>{f(r)}</td>" for _, f, n in cols) + "</tr>"
    return f"<table><tr>{head}</tr>{body}</table>"


def build_report_html(ranked: pd.DataFrame, meta: dict, audit_rows: list[dict], geo: dict | None,
                      banner: str | None = None) -> str:
    ranked = ranked.copy()
    ranked["_key"] = ranked["source"].astype(str) + ":" + ranked["source_listing_id"].astype(str)
    primary = ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category")
    top = primary.head(meta["top_n"])
    stretch = ranked[ranked["category"] == "STRETCH"].sort_values("rank_in_category")
    in_scope = ranked[ranked["category"].isin(["PRIMARY", "STRETCH"])]

    tiles = "".join(f"<div class='tile'><div class='label'>{E(k)}</div><div class='value'>{v}</div></div>" for k, v in (
        ("Listings collected", f"{meta['n_raw']:,}"), ("Unique after de-duplication", f"{meta['n_unique']:,}"),
        ("Budget-compliant Miraflores matches", f"{meta['n_primary']:,}"), ("Stretch (USD 1,001–1,100)", f"{meta['n_stretch']:,}")))

    src_rows = "".join(
        f"<tr><td>{E(a['Source'])}</td><td>{E(a['Status'])}</td><td>{E(a['Method'])}</td>"
        f"<td class='num'>{E(str(a['Records collected']))}</td><td>{E(_short(a['Limitations / errors']))}</td></tr>"
        for a in audit_rows if not str(a["Status"]).startswith("PENDING (not automated"))
    pending = [a["Source"] for a in audit_rows if str(a["Status"]).startswith("PENDING (not automated")]
    pending_html = (f"<p class='sub'>Also discovered but not automated in this iteration (listed in the workbook's "
                    f"SOURCE_AUDIT; can be added via manual import): {E(', '.join(pending))}.</p>" if pending else "")

    # market snapshot by bedroom count
    snap_rows = ""
    for beds, g in in_scope.groupby("bedrooms"):
        maint_known = g["maintenance_usd"].notna().mean() * 100 if len(g) else 0
        snap_rows += (f"<tr><td>{int(beds)} bedroom{'s' if beds > 1 else ''}</td><td class='num'>{len(g)}</td>"
                      f"<td class='num'>{_fmt_usd(g['rent_usd'].median())}</td>"
                      f"<td class='num'>{(str(round(g['area_m2'].median())) + ' m²') if g['area_m2'].notna().any() else 'UNKNOWN'}</td>"
                      f"<td class='num'>{(format(g['rent_usd_per_m2'].median(), '.1f')) if g['rent_usd_per_m2'].notna().any() else 'UNKNOWN'}</td>"
                      f"<td class='num'>{(g['furnished'] == True).mean() * 100:.0f}%</td>"  # noqa: E712
                      f"<td class='num'>{maint_known:.0f}%</td></tr>")
    snapshot = (f"<table><tr><th>Segment (Miraflores, ≤ USD 1,100)</th><th class='num'>Listings</th>"
                f"<th class='num'>Median rent</th><th class='num'>Median area</th><th class='num'>Median USD/m²</th>"
                f"<th class='num'>Furnished</th><th class='num'>Maintenance published</th></tr>{snap_rows}</table>"
                if snap_rows else "<p class='muted'>No in-scope listings collected in this run.</p>")

    quiet_space = primary.assign(_qs=primary["quietness_score_0_100"] * 0.6 + primary["pts_space"] * 2) \
        .sort_values("_qs", ascending=False).head(5)
    value = primary[primary["value_band"].isin(["EXCELLENT_VALUE", "GOOD_VALUE"]) & (primary["noise_risk"] != "HIGH")] \
        .sort_values("rent_usd_per_m2").head(5)
    link = lambda r: f"<a href='{E(r['source_url'])}'>{E(C.property_label(r))}</a>" if r.get("source_url") else E(C.property_label(r))
    qs_table = _mini_table(quiet_space, [
        ("Property", link, False), ("Quietness", lambda r: f"{r['quietness_score_0_100']}/100 ({E(str(r['noise_confidence']).lower())} conf.)", True),
        ("Area", lambda r: f"{C.num(r['area_m2']):.0f} m²" if C.num(r['area_m2']) else "UNKNOWN", True),
        ("Total / month", lambda r: E(str(r["estimated_total_text"])), False)])
    val_table = _mini_table(value, [
        ("Property", link, False), ("USD/m²", lambda r: f"{r['rent_usd_per_m2']:.1f}", True),
        ("Value band", lambda r: E(str(r["value_band"]).replace("_", " ").lower()), False),
        ("Noise", lambda r: E(str(r["noise_risk"])), False)])
    stretch_table = _mini_table(stretch.head(5), [
        ("Property", link, False), ("Rent", lambda r: _fmt_usd(r["rent_usd"]), True),
        ("Est. total", lambda r: _fmt_usd(r["estimated_total_monthly_usd"]), True),
        ("Fit", lambda r: f"{r['fit_score']:.0f}", True), ("Why consider it", lambda r: E(str(r["main_advantage"])), False)])

    # lease observations — computed, never assumed
    def share(col, pred):
        s = in_scope[col].dropna()
        return (pred(s).mean() * 100, len(s)) if len(s) else (None, 0)
    obs = []
    mc = in_scope["minimum_contract_months"].dropna()
    if len(mc):
        obs.append(f"Minimum term stated in {len(mc)} of {len(in_scope)} listings; most common: "
                   f"{int(mc.mode().iloc[0])} months. A monthly rent is not a month-to-month contract.")
    else:
        obs.append("No listing stated a minimum term in machine-readable form — ask every landlord.")
    dep = in_scope["deposit_months"].dropna()
    if len(dep):
        obs.append(f"Deposit stated in {len(dep)} listings; typical {dep.median():g} month(s); "
                   f"{(dep >= 3).sum()} ask 3 or more.")
    m_known = in_scope["maintenance_usd"].notna().sum()
    obs.append(f"Maintenance fee published or included in {m_known + int((in_scope['maintenance_included_in_rent'] == True).sum())} "  # noqa: E712
               f"of {len(in_scope)} listings — where it is missing, the true monthly cost is higher than the rent shown.")
    conv = (in_scope["rent_usd_basis"] == "CALCULATED").sum()
    obs.append(f"{conv} listing(s) are priced in soles; their USD figures are converted at the single rate "
               f"S/ {meta['fx_rate']:.3f} per USD and will move with the exchange rate.")

    audit_note = ""
    if meta["n_raw"] == 0:
        audit_note = ("<p><b>No listings could be collected in this run.</b> See the source table above and RUN_LOG.md; "
                      "the shortlist sections below are empty rather than filled with unverified data.</p>")

    cards = "".join(_card(i, r) for i, r in enumerate(C.records(top), start=1)) or \
        "<p class='muted'>No budget-compliant listings available in this run.</p>"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Miraflores Rental Shortlist</title><style>{CSS}</style></head><body>
{f'<div class="banner">{E(banner)}</div>' if banner else ''}
<h1>Miraflores Rental Shortlist</h1>
<p class="sub">Executive report · generated {E(meta['generated_at'])} · for a couple relocating to Lima</p>
<div class="tiles">{tiles}</div>
<p>This report ranks 1–2 bedroom apartments for rent inside the Miraflores district at or below USD 1,000 per month,
favouring quiet streets, usable space and value. Every figure comes from the listings themselves or from
OpenStreetMap; unknown values are shown as UNKNOWN rather than estimated. Listings are not guaranteed to be available —
each card states when it was last seen or checked.</p>
{audit_note}

<h2>1 · Requirements</h2>
<table>
<tr><th style="width:28%">Criterion</th><th>Applied as</th></tr>
<tr><td>Location</td><td>Miraflores district only (district outline from OpenStreetMap where coordinates exist). Other districts only in “Near misses”.</td></tr>
<tr><td>Budget</td><td>Base rent ≤ USD 1,000 (hard). Preferred: rent + maintenance ≤ USD 1,000 (flagged when exceeded). USD 1,001–1,100 kept separately as “Stretch”.</td></tr>
<tr><td>Size</td><td>1 or 2 bedrooms; studios excluded unless the listing itself classifies the unit as 1 bedroom.</td></tr>
<tr><td>Priorities</td><td>Quiet (25 pts) · budget (20) · space (20) · daily livability (10) · move-in readiness (8) · building/security (7) · listing quality (10).</td></tr>
<tr><td>Nice to have</td><td>Furnished, natural light, security, laundry, balcony, parking — scored as bonuses, never required.</td></tr>
</table>

<h2>2 · Sources searched</h2>
<table><tr><th>Source</th><th style="width:17%">Status</th><th>Method</th><th class="num">Records</th><th>Notes</th></tr>{src_rows}</table>
{pending_html}
<p class="sub">Exchange rate used for every conversion: 1 USD = S/ {meta['fx_rate']:.3f} — {E(meta['fx_source'])}.</p>

<h2>3 · Market snapshot</h2>
{snapshot}
<figure>{scatter_svg(in_scope, top, meta['budget'])}
<figcaption>Each dot is one unique listing (duplicates across portals merged). Relative to this sample only — not an official valuation.</figcaption></figure>

<h2>4 · Top 10</h2>
{cards}

<section class="keep"><h2>5 · Best quiet-space candidates</h2>
<p class="sub">Ranked by estimated quietness combined with space score.</p>
{qs_table}</section>
<section class="keep"><h2>6 · Best value candidates</h2>
<p class="sub">Lowest rent per m² within their bedroom group (relative to this sample), excluding high-noise-risk units.</p>
{val_table}</section>
<section class="keep"><h2>7 · Stretch / negotiable (USD 1,001–1,100)</h2>
{stretch_table}</section>

<h2 class="pb">8 · Map</h2>
<figure>{map_svg(ranked, top, geo)}
<figcaption>Numbered pins are the Top 10. Positions are as published by the portals; some portals show approximate locations.</figcaption></figure>

<h2>9 · Lease observations</h2>
<ul>{''.join(f'<li>{E(o)}</li>' for o in obs)}</ul>

<h2>10 · Verification checklist before signing</h2>
<ul>
<li><b>Noise, in person, three times:</b> weekday rush hour (7:30–9:00 or 18:00–20:00), a weekday evening, and a Friday or Saturday night after 23:00. Stand in the bedroom with windows closed.</li>
<li>Check which rooms face the street versus the interior; ask if windows are double-glazed.</li>
<li>Confirm the final rent, maintenance fee, and what is included (water, gas, electricity, internet, arbitrios).</li>
<li>Confirm minimum term, deposit months, advance months, and the penalty for early exit. Ask for the contract draft in advance.</li>
<li>Ask which documents a foreign tenant needs (passport / carné de extranjería, proof of income, guarantor).</li>
<li>Verify the owner or agent: ask for the property registry record (partida registral, SUNARP) and never pay a deposit before visiting.</li>
<li>Photograph the inventory and existing damage at move-in; attach it to the contract.</li>
<li>Test water pressure, hot water, mobile signal and internet availability in the unit.</li>
</ul>

<h2>11 · Methodology and limitations</h2>
<ul>
<li><b>Collection.</b> Portal searches for Miraflores rentals (1–2 bedrooms, ≤ USD 1,150 at query time) followed by
re-validation of every record after extraction; nothing is trusted from query filters alone.</li>
<li><b>De-duplication.</b> Listings posted on several portals are grouped by URL, portal id, coordinates, area, price,
phone, fuzzy title/description similarity and shared photo ids. One canonical record per group is ranked; all source links are kept.</li>
<li><b>Currency.</b> Values published in both currencies are kept as published; otherwise converted with one documented rate. The workbook marks every value as PUBLISHED or CALCULATED.</li>
<li><b>Noise estimate.</b> Distance to major roads and arterials, nightclubs, bar and restaurant clusters (OpenStreetMap) combined with listing text (interior-facing, acoustic windows, avenue view, floor). It is an estimate with a stated confidence and must be confirmed in person.</li>
<li><b>Livability.</b> Walking distance to supermarket, pharmacy, park, café, public transport and the Malecón. Nightlife is not rewarded.</li>
<li><b>Limits.</b> Portal data is self-reported by advertisers; some locations are approximate; OpenStreetMap may miss venues;
availability changes daily. Fit scores rank options — they do not replace a visit.</li>
</ul>
<p class="sub">Full field-level data, duplicate groups, red flags and source audit: Miraflores_Rental_Shortlist.xlsx.</p>
</body></html>"""


def html_to_pdf(html_path: Path, pdf_path: Path, banner: str | None = None) -> None:
    from playwright.sync_api import sync_playwright
    footer_left = (f"<b style='color:#9b1c13'>{E(banner)}</b>" if banner else "Miraflores Rental Shortlist")
    exe = None
    for cand in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome")):
        exe = str(cand)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page.pdf(path=str(pdf_path), format="A4", print_background=True,
                 display_header_footer=True,
                 header_template="<span></span>",
                 footer_template=("<div style='font-size:7.5pt;color:#898781;width:100%;padding:0 14mm;"
                                  "display:flex;justify-content:space-between;font-family:Liberation Sans,Arial'>"
                                  f"<span>{footer_left}</span>"
                                  "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>"),
                 margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        browser.close()
