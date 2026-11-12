"""Question popup (pytest-qt): keyboard-only completion, Back, Later, Skip, auto-close."""

from collections.abc import Callable

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from tea.db.rows import Question
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.question_popup import DONE, LATER, TIMEOUT, QuestionPopup

Saved = list[tuple[int, str, bool]]
CTRL = Qt.KeyboardModifier.ControlModifier


def _q(qid: int, kind: str = "text", options: list[str] | None = None) -> Question:
    return Question(
        id=qid, text=f"Question number {qid}?", kind=kind, options=options or [],
        category="voice", origin="bank", week_start=None, blog_id=None, active=True,
        asked_count=0, last_asked_at=None, template_key=None, bank_key=None,
    )  # fmt: skip


CHOICE = _q(2, "choice", ["Always", "Sometimes", "Never"])
SCALE = _q(3, "scale", ["Short", "Long"])


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


@pytest.fixture
def make(qtbot: QtBot, theme: Theme) -> Callable[..., tuple[QuestionPopup, Saved, list[str]]]:
    def build(
        questions: list[Question], *, login: bool = False, timeout_ms: int = 90_000
    ) -> tuple[QuestionPopup, Saved, list[str]]:
        saved: Saved = []
        ends: list[str] = []
        popup = QuestionPopup(
            theme,
            questions,
            lambda q, text, skipped: saved.append((q.id, text, skipped)),
            login=login,
            reduce_motion=True,
            timeout_ms=timeout_ms,
        )
        popup.finished.connect(ends.append)
        qtbot.addWidget(popup)
        popup.show()
        qtbot.waitExposed(popup)
        if not login:  # the owner started it, so it takes focus
            qtbot.waitUntil(lambda: QApplication.activeWindow() is popup)
        return popup, saved, ends

    return build


def _focus(popup: QuestionPopup) -> QWidget:
    w = popup.focusWidget()
    assert w is not None
    return w


def _ctrl_return(qtbot: QtBot, popup: QuestionPopup) -> None:
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Return, CTRL)


def test_text_question_keyboard_only(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([_q(1)])
    popup.activateWindow()
    qtbot.keyClicks(_focus(popup), "plain and dry")
    _ctrl_return(qtbot, popup)
    assert saved == [(1, "plain and dry", False)]
    assert ends == [DONE]
    assert not popup.isVisible()


def test_text_input_is_multiline_and_tab_leaves_it(
    qtbot: QtBot, make: Callable[..., tuple]
) -> None:
    popup, saved, _ = make([_q(1)])
    edit = popup.text_edit
    qtbot.keyClicks(edit, "one")
    qtbot.keyClick(edit, Qt.Key.Key_Return)
    qtbot.keyClicks(edit, "two")
    assert edit.toPlainText() == "one\ntwo"
    assert edit.tabChangesFocus()
    rows3 = edit.height()
    for _ in range(8):
        qtbot.keyClick(edit, Qt.Key.Key_Return)
    assert edit.height() > rows3
    assert edit.height() <= popup.rows_height(6)
    assert saved == []


def test_choice_question_keyboard_only(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([CHOICE])
    first = _focus(popup)
    assert first is popup.choice_buttons[0]
    qtbot.keyClick(first, Qt.Key.Key_Space)
    assert popup.choice_buttons[0].isChecked()
    qtbot.keyClick(first, Qt.Key.Key_Down)
    assert popup.choice_buttons[1].isChecked()
    _ctrl_return(qtbot, popup)
    assert saved == [(2, "Sometimes", False)]
    assert ends == [DONE]


def test_scale_question_keyboard_only(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([SCALE])
    first = _focus(popup)
    assert first is popup.scale_buttons[0]
    assert len(popup.scale_buttons) == 5
    qtbot.keyClick(first, Qt.Key.Key_Space)
    assert popup.scale_buttons[0].isChecked()
    # Arrow keys move inside the segmented control; Tab leaves it (an exclusive group).
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Right)
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Right)
    assert popup.scale_buttons[2].isChecked()
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Tab)
    assert _focus(popup) not in popup.scale_buttons
    _ctrl_return(qtbot, popup)
    assert saved == [(3, "3", False)]
    assert ends == [DONE]


def test_scale_shows_low_and_high_labels(make: Callable[..., tuple]) -> None:
    popup, _, _ = make([SCALE])
    assert popup.scale_labels == ("Short", "Long")


def test_whole_session_by_keyboard(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([_q(1), CHOICE, SCALE])
    assert popup.progress_text() == "Question 1 of 3"
    qtbot.keyClicks(_focus(popup), "a")
    _ctrl_return(qtbot, popup)
    assert popup.progress_text() == "Question 2 of 3"
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Space)
    _ctrl_return(qtbot, popup)
    assert popup.next_button.text() == strings.POPUP_DONE
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Space)
    _ctrl_return(qtbot, popup)
    assert saved == [(1, "a", False), (2, "Always", False), (3, "1", False)]
    assert ends == [DONE]


def test_next_needs_an_answer(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, _ = make([_q(1), CHOICE])
    assert not popup.next_button.isEnabled()
    qtbot.keyClicks(_focus(popup), "   ")
    assert not popup.next_button.isEnabled()
    _ctrl_return(qtbot, popup)
    assert saved == [] and popup.index == 0
    qtbot.keyClicks(_focus(popup), "x")
    assert popup.next_button.isEnabled()
    assert popup.next_button.text() == strings.POPUP_NEXT


def test_back_hidden_on_first_and_keeps_answers(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, _ = make([_q(1), CHOICE, SCALE])
    assert popup.back_button.isHidden()
    qtbot.keyClicks(_focus(popup), "first answer")
    _ctrl_return(qtbot, popup)
    popup.choice_buttons[2].click()
    assert not popup.back_button.isHidden()
    qtbot.mouseClick(popup.back_button, Qt.MouseButton.LeftButton)
    assert popup.index == 0
    assert popup.text_edit.toPlainText() == "first answer"
    _ctrl_return(qtbot, popup)  # unchanged: not saved twice
    assert popup.choice_buttons[2].isChecked()  # the unsaved choice came back too
    assert saved == [(1, "first answer", False)]
    qtbot.mouseClick(popup.back_button, Qt.MouseButton.LeftButton)
    popup.text_edit.setPlainText("changed")
    _ctrl_return(qtbot, popup)
    assert saved == [(1, "first answer", False), (1, "changed", False)]


def test_skip_records_skipped(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([_q(1), CHOICE])
    qtbot.keyClicks(_focus(popup), "not this")
    qtbot.mouseClick(popup.skip_button, Qt.MouseButton.LeftButton)
    assert saved == [(1, "", True)]
    assert popup.index == 1
    qtbot.mouseClick(popup.skip_button, Qt.MouseButton.LeftButton)
    assert saved == [(1, "", True), (2, "", True)]
    assert ends == [DONE]


def test_escape_is_later_and_keeps_progress(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([_q(1), _q(2)])
    qtbot.keyClicks(_focus(popup), "kept")
    _ctrl_return(qtbot, popup)
    qtbot.keyClicks(_focus(popup), "typed, not sent")
    qtbot.keyClick(_focus(popup), Qt.Key.Key_Escape)
    assert saved == [(1, "kept", False)]  # Later is not a skip
    assert ends == [LATER]
    assert not popup.isVisible()


def test_later_button(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([_q(1)])
    qtbot.mouseClick(popup.later_button, Qt.MouseButton.LeftButton)
    assert saved == [] and ends == [LATER]


def test_login_popup_auto_closes_as_timeout(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, saved, ends = make([_q(1)], login=True, timeout_ms=60)
    qtbot.waitUntil(lambda: ends == [TIMEOUT], timeout=2000)
    assert saved == [] and not popup.isVisible()


def test_interaction_restarts_the_timer(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    popup, _, ends = make([_q(1)], login=True, timeout_ms=300)
    for _ in range(4):
        qtbot.wait(150)
        qtbot.keyClicks(popup.text_edit, "x")
    assert ends == []
    qtbot.waitUntil(lambda: ends == [TIMEOUT], timeout=2000)


def test_scope_popup_never_times_out(qtbot: QtBot, make: Callable[..., tuple]) -> None:
    _, _, ends = make([_q(1)], login=False, timeout_ms=30)
    qtbot.wait(150)
    assert ends == []


def test_window_flags_and_activation(make: Callable[..., tuple]) -> None:
    login, _, _ = make([_q(1)], login=True)
    flags = login.windowFlags()
    for flag in (
        Qt.WindowType.Tool,
        Qt.WindowType.FramelessWindowHint,
        Qt.WindowType.WindowStaysOnTopHint,
    ):
        assert flags & flag
    assert login.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert login.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    scope, _, _ = make([_q(1)], login=False)
    assert not scope.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_card_size_follows_tokens(theme: Theme, make: Callable[..., tuple]) -> None:
    popup, _, _ = make([_q(1)])
    assert popup.card.objectName() == "PopupCard"
    assert popup.card.width() == theme.size("width")
    assert theme.size("popup_min_height") <= popup.card.height() <= theme.size("popup_max_height")


def test_entry_animation_runs_160ms(qtbot: QtBot, theme: Theme) -> None:
    popup = QuestionPopup(theme, [_q(1)], lambda *_: None, login=True, reduce_motion=False)
    qtbot.addWidget(popup)
    popup.show()
    assert popup.entry is not None and popup.entry.duration() == 160
    qtbot.waitUntil(lambda: popup.rise == 0, timeout=2000)
    qtbot.waitUntil(lambda: popup.entry is not None and popup.entry.state().name == "Stopped")
    assert popup.card.graphicsEffect() is not None  # the shadow stays; the fade effect is gone


def test_accessible_names(make: Callable[..., tuple]) -> None:
    popup, _, _ = make([_q(1)])
    assert popup.text_edit.accessibleName() == "Question number 1?"
    assert popup.later_button.text() == strings.POPUP_LATER


# Resuming a scope session (M8)


def _resumed(
    qtbot: QtBot, theme: Theme, start: int, answered: dict[int, tuple[str, bool]]
) -> tuple[QuestionPopup, Saved]:
    saved: Saved = []
    popup = QuestionPopup(
        theme, [_q(1), CHOICE, _q(4), SCALE],
        lambda q, text, skipped: saved.append((q.id, text, skipped)),
        login=False, reduce_motion=True, start=start, answered=answered,
    )  # fmt: skip
    qtbot.addWidget(popup)
    popup.show()
    qtbot.waitExposed(popup)
    return popup, saved


def test_resume_opens_at_start_with_real_numbering(qtbot: QtBot, theme: Theme) -> None:
    popup, _ = _resumed(qtbot, theme, 2, {1: ("first", False), 2: ("", True)})
    assert popup.index == 2
    assert popup.current.id == 4
    assert popup.progress_text() == "Question 3 of 4"
    assert not popup.back_button.isHidden()


def test_back_after_resume_shows_stored_answers(qtbot: QtBot, theme: Theme) -> None:
    popup, saved = _resumed(qtbot, theme, 2, {1: ("first", False), 2: ("Never", False)})
    popup.back_button.click()
    assert popup.choice_buttons[2].isChecked()
    popup.back_button.click()
    assert popup.text_edit.toPlainText() == "first"
    popup.next_button.click()  # unchanged: not saved again
    popup.next_button.click()
    assert saved == []
    assert popup.current.id == 4


def test_changed_answer_after_resume_is_saved(qtbot: QtBot, theme: Theme) -> None:
    popup, saved = _resumed(qtbot, theme, 1, {1: ("first", False)})
    popup.back_button.click()
    popup.text_edit.setPlainText("better")
    popup.next_button.click()
    assert saved == [(1, "better", False)]


def test_start_past_the_end_is_clamped(qtbot: QtBot, theme: Theme) -> None:
    popup, _ = _resumed(qtbot, theme, 9, {})
    assert popup.index == 3
