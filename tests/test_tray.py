"""Tray icon and menu (UI_DESIGN section 5)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.settings import Settings
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.tray import Tray

KAMPALA = ZoneInfo("Africa/Kampala")


def _tray(qapp: QApplication, settings: Settings | None = None) -> Tray:
    clock = FakeClock(datetime(2026, 11, 11, 10, 0, tzinfo=KAMPALA))  # Wednesday
    return Tray(Theme(qapp, appearance="light", scale=1.0), settings or Settings(), clock)


def test_menu_items_in_order(qapp: QApplication) -> None:
    tray = _tray(qapp)
    texts = [a.text() for a in tray.menu.actions() if not a.isSeparator()]
    assert texts == [
        strings.TRAY_OPEN,
        strings.TRAY_ANSWER,
        strings.TRAY_NEW_BLOG,
        strings.TRAY_RESUME,
        strings.TRAY_OPEN_HANDOFF,
        "Prompt due Fri 6:00 pm",
        strings.TRAY_PAUSE,
        strings.TRAY_QUIT,
    ]
    assert not tray.open_handoff_action.isVisible()
    assert not tray.resume_action.isVisible()
    assert not tray.due_action.isEnabled()
    assert tray.pause_action.isCheckable()


def test_due_line_after_this_weeks_prompt_points_to_next_week(qapp: QApplication) -> None:
    tray = _tray(qapp)
    tray.clock.set(datetime(2026, 11, 13, 19, 0, tzinfo=KAMPALA))  # after Friday 18:00
    tray.refresh_due()
    assert tray.due_action.text() == "Prompt due Fri 6:00 pm"
    tray.clock.set(datetime(2026, 11, 13, 9, 30, tzinfo=KAMPALA))
    tray.refresh_due()
    assert tray.due_action.text() == "Prompt due today 6:00 pm"


def test_signals_fire(qapp: QApplication, qtbot: QtBot) -> None:
    tray = _tray(qapp)
    with qtbot.waitSignal(tray.open_requested):
        tray.open_action.trigger()
    with qtbot.waitSignal(tray.new_blog_requested):
        tray.new_blog_action.trigger()
    with qtbot.waitSignal(tray.quit_requested):
        tray.quit_action.trigger()
    with qtbot.waitSignal(tray.pause_toggled) as blocker:
        tray.pause_action.trigger()
    assert blocker.args == [True]


def test_attention_icon_switch(qapp: QApplication) -> None:
    tray = _tray(qapp)
    normal = tray.icon().cacheKey()
    tray.set_attention(True)
    assert tray.icon().cacheKey() != normal
    assert tray.attention
    tray.set_attention(False)
    assert not tray.attention


def test_pause_state_syncs(qapp: QApplication) -> None:
    tray = _tray(qapp, Settings(pause_automation=True))
    assert tray.pause_action.isChecked()
    tray.set_paused(False)
    assert not tray.pause_action.isChecked()
