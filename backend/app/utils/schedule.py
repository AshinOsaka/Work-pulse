"""Company work schedule: which calendar days count as working days.

A day is a working day when its weekday is one of the company's `work_days` (ISO weekdays, Monday = 1 … Sunday = 7)
and it is not listed in `holidays` ("YYYY-MM-DD"). Everything else — the weekly day off (e.g. Sunday) and fixed
holidays — is a non-working day. Productivity and attendance use this so a day off is shown as a holiday rather than
counted as absence or missing data. The productivity score itself is duration-weighted, so a day with no data never
lowers the percentage regardless.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


def is_working_day(day: date, work_days: Iterable[int], holidays: Iterable[str]) -> bool:
    if day.isoweekday() not in set(work_days):
        return False
    return day.isoformat() not in set(holidays)


def count_working_days(start: date, end: date, work_days: Iterable[int], holidays: Iterable[str]) -> int:
    """Inclusive count of working days in [start, end]."""
    weekdays, dates = set(work_days), set(holidays)
    total = 0
    cursor = start
    while cursor <= end:
        if cursor.isoweekday() in weekdays and cursor.isoformat() not in dates:
            total += 1
        cursor += timedelta(days=1)
    return total
