"""TeaApp wiring: tray or no tray, --background, IPC show, pause sync, quit."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea import settings as settings_mod
from tea.app import TeaApp
from tea.single_instance import SingleInstance


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


def _make(qapp: QApplication, qtbot: QtBot, instance: SingleInstance, tray: bool) -> TeaApp:
    tea = TeaApp(qapp, instance, tray_available=tray)
    qtbot.addWidget(tea.window)
    return tea


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
