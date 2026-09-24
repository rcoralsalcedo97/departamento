"""Gate 10 — final deliverable QA (automated; results go to RUN_LOG.md).

Checks the finished files, not just the data: the workbook opens with the right sheets and
live hyperlinks; every PDF page renders with no text running off the page or overlapping;
the Top-10 links answer; no demo/synthetic data or credential leaked; and the Top 10 obey
the hard requirements. Page renders are written to data/processed/qa/ for a human look.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

from .. import config as K

DEMO_RX = re.compile(r"\(DEMO|\bDEMO\b|Calle Ejemplo|Av\. Ejemplo|SYNTHETIC|Synthetic|synthetic|example\.com|\bfake listing")
TOKEN_RX = re.compile(r"apify_api_[A-Za-z0-9]{16,}")
REQUIRED_SHEETS = ["CLIENT_TOP_PICKS", "EXECUTIVE_SHORTLIST", "ALL_MATCHES", "STRETCH_NEGOTIABLE", "NEAR_MISSES",
                   "SOURCE_AUDIT", "METHODOLOGY", "CONTACT_GUIDE"]


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class Report:
    def __init__(self):
        self.lines: list[str] = []
        self.failed = False

    def add(self, status: str, label: str, detail: str = "") -> None:
        if status == "FAIL":
            self.failed = True
        self.lines.append(f"{status:4}  {label}" + (f" — {detail}" if detail else ""))


# --------------------------------------------------------------------------- workbook
def xlsx_checks(path: Path, rep: Report, production: bool) -> list[str]:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path)
    except Exception as exc:  # noqa: BLE001
        rep.add("FAIL", "1. XLSX opens", str(exc))
        return []
    missing = [s for s in REQUIRED_SHEETS if s not in wb.sheetnames]
    first_ok = wb.sheetnames[0] == "CLIENT_TOP_PICKS"
    links = sum(1 for ws in wb for row in ws.iter_rows() for c in row if c.hyperlink)
    rep.add("PASS" if not missing and first_ok else "FAIL", "1. XLSX opens with the expected sheets",
            f"{len(wb.sheetnames)} sheets, first = {wb.sheetnames[0]}, {links} hyperlinks"
            + (f", missing {missing}" if missing else ""))
    clipped = []
    for name in ("CLIENT_TOP_PICKS", "EXECUTIVE_SHORTLIST"):
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        for row in ws.iter_rows(min_row=5):
            for c in row:
                if c.value is None or c.hyperlink or (c.alignment and c.alignment.wrap_text):
                    continue
                width = ws.column_dimensions[c.column_letter].width or 8.43
                if len(str(c.value)) > width * 1.15:
                    clipped.append(f"{name}!{c.coordinate}")
    rep.add("PASS" if not clipped else "FAIL", "4. No clipped (unwrapped, overflowing) cells",
            ", ".join(clipped[:8]) + (" …" if len(clipped) > 8 else ""))
    urls = []
    if "CLIENT_TOP_PICKS" in wb.sheetnames:
        for row in wb["CLIENT_TOP_PICKS"].iter_rows(min_row=5):
            for c in row:
                if c.hyperlink and c.hyperlink.target:
                    urls.append(c.hyperlink.target)
    if production:
        hits = [f"{ws.title}!{c.coordinate}" for ws in wb for row in ws.iter_rows() for c in row
                if isinstance(c.value, str) and DEMO_RX.search(c.value)]
        rep.add("PASS" if not hits else "FAIL", "6. No demo/synthetic data in the workbook", ", ".join(hits[:5]))
    return urls


def render_sheet_png(path: Path, sheet: str, out_png: Path) -> None:
    """Approximate on-screen rendering of a sheet (column widths, wrapping) for visual review."""
    import html as H
    from openpyxl import load_workbook
    from playwright.sync_api import sync_playwright
    ws = load_workbook(path)[sheet]
    widths = [(ws.column_dimensions[c.column_letter].width or 8.43) * 7.2 for c in ws[4]]
    rows_html = []
    for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 16)):
        cells = []
        for j, c in enumerate(r):
            v = "" if c.value is None else str(c.value)
            style = f"width:{widths[j] if j < len(widths) else 60:.0f}px;max-width:{widths[j] if j < len(widths) else 60:.0f}px;"
            wrap = c.alignment is not None and c.alignment.wrap_text
            style += "white-space:normal;" if wrap else "white-space:nowrap;overflow:hidden;"
            if c.hyperlink:
                v = f"<u style='color:#1f5fbf'>{H.escape(v)}</u>"
            else:
                v = H.escape(v)
            bg = c.fill.fgColor.rgb if c.fill and c.fill.fill_type == "solid" else None
            if isinstance(bg, str) and len(bg) == 8:
                style += f"background:#{bg[2:]};"
            if c.font and c.font.color and isinstance(c.font.color.rgb, str) and len(c.font.color.rgb) == 8:
                style += f"color:#{c.font.color.rgb[2:]};"
            if c.font and c.font.bold:
                style += "font-weight:bold;"
            cells.append(f"<td style='{style}'>{v}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    doc = ("<html><body style='margin:0;font:12px Calibri,Liberation Sans,Arial'><table style='border-collapse:"
           "collapse;table-layout:fixed' border=1 cellpadding=3>" + "".join(rows_html) + "</table></body></html>")
    tmp = out_png.with_suffix(".html")
    tmp.write_text(doc, encoding="utf-8")
    exe = next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=str(exe)) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1366, "height": 768})
        pg.goto(tmp.resolve().as_uri())
        pg.screenshot(path=str(out_png), full_page=False)
        b.close()


# --------------------------------------------------------------------------- PDF
def pdf_checks(path: Path, rep: Report, out_dir: Path, production: bool) -> list[str]:
    import pymupdf
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001
        rep.add("FAIL", "2. PDF opens", str(exc))
        return []
    n = len(doc)
    overflow, overlaps, links, text_all = [], [], [], []
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc, start=1):
        page.get_pixmap(dpi=80).save(out_dir / f"pdf_page_{i:02d}.png")
        w = page.rect.width
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                bbox = pymupdf.Rect(line["bbox"])
                txt = "".join(sp["text"] for sp in line["spans"]).strip()
                if not txt:
                    continue
                text_all.append(txt)
                if bbox.x1 > w - 8 or bbox.x0 < 8:
                    overflow.append(f"p{i}: '{txt[:30]}'")
                lines.append((bbox, txt))
        for a in range(len(lines)):
            for b in range(a + 1, len(lines)):
                inter = lines[a][0] & lines[b][0]
                if inter.is_empty:
                    continue
                small = min(lines[a][0].get_area(), lines[b][0].get_area()) or 1
                if inter.get_area() / small > 0.35:
                    overlaps.append(f"p{i}: '{lines[a][1][:20]}' × '{lines[b][1][:20]}'")
        links += [ln.get("uri") for ln in page.get_links() if ln.get("uri")]
    rep.add("PASS" if 6 <= n <= 10 else "WARN", "2. PDF opens and every page renders",
            f"{n} pages (target 6–10); page images in {out_dir}")
    rep.add("PASS" if not overflow else "FAIL", "4b. No text running off the page", "; ".join(overflow[:5]))
    rep.add("PASS" if not overlaps else "FAIL", "5. No overlapping text", "; ".join(overlaps[:5]))
    if production:
        joined = "\n".join(text_all)
        hits = DEMO_RX.findall(joined)
        rep.add("PASS" if not hits else "FAIL", "6b. No demo/synthetic wording in the PDF", ", ".join(sorted(set(hits))))
    return links


# --------------------------------------------------------------------------- links, leaks, rules
def link_checks(urls: list[str], http, rep: Report, label: str) -> None:
    if http is None:
        rep.add("SKIP", label, "no network client")
        return
    listing = [u for u in dict.fromkeys(urls) if not re.search(r"wa\.me|google\.com/maps|openstreetmap", u)]
    other = [u for u in dict.fromkeys(urls) if u not in listing]
    dead, protected, alive = [], [], 0
    for u in listing:
        try:
            r = http.request_json("GET", u, timeout=25)
            if r.status_code in (404, 410):
                dead.append(u)
            elif r.status_code in (401, 403, 429, 503):
                protected.append(u)
            else:
                alive += 1
        except Exception as exc:  # noqa: BLE001
            protected.append(f"{u} ({type(exc).__name__})")
    malformed = [u for u in other if not u.startswith("https://")]
    status = "FAIL" if dead or malformed else ("WARN" if protected else "PASS")
    rep.add(status, label, f"{alive} listing links answer, {len(protected)} bot-protected/unreachable to scripts "
                           f"(open manually), {len(dead)} dead; {len(other)} map/WhatsApp links well-formed"
            + (f"; dead: {dead[:3]}" if dead else ""))


def leak_checks(paths: list[Path], token: str | None, rep: Report) -> None:
    import subprocess
    scan = list(paths)
    for pattern in ("*.md", "config/*", "outputs/*", "data/processed/*.csv", "data/processed/*.json"):
        scan += [p for p in K.ROOT.glob(pattern) if p.is_file()]
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=K.ROOT, capture_output=True, text=True).stdout.split()
        scan += [K.ROOT / t for t in tracked]
    except Exception:  # noqa: BLE001
        pass
    leaked = []
    for p in dict.fromkeys(scan):
        if not p.is_file() or p.name == ".env" or p.stat().st_size > 30_000_000:
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if TOKEN_RX.search(data.decode("latin-1")) or (token and token.encode() in data):
            leaked.append(str(p.relative_to(K.ROOT)))
    rep.add("PASS" if not leaked else "FAIL", "7. No secret/token in any file", ", ".join(leaked))


def rule_checks(ranked: pd.DataFrame, cfg: dict, rep: Report, production: bool) -> None:
    top = ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category").head(cfg["shortlist"]["top_n"])
    district = cfg["location"]["district"]
    bad_d = [r["source_url"] for r in top.to_dict("records")
             if not (r.get("district") == district and r.get("inside_district_polygon") is not False)
             and r.get("inside_district_polygon") is not True]
    rep.add("PASS" if not bad_d and len(top) else "FAIL", "8. Every Top-10 listing is in Miraflores",
            f"{len(top)} checked" + (f"; problems: {bad_d[:3]}" if bad_d else ""))
    rep.add("PASS" if top["bedrooms"].isin([1, 2]).all() else "FAIL", "9. Every Top-10 listing has 1–2 bedrooms")
    wrong = []
    for r in top.to_dict("records"):
        rent, total = _num(r.get("rent_usd")), _num(r.get("estimated_total_monthly_usd"))
        bc = r.get("budget_class")
        if rent is None or rent > cfg["budget"]["target_max_rent"]:
            wrong.append(f"{r['source_url']} rent {rent}")
        elif bc == "STRICT_ALL_IN" and not (total is not None and total <= cfg["budget"]["target_max_total"]
                                            or r.get("maintenance_included_in_rent") is True):
            wrong.append(f"{r['source_url']} marked STRICT without known total")
        elif bc == "BASE_RENT_COMPLIANT" and total is not None and total <= cfg["budget"]["target_max_total"]:
            wrong.append(f"{r['source_url']} total ≤ budget but not STRICT")
    rep.add("PASS" if not wrong else "FAIL", "10. Budget classification consistent", "; ".join(wrong[:3]))
    groups = ranked["duplicate_group_id"]
    rep.add("PASS" if groups.notna().all() and groups.is_unique else "FAIL", "11. Duplicate groups",
            f"{groups.nunique()} canonical groups; {int((ranked['number_of_records'] > 1).sum())} merge ≥2 records")
    conf_ok = top["noise_confidence"].isin(["HIGH", "MEDIUM", "LOW"]).all() and \
        top["quietness_reason"].astype(str).str.contains("confidence").all()
    rep.add("PASS" if conf_ok else "FAIL", "12. Quietness claims state their confidence")
    if production:
        demo = [r["source_url"] for r in ranked.to_dict("records")
                if DEMO_RX.search(" ".join(str(r.get(k) or "") for k in ("title", "address", "source_url",
                                                                        "agency_name")))]
        rep.add("PASS" if not demo else "FAIL", "6c. Zero demo/synthetic records in the production dataset",
                f"{len(ranked)} records scanned" + (f"; found {demo[:3]}" if demo else ""))
    counts = top["active_status"].value_counts().to_dict()
    rep.add("INFO", "Top-10 availability", ", ".join(f"{k} {v}" for k, v in counts.items()))


def final_qa(ranked: pd.DataFrame, paths, cfg: dict, token: str | None, http,
             production: bool = True) -> tuple[list[str], bool]:
    xlsx, pdf, txt = paths
    rep = Report()
    qa_dir = K.PROCESSED / "qa" if production else Path(pdf).parent / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    urls = xlsx_checks(Path(xlsx), rep, production)
    try:
        render_sheet_png(Path(xlsx), "CLIENT_TOP_PICKS", qa_dir / "xlsx_client_top_picks.png")
        rep.add("PASS", "1b. XLSX rendered for visual review", str((qa_dir / "xlsx_client_top_picks.png").name))
    except Exception as exc:  # noqa: BLE001
        rep.add("WARN", "1b. XLSX render", f"{type(exc).__name__}: {exc}")
    pdf_links = pdf_checks(Path(pdf), rep, qa_dir, production)
    if production:
        txt_hits = DEMO_RX.findall(Path(txt).read_text(encoding="utf-8"))
        rep.add("PASS" if not txt_hits else "FAIL", "6d. No demo data in contact templates", ", ".join(set(txt_hits)))
        link_checks(urls, http, rep, "3. Top-10 hyperlinks (workbook) respond")
        rep.add("PASS" if pdf_links else "FAIL", "3b. PDF contains clickable links", f"{len(pdf_links)} links")
    leak_checks([Path(xlsx), Path(pdf), Path(txt)], token, rep)
    rule_checks(ranked, cfg, rep, production)
    if production:
        top_urls = list(ranked[ranked["category"] == "PRIMARY"].sort_values("rank_in_category")
                        .head(cfg["shortlist"]["top_n"])["source_url"])
        link_checks(top_urls, http, rep, "13. Top-10 source URLs re-checked at the end")
    return rep.lines, not rep.failed
