from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from tea.domain.weeks import (
    due_at,
    focus_due,
    next_week_start,
    pick_due,
    previous_week_start,
    prompt_due,
    week_start,
)
from tea.settings import Settings

LONDON = ZoneInfo("Europe/London")
KAMPALA = ZoneInfo("Africa/Kampala")


@pytest.mark.parametrize(
    ("day", "monday"),
    [
        (date(2020, 12, 31), date(2020, 12, 28)),
        (date(2021, 1, 1), date(2020, 12, 28)),
        (date(2021, 1, 3), date(2020, 12, 28)),
        (date(2021, 1, 4), date(2021, 1, 4)),
        (date(2025, 12, 31), date(2025, 12, 29)),
        (date(2026, 1, 1), date(2025, 12, 29)),
        (date(2027, 1, 1), date(2026, 12, 28)),
        (date(2027, 1, 3), date(2026, 12, 28)),
        (date(2024, 2, 29), date(2024, 2, 26)),
        (date(2024, 3, 3), date(2024, 2, 26)),
        (date(2024, 3, 4), date(2024, 3, 4)),
        (date(2026, 3, 30), date(2026, 3, 30)),
        (date(2026, 10, 25), date(2026, 10, 19)),
        (date(2026, 10, 26), date(2026, 10, 26)),
    ],
)
def test_week_start(day: date, monday: date) -> None:
    assert week_start(day) == monday


def test_week_start_from_datetime_uses_local_date() -> None:
    assert week_start(datetime(2026, 11, 15, 23, 59, tzinfo=KAMPALA)) == date(2026, 11, 9)
    assert week_start(datetime(2026, 11, 16, 0, 0, tzinfo=KAMPALA)) == date(2026, 11, 16)


@pytest.mark.parametrize(
    ("ws", "prev"),
    [
        (date(2021, 1, 4), date(2020, 12, 28)),
        (date(2024, 3, 4), date(2024, 2, 26)),
        (date(2027, 1, 4), date(2026, 12, 28)),
        (date(2026, 1, 1), date(2025, 12, 22)),  # not a Monday: normalised first
    ],
)
def test_previous_week_start(ws: date, prev: date) -> None:
    assert previous_week_start(ws) == prev


def test_next_week_start_across_year_end() -> None:
    assert next_week_start(date(2026, 12, 28)) == date(2027, 1, 4)
    assert next_week_start(date(2026, 12, 31)) == date(2027, 1, 4)


def test_due_datetimes_default_settings() -> None:
    s = Settings()
    ws = date(2026, 11, 9)
    assert focus_due(ws, s, KAMPALA) == datetime(2026, 11, 9, 9, 0, tzinfo=KAMPALA)
    assert pick_due(ws, s, KAMPALA) == datetime(2026, 11, 12, 9, 0, tzinfo=KAMPALA)
    assert prompt_due(ws, s, KAMPALA) == datetime(2026, 11, 13, 18, 0, tzinfo=KAMPALA)


def test_due_datetimes_follow_settings() -> None:
    s = Settings(focus_day=1, focus_time=time(7, 15), prompt_day=6, prompt_time=time(23, 30))
    ws = date(2026, 12, 28)
    assert focus_due(ws, s, KAMPALA) == datetime(2026, 12, 29, 7, 15, tzinfo=KAMPALA)
    assert prompt_due(ws, s, KAMPALA) == datetime(2027, 1, 3, 23, 30, tzinfo=KAMPALA)


def test_due_normalises_week_start() -> None:
    assert due_at(date(2026, 11, 12), 0, time(9), KAMPALA) == datetime(
        2026, 11, 9, 9, tzinfo=KAMPALA
    )


def test_due_rejects_bad_weekday() -> None:
    with pytest.raises(ValueError):
        due_at(date(2026, 11, 9), 7, time(9), KAMPALA)


def test_late_march_monday_keeps_wall_clock_time() -> None:
    # Clocks went forward in London on Sunday 2026-03-29.
    s = Settings()
    before = focus_due(date(2026, 3, 23), s, LONDON)
    after = focus_due(date(2026, 3, 30), s, LONDON)
    assert (before.hour, after.hour) == (9, 9)
    assert before.utcoffset() == timedelta(0)
    assert after.utcoffset() == timedelta(hours=1)
    # Subtract in UTC: Python ignores offsets when both sides share one tzinfo.
    assert after.astimezone(UTC) - before.astimezone(UTC) == timedelta(hours=167)


def test_late_october_monday_keeps_wall_clock_time() -> None:
    # Clocks went back in London on Sunday 2026-10-25.
    s = Settings()
    friday_before = prompt_due(date(2026, 10, 19), s, LONDON)
    monday_after = focus_due(date(2026, 10, 26), s, LONDON)
    assert friday_before.utcoffset() == timedelta(hours=1)
    assert monday_after.utcoffset() == timedelta(0)
    assert monday_after.hour == 9
    monday_before = focus_due(date(2026, 10, 19), s, LONDON)
    assert monday_after.astimezone(UTC) - monday_before.astimezone(UTC) == timedelta(hours=169)


def test_sunday_due_in_switch_week() -> None:
    s = Settings(prompt_day=6, prompt_time=time(18))
    due = prompt_due(date(2026, 3, 23), s, LONDON)
    assert (due.date(), due.hour, due.utcoffset()) == (date(2026, 3, 29), 18, timedelta(hours=1))
