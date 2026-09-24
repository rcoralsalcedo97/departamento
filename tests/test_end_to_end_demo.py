"""Offline end-to-end run on synthetic fixtures (no network): exercises every gate and all deliverables."""
from openpyxl import load_workbook

from src import pipeline


def test_demo_pipeline_builds_all_deliverables(tmp_path):
    assert pipeline.main(["--mode", "demo", "--out", str(tmp_path)]) == 0
    out = tmp_path
    wb = load_workbook(out / "PREVIEW_SYNTHETIC_Miraflores_Rental_Shortlist.xlsx")
    assert wb.sheetnames == ["CLIENT_TOP_PICKS", "EXECUTIVE_SHORTLIST", "ALL_MATCHES", "STRETCH_NEGOTIABLE", "NEAR_MISSES",
                             "SOURCE_AUDIT", "METHODOLOGY", "CONTACT_GUIDE"]
    assert len([r for r in wb["CLIENT_TOP_PICKS"].iter_rows(min_row=5) if r[0].value]) == 10
    assert wb["CLIENT_TOP_PICKS"].max_column <= 14
    ws = wb["EXECUTIVE_SHORTLIST"]
    assert "SYNTHETIC" in str(ws["A3"].value)
    assert any(c.hyperlink for row in ws.iter_rows() for c in row)
    assert (out / "PREVIEW_SYNTHETIC_Miraflores_Rental_Executive_Report.pdf").stat().st_size > 20000
    assert "ESPAÑOL" in (out / "PREVIEW_SYNTHETIC_Contact_Templates.txt").read_text(encoding="utf-8")
