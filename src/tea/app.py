"""QApplication setup, wiring, tray and lifecycle."""

import logging
import sys
from datetime import date

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tea import config
from tea import settings as settings_mod
from tea.clock import Clock, SystemClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.domain.questions import seed_bank
from tea.domain.weekly import handoff_title
from tea.logging_setup import log_event, setup_logging
from tea.notify import DBusBackend, Notifier
from tea.scheduler_runner import Executor, SchedulerRunner
from tea.settings import Settings, SettingsError
from tea.single_instance import SingleInstance
from tea.ui import strings
from tea.ui.login_flow import LoginFlow
from tea.ui.main_window import MainWindow
from tea.ui.theme import Theme, load_fonts
from tea.ui.tray import Tray
from tea.ui.week_flow import WeekFlow
from tea.ui.widgets.answers_preview import AnswersPreview, preview_text

MSG_SHOW = "show"
MSG_QUESTIONS = "login-questions"


def _load_settings() -> Settings:
    try:
        return settings_mod.load()
    except SettingsError as exc:
        # Keep the broken file for the owner to fix; run on defaults (Settings screen in M10).
        log_event("settings_load_failed", logging.WARNING, error=type(exc).__name__)
        return Settings()


class TeaApp:
    """Holds the long-lived objects so Qt does not garbage-collect them."""

    def __init__(
        self,
        app: QApplication,
        instance: SingleInstance,
        tray_available: bool | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.app = app
        self.instance = instance
        self.clock: Clock = clock or SystemClock()
        settings = _load_settings()
        self.settings = settings
        self.conn = open_db(config.db_path())
        self.repos = Repos(self.conn, self.clock)
        seed_bank(self.repos)
        load_fonts()
        self.theme = Theme(app, settings.appearance)
        self.theme.apply()
        self.window = MainWindow(self.theme, settings, save_settings=self._save)
        self.login = LoginFlow(self.theme, self.repos, self.clock, lambda: self.settings)
        self.week = WeekFlow(
            self.theme, self.repos, self.clock, lambda: self.settings,
            self.window.week_screen, self.login,
        )  # fmt: skip
        self.preview: AnswersPreview | None = None
        backend = DBusBackend.create()
        self.notifier = Notifier(self.clock, backend, fallback=self._tray_message)
        if backend is not None:
            backend.action.connect(self.notifier.on_server_action)
        self.executor = Executor(
            self.repos, self.clock, lambda: self.settings, self.notifier, self.week
        )
        self.runner = SchedulerRunner(self.executor, self.clock)
        self._wire_week()
        self.tray: Tray | None = None
        if tray_available is None:
            tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if tray_available:
            self._build_tray(settings)
        else:
            log_event("tray_unavailable", logging.WARNING)
        instance.message.connect(self._on_message)

    def _wire_week(self) -> None:
        week, runner, notifier = self.week, self.runner, self.notifier
        runner.ran.connect(week.refresh)
        runner.ran.connect(self._refresh_tray)
        week.focus_saved.connect(runner.run_now)
        week.prompt_rebuilt.connect(self._announce_rebuilt)
        # M7 opens the hand-off dialog and the draft view; until then, the window.
        week.open_handoff.connect(lambda _hid: self.show_window())
        week.open_draft.connect(lambda _bid: self.show_window("drafts"))
        week.answer_requested.connect(self.login.ask_now)
        week.preview_requested.connect(self._show_preview)
        notifier.action_invoked.connect(self._on_notification_action)
        notifier.announced.connect(self._attention)
        self.window.pause_changed.connect(self._on_pause_changed)

    def _on_pause_changed(self, _paused: bool) -> None:
        self.week.refresh()
        self.runner.run_now()  # resuming runs the due jobs at once

    def _announce_rebuilt(self, handoff_id: int) -> None:
        h = self.repos.handoffs.get(handoff_id)
        if h is not None:
            self.notifier.prompts_ready([(h.id, h.kind, handoff_title(self.repos, h))])
        self._refresh_tray()

    def _on_notification_action(self, target: str) -> None:
        kind, _, value = target.partition(":")
        if kind == "focus":
            self.show_window("this_week")
            self.week.show_focus_dialog(date.fromisoformat(value), owner=True)
        else:
            self.show_window("this_week")

    def _show_preview(self) -> None:
        dialog = AnswersPreview(self.theme, preview_text(self.repos, self.clock, self.settings))
        self.preview = dialog
        dialog.show()

    def _tray_message(self, title: str, body: str) -> None:
        if self.tray is not None:
            self.tray.showMessage(title, body)
        else:
            log_event("notification_dropped", logging.WARNING)

    def _attention(self) -> None:
        if self.tray is not None and not self.window.isActiveWindow():
            self.tray.set_attention(True)

    def _refresh_tray(self) -> None:
        if self.tray is not None:
            waiting = bool(self.repos.handoffs.list(open_only=True))
            self.tray.open_handoff_action.setVisible(waiting)
            self.tray.refresh_due()

    def _build_tray(self, settings: Settings) -> None:
        tray = Tray(self.theme, settings, self.clock)
        tray.open_requested.connect(self.show_window)
        tray.answer_requested.connect(self.login.ask_now)
        self.login.nothing_to_ask.connect(
            lambda: tray.showMessage(strings.APP_NAME, strings.NO_QUESTIONS_LEFT)
        )
        tray.new_blog_requested.connect(lambda: self.show_window("new_blog"))
        tray.pause_toggled.connect(self.window.set_paused)
        tray.quit_requested.connect(self.quit)
        tray.open_handoff_requested.connect(lambda: self.show_window("this_week"))
        tray.messageClicked.connect(self.notifier.on_fallback_clicked)
        self.window.pause_changed.connect(tray.set_paused)
        tray.show()
        self.tray = tray
        self.window.set_hide_on_close(True)
        self.app.setQuitOnLastWindowClosed(False)

    def _save(self, settings: Settings) -> None:
        self.settings = settings
        try:
            settings_mod.save(settings)
        except OSError as exc:
            log_event("settings_save_failed", logging.WARNING, error=type(exc).__name__)
        if self.tray is not None:
            self.tray.set_settings(settings)
        self.week.refresh()

    def _on_message(self, message: str) -> None:
        known = message in (MSG_SHOW, MSG_QUESTIONS)
        log_event("ipc_message", kind=message if known else "other")
        if message == MSG_SHOW:
            self.show_window()
        elif message == MSG_QUESTIONS:
            self.login.ask_now()

    def show_window(self, screen: str | None = None) -> None:
        if screen:
            self.window.show_screen(screen)
        self.window.bring_to_front()
        if self.tray is not None:
            self.tray.set_attention(False)

    def start(self, background: bool, ask_questions: bool = False) -> None:
        """Show the window, or stay in the tray for `--background` (autostart).

        Then the manual session for `tea login-questions`, and the scheduler, whose first
        pass shows the focus dialog and the login questions when they are due.
        """
        if not background:
            self.window.show()
        if ask_questions:
            self.login.ask_now()
        # The first evaluate runs the start jobs, login questions included (D12).
        self.runner.start()

    def quit(self) -> None:
        self.window.save_geometry()
        self.app.quit()

    def close(self) -> None:
        self.runner.stop()
        self.conn.close()


def run_app(background: bool = False, ask_questions: bool = False) -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(config.APP_NAME)
    app.setDesktopFileName(config.APP_NAME)
    instance = SingleInstance(config.runtime_dir())
    if not instance.acquire():
        # Another tea is running: ask it to show its window, then leave.
        if instance.notify_running(MSG_QUESTIONS if ask_questions else MSG_SHOW):
            return 0
        print(strings.INSTANCE_NOT_RESPONDING, file=sys.stderr)
        return 1
    setup_logging()
    if instance.listen_error:
        log_event("ipc_listen_failed", logging.WARNING, error=instance.listen_error)
    log_event("app_start", background=background)
    tea = TeaApp(app, instance)
    app.setWindowIcon(tea.theme.app_icon())
    tea.start(background, ask_questions=ask_questions)
    try:
        return app.exec()
    finally:
        tea.window.save_geometry()
        tea.close()
        instance.release()
        log_event("app_exit")
