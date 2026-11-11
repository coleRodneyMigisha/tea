"""Pure scheduler pieces: evaluate on hand-built state, rollover planning, DST, the Qt runner."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtWidgets import QApplication
from sched_world import World

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain.improve import BlogInfo, plan_rollover
from tea.scheduler import (
    EnterPickMode,
    PreparePacket,
    Rollover,
    SchedulerState,
    WeekInfo,
    evaluate,
)
from tea.scheduler_runner import SchedulerRunner
from tea.settings import Settings

TZ = ZoneInfo("Africa/Kampala")
WEEK = date(2026, 11, 9)


def state(**kw: object) -> SchedulerState:
    base: dict[str, object] = {
        "settings": Settings(),
        "trigger": "tick",
        "rollover_done": frozenset({WEEK}),
    }
    base.update(kw)
    return SchedulerState(**base)  # type: ignore[arg-type]


def test_evaluate_is_pure_and_deterministic() -> None:
    s = state(weeks={WEEK: WeekInfo(WEEK, None, False, None)})
    now = datetime(2026, 11, 13, 20, 0, tzinfo=TZ)
    first = evaluate(now, s)
    assert first == evaluate(now, s)
    assert first == [EnterPickMode(WEEK), PreparePacket("weekly_pick", WEEK)]


def test_pause_returns_nothing() -> None:
    s = state(settings=Settings(pause_automation=True), rollover_done=frozenset())
    assert evaluate(datetime(2026, 11, 13, 20, 0, tzinfo=TZ), s) == []


def test_rollover_comes_first() -> None:
    s = state(rollover_done=frozenset(), trigger="start")
    acts = evaluate(datetime(2026, 11, 9, 10, 0, tzinfo=TZ), s)
    assert acts[0] == Rollover(WEEK)


def test_due_compares_instants_not_offsets() -> None:
    """A `now` in another zone is still compared as an instant."""
    s = state(weeks={WEEK: WeekInfo(WEEK, "Focus", False, 1)})
    before = datetime(2026, 11, 13, 14, 59, tzinfo=ZoneInfo("UTC"))  # 17:59 Kampala
    after = datetime(2026, 11, 13, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert evaluate(before, s, tz=TZ) == []
    assert evaluate(after, s, tz=TZ) == [PreparePacket("weekly", WEEK)]


def blog(id: int, week: date, *, status: str = "ready", carried: int = 0, used: bool = False,
         draft: bool = True) -> BlogInfo:  # fmt: skip
    return BlogInfo(id, week, status, carried, used, draft)


def test_plan_rollover_rules() -> None:
    w1 = WEEK + timedelta(days=7)
    blogs = [
        blog(1, WEEK - timedelta(days=7)),
        blog(2, WEEK),
        blog(3, WEEK, used=True),
        blog(4, WEEK, draft=False, status="prompt_ready"),
        blog(5, w1),  # this week's own blog never carries yet
        blog(6, WEEK - timedelta(days=14), status="shelved"),
    ]
    plan = plan_rollover(blogs, w1, limit=1)
    assert (plan.carry, plan.shelve, plan.expire) == ((2,), (1,), ())
    assert plan_rollover([blog(2, WEEK, carried=1)], w1, limit=1).expire == (2,)
    assert plan_rollover([blog(2, WEEK)], w1, limit=0).expire == (2,)
    assert plan_rollover([], w1, limit=1) == plan_rollover([], w1, limit=3)


LONDON = ZoneInfo("Europe/London")


@pytest.mark.parametrize("monday", [date(2026, 3, 23), date(2026, 10, 19)])
def test_dst_weeks(qapp: QApplication, repos: Repos, monday: date) -> None:
    """Weeks that end on a DST change: the prompt is at 18:00 local and rollover runs once."""
    clock = FakeClock(datetime(monday.year, monday.month, monday.day, 9, 5, tzinfo=LONDON))
    world = World(Repos(repos.conn, clock), clock)
    world.set_focus("Clocks change", monday)
    friday = monday + timedelta(days=4)
    world.at(friday, 17, 59)
    world.clock.set(datetime(friday.year, friday.month, friday.day, 17, 59, tzinfo=LONDON))
    assert all(not isinstance(a, PreparePacket) for a in world.run())
    world.clock.set(datetime(friday.year, friday.month, friday.day, 18, 0, tzinfo=LONDON))
    assert PreparePacket("weekly", monday) in world.run()
    sunday = monday + timedelta(days=6)
    world.clock.set(datetime(sunday.year, sunday.month, sunday.day, 23, 50, tzinfo=LONDON))
    rolls = 0
    for _ in range(30):
        rolls += sum(isinstance(a, Rollover) for a in world.run())
        world.clock.advance(minutes=1)
    assert rolls == 1


# Qt runner


class RecordingExecutor:
    def __init__(self) -> None:
        self.triggers: list[str] = []

    def run(self, trigger: str) -> list[object]:
        self.triggers.append(trigger)
        return []


@pytest.fixture
def runner(qapp: QApplication) -> tuple[SchedulerRunner, RecordingExecutor, FakeClock]:
    clock = FakeClock(datetime(2026, 11, 13, 17, 0, tzinfo=TZ))
    ex = RecordingExecutor()
    r = SchedulerRunner(ex, clock, listen_for_sleep=False)  # type: ignore[arg-type]
    return r, ex, clock


def test_runner_start_tick_and_gap(
    runner: tuple[SchedulerRunner, RecordingExecutor, FakeClock],
) -> None:
    r, ex, clock = runner
    r.start()
    assert r.timer.interval() == 60_000 and r.timer.isActive()
    clock.advance(seconds=60)
    r.tick()
    clock.advance(minutes=5)
    r.tick()  # exactly 5 minutes is not a gap
    clock.advance(minutes=5, seconds=1)
    r.tick()  # more than 5 minutes: the machine slept
    clock.advance(minutes=-30)
    r.tick()  # the clock went back: an ordinary tick
    assert ex.triggers == ["start", "tick", "tick", "wake", "tick"]
    r.stop()
    assert not r.timer.isActive()


def test_runner_prepare_for_sleep(
    runner: tuple[SchedulerRunner, RecordingExecutor, FakeClock],
) -> None:
    r, ex, clock = runner
    r.start()
    r.on_prepare_for_sleep(True)
    clock.advance(hours=3)
    r.on_prepare_for_sleep(False)
    clock.advance(seconds=30)
    r.tick()  # the resume was already handled; no second wake from the gap
    assert ex.triggers == ["start", "wake", "tick"]


def test_runner_run_now(runner: tuple[SchedulerRunner, RecordingExecutor, FakeClock]) -> None:
    r, ex, _ = runner
    r.start()
    r.run_now()
    assert ex.triggers == ["start", "tick"]


def test_scheduler_logs_only_safe_fields(
    qapp: QApplication, repos: Repos, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With TEA_DEBUG=1 a rejected log field raises, so a whole week must run cleanly."""
    from tea.notify import Notifier

    monkeypatch.setenv("TEA_DEBUG", "1")
    world = World(repos, clock)
    for day, hour, trigger in (
        (9, 9, "start"),
        (12, 9, "tick"),
        (13, 18, "tick"),
        (13, 21, "wake"),
    ):
        world.clock.set(datetime(2026, 11, day, hour, 0, tzinfo=TZ))
        assert world.run(trigger) != []
    n: Notifier = world.notifier
    n.on_server_action(world.backend.sent[0].id, "default")
