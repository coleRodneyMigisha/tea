"""Login question flow: one session per start, cooldown after dismissal, answers persist."""

import random
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.domain import questions as qs
from tea.settings import Settings
from tea.ui.login_flow import LoginFlow
from tea.ui.theme import Theme

WEEK = date(2026, 11, 9)


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


@pytest.fixture
def flow(qtbot: QtBot, theme: Theme, repos: Repos, clock: FakeClock) -> Callable[..., LoginFlow]:
    qs.seed_bank(repos)

    def build(settings: Settings | None = None, timeout_ms: int = 90_000) -> LoginFlow:
        s = settings or Settings()
        f = LoginFlow(
            theme, repos, clock, lambda: s, rng=random.Random(0), timeout_ms=timeout_ms,
            reduce_motion=True,
        )  # fmt: skip
        return f

    return build


def _close(qtbot: QtBot, f: LoginFlow) -> None:
    assert f.popup is not None
    qtbot.addWidget(f.popup)


def test_app_start_shows_a_login_session(qtbot: QtBot, flow: Callable[..., LoginFlow]) -> None:
    f = flow()
    assert f.on_app_start()
    _close(qtbot, f)
    assert f.popup is not None and f.popup.isVisible()
    assert f.popup.progress_text() == "Question 1 of 3"
    assert f.popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_only_one_session_per_app_start(qtbot: QtBot, flow: Callable[..., LoginFlow]) -> None:
    f = flow()
    assert f.on_app_start()
    _close(qtbot, f)
    assert f.popup is not None
    f.popup.later_button.click()
    assert not f.on_app_start()


def test_timeout_starts_the_cooldown(
    qtbot: QtBot, flow: Callable[..., LoginFlow], clock: FakeClock
) -> None:
    f = flow(timeout_ms=40)
    assert f.on_app_start()
    _close(qtbot, f)
    qtbot.waitUntil(lambda: f.popup is None, timeout=2000)
    clock.advance(minutes=119)
    assert not flow().on_app_start()  # a fresh app start inside the pause
    clock.advance(minutes=1)
    g = flow()
    assert g.on_app_start()
    _close(qtbot, g)


def test_later_starts_the_cooldown(
    qtbot: QtBot, flow: Callable[..., LoginFlow], clock: FakeClock
) -> None:
    f = flow()
    f.on_app_start()
    _close(qtbot, f)
    assert f.popup is not None
    f.popup.later_button.click()
    clock.advance(minutes=60)
    assert not flow().on_app_start()


def test_pause_length_comes_from_settings(
    qtbot: QtBot, flow: Callable[..., LoginFlow], clock: FakeClock
) -> None:
    s = Settings(dismiss_pause_minutes=30)
    f = flow(s)
    f.on_app_start()
    _close(qtbot, f)
    assert f.popup is not None
    f.popup.later_button.click()
    clock.advance(minutes=30)
    g = flow(s)
    assert g.on_app_start()
    _close(qtbot, g)


def test_completing_sets_no_cooldown(
    qtbot: QtBot, flow: Callable[..., LoginFlow], repos: Repos
) -> None:
    f = flow(Settings(questions_per_login=1))
    f.on_app_start()
    _close(qtbot, f)
    assert f.popup is not None
    f.popup.skip_button.click()
    assert f.popup is None
    assert qs.login_allowed(repos, repos.questions.clock.now())


def test_zero_questions_per_login_shows_nothing(flow: Callable[..., LoginFlow]) -> None:
    assert not flow(Settings(questions_per_login=0)).on_app_start()


def test_ask_now_ignores_cooldown_takes_focus_and_never_times_out(
    qtbot: QtBot, flow: Callable[..., LoginFlow], repos: Repos, clock: FakeClock
) -> None:
    qs.note_dismissed(repos, clock.now(), minutes=120)
    f = flow(timeout_ms=30)
    assert not f.on_app_start()
    assert f.ask_now()
    _close(qtbot, f)
    assert f.popup is not None
    assert not f.popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    qtbot.wait(120)
    assert f.popup is not None and f.popup.isVisible()


def test_ask_now_while_open_reuses_the_popup(qtbot: QtBot, flow: Callable[..., LoginFlow]) -> None:
    f = flow()
    f.on_app_start()
    _close(qtbot, f)
    first = f.popup
    assert f.ask_now()
    assert f.popup is first


def test_answers_are_recorded_with_login_context(
    qtbot: QtBot, flow: Callable[..., LoginFlow], repos: Repos
) -> None:
    blog = repos.blogs.create("Wikis", "Wikis", "weekly")
    qs.instantiate_improve(repos, blog, "Wikis")
    f = flow()
    f.on_app_start()
    _close(qtbot, f)
    popup = f.popup
    assert popup is not None
    popup.text_edit.setPlainText("an improvement")
    popup.next_button.click()
    popup.skip_button.click()
    (a, b) = repos.answers.list()
    assert a.context == "login" and a.week_start == WEEK and a.blog_id == blog.id
    assert a.answer_text == "an improvement" and not a.skipped
    assert b.skipped and b.blog_id is None


def test_answers_persist_across_restart(
    qtbot: QtBot, theme: Theme, tmp_path: Path, clock: FakeClock
) -> None:
    path = tmp_path / "restart.db"
    conn = open_db(path)
    repos = Repos(conn, clock)
    qs.seed_bank(repos)
    f = LoginFlow(theme, repos, clock, lambda: Settings(), rng=random.Random(3))
    f.on_app_start()
    _close(qtbot, f)
    popup = f.popup
    assert popup is not None
    asked = popup.questions[0]
    if asked.kind == "text":
        popup.text_edit.setPlainText("persisted")
    elif asked.kind == "choice":
        popup.choice_buttons[0].click()
    else:
        popup.scale_buttons[3].click()
    popup.next_button.click()
    popup.later_button.click()
    conn.close()

    conn2 = open_db(path)
    try:
        again = Repos(conn2, clock)
        (answer,) = again.answers.list()
        assert answer.question_id == asked.id and not answer.skipped and answer.answer_text
        q = again.questions.get(asked.id)
        assert q is not None and q.asked_count == 1
        clock.advance(timedelta(hours=1))
        assert not qs.login_allowed(again, clock.now())
    finally:
        conn2.close()


def test_later_on_manual_session_sets_no_pause(
    qtbot: QtBot, flow: Callable[..., LoginFlow], repos: Repos, clock: FakeClock
) -> None:
    f = flow()
    assert f.ask_now()
    _close(qtbot, f)
    assert f.popup is not None
    f.popup.later_button.click()
    assert qs.login_allowed(repos, clock.now())
    assert flow().on_app_start()


def test_ask_now_with_nothing_to_ask_says_so(
    qtbot: QtBot, theme: Theme, repos: Repos, clock: FakeClock
) -> None:
    for q in repos.questions.list():
        repos.questions.set_active(q.id, False)
    f = LoginFlow(theme, repos, clock, lambda: Settings(), rng=random.Random(0))
    with qtbot.waitSignal(f.nothing_to_ask, timeout=500):
        assert not f.ask_now()
    assert f.popup is None


def test_ask_now_turns_an_open_login_popup_manual(
    qtbot: QtBot, flow: Callable[..., LoginFlow], repos: Repos, clock: FakeClock
) -> None:
    f = flow(timeout_ms=60)
    f.on_app_start()
    _close(qtbot, f)
    popup = f.popup
    assert popup is not None
    f.ask_now()
    qtbot.wait(200)
    assert f.popup is popup and popup.isVisible() and not popup.login
    assert not popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_changing_an_answer_via_back_counts_one_ask(
    qtbot: QtBot, flow: Callable[..., LoginFlow], repos: Repos
) -> None:
    f = flow(Settings(questions_per_login=2))
    f.on_app_start()
    _close(qtbot, f)
    popup = f.popup
    assert popup is not None
    first = popup.questions[0]
    popup.skip_button.click()
    popup.back_button.click()
    popup.skip_button.click()  # unchanged: nothing saved
    popup.back_button.click()
    if first.kind == "text":
        popup.text_edit.setPlainText("now answered")
    elif first.kind == "choice":
        popup.choice_buttons[0].click()
    else:
        popup.scale_buttons[0].click()
    popup.next_button.click()
    assert len([a for a in repos.answers.list() if a.question_id == first.id]) == 2
    q = repos.questions.get(first.id)
    assert q is not None and q.asked_count == 1
