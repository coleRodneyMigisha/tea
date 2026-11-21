"""Snapshot states for the Settings screen and the checks dialog (M10)."""

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QApplication, QScrollArea

from tea import doctor
from tea.clock import Clock
from tea.db.repos import Repos
from tea.settings import Settings

INTERESTS = ["Small teams", "Open data", "Right to repair", "Remote work", "Climate"]
NOTES = "Short sentences. British spelling. I never open with a question."


def _settle() -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    for _ in range(3):
        app.processEvents()


def _scroll(window: Any, to: str | None, widget: Any = None) -> None:
    """Show the window, then scroll to the bottom or to bring `widget` into view."""
    window.show()
    _settle()
    area = window.settings_screen.findChild(QScrollArea, "FormScroll")
    if to == "end":
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum())
    elif to == "widget" and widget is not None:
        area.ensureWidgetVisible(widget, 0, 40)
    _settle()


def _build(settings: Settings, to: str | None = None, fill: Callable[[Any], Any] | None = None):  # type: ignore[no-untyped-def]
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.ui.main_window import MainWindow

        window = MainWindow(
            theme, settings, save_settings=lambda _s: None, remember_geometry=False, clock=clock
        )
        window.show_screen("settings")
        screen = window.settings_screen
        target = fill(screen) if fill is not None else None
        _scroll(window, to, target)
        return window

    return build


def _filled() -> Settings:
    return Settings(interests=INTERESTS, region="East Africa", style_notes=NOTES)


def _interest_problem(screen: Any) -> Any:
    screen.interests.entry.setText("climate")
    screen.interests.entry.returnPressed.emit()
    return screen.interests


def _url_problem(screen: Any) -> Any:
    screen.claude_url.setText("http://claude.ai/new")
    screen.claude_url.editingFinished.emit()
    return screen.claude_url_error


def _checks(theme: Any, repos: Repos, clock: Clock) -> Any:
    from tea.ui import strings
    from tea.ui.widgets.report_dialog import ReportDialog

    probes = doctor.Probes(tray=lambda: True, notifications=lambda: False)
    return ReportDialog(
        theme, strings.SETTINGS_CHECKS_TITLE, doctor.report(doctor.run_checks(probes))
    )


def register_all(register: Callable[[str, str, Any], None], state: Callable[..., Any]) -> None:
    name = "settings"
    register(name, "empty", state(name, build=_build(Settings())))  # replaces the M3 title only
    register(name, "filled", state(name, build=_build(_filled(), "widget", lambda s: s.claude_url)))
    register(name, "interest_error", state(name, build=_build(_filled(), None, _interest_problem)))
    register(name, "url_error", state(name, build=_build(_filled(), "widget", _url_problem)))
    register(name, "bottom", state(name, build=_build(_filled(), "end")))
    register(name, "paused", state(name, build=_build(Settings(pause_automation=True), "end")))
    register("report_dialog", "checks", state("report_dialog", build=_checks))
