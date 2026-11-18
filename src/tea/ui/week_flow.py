"""This week controller: the focus dialog, the screen's view, and the scheduler's UI hooks.

The scheduler pushes the focus dialog; "Not now" on a pushed dialog starts the dismissal
pause. The owner's own "Set focus" or "Edit focus" never does. When the focus dialog and
the login questions are both due, the questions wait until the dialog closes.
"""

import logging
from collections.abc import Callable
from datetime import date
from typing import Protocol

from PySide6.QtCore import QObject, Signal

from tea.clock import Clock
from tea.db.repos import Repos
from tea.domain import weekly
from tea.domain.weeks import week_start
from tea.logging_setup import log_event
from tea.settings import Settings
from tea.ui.screens.this_week import ThisWeekScreen
from tea.ui.theme import Theme
from tea.ui.week_state import week_view
from tea.ui.widgets.focus_dialog import FocusDialog
from tea.ui.widgets.why_dialog import WhyDialog


class LoginStarter(Protocol):
    def on_app_start(self) -> bool: ...


class WeekFlow(QObject):
    focus_saved = Signal()
    prompt_rebuilt = Signal(int)  # a hand-off prepared at once because the focus changed
    open_handoff = Signal(int)
    open_draft = Signal(int)
    answer_requested = Signal()
    preview_requested = Signal()

    def __init__(
        self,
        theme: Theme,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        screen: ThisWeekScreen,
        login: LoginStarter,
        *,
        reduce_motion: bool | None = None,
    ) -> None:
        super().__init__()
        self.theme = theme
        self.repos = repos
        self.clock = clock
        self._settings = settings
        self.screen = screen
        self.login = login
        self.dialog: FocusDialog | None = None
        self.why_dialog: WhyDialog | None = None
        self.handoff_open: Callable[[], bool] = lambda: False  # set by the app (HandoffFlow)
        self._login_waiting = False
        if reduce_motion is not None:
            screen.ring.reduce_motion = reduce_motion
        screen.set_focus_requested.connect(self.edit_focus)
        screen.open_handoff_requested.connect(self.open_handoff)
        screen.open_draft_requested.connect(self.open_draft)
        screen.answer_requested.connect(self.answer_requested)
        screen.preview_requested.connect(self.preview_requested)
        screen.why_requested.connect(self.show_why_dialog)
        self.refresh()

    # Scheduler hooks

    def show_focus_dialog(self, week: date, *, owner: bool = False) -> None:
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        w = self.repos.weeks.get(week)
        current = w.focus_text or "" if w is not None else ""
        carried = any(
            b.status == "ready" and b.carried_weeks >= 1
            for b in self.repos.blogs.list(origin="weekly")
        )
        dialog = FocusDialog(self.theme, current=current, carried=carried)
        dialog.focus_saved.connect(lambda text: self._save(week, text))
        dialog.dismissed.connect(lambda: self._dismissed(week, owner))
        dialog.finished.connect(self._closed)
        self.dialog = dialog
        log_event("focus_dialog_shown", owner=owner)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def show_login_questions(self) -> None:
        if self.dialog is not None:
            self._login_waiting = True
            return
        self.login.on_app_start()

    def focus_dialog_open(self) -> bool:
        return self.dialog is not None

    def handoff_dialog_open(self) -> bool:
        return self.handoff_open()

    def state_changed(self) -> None:
        self.refresh()

    # Owner actions

    def edit_focus(self) -> None:
        self.show_focus_dialog(week_start(self.clock.now()), owner=True)

    def refresh(self) -> None:
        self.screen.set_view(week_view(self.repos, self._settings(), self.clock.now()))

    def show_why_dialog(self) -> None:
        view = week_view(self.repos, self._settings(), self.clock.now())
        if not view.focus or view.topic_origin != "auto_trending":
            return

        if self.why_dialog is not None:
            self.why_dialog.raise_()
            self.why_dialog.activateWindow()
            return

        dialog = WhyDialog(
            self.theme,
            topic=view.focus,
            candidates=view.trend_candidates,
        )
        dialog.finished.connect(self._why_closed)
        self.why_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _why_closed(self, _result: int) -> None:
        dialog, self.why_dialog = self.why_dialog, None
        if dialog is not None:
            dialog.deleteLater()

    def _save(self, week: date, text: str) -> None:
        try:
            rebuilt = weekly.save_focus(self.repos, self._settings(), self.clock, week, text)
        except Exception as exc:  # the focus is kept; the scheduler retries the prompt
            log_event("focus_rebuild_failed", logging.WARNING, error=type(exc).__name__)
            rebuilt = None
        log_event("focus_saved", rebuilt=rebuilt is not None)
        if rebuilt is not None:
            self.prompt_rebuilt.emit(rebuilt.id)
        self.refresh()
        self.focus_saved.emit()

    def _dismissed(self, week: date, owner: bool) -> None:
        if owner:
            return
        minutes = self._settings().dismiss_pause_minutes
        weekly.dismiss_focus(self.repos, self.clock, week, minutes=minutes)
        log_event("focus_dialog_dismissed")

    def _closed(self, _result: int) -> None:
        dialog, self.dialog = self.dialog, None
        if dialog is not None:
            dialog.deleteLater()
        if self._login_waiting:
            self._login_waiting = False
            self.login.on_app_start()
