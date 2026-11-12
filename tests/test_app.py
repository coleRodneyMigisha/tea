"""TeaApp wiring: tray or no tray, --background, IPC show, pause sync, quit."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea import settings as settings_mod
from tea.app import MSG_QUESTIONS, TeaApp
from tea.clock import FakeClock
from tea.single_instance import SingleInstance
from tea.ui.widgets.focus_dialog import FocusDialog
from tea.ui.widgets.question_popup import QuestionPopup


@pytest.fixture
def instance(tmp_path: Path) -> Iterator[SingleInstance]:
    inst = SingleInstance(tmp_path / "run")
    assert inst.acquire()
    yield inst
    inst.release()


@pytest.fixture(autouse=True)
def restore_quit_flag(qapp: QApplication) -> Iterator[None]:
    yield
    qapp.setQuitOnLastWindowClosed(True)
    for widget in qapp.topLevelWidgets():
        if isinstance(widget, QuestionPopup | FocusDialog):
            widget.close()
            widget.deleteLater()


# A Monday before the focus time: the first scheduler pass shows only the login questions.
START = datetime(2026, 11, 9, 8, 0, tzinfo=ZoneInfo("Africa/Kampala"))


_MADE: list[TeaApp] = []


@pytest.fixture(autouse=True)
def stop_schedulers() -> Iterator[None]:
    """A live 60-second timer would refresh a deleted window during a later test."""
    yield
    while _MADE:
        _MADE.pop().runner.stop()


def _make(qapp: QApplication, qtbot: QtBot, instance: SingleInstance, tray: bool) -> TeaApp:
    tea = TeaApp(qapp, instance, tray_available=tray, clock=FakeClock(START))
    _MADE.append(tea)
    qtbot.addWidget(tea.window)
    return tea


def test_start_seeds_the_bank_and_shows_login_questions(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=False)
    assert len(tea.repos.questions.list(origin="bank")) > 30
    tea.start(background=True)
    popup = tea.login.popup
    assert popup is not None and popup.isVisible() and popup.login
    assert popup.progress_text() == "Question 1 of 3"
    tea.close()


def test_tray_answer_now_opens_a_focused_popup(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    tea.login.on_app_start()
    assert tea.login.popup is not None
    tea.login.popup.later_button.click()  # dismissed: the cooldown starts
    tea.tray.answer_action.trigger()
    popup = tea.login.popup
    assert popup is not None and popup.isVisible() and not popup.login
    tea.tray.hide()
    tea.close()


def test_ipc_login_questions_opens_the_popup(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=False)
    instance.message.emit(MSG_QUESTIONS)
    assert tea.login.popup is not None and not tea.login.popup.login
    tea.close()


def test_with_tray_close_hides_and_app_keeps_running(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    assert not qapp.quitOnLastWindowClosed()
    tea.start(background=False)
    tea.window.close()
    assert not tea.window.isVisible()
    assert not tea.window.closed_for_real
    tea.tray.hide()


def test_without_tray_close_quits(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=False)
    assert tea.tray is None
    assert qapp.quitOnLastWindowClosed()
    tea.start(background=False)
    tea.window.close()
    assert tea.window.closed_for_real


def test_background_start_stays_hidden(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    tea.start(background=True)
    assert not tea.window.isVisible()
    assert tea.tray is not None
    tea.tray.hide()


def test_ipc_show_brings_window_and_clears_attention(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    tea.start(background=True)
    tea.tray.set_attention(True)
    instance.message.emit("show")
    assert tea.window.isVisible()
    assert not tea.tray.attention
    tea.tray.hide()


def test_tray_new_blog_opens_that_screen(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    tea.tray.new_blog_action.trigger()
    assert tea.window.isVisible()
    assert tea.window.current_screen() == "new_blog"
    tea.tray.hide()


def test_pause_syncs_between_tray_footer_and_settings_file(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    tea.tray.pause_action.trigger()
    assert tea.window.settings.pause_automation is True
    assert settings_mod.load().pause_automation is True
    tea.window.set_paused(False)
    assert not tea.tray.pause_action.isChecked()
    assert settings_mod.load().pause_automation is False
    tea.tray.hide()


def test_quit_saves_geometry_and_quits(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tea import config

    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    quits: list[bool] = []
    monkeypatch.setattr(tea.app, "quit", lambda: quits.append(True))
    tea.start(background=False)
    tea.tray.quit_action.trigger()
    assert quits == [True]
    assert config.window_state_path().is_file()
    tea.tray.hide()


def test_start_sweeps_copies_cut_off_by_a_crash(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    from tea.domain import attachments

    stale = attachments.reserve(7, "report.pdf")
    tea = _make(qapp, qtbot, instance, tray=False)
    tea.start(background=True)
    assert not stale.part.exists()
    tea.close()


# M7: the hand-off dialog and the draft view are reached from everywhere


def _weekly(tea: TeaApp) -> int:
    from tea.domain import weekly
    from tea.settings import Settings

    week = START.date()
    weekly.save_focus(tea.repos, Settings(), tea.clock, week, "Small teams")
    return weekly.prepare_packet(tea.repos, Settings(), tea.clock, "weekly", week).id


def test_notification_action_opens_the_handoff_dialog(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=False)
    hid = _weekly(tea)
    assert not tea.week.handoff_dialog_open()
    tea._on_notification_action(f"handoff:{hid}")
    assert hid in tea.handoffs.dialogs and tea.handoffs.dialogs[hid].isVisible()
    assert tea.week.handoff_dialog_open()
    tea.handoffs.close_all()
    tea.close()


def test_ring_and_tray_open_the_handoff_dialog(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    hid = _weekly(tea)
    tea.week.open_handoff.emit(hid)
    assert hid in tea.handoffs.dialogs
    tea.handoffs.close_all()
    qtbot.waitUntil(lambda: not tea.handoffs.dialogs)
    assert tea.tray is not None
    tea.tray.open_handoff_requested.emit()
    assert hid in tea.handoffs.dialogs
    tea.handoffs.close_all()
    tea.close()


def test_import_then_open_draft_shows_the_drafts_screen(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    from tea.devtools import sample_replies

    tea = _make(qapp, qtbot, instance, tray=False)
    hid = _weekly(tea)
    tea.week.open_handoff.emit(hid)
    dialog = tea.handoffs.dialogs[hid]
    dialog.copy_button.click()
    dialog.paste_box.setPlainText(sample_replies.WEEKLY)
    dialog.import_button.click()
    dialog.open_draft_button.click()
    assert tea.window.current_screen() == "drafts"
    assert tea.drafts.view.title_label.text().startswith("Small teams need fewer documents")
    tea.close()


def test_tray_resume_entry_follows_the_scope_session(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    assert tea.tray is not None
    assert not tea.tray.resume_action.isVisible()
    screen = tea.window.new_blog_screen
    screen.topic_edit.setText("Green tea at work")
    screen.start_button.click()
    popup = tea.new_blog.popup
    assert popup is not None
    popup.later_button.click()
    assert tea.tray.resume_action.isVisible()
    tea.tray.resume_action.trigger()
    assert tea.new_blog.popup is not None
    assert tea.new_blog.popup.index == 0
    tea.new_blog.popup.later_button.click()
    tea.close()


def test_new_blog_done_opens_the_handoff_from_the_app(
    qapp: QApplication, qtbot: QtBot, instance: SingleInstance
) -> None:
    tea = _make(qapp, qtbot, instance, tray=True)
    screen = tea.window.new_blog_screen
    screen.topic_edit.setText("Green tea at work")
    screen.start_button.click()
    popup = tea.new_blog.popup
    assert popup is not None
    while tea.new_blog.popup is popup:
        popup.skip_button.click()
    assert tea.handoffs.is_open()
    assert tea.tray is not None
    assert tea.tray.open_handoff_action.isVisible()
    assert not tea.tray.resume_action.isVisible()
    tea.close()
