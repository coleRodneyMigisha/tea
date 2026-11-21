"""The Qt half of the scheduler (ARCHITECTURE 4): run `evaluate` and carry out its actions.

`Executor` loads state, evaluates and applies actions against the database, the notifier
and the UI hooks; it has no timers, so tests drive it directly. `SchedulerRunner` calls it
at app start, every 60 seconds, and on resume from sleep (a wall-clock gap of more than
5 minutes between ticks, or logind's `PrepareForSleep(false)`).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from PySide6.QtCore import SLOT, QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Handoff
from tea.domain import improve, weekly
from tea.domain.weekly import elapsed
from tea.logging_setup import log_event
from tea.scheduler import (
    Action,
    EnterPickMode,
    NotifyNoFocus,
    PreparePacket,
    RemindHandoff,
    Rollover,
    ShowFocusDialog,
    ShowLoginQuestions,
    Trigger,
    evaluate,
    load_state,
)
from tea.settings import Settings

TICK_MS = 60_000
WAKE_GAP = timedelta(minutes=5)
RETRY_FIRST = timedelta(minutes=5)  # a failing PreparePacket waits 5, 10, 20, 40, then 60 minutes
RETRY_LONGEST = timedelta(minutes=60)
TELL_OWNER_AFTER = 3  # failures in a row before the owner gets one notification


@dataclass
class _Failure:
    count: int
    retry_at: datetime


class Hooks(Protocol):
    """What the scheduler asks of the UI."""

    def show_focus_dialog(self, week: date) -> None: ...
    def show_login_questions(self) -> None: ...
    def focus_dialog_open(self) -> bool: ...
    def handoff_dialog_open(self) -> bool: ...
    def state_changed(self) -> None: ...


class Notifications(Protocol):
    def prompts_ready(self, items: list[tuple[int, str, str]]) -> None: ...
    def reminders(self, items: list[tuple[int, str]]) -> None: ...
    def focus_prompt(self, week: date) -> None: ...
    def pick_mode(self, week: date) -> None: ...
    def no_focus(self, week: date) -> None: ...
    def prepare_failed(self, week: date) -> None: ...


class Executor:
    def __init__(
        self,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        notifier: Notifications,
        hooks: Hooks,
    ) -> None:
        self.repos = repos
        self.clock = clock
        self._settings = settings
        self.notifier = notifier
        self.hooks = hooks
        self._failures: dict[tuple[str, date, int | None], _Failure] = {}

    def run(self, trigger: Trigger) -> list[Action]:
        settings = self._settings()
        now = self.clock.now()
        state = load_state(
            self.repos, settings, trigger, now=now, tz=self.clock.tz(),
            handoff_dialog_open=self.hooks.handoff_dialog_open(),
            focus_dialog_open=self.hooks.focus_dialog_open(),
        )  # fmt: skip
        actions = evaluate(now, state)
        ready: list[tuple[int, str, str]] = []
        waiting: list[tuple[int, str]] = []
        for action in actions:
            try:
                self._apply(action, settings, ready, waiting)
            except Exception as exc:  # one failed job must not stop the others
                log_event("scheduler_action_failed", logging.WARNING,
                          kind=type(action).__name__, error=type(exc).__name__)  # fmt: skip
        if ready:
            self.notifier.prompts_ready(ready)
        if waiting:
            self.notifier.reminders(waiting)  # one notification for every prompt still waiting
        if actions:
            log_event("scheduler_ran", kind=trigger, actions=len(actions))
            self.hooks.state_changed()
        return actions

    def _apply(
        self,
        action: Action,
        settings: Settings,
        ready: list[tuple[int, str, str]],
        waiting: list[tuple[int, str]],
    ) -> None:
        repos = self.repos
        match action:
            case Rollover(week=week, carry=carry, shelve=shelve, expire=expire):
                improve.apply_rollover(repos, week, improve.RolloverPlan(carry, shelve, expire))
            case ShowFocusDialog(week=week):
                if weekly.note_focus_shown(repos, week):
                    self.notifier.focus_prompt(week)
                self.hooks.show_focus_dialog(week)
            case EnterPickMode(week=week):
                weekly.enter_pick_mode(repos, settings, week)
                self.notifier.pick_mode(week)
            case PreparePacket(kind=kind, week=week, blog_id=blog_id):
                made = self._prepare(kind, week, blog_id, settings)
                if made is not None:
                    ready.append((made.id, made.kind, weekly.handoff_title(repos, made)))
            case ShowLoginQuestions():
                self.hooks.show_login_questions()
            case RemindHandoff(handoff_id=hid):
                repos.handoffs.record_reminder(hid)
                h = repos.handoffs.get(hid)
                if h is not None:
                    waiting.append((hid, weekly.handoff_title(repos, h)))
            case NotifyNoFocus(week=week):
                weekly.note_no_focus(repos, week)
                self.notifier.no_focus(week)

    def _prepare(
        self, kind: str, week: date, blog_id: int | None, settings: Settings
    ) -> Handoff | None:
        """Build a packet; after a failure wait longer each time, and tell the owner once."""
        key = (kind, week, blog_id)
        now = self.clock.now()
        failure = self._failures.get(key)
        if failure is not None and now < failure.retry_at:
            return None
        try:
            made = weekly.prepare_packet(self.repos, settings, self.clock, kind, week, blog_id)
        except Exception as exc:
            count = failure.count + 1 if failure is not None else 1
            wait = min(RETRY_FIRST * 2 ** (count - 1), RETRY_LONGEST)
            self._failures[key] = _Failure(count, now + wait)
            log_event("prepare_packet_failed", logging.WARNING, kind=kind,
                      error=type(exc).__name__, attempts=count)  # fmt: skip
            if count == TELL_OWNER_AFTER:
                self.notifier.prepare_failed(week)
            return None
        self._failures.pop(key, None)
        return made


class Runs(Protocol):
    def run(self, trigger: Trigger) -> list[Action]: ...


class SchedulerRunner(QObject):
    ran = Signal()

    def __init__(
        self,
        executor: Runs,
        clock: Clock,
        *,
        interval_ms: int = TICK_MS,
        listen_for_sleep: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.executor = executor
        self.clock = clock
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.tick)
        self._listen = listen_for_sleep
        self._last: datetime | None = None
        self._running = False

    def start(self) -> None:
        self._run("start")
        self.timer.start()
        if self._listen:
            # PySide6 takes the str from SLOT(); its stub wrongly asks for bytes.
            ok = QDBusConnection.systemBus().connect(  # type: ignore[call-overload]
                "org.freedesktop.login1", "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager", "PrepareForSleep",
                self, SLOT("on_prepare_for_sleep(bool)"),
            )  # fmt: skip
            if not ok:
                log_event("sleep_signal_unavailable", logging.WARNING)

    def stop(self) -> None:
        self.timer.stop()

    @Slot()
    def tick(self) -> None:
        now = self.clock.now()
        gap = elapsed(now, self._last) if self._last is not None else timedelta(0)
        self._run("wake" if gap > WAKE_GAP else "tick")

    def run_now(self) -> None:
        """Evaluate straight away, for example after the owner changed a setting."""
        self._run("tick")

    @Slot(bool)
    def on_prepare_for_sleep(self, sleeping: bool) -> None:
        if sleeping:
            log_event("sleep")
            return
        self._run("wake")

    def _run(self, trigger: Trigger) -> None:
        if self._running:
            return
        self._running = True
        self._last = self.clock.now()
        try:
            self.executor.run(trigger)
        except Exception as exc:  # never let one bad pass stop the timer
            log_event("scheduler_failed", logging.ERROR, error=type(exc).__name__)
        finally:
            self._running = False
        self.ran.emit()
