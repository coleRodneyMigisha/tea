"""Clock protocol, SystemClock and FakeClock (tests).

This is the only module allowed to read the wall clock. Everything else takes a Clock.
"""

import contextlib
import os
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Clock(Protocol):
    def now(self) -> datetime:
        """Current local time, timezone-aware."""
        ...

    def tz(self) -> tzinfo:
        """The local timezone used for due times."""
        ...


def local_tz() -> tzinfo:
    """The machine's IANA zone (so wall-clock due times survive DST), else a fixed offset."""
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    with contextlib.suppress(OSError):
        target = str(Path("/etc/localtime").resolve())
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    with contextlib.suppress(OSError):
        candidates.append(Path("/etc/timezone").read_text().strip())
    for key in candidates:
        if not key:
            continue
        try:
            return ZoneInfo(key)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    fallback = datetime.now().astimezone().tzinfo
    assert fallback is not None
    return fallback


def _debug_start(tz: tzinfo) -> datetime | None:
    if os.environ.get("TEA_DEBUG") != "1":
        return None
    raw = os.environ.get("TEA_NOW", "")
    if not raw:
        return None
    try:
        start = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return start.replace(tzinfo=tz) if start.tzinfo is None else start.astimezone(tz)


class SystemClock:
    """Real time. With TEA_DEBUG=1, TEA_NOW sets the start time and the clock runs on from there."""

    def __init__(self) -> None:
        self._tz = local_tz()
        start = _debug_start(self._tz)
        self._offset = start - self._real() if start else timedelta(0)

    def _real(self) -> datetime:
        return datetime.now(self._tz)

    def now(self) -> datetime:
        return self._real() + self._offset

    def tz(self) -> tzinfo:
        return self._tz


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime, tz: tzinfo | None = None) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self._tz = tz or start.tzinfo
        self._now = start.astimezone(self._tz)

    def now(self) -> datetime:
        return self._now

    def tz(self) -> tzinfo:
        return self._tz

    def set(self, when: datetime) -> None:
        if when.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self._now = when.astimezone(self._tz)

    def advance(self, delta: timedelta | None = None, **kwargs: float) -> None:
        step = (delta or timedelta(0)) + timedelta(**kwargs)
        # Add in UTC so the result is a real elapsed duration, then show it in local time.
        self._now = (self._now.astimezone(ZoneInfo("UTC")) + step).astimezone(self._tz)


def iso(when: datetime) -> str:
    """Storage format: ISO 8601, local time with offset, whole seconds."""
    return when.isoformat(timespec="seconds")
