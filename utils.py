from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


def previous_business_day(today: date | None = None) -> date:
    """Most recent weekday strictly before `today` (exchange holidays surface as empty API responses)."""
    d = (today or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def render_sql(path: Path, **params: str) -> str:
    """Load a .sql file and fill {placeholders}. Only trusted values (ISO dates) are ever passed in."""
    return path.read_text(encoding="utf-8").format(**params)
