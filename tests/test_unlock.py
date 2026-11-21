"""Optional login questions when the screen unlocks (M11, off by default)."""

import random
from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain import questions as qs
from tea.settings import Settings
from tea.ui.login_flow import LoginFlow
from tea.ui.theme import Theme
from tea.unlock import UnlockWatcher


@pytest.fixture
def make(
    qtbot: QtBot, qapp: QApplication, repos: Repos, clock: FakeClock
) -> Callable[..., LoginFlow]:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    qs.seed_bank(repos)

    def build(**changes: object) -> LoginFlow:
        settings = Settings(**changes)  # type: ignore[arg-type]
        return LoginFlow(
            theme, repos, clock, lambda: settings, rng=random.Random(0), reduce_motion=True
        )

    return build


def _shown(qtbot: QtBot, flow: LoginFlow) -> bool:
    if flow.popup is not None:
        qtbot.addWidget(flow.popup)
    return flow.popup is not None


def test_unlock_does_nothing_by_default(qtbot: QtBot, make: Callable[..., LoginFlow]) -> None:
    flow = make()
    assert not flow.on_unlock()
    assert not _shown(qtbot, flow)


def test_unlock_shows_a_session_when_the_setting_is_on(
    qtbot: QtBot, make: Callable[..., LoginFlow]
) -> None:
    flow = make(questions_on_unlock=True)
    assert flow.on_unlock()
    assert _shown(qtbot, flow) and flow.popup is not None and flow.popup.login


def test_unlock_works_again_after_a_completed_session_but_not_in_the_cooldown(
    qtbot: QtBot, make: Callable[..., LoginFlow], clock: FakeClock
) -> None:
    flow = make(questions_on_unlock=True)
    assert flow.on_app_start()
    assert flow.popup is not None
    qtbot.addWidget(flow.popup)
    flow.popup.later_button.click()  # dismissed: the 120-minute pause starts
    clock.advance(minutes=60)
    assert not flow.on_unlock()
    clock.advance(minutes=60)
    assert flow.on_unlock()  # the same cooldown as a login
    assert _shown(qtbot, flow)


def test_unlock_never_opens_a_second_popup(qtbot: QtBot, make: Callable[..., LoginFlow]) -> None:
    flow = make(questions_on_unlock=True)
    assert flow.on_unlock()
    assert _shown(qtbot, flow)
    assert not flow.on_unlock()


def test_unlock_respects_zero_questions_and_paused_automation(
    qtbot: QtBot, make: Callable[..., LoginFlow]
) -> None:
    assert not make(questions_on_unlock=True, questions_per_login=0).on_unlock()
    assert not make(questions_on_unlock=True, pause_automation=True).on_unlock()


def test_watcher_emits_only_when_the_screen_unlocks(qtbot: QtBot) -> None:
    watcher = UnlockWatcher(listen=False)
    with qtbot.assertNotEmitted(watcher.unlocked):
        watcher.on_active_changed(True)  # the screen locked
    with qtbot.waitSignal(watcher.unlocked, timeout=500):
        watcher.on_active_changed(False)


def test_watcher_can_be_switched_off_and_on_without_error(qtbot: QtBot) -> None:
    watcher = UnlockWatcher(listen=False)
    watcher.set_enabled(True)
    watcher.set_enabled(True)
    watcher.set_enabled(False)
    assert not watcher.enabled
