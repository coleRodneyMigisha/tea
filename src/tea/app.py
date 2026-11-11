"""QApplication setup, wiring, tray and lifecycle."""

import logging
import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tea import config
from tea import settings as settings_mod
from tea.clock import SystemClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.domain.questions import seed_bank
from tea.logging_setup import log_event, setup_logging
from tea.settings import Settings, SettingsError
from tea.single_instance import SingleInstance
from tea.ui import strings
from tea.ui.login_flow import LoginFlow
from tea.ui.main_window import MainWindow
from tea.ui.theme import Theme, load_fonts
from tea.ui.tray import Tray

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
        self, app: QApplication, instance: SingleInstance, tray_available: bool | None = None
    ) -> None:
        self.app = app
        self.instance = instance
        self.clock = SystemClock()
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
        self.tray: Tray | None = None
        if tray_available is None:
            tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if tray_available:
            self._build_tray(settings)
        else:
            log_event("tray_unavailable", logging.WARNING)
        instance.message.connect(self._on_message)

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

        Then the login questions (D12: they fire when the app starts), or the manual session
        for `tea login-questions`.
        """
        if not background:
            self.window.show()
        if ask_questions:
            self.login.ask_now()
        else:
            self.login.on_app_start()

    def quit(self) -> None:
        self.window.save_geometry()
        self.app.quit()

    def close(self) -> None:
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
