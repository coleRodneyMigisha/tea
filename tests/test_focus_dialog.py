"""Focus dialog (UI_DESIGN 4, focus dialog)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.focus_dialog import FocusDialog


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


def make(qtbot: QtBot, theme: Theme, **kw: object) -> FocusDialog:
    d = FocusDialog(theme, **kw)  # type: ignore[arg-type]
    qtbot.addWidget(d)
    d.show()
    return d


def test_layout_and_copy(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme)
    assert d.title.text() == strings.FOCUS_TITLE and d.windowTitle() == strings.FOCUS_TITLE
    assert d.hint.text() == strings.FOCUS_HINT
    assert not d.carried_line.isVisible()
    assert d.width() == theme.size("dialog_width")
    assert (d.save_button.text(), d.later_button.text()) == (
        strings.FOCUS_SAVE,
        strings.FOCUS_LATER,
    )
    assert not d.save_button.isEnabled()
    assert not d.isModal()


def test_carried_line(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme, carried=True)
    assert d.carried_line.isVisible() and d.carried_line.text() == strings.FOCUS_CARRIED


def test_save_emits_stripped_text(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme)
    d.editor.setPlainText("   ")
    assert not d.save_button.isEnabled()
    d.editor.setPlainText("  Small teams ship faster \n")
    with qtbot.waitSignal(d.focus_saved) as sig:
        d.save_button.click()
    assert sig.args == ["Small teams ship faster"]
    assert d.result() == QDialog.DialogCode.Accepted


def test_not_now_rejects(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme)
    with qtbot.waitSignal(d.dismissed):
        d.later_button.click()
    assert d.result() == QDialog.DialogCode.Rejected


def test_escape_is_not_now(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme)
    with qtbot.waitSignal(d.dismissed):
        qtbot.keyClick(d.editor, Qt.Key.Key_Escape)


def test_ctrl_return_saves(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme)
    d.editor.setPlainText("Focus")
    with qtbot.waitSignal(d.focus_saved):
        qtbot.keyClick(d.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)


def test_prefilled(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme, current="Old focus")
    assert d.editor.toPlainText() == "Old focus" and d.save_button.isEnabled()


def test_editor_is_keyboard_first(qtbot: QtBot, theme: Theme) -> None:
    d = make(qtbot, theme)
    assert d.editor.font().family() == theme.font("reading", "title_s").family()
    assert d.editor.font().pixelSize() == theme.type_px("title_s")
    assert d.editor.accessibleName() == strings.FOCUS_TITLE
    assert d.editor.tabChangesFocus()
