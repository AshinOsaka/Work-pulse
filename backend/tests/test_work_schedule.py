"""Company work schedule: working weekdays + holidays, used by productivity and attendance.

A 6-day week (Sunday off) scores over Monday-Saturday; non-working days are holidays, not absence.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.utils.schedule import count_working_days, is_working_day
from tests.org_helpers import Workspace, auth


def test_is_working_day_respects_weekly_day_off_and_holidays() -> None:
    work_days = [1, 2, 3, 4, 5, 6]  # Monday-Saturday, Sunday off
    holidays = {"2026-10-26"}
    assert is_working_day(date(2026, 10, 24), work_days, holidays) is True  # Saturday
    assert is_working_day(date(2026, 10, 25), work_days, holidays) is False  # Sunday (weekly off)
    assert is_working_day(date(2026, 10, 26), work_days, holidays) is False  # Monday, but a holiday
    assert is_working_day(date(2026, 10, 27), work_days, holidays) is True  # Tuesday


def test_count_working_days_for_a_six_day_week() -> None:
    # A full week Mon 19 - Sun 25 Oct 2026 with Sunday off = 6 working days.
    assert count_working_days(date(2026, 10, 19), date(2026, 10, 25), [1, 2, 3, 4, 5, 6], set()) == 6
    # Same week, five-day week = 5.
    assert count_working_days(date(2026, 10, 19), date(2026, 10, 25), [1, 2, 3, 4, 5], set()) == 5
    # One holiday inside the six-day week drops it to 5.
    assert count_working_days(date(2026, 10, 19), date(2026, 10, 25), [1, 2, 3, 4, 5, 6], {"2026-10-21"}) == 5


def test_new_workspace_defaults_to_monday_to_friday(ws: Workspace) -> None:
    company = ws.get("/companies/current").json()
    assert company["work_days"] == [1, 2, 3, 4, 5]
    assert company["holidays"] == []


def test_admin_sets_a_six_day_week_with_a_holiday(ws: Workspace) -> None:
    r = ws.patch(
        "/companies/current", {"work_days": [6, 1, 2, 3, 4, 5], "holidays": ["2026-12-25", "2026-10-02"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["work_days"] == [1, 2, 3, 4, 5, 6]  # stored sorted, Sunday (7) excluded
    assert body["holidays"] == ["2026-10-02", "2026-12-25"]  # sorted, de-duplicated


def test_invalid_schedule_is_rejected(ws: Workspace) -> None:
    assert ws.patch("/companies/current", {"work_days": []}).status_code == 422
    assert ws.patch("/companies/current", {"work_days": [0, 8]}).status_code == 422
    assert ws.patch("/companies/current", {"holidays": ["25-12-2026"]}).status_code == 422


def test_employees_without_policy_permission_cannot_change_the_schedule(
    ws: Workspace, client: TestClient
) -> None:
    member = ws.member("Emp Loyee")
    r = client.patch("/api/companies/current", json={"work_days": [1, 2, 3]}, headers=auth(member.token))
    assert r.status_code == 403
