import pandas as pd
from openpyxl import load_workbook

from fin_scraper.report import write_excel_report


def test_excel_report_has_formatted_sheets(tmp_path):
    sheets = {
        "Daily Summary": pd.DataFrame({"ticker": ["AAPL", "MSFT"], "buy_notional": [1234.5, 99.0]}),
        "Top Customers": pd.DataFrame({"customer_id": ["C1"], "fees": [3.2]}),
    }
    path = write_excel_report(sheets, tmp_path / "r.xlsx")
    wb = load_workbook(path)
    assert wb.sheetnames == ["Daily Summary", "Top Customers"]
    ws = wb["Daily Summary"]
    assert ws.freeze_panes == "A2"
    assert ws["A1"].font.bold
    assert ws["B2"].value == 1234.5
