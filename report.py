"""Excel report for the finance desk, built from the reporting views in Snowflake."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .config import Settings
from .warehouse import Warehouse

REPORT_QUERIES = {
    "Daily Summary": """
        SELECT ticker, company_name, sector, total_orders, filled_orders, cancelled_orders,
               rejected_orders, buy_notional, sell_notional, total_fees
        FROM reporting.vw_daily_order_summary
        WHERE order_date = '{run_date}'::DATE ORDER BY buy_notional + sell_notional DESC""",
    "Ticker Performance": """
        SELECT ticker, company_name, sector, open_price, high_price, low_price, close_price,
               volume, price_change_pct
        FROM reporting.vw_ticker_performance
        WHERE trade_date = '{run_date}'::DATE ORDER BY price_change_pct DESC""",
    "Top Customers": """
        SELECT customer_id, full_name, segment, COUNT(*) AS filled_orders,
               SUM(gross_amount) AS gross_notional, SUM(fees) AS fees
        FROM reporting.vw_orders_enriched
        WHERE order_date = '{run_date}'::DATE AND status = 'FILLED'
        GROUP BY customer_id, full_name, segment ORDER BY gross_notional DESC LIMIT 10""",
}


def write_excel_report(sheets: dict[str, pd.DataFrame], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header_fill = PatternFill("solid", fgColor="1F2A37")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")
            for idx, col in enumerate(df.columns, start=1):
                width = max([len(str(col))] + [len(f"{v:,.2f}" if isinstance(v, float) else str(v)) for v in df[col].head(200)])
                ws.column_dimensions[get_column_letter(idx)].width = min(width + 3, 40)
                if pd.api.types.is_float_dtype(df[col]) or df[col].map(lambda v: hasattr(v, "quantize")).any():
                    for cell in ws[get_column_letter(idx)][1:]:
                        cell.number_format = "#,##0.00"
    return path


def export_daily_report(run_date: date, settings: Settings) -> Path:
    with Warehouse(settings) as wh:
        sheets = {name: wh.query_df(sql.format(run_date=run_date.isoformat()))
                  for name, sql in REPORT_QUERIES.items()}
    for df in sheets.values():  # Snowflake NUMBER arrives as Decimal
        for col in df.columns:
            if df[col].map(lambda v: hasattr(v, "quantize")).any():
                df[col] = pd.to_numeric(df[col])
    return write_excel_report(sheets, settings.export_dir / f"daily_report_{run_date.isoformat()}.xlsx")
