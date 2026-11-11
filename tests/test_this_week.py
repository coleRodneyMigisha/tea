"""This week screen and its controller (WeekFlow): states, buttons, focus dialog, login order."""

from collections.abc import Iterator
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain import weekly
from tea.settings import Settings
from tea.ui import strings
from tea.ui.screens.this_week import ThisWeekScreen
from tea.ui.theme import Theme
from tea.ui.week_flow import WeekFlow
from tea.ui.week_state import week_view

TZ = ZoneInfo("Africa/Kampala")
WEEK = date(2026, 11, 9)


def t(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    th = Theme(qapp, appearance="light", scale=1.0)
    th.apply()
    return th


@pytest.fixture
def screen(qtbot: QtBot, theme: Theme) -> ThisWeekScreen:
    s = ThisWeekScreen(theme, reduce_motion=True)
    qtbot.addWidget(s)
    s.show()
    return s


def show(screen: ThisWeekScreen, repos: Repos, clock: FakeClock, **settings: object) -> None:
    screen.set_view(week_view(repos, Settings.model_validate(settings), clock.now()))


def test_no_focus_state(screen: ThisWeekScreen, repos: Repos, clock: FakeClock) -> None:
    clock.set(t(10, 10))
    show(screen, repos, clock)
    assert screen.ring.state == "no_focus"
    assert screen.action_button.text() == strings.SET_FOCUS and screen.action_button.isVisible()
    assert screen.focus_text.text() == strings.EMPTY_FOCUS
    assert not screen.pick_chip.isVisible() and not screen.caption.isVisible()
    assert not screen.edit_focus_button.isVisible()


def test_no_focus_thursday_morning_caption(
    screen: ThisWeekScreen, repos: Repos, clock: FakeClock
) -> None:
    clock.set(t(12, 7))
    show(screen, repos, clock)
    assert screen.caption.isVisible()
    assert screen.caption.text() == strings.PICK_SOON.format(time="9 am")


def test_steeping_state(screen: ThisWeekScreen, repos: Repos, clock: FakeClock) -> None:
    clock.set(t(9, 9))
    weekly.save_focus(repos, Settings(), clock, WEEK, "Small teams")
    clock.set(t(11, 13, 30))
    show(screen, repos, clock)
    assert screen.ring.state == "steeping"
    assert screen.focus_text.text() == "Small teams"
    assert not screen.action_button.isVisible()
    assert screen.edit_focus_button.isVisible()
    assert screen.ring.accessibleName() == "Prompt due Friday 6 pm, 2 days 4 hours left"


def test_pick_state_shows_chip(screen: ThisWeekScreen, repos: Repos, clock: FakeClock) -> None:
    clock.set(t(12, 9))
    weekly.enter_pick_mode(repos, Settings(), WEEK)
    show(screen, repos, clock)
    assert screen.ring.state == "pick"
    assert screen.pick_chip.isVisible() and screen.pick_chip.text() == strings.CHIP_PICK
    assert not screen.action_button.isVisible()
    assert screen.edit_focus_button.text() == strings.SET_OWN_TOPIC


def test_prompt_ready_and_copied(screen: ThisWeekScreen, repos: Repos, clock: FakeClock) -> None:
    s = Settings()
    clock.set(t(9, 9))
    weekly.save_focus(repos, s, clock, WEEK, "Small teams")
    clock.set(t(13, 18))
    h = weekly.prepare_packet(repos, s, clock, "weekly", WEEK)
    show(screen, repos, clock)
    assert screen.action_button.text() == strings.OPEN_HANDOFF
    assert not screen.caption.isVisible()
    got: list[int] = []
    screen.open_handoff_requested.connect(got.append)
    screen.action_button.click()
    assert got == [h.id]
    repos.handoffs.mark_copied(h.id)
    show(screen, repos, clock)
    assert screen.caption.isVisible() and screen.caption.text() == strings.WAITING_FOR_REPLY


def test_paused_state(screen: ThisWeekScreen, repos: Repos, clock: FakeClock) -> None:
    clock.set(t(10, 10))
    show(screen, repos, clock, pause_automation=True)
    assert screen.ring.state == "paused"
    assert not screen.action_button.isVisible()
    assert screen.edit_focus_button.text() == strings.SET_FOCUS  # not pick mode's name


def test_questions_card(
    qtbot: QtBot, screen: ThisWeekScreen, repos: Repos, clock: FakeClock
) -> None:
    clock.set(t(10, 10))
    show(screen, repos, clock)
    assert screen.answered_label.text() == strings.ANSWERED.format(n=0)
    with qtbot.waitSignal(screen.answer_requested, timeout=500):
        screen.answer_button.click()
    with qtbot.waitSignal(screen.preview_requested, timeout=500):
        screen.preview_button.click()


# WeekFlow


class FakeLogin:
    def __init__(self) -> None:
        self.started = 0

    def on_app_start(self) -> bool:
        self.started += 1
        return True


@pytest.fixture
def flow(
    qtbot: QtBot, theme: Theme, screen: ThisWeekScreen, repos: Repos, clock: FakeClock
) -> Iterator[tuple[WeekFlow, FakeLogin]]:
    login = FakeLogin()
    settings = Settings()
    f = WeekFlow(theme, repos, clock, lambda: settings, screen, login, reduce_motion=True)
    clock.set(t(9, 9, 30))
    yield f, login
    if f.dialog is not None:  # closing it later would write to a closed database
        f.dialog.blockSignals(True)
        f.dialog.close()
        f.dialog.deleteLater()


def test_scheduler_dialog_saves_focus(
    qtbot: QtBot, flow: tuple[WeekFlow, FakeLogin], repos: Repos, screen: ThisWeekScreen
) -> None:
    f, _ = flow
    f.show_focus_dialog(WEEK)
    assert f.focus_dialog_open()
    d = f.dialog
    assert d is not None
    d.editor.setPlainText("Small teams")
    with qtbot.waitSignal(f.focus_saved):
        d.save_button.click()
    assert not f.focus_dialog_open()
    w = repos.weeks.get(WEEK)
    assert w is not None and w.focus_text == "Small teams" and w.blog_id is not None
    blog = repos.blogs.get(w.blog_id)
    assert blog is not None and blog.allowed_sources == ["own_documents", "web"]
    assert repos.questions.list(origin="week", week_start=WEEK) != []
    assert screen.focus_text.text() == "Small teams"


def test_scheduler_dialog_not_now_snoozes(
    flow: tuple[WeekFlow, FakeLogin], repos: Repos, clock: FakeClock
) -> None:
    f, _ = flow
    f.show_focus_dialog(WEEK)
    assert f.dialog is not None
    f.dialog.later_button.click()
    job = repos.jobs.get("focus_prompt", WEEK)
    assert job is not None and job.snoozed_until is not None
    assert datetime.fromisoformat(job.snoozed_until) == t(9, 11, 30)


def test_owner_opened_dialog_not_now_does_not_snooze(
    flow: tuple[WeekFlow, FakeLogin], repos: Repos, screen: ThisWeekScreen
) -> None:
    f, _ = flow
    f.refresh()
    screen.action_button.click()  # Set focus
    assert f.dialog is not None and f.focus_dialog_open()
    f.dialog.later_button.click()
    job = repos.jobs.get("focus_prompt", WEEK)
    assert job is None or job.snoozed_until is None


def test_second_show_reuses_open_dialog(flow: tuple[WeekFlow, FakeLogin]) -> None:
    f, _ = flow
    f.show_focus_dialog(WEEK)
    first = f.dialog
    f.show_focus_dialog(WEEK)
    assert f.dialog is first


def test_login_questions_wait_for_focus_dialog(flow: tuple[WeekFlow, FakeLogin]) -> None:
    f, login = flow
    f.show_focus_dialog(WEEK)
    f.show_login_questions()
    assert login.started == 0
    assert f.dialog is not None
    f.dialog.later_button.click()
    assert login.started == 1


def test_login_questions_at_once_without_dialog(flow: tuple[WeekFlow, FakeLogin]) -> None:
    f, login = flow
    f.show_login_questions()
    assert login.started == 1


def test_carried_line_when_a_draft_carries(
    flow: tuple[WeekFlow, FakeLogin], repos: Repos, clock: FakeClock
) -> None:
    f, _ = flow
    b = repos.blogs.create("Old", "Old", "weekly", status="ready")
    repos.blogs.update(b.id, carried_weeks=1)
    f.show_focus_dialog(WEEK)
    assert f.dialog is not None and f.dialog.carried_line.isVisibleTo(f.dialog)


def test_focus_is_kept_when_the_rebuild_fails(
    qtbot: QtBot, flow: tuple[WeekFlow, FakeLogin], repos: Repos, clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    from tea.handoff.packets import PacketError

    f, _ = flow
    s = Settings()
    weekly.enter_pick_mode(repos, s, WEEK)
    clock.set(t(13, 18))
    weekly.prepare_packet(repos, s, clock, "weekly_pick", WEEK)

    def boom(*_a: object, **_k: object) -> None:
        raise PacketError("no")

    monkeypatch.setattr(weekly, "prepare_packet", boom)
    f.show_focus_dialog(WEEK, owner=True)
    assert f.dialog is not None
    f.dialog.editor.setPlainText("Own topic")
    f.dialog.save_button.click()  # must not raise out of the slot
    w = repos.weeks.get(WEEK)
    assert w is not None and w.focus_text == "Own topic"
