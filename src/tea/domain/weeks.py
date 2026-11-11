"""ISO week helpers and due datetimes.

Due times are built from the local calendar date plus a wall-clock time in a real zone,
so a week is not assumed to last 168 hours (DST weeks last 167 or 169).
"""

from datetime import date, datetime, time, timedelta, tzinfo

from tea.settings import Settings


def week_start(day: date | datetime) -> date:
    """Monday of the ISO week holding `day` (a datetime is read in its own local zone)."""
    d = day.date() if isinstance(day, datetime) else day
    return d - timedelta(days=d.weekday())


def previous_week_start(day: date) -> date:
    return week_start(day) - timedelta(days=7)


def next_week_start(day: date) -> date:
    return week_start(day) + timedelta(days=7)


def due_at(week: date, weekday: int, at: time, tz: tzinfo) -> datetime:
    """Local datetime for `weekday` (0 = Monday) at `at` in the week holding `week`."""
    if not 0 <= weekday <= 6:
        raise ValueError(f"weekday must be 0 to 6, got {weekday}")
    day = week_start(week) + timedelta(days=weekday)
    return datetime.combine(day, at, tzinfo=tz)


def focus_due(week: date, settings: Settings, tz: tzinfo) -> datetime:
    return due_at(week, settings.focus_day, settings.focus_time, tz)


def pick_due(week: date, settings: Settings, tz: tzinfo) -> datetime:
    return due_at(week, settings.pick_day, settings.pick_time, tz)


def prompt_due(week: date, settings: Settings, tz: tzinfo) -> datetime:
    return due_at(week, settings.prompt_day, settings.prompt_time, tz)
