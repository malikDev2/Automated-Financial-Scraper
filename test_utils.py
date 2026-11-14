from datetime import date

from fin_scraper.utils import business_days, previous_business_day


def test_previous_business_day_skips_weekends():
    assert previous_business_day(date(2024, 6, 3)) == date(2024, 5, 31)   # Mon -> Fri
    assert previous_business_day(date(2024, 6, 4)) == date(2024, 6, 3)    # Tue -> Mon
    assert previous_business_day(date(2024, 6, 1)) == date(2024, 5, 31)   # Sat -> Fri


def test_business_days_range():
    days = business_days(date(2024, 5, 31), date(2024, 6, 4))
    assert days == [date(2024, 5, 31), date(2024, 6, 3), date(2024, 6, 4)]
