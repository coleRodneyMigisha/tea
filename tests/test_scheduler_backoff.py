"""A failing PreparePacket backs off and tells the owner once (M5 review, M11)."""

from datetime import timedelta

import pytest
from PySide6.QtWidgets import QApplication
from sched_world import WEEK, World

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain import weekly
from tea.ui import strings

FRI = WEEK + timedelta(days=4)


@pytest.fixture
def world(qapp: QApplication, repos: Repos, clock: FakeClock) -> World:
    return World(repos, clock)


class Failing:
    """Makes `prepare_packet` raise, and counts the calls."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        self.real = weekly.prepare_packet
        monkeypatch.setattr(weekly, "prepare_packet", self)

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        raise RuntimeError("disk full")

    def mend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weekly, "prepare_packet", self.real)


def _failure_notices(world: World) -> list[str]:
    return [s.title for s in world.backend.sent if s.title == strings.NOTIFY_PREPARE_FAILED]


def _ready_world(world: World) -> World:
    world.at(WEEK, 9, 5)
    world.set_focus("Why small teams ship faster")
    assert world.handoffs() == []  # nothing is prepared before Friday 18:00
    return world.at(FRI, 18, 0)


def test_failing_packet_is_retried_with_growing_gaps(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready_world(world)
    failing = Failing(monkeypatch)
    world.run()
    assert failing.calls == 1
    for _ in range(4):  # every minute for four minutes: no new attempt
        world.clock.advance(minutes=1)
        world.run()
    assert failing.calls == 1
    world.clock.advance(minutes=1)  # five minutes after the first failure
    world.run()
    assert failing.calls == 2
    world.clock.advance(minutes=9)
    world.run()
    assert failing.calls == 2  # the next gap is longer: 10 minutes
    world.clock.advance(minutes=1)
    world.run()
    assert failing.calls == 3


def test_gap_stops_growing_at_one_hour(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _ready_world(world)
    failing = Failing(monkeypatch)
    for _ in range(12 * 60):  # twelve hours, one tick a minute
        world.run()
        world.clock.advance(minutes=1)
    assert failing.calls <= 3 + 12  # 5, 10, 20, 40 minutes then hourly


def test_owner_is_told_once_after_three_failures(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready_world(world)
    Failing(monkeypatch)
    for _ in range(3 * 60):
        world.run()
        world.clock.advance(minutes=1)
    assert len(_failure_notices(world)) == 1


def test_success_after_failures_clears_the_backoff(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready_world(world)
    failing = Failing(monkeypatch)
    world.run()
    failing.mend(monkeypatch)
    world.clock.advance(minutes=5)
    world.run()
    assert [h.kind for h in world.live()] == ["weekly"]
    assert _failure_notices(world) == []
