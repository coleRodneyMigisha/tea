"""Main window shell: rail, empty screens, footer, shortcuts, geometry, close-to-tray."""

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from tea import config
from tea.settings import Settings
from tea.ui import strings
from tea.ui.main_window import SCREEN_NAMES, MainWindow
from tea.ui.theme import Theme


@pytest.fixture
def saved() -> list[Settings]:
    return []


@pytest.fixture
def window(qapp: QApplication, qtbot: QtBot, saved: list[Settings]) -> MainWindow:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    win = MainWindow(theme, Settings(), save_settings=saved.append)
    qtbot.addWidget(win)
    win.show()
    return win


def _labels(win: MainWindow) -> list[str]:
    return [label.text() for label in win.findChildren(QLabel) if label.isVisible()]


def test_rail_has_four_items_in_order(window: MainWindow) -> None:
    texts = [b.text() for b in window.nav_buttons]
    assert texts == [strings.NAV_WEEK, strings.NAV_NEW, strings.NAV_DRAFTS, strings.NAV_SETTINGS]
    assert all(b.property("nav") is True for b in window.nav_buttons)
    assert all(not b.icon().isNull() for b in window.nav_buttons)
    assert SCREEN_NAMES == ("this_week", "new_blog", "drafts", "settings")


def test_starts_on_this_week_with_empty_focus_copy(window: MainWindow) -> None:
    assert window.current_screen() == "this_week"
    assert window.nav_buttons[0].isChecked()
    assert strings.EMPTY_FOCUS in _labels(window)


def test_empty_focus_uses_muted_display_style(window: MainWindow) -> None:
    label = next(lb for lb in window.findChildren(QLabel) if lb.text() == strings.EMPTY_FOCUS)
    assert label.property("role") == "display"
    assert label.property("muted") is True


def test_drafts_screen_shows_empty_state(window: MainWindow) -> None:
    window.show_screen("drafts")
    assert strings.EMPTY_DRAFTS in _labels(window)
    assert window.nav_buttons[2].isChecked()


def test_clicking_nav_switches_screen(window: MainWindow, qtbot: QtBot) -> None:
    qtbot.mouseClick(window.nav_buttons[3], Qt.MouseButton.LeftButton)
    assert window.current_screen() == "settings"


@pytest.mark.parametrize(
    ("keys", "screen"),
    [("Ctrl+1", "this_week"), ("Ctrl+2", "new_blog"), ("Ctrl+3", "drafts"),
     ("Ctrl+4", "settings"), ("Ctrl+N", "new_blog")],
)  # fmt: skip
def test_shortcuts_switch_screens(window: MainWindow, keys: str, screen: str) -> None:
    window.show_screen("settings" if screen != "settings" else "drafts")
    assert window.trigger_shortcut(keys)
    assert window.current_screen() == screen


def test_footer_toggles_pause_and_saves(window: MainWindow, qtbot: QtBot, saved: list) -> None:
    footer = window.findChild(QPushButton, "RailFooter")
    assert footer is not None
    assert footer.text() == strings.AUTOMATION_ON
    qtbot.mouseClick(footer, Qt.MouseButton.LeftButton)
    assert footer.text() == strings.AUTOMATION_PAUSED
    assert footer.property("state") == "paused"
    assert not footer.icon().isNull()
    assert saved[-1].pause_automation is True
    qtbot.mouseClick(footer, Qt.MouseButton.LeftButton)
    assert footer.text() == strings.AUTOMATION_ON
    assert footer.icon().isNull()
    assert saved[-1].pause_automation is False


def test_pause_changed_signal_and_external_update(window: MainWindow, qtbot: QtBot) -> None:
    with qtbot.waitSignal(window.pause_changed) as blocker:
        window.set_paused(True)
    assert blocker.args == [True]
    footer = window.findChild(QPushButton, "RailFooter")
    assert footer is not None and footer.text() == strings.AUTOMATION_PAUSED


def test_default_and_minimum_size(window: MainWindow) -> None:
    assert window.minimumSize() == QSize(900, 600)
    assert window.size() == QSize(1120, 740)
    assert window.rail.width() == 208


def test_geometry_is_remembered(qapp: QApplication, qtbot: QtBot) -> None:
    # The offscreen screen is 800 x 600 and restoreGeometry clamps to it, so shrink the
    # window's minimum size with a 0.8 scale and use a size that fits.
    theme = Theme(qapp, appearance="light", scale=0.8)
    first = MainWindow(theme, Settings(), save_settings=lambda s: None)
    qtbot.addWidget(first)
    first.show()
    first.resize(760, 500)
    first.save_geometry()
    ini = config.state_dir() / "window.ini"
    assert ini.is_file()
    assert QSettings(str(ini), QSettings.Format.IniFormat).value("geometry") is not None
    second = MainWindow(theme, Settings(), save_settings=lambda s: None)
    qtbot.addWidget(second)
    second.show()
    assert second.size() == QSize(760, 500)


def test_close_hides_when_tray_keeps_app(window: MainWindow) -> None:
    window.set_hide_on_close(True)
    window.close()
    assert not window.isVisible()
    assert not window.closed_for_real


def test_bring_to_front_shows_hidden_window(window: MainWindow) -> None:
    window.hide()
    window.bring_to_front()
    assert window.isVisible()


def test_rebuilds_icons_when_theme_changes(window: MainWindow) -> None:
    before = window.nav_buttons[0].icon().cacheKey()
    window.theme.set_appearance("dark")
    assert window.nav_buttons[0].icon().cacheKey() != before


def test_state_dir_is_isolated(tmp_dirs: Path) -> None:
    assert str(config.state_dir()).startswith(str(tmp_dirs))
