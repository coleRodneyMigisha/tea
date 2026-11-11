"""Test harness for the scheduler: a FakeClock, a real database, fake UI hooks, fake DBus.

`World.run(trigger)` loads state, evaluates and applies the actions, like the Qt runner does.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.db.rows import Handoff
from tea.devtools import sample_replies
from tea.domain import questions as qs
from tea.domain import weekly
from tea.handoff.importer import import_reply
from tea.notify import Notifier
from tea.scheduler import Action
from tea.scheduler_runner import Executor
from tea.settings import Settings

TZ = ZoneInfo("Africa/Kampala")  # the conftest clock's zone

WEEK = date(2026, 11, 9)  # Monday; W+1 = 16 Nov, W+2 = 23 Nov, W+3 = 30 Nov
W1 = date(2026, 11, 16)
W2 = date(2026, 11, 23)
W3 = date(2026, 11, 30)


def at(day: date, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


@dataclass
class Sent:
    replaces_id: int
    title: str
    body: str
    action: str
    id: int


class FakeBackend:
    """Stands in for the DBus notification server."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[Sent] = []
        self.fail = fail
        self._next = 100

    def send(self, replaces_id: int, title: str, body: str, action: str, done: Any) -> None:
        if self.fail:
            done(None)
            return
        self._next += 1
        nid = replaces_id or self._next
        self.sent.append(Sent(replaces_id, title, body, action, nid))
        done(nid)


@dataclass
class FakeHooks:
    focus_shown: list[date] = field(default_factory=list)
    login_shown: int = 0
    focus_open: bool = False
    handoff_open: bool = False
    changed: int = 0

    def show_focus_dialog(self, week: date) -> None:
        self.focus_shown.append(week)

    def show_login_questions(self) -> None:
        self.login_shown += 1

    def focus_dialog_open(self) -> bool:
        return self.focus_open

    def handoff_dialog_open(self) -> bool:
        return self.handoff_open

    def state_changed(self) -> None:
        self.changed += 1


class World:
    def __init__(self, repos: Repos, clock: FakeClock, **settings: Any) -> None:
        self.repos = repos
        self.clock = clock
        self.settings = Settings(**settings)
        self.backend = FakeBackend()
        self.notifier = Notifier(clock, self.backend)
        self.hooks = FakeHooks()
        self.executor = Executor(repos, clock, lambda: self.settings, self.notifier, self.hooks)
        qs.seed_bank(repos)

    def set(self, **changes: Any) -> None:
        self.settings = Settings.model_validate({**self.settings.model_dump(), **changes})

    def at(self, day: date, hour: int = 0, minute: int = 0) -> "World":
        self.clock.set(at(day, hour, minute))
        return self

    def run(self, trigger: str = "tick") -> list[Action]:
        return self.executor.run(trigger)  # type: ignore[arg-type]

    # Owner actions

    def set_focus(self, text: str, week: date = WEEK) -> Handoff | None:
        rebuilt = weekly.save_focus(self.repos, self.settings, self.clock, week, text)
        if rebuilt is not None:
            self.notifier.prompts_ready([(rebuilt.id, rebuilt.kind, "")])
        return rebuilt

    def import_for(self, handoff: Handoff, kind: str = "weekly") -> None:
        text = {
            "weekly": sample_replies.WEEKLY,
            "weekly_pick": sample_replies.WEEKLY_PICK,
            "improve": sample_replies.IMPROVE,
        }[kind]
        import_reply(self.repos, handoff.id, text)

    # Queries

    def handoffs(self, **filters: Any) -> list[Handoff]:
        return self.repos.handoffs.list(**filters)

    def live(self, kind: str | None = None) -> list[Handoff]:
        return [h for h in self.repos.handoffs.list(kind=kind) if h.status != "superseded"]

    def titles(self) -> list[str]:
        return [s.title for s in self.backend.sent]


def kinds(actions: list[Action]) -> list[str]:
    return [type(a).__name__ for a in actions]
