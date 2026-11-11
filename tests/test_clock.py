import re
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tea.clock import Clock, FakeClock, SystemClock, local_tz

SRC = Path(__file__).resolve().parent.parent / "src" / "tea"
KAMPALA = ZoneInfo("Africa/Kampala")


def test_fake_clock_is_a_clock() -> None:
    fake: Clock = FakeClock(datetime(2026, 1, 1, tzinfo=KAMPALA))
    assert fake.now() == datetime(2026, 1, 1, tzinfo=KAMPALA)
    assert fake.tz() is KAMPALA


def test_fake_clock_set_and_advance() -> None:
    fake = FakeClock(datetime(2026, 11, 13, 17, 59, tzinfo=KAMPALA))
    fake.advance(timedelta(minutes=1))
    assert fake.now() == datetime(2026, 11, 13, 18, 0, tzinfo=KAMPALA)
    fake.advance(hours=2, minutes=30)
    assert fake.now() == datetime(2026, 11, 13, 20, 30, tzinfo=KAMPALA)
    fake.set(datetime(2027, 1, 4, 9, 0, tzinfo=KAMPALA))
    assert fake.now() == datetime(2027, 1, 4, 9, 0, tzinfo=KAMPALA)


def test_fake_clock_does_not_move_on_its_own() -> None:
    fake = FakeClock(datetime(2026, 1, 1, tzinfo=KAMPALA))
    assert fake.now() == fake.now()


def test_fake_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 1, 1))
    fake = FakeClock(datetime(2026, 1, 1, tzinfo=KAMPALA))
    with pytest.raises(ValueError):
        fake.set(datetime(2026, 1, 2))


def test_fake_clock_converts_to_its_zone() -> None:
    fake = FakeClock(datetime(2026, 1, 1, 6, 0, tzinfo=ZoneInfo("UTC")), tz=KAMPALA)
    assert fake.now().tzinfo is KAMPALA
    assert fake.now().hour == 9


def test_system_clock_is_aware_and_current() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is not None
    assert isinstance(clock.tz(), tzinfo)
    assert abs(now - SystemClock().now()) < timedelta(seconds=5)


def test_local_tz_honors_tz_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Europe/London")
    assert local_tz() == ZoneInfo("Europe/London")


def test_tea_now_ignored_without_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEA_NOW", "2001-01-01T00:00:00")
    monkeypatch.delenv("TEA_DEBUG", raising=False)
    assert SystemClock().now().year != 2001


def test_tea_now_honored_with_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Africa/Kampala")
    monkeypatch.setenv("TEA_DEBUG", "1")
    monkeypatch.setenv("TEA_NOW", "2026-11-13T17:59:00")
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.replace(tzinfo=None) - datetime(2026, 11, 13, 17, 59) < timedelta(seconds=5)
    assert now.utcoffset() == timedelta(hours=3)


def test_tea_now_bad_value_falls_back_to_real_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEA_DEBUG", "1")
    monkeypatch.setenv("TEA_NOW", "not a date")
    assert SystemClock().now().year >= 2026


def test_no_wall_clock_calls_outside_clock_module() -> None:
    pattern = re.compile(r"\b(datetime\.now|datetime\.today|date\.today|datetime\.utcnow)\(")
    offenders = [
        f"{path.relative_to(SRC)}:{n}"
        for path in SRC.rglob("*.py")
        if path.name != "clock.py" or path.parent != SRC
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
