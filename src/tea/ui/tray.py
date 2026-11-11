"""Tray icon and menu (UI_DESIGN 5). Works without a tray: the app checks availability."""

from datetime import datetime, tzinfo

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from tea.clock import Clock
from tea.domain.weeks import next_week_start, prompt_due, week_start
from tea.settings import Settings
from tea.ui import strings
from tea.ui.theme import Theme


def short_time(when: datetime) -> str:
    hour = when.hour % 12 or 12
    suffix = strings.AM if when.hour < 12 else strings.PM
    return f"{hour}:{when.minute:02d} {suffix}"


def due_text(now: datetime, settings: Settings, tz: tzinfo) -> str:
    """ "Prompt due Fri 6:00 pm" for the next prompt time at or after `now`."""
    due = prompt_due(week_start(now), settings, tz)
    if now >= due:
        due = prompt_due(next_week_start(week_start(now)), settings, tz)
    today = due.date() == now.date()
    day = strings.TRAY_DUE_TODAY if today else strings.WEEKDAY_SHORT[due.weekday()]
    return strings.TRAY_DUE.format(when=f"{day} {short_time(due)}")


class Tray(QSystemTrayIcon):
    open_requested = Signal()
    answer_requested = Signal()
    new_blog_requested = Signal()
    open_handoff_requested = Signal()
    pause_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(self, theme: Theme, settings: Settings, clock: Clock) -> None:
        super().__init__(theme.app_icon())
        self.theme = theme
        self.settings = settings
        self.clock = clock
        self.attention = False
        self.setToolTip(strings.TRAY_TOOLTIP)
        self.menu = QMenu()
        self.open_action = self.menu.addAction(strings.TRAY_OPEN)
        self.open_action.triggered.connect(self.open_requested)
        self.answer_action = self.menu.addAction(strings.TRAY_ANSWER)
        self.answer_action.triggered.connect(self.answer_requested)
        self.new_blog_action = self.menu.addAction(strings.TRAY_NEW_BLOG)
        self.new_blog_action.triggered.connect(self.new_blog_requested)
        self.open_handoff_action = self.menu.addAction(strings.TRAY_OPEN_HANDOFF)
        self.open_handoff_action.triggered.connect(self.open_handoff_requested)
        self.open_handoff_action.setVisible(False)  # shown when a hand-off waits (M7)
        self.menu.addSeparator()
        self.due_action = self.menu.addAction("")
        self.due_action.setEnabled(False)
        self.pause_action = self.menu.addAction(strings.TRAY_PAUSE)
        self.pause_action.setCheckable(True)
        self.pause_action.setChecked(settings.pause_automation)
        self.pause_action.toggled.connect(self.pause_toggled)
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction(strings.TRAY_QUIT)
        self.quit_action.triggered.connect(self.quit_requested)
        self.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.refresh_due)
        self.activated.connect(self._on_activated)
        self.refresh_due()

    def refresh_due(self) -> None:
        self.due_action.setText(due_text(self.clock.now(), self.settings, self.clock.tz()))

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.set_paused(settings.pause_automation)
        self.refresh_due()

    def set_paused(self, paused: bool) -> None:
        if self.pause_action.isChecked() != paused:
            self.pause_action.blockSignals(True)
            self.pause_action.setChecked(paused)
            self.pause_action.blockSignals(False)

    def set_attention(self, attention: bool) -> None:
        self.attention = attention
        self.setIcon(self.theme.app_icon(attention))

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_requested.emit()
