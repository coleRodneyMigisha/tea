"""The 22 required scheduler scenarios (docs/TESTING.md section 2), against FakeClock.

Defaults: focus Monday 09:00, pick mode Thursday 09:00, prompt Friday 18:00, reminder pause
2 hours, carry-over 1 week. WEEK is Monday 9 November 2026 (Africa/Kampala, no DST).
"""

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication
from sched_world import W1, W2, W3, WEEK, World, at

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain import improve, weekly
from tea.domain import questions as qs
from tea.scheduler import (
    EnterPickMode,
    NotifyNoFocus,
    PreparePacket,
    RemindHandoff,
    Rollover,
    ShowFocusDialog,
    ShowLoginQuestions,
)
from tea.ui import strings

WED, THU, FRI, SAT, SUN = (WEEK + timedelta(days=n) for n in (2, 3, 4, 5, 6))
FRI1 = W1 + timedelta(days=4)
FOCUS = "Why small teams ship faster"


@pytest.fixture
def world(qapp: QApplication, repos: Repos, clock: FakeClock) -> World:
    return World(repos, clock)


def packets(actions: list[object]) -> list[PreparePacket]:
    return [a for a in actions if isinstance(a, PreparePacket)]


def count(world: World, title: str) -> int:
    return world.titles().count(title)


def ready_week(world: World, week: date = WEEK, focus: str = FOCUS) -> int:
    """A weekly blog for `week` with an imported, unused draft. Returns the blog id."""
    world.at(week, 9, 5)
    world.set_focus(focus, week)
    h = weekly.prepare_packet(world.repos, world.settings, world.clock, "weekly", week)
    world.import_for(h)
    assert h.blog_id is not None
    return h.blog_id


# 1


def test_01_normal_week(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(FRI, 17, 59)
    assert packets(world.run()) == []
    assert world.handoffs() == []

    world.at(FRI, 18, 0)
    assert packets(world.run()) == [PreparePacket("weekly", WEEK)]
    [h] = world.handoffs()
    assert (h.kind, h.status, h.week_start) == ("weekly", "prompt_ready", WEEK)
    assert count(world, strings.NOTIFY_PROMPT_READY) == 1

    assert world.run() == []
    world.at(FRI, 18, 1)
    assert world.run() == []
    assert len(world.handoffs()) == 1
    assert count(world, strings.NOTIFY_PROMPT_READY) == 1


# 2


def test_02_app_off_at_prompt_time(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(SAT, 10, 0)
    assert packets(world.run("start")) == [PreparePacket("weekly", WEEK)]
    assert world.handoffs()[0].created_at.startswith("2026-11-14T10:00")
    assert count(world, strings.NOTIFY_PROMPT_READY) == 1


# 3


def test_03_asleep_over_prompt_time(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(FRI, 17, 30)
    assert packets(world.run()) == []
    world.at(FRI, 21, 15)  # clock jump on resume
    assert packets(world.run("wake")) == [PreparePacket("weekly", WEEK)]
    assert count(world, strings.NOTIFY_PROMPT_READY) == 1


# 4


def test_04_focus_prompt_pause_after_dismissal(world: World) -> None:
    world.at(WEEK, 8, 59)
    assert ShowFocusDialog(WEEK) not in world.run("start")
    world.at(WEEK, 9, 0)
    assert ShowFocusDialog(WEEK) in world.run()  # first time due, app running
    assert world.hooks.focus_shown == [WEEK]
    assert count(world, strings.NOTIFY_FOCUS) == 1

    world.at(WEEK, 9, 10)
    weekly.dismiss_focus(
        world.repos, world.clock, WEEK, minutes=world.settings.dismiss_pause_minutes
    )
    for hour, minute, trigger in ((9, 11, "tick"), (11, 0, "wake"), (11, 9, "start")):
        world.at(WEEK, hour, minute)
        assert ShowFocusDialog(WEEK) not in world.run(trigger)
    world.at(WEEK, 11, 15)
    assert ShowFocusDialog(WEEK) not in world.run("tick")  # only at a login or wake
    assert ShowFocusDialog(WEEK) in world.run("wake")
    assert count(world, strings.NOTIFY_FOCUS) == 1  # the notification goes out once a week

    world.hooks.focus_open = True
    world.at(WEEK, 15, 0)
    assert ShowFocusDialog(WEEK) not in world.run("start")
    world.hooks.focus_open = False

    world.at(WED, 20, 0)
    assert ShowFocusDialog(WEEK) in world.run("start")
    world.at(THU, 9, 0)
    acts = world.run("start")
    assert EnterPickMode(WEEK) in acts
    assert ShowFocusDialog(WEEK) not in acts
    world.at(THU, 13, 0)
    assert ShowFocusDialog(WEEK) not in world.run("wake")


def test_04_focus_prompt_runs_until_prompt_time_when_pick_is_off(world: World) -> None:
    world.set(pick_enabled=False)
    world.at(THU, 10, 0)
    assert ShowFocusDialog(WEEK) in world.run("start")
    world.at(FRI, 17, 0)
    assert ShowFocusDialog(WEEK) in world.run("wake")
    world.at(FRI, 18, 1)
    assert ShowFocusDialog(WEEK) not in world.run("start")


def test_04_focus_prompt_done_once_focus_saved(world: World) -> None:
    world.at(WEEK, 9, 0)
    world.run("start")
    world.set_focus(FOCUS)
    world.at(WEEK, 12, 0)
    assert ShowFocusDialog(WEEK) not in world.run("start")


# 5


def test_05_pick_mode(world: World) -> None:
    world.at(THU, 8, 59)
    assert EnterPickMode(WEEK) not in world.run("start")
    world.at(THU, 9, 0)
    assert EnterPickMode(WEEK) in world.run()
    w = world.repos.weeks.get(WEEK)
    assert w is not None and w.pick_mode and w.blog_id is not None
    blog = world.repos.blogs.get(w.blog_id)
    assert blog is not None and (blog.topic, blog.topic_origin) == ("", "auto_trending")
    assert count(world, strings.NOTIFY_PICK) == 1
    world.at(THU, 9, 1)
    assert EnterPickMode(WEEK) not in world.run()
    world.at(THU, 15, 0)
    assert EnterPickMode(WEEK) not in world.run("start")
    assert count(world, strings.NOTIFY_PICK) == 1

    world.at(FRI, 18, 0)
    assert packets(world.run()) == [PreparePacket("weekly_pick", WEEK)]
    assert [h.kind for h in world.handoffs()] == ["weekly_pick"]


# 6


def test_06_pick_mode_with_machine_off(world: World) -> None:
    world.at(WED, 9, 0)
    world.run("start")
    world.at(FRI, 20, 0)
    acts = world.run("start")
    order = [a for a in acts if isinstance(a, EnterPickMode | PreparePacket)]
    assert order == [EnterPickMode(WEEK), PreparePacket("weekly_pick", WEEK)]
    assert [h.kind for h in world.handoffs()] == ["weekly_pick"]


# 7


@pytest.mark.parametrize("when", [(THU, 9, 30), (FRI, 17, 0)])
def test_07_focus_after_pick_mode_before_prompt(world: World, when: tuple[date, int, int]) -> None:
    world.at(THU, 9, 0)
    world.run()
    world.at(*when)
    world.set_focus(FOCUS)
    w = world.repos.weeks.get(WEEK)
    assert w is not None and not w.pick_mode and w.focus_text == FOCUS
    blog = world.repos.blogs.get(w.blog_id or 0)
    assert blog is not None and (blog.topic, blog.topic_origin) == (FOCUS, "owner")
    world.at(FRI, 18, 0)
    assert packets(world.run()) == [PreparePacket("weekly", WEEK)]
    assert [h.kind for h in world.handoffs()] == ["weekly"]


def test_07_focus_after_pick_packet_exists(world: World) -> None:
    world.at(THU, 9, 0)
    world.run()
    world.at(FRI, 18, 0)
    world.run()
    [pick] = world.handoffs()
    world.at(FRI, 19, 0)
    rebuilt = world.set_focus(FOCUS)
    assert rebuilt is not None and rebuilt.kind == "weekly" and rebuilt.status == "prompt_ready"
    old = world.repos.handoffs.get(pick.id)
    assert old is not None and old.status == "superseded"
    assert packets(world.run()) == []
    assert [h.kind for h in world.live()] == ["weekly"]
    world.at(FRI, 22, 0)
    assert [a for a in world.run("start") if isinstance(a, RemindHandoff)] == [
        RemindHandoff(rebuilt.id)
    ]


def test_07_focus_before_pick_time_means_no_pick_mode(world: World) -> None:
    world.at(THU, 8, 59)
    world.set_focus(FOCUS)
    world.at(THU, 9, 0)
    assert EnterPickMode(WEEK) not in world.run()
    w = world.repos.weeks.get(WEEK)
    assert w is not None and not w.pick_mode
    assert count(world, strings.NOTIFY_PICK) == 0


def test_07_changed_focus_rebuilds_an_open_weekly_prompt(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(FRI, 18, 0)
    world.run()
    world.at(FRI, 19, 0)
    rebuilt = world.set_focus("A different idea")
    assert rebuilt is not None
    assert [h.status for h in world.handoffs()] == ["superseded", "prompt_ready"]
    assert world.set_focus("A different idea") is None  # same text: nothing to rebuild


# 8


def test_08_pick_switch_off(world: World) -> None:
    world.set(pick_enabled=False)
    world.at(THU, 9, 0)
    assert EnterPickMode(WEEK) not in world.run()
    w = world.repos.weeks.get(WEEK)
    assert w is None or not w.pick_mode
    world.at(FRI, 18, 0)
    acts = world.run()
    assert NotifyNoFocus(WEEK) in acts and packets(acts) == []
    assert world.run() == [] and world.run("start").count(NotifyNoFocus(WEEK)) == 0
    assert count(world, strings.NOTIFY_NO_FOCUS) == 1
    assert world.handoffs() == []


# 9


def _prompt_ready(world: World) -> int:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(FRI, 18, 0)
    world.run()
    return world.handoffs()[0].id


def reminders(actions: list[object]) -> list[object]:
    return [a for a in actions if isinstance(a, RemindHandoff)]


def test_09_reminders(world: World) -> None:
    hid = _prompt_ready(world)
    world.at(FRI, 21, 0)
    assert reminders(world.run("tick")) == []  # only at a login or wake
    assert reminders(world.run("start")) == [RemindHandoff(hid)]
    h = world.repos.handoffs.get(hid)
    assert h is not None and h.reminder_count == 1
    first, last = world.backend.sent[0], world.backend.sent[-1]
    assert last.title == strings.NOTIFY_REMINDER and last.replaces_id == first.id

    world.at(FRI, 22, 0)
    assert reminders(world.run("start")) == []  # 2-hour pause
    world.at(SAT, 10, 0)
    world.hooks.handoff_open = True
    assert reminders(world.run("start")) == []
    world.hooks.handoff_open = False
    assert reminders(world.run("wake")) == [RemindHandoff(hid)]

    h = world.repos.handoffs.get(hid)
    assert h is not None
    world.import_for(h)
    world.at(SUN, 10, 0)
    assert reminders(world.run("start")) == []


def test_09_no_reminders_when_off(world: World) -> None:
    _prompt_ready(world)
    world.set(reminders_enabled=False)
    world.at(FRI, 21, 0)
    assert reminders(world.run("start")) == []


def test_09_no_reminder_soon_after_the_prompt(world: World) -> None:
    _prompt_ready(world)
    world.at(FRI, 19, 0)
    assert reminders(world.run("start")) == []


# 10


def test_10_week_boundary(world: World) -> None:
    hid = _prompt_ready(world)
    world.at(SUN, 23, 59)
    world.run()
    world.at(W1, 0, 1)
    acts = world.run()
    assert packets(acts) == []
    assert [h.id for h in world.handoffs(week_start=WEEK)] == [hid]
    world.at(W1, 9, 0)
    acts = world.run()
    assert ShowFocusDialog(W1) in acts and ShowFocusDialog(WEEK) not in acts
    world.at(W1, 10, 0)
    assert reminders(world.run("start")) == [RemindHandoff(hid)]


def test_10_catch_up_for_last_week(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(W1, 10, 0)  # off from Friday afternoon until Monday
    assert packets(world.run("start")) == [PreparePacket("weekly", WEEK)]
    world.at(W1 + timedelta(days=4), 18, 1)  # more than 7 days after last week's prompt time
    assert PreparePacket("weekly", WEEK) not in world.run()


def test_10_no_catch_up_after_seven_days(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(FRI1, 18, 1)
    assert PreparePacket("weekly", WEEK) not in world.run("start")


# 11


def test_11_carry_over(world: World) -> None:
    blog_id = ready_week(world)
    world.at(W1, 0, 1)
    acts = world.run()
    assert [a for a in acts if isinstance(a, Rollover)] == [Rollover(W1, carry=(blog_id,))]
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and (blog.carried_weeks, blog.status) == (1, "ready")
    improve_qs = world.repos.questions.list(origin="improve", blog_id=blog_id)
    assert 4 <= len(improve_qs) <= 6
    world.at(W1, 0, 2)
    world.run("start")
    assert len(world.repos.questions.list(origin="improve", blog_id=blog_id)) == len(improve_qs)

    world.at(W1, 9, 5)
    world.set_focus("This week's idea", W1)
    world.at(FRI1, 18, 0)
    assert packets(world.run()) == [
        PreparePacket("weekly", W1),
        PreparePacket("improve", W1, blog_id),
    ]
    imp = world.handoffs(kind="improve")
    assert [(h.blog_id, h.week_start) for h in imp] == [(blog_id, W1)]
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "ready"  # the improve prompt leaves it ready

    world.at(W2, 0, 1)
    world.run()
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "shelved"
    assert world.repos.questions.list(origin="improve", blog_id=blog_id) == []


def test_11_improve_without_a_focus(world: World) -> None:
    blog_id = ready_week(world)
    world.set(pick_enabled=False)
    world.at(FRI1, 18, 0)
    acts = world.run("start")
    assert packets(acts) == [PreparePacket("improve", W1, blog_id)]
    assert NotifyNoFocus(W1) in acts


# 12


@pytest.mark.parametrize("mark", ["copied", "posted"])
def test_12_used_drafts_do_not_carry(world: World, mark: str) -> None:
    blog_id = ready_week(world)
    draft = world.repos.drafts.latest_for_blog(blog_id)
    assert draft is not None
    getattr(world.repos.drafts, f"mark_{mark}")(draft.id)
    world.at(W1, 0, 1)
    acts = world.run()
    assert [a for a in acts if isinstance(a, Rollover)] == [Rollover(W1)]
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.carried_weeks == 0
    assert world.repos.questions.list(origin="improve", blog_id=blog_id) == []
    world.at(FRI1, 18, 0)
    assert all(p.kind != "improve" for p in packets(world.run()))


# 13


def test_13_carry_limit_zero(world: World) -> None:
    world.set(carry_over_weeks=0)
    blog_id = ready_week(world)
    world.at(W1, 0, 1)
    world.run()
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "shelved"
    world.at(FRI1, 18, 0)
    assert all(p.kind != "improve" for p in packets(world.run()))


def test_13_carry_limit_two(world: World) -> None:
    world.set(carry_over_weeks=2)
    blog_id = ready_week(world)
    for week, carried, status in ((W1, 1, "ready"), (W2, 2, "ready"), (W3, 3, "shelved")):
        world.at(week, 0, 1)
        world.run()
        blog = world.repos.blogs.get(blog_id)
        assert blog is not None and (blog.carried_weeks, blog.status) == (carried, status)


# 14


def test_14_only_the_most_recent_carries(world: World) -> None:
    older = ready_week(world, WEEK - timedelta(days=7), "Older idea")
    newer = ready_week(world, WEEK, FOCUS)
    world.at(W1, 0, 1)
    acts = world.run()
    assert [a for a in acts if isinstance(a, Rollover)] == [
        Rollover(W1, carry=(newer,), shelve=(older,))
    ]
    old, new = world.repos.blogs.get(older), world.repos.blogs.get(newer)
    assert old is not None and new is not None
    assert (old.status, new.status, new.carried_weeks) == ("shelved", "ready", 1)


# 15


def test_15_revive(world: World) -> None:
    world.set(carry_over_weeks=0)
    blog_id = ready_week(world)
    world.at(W1, 0, 1)
    world.run()
    world.at(W1 + timedelta(days=2), 14, 0)
    improve.revive(world.repos, world.settings, blog_id)
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "ready"
    assert world.repos.questions.list(origin="improve", blog_id=blog_id) != []
    world.at(FRI1, 18, 0)
    assert PreparePacket("improve", W1, blog_id) in world.run()
    world.at(W2, 0, 1)
    world.run()
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "shelved"


# 16


def test_16_rollover_idempotent(world: World) -> None:
    blog_id = ready_week(world)
    world.at(SUN, 23, 55)
    rolls = 0
    for _ in range(10):
        rolls += sum(isinstance(a, Rollover) and a.week == W1 for a in world.run())
        world.clock.advance(minutes=1)
    assert rolls == 1
    blog = world.repos.blogs.get(blog_id)
    assert blog is not None and blog.carried_weeks == 1
    n = len(world.repos.questions.list(origin="improve", blog_id=blog_id, active_only=False))
    assert 4 <= n <= 6


# 17


def test_17_regenerate(world: World) -> None:
    hid = _prompt_ready(world)
    world.at(FRI, 18, 30)
    new = weekly.regenerate(world.repos, world.settings, world.clock, hid)
    old = world.repos.handoffs.get(hid)
    assert old is not None and old.status == "superseded"
    assert new.status == "prompt_ready" and new.kind == "weekly" and new.week_start == WEEK
    assert packets(world.run()) == []
    world.at(FRI, 21, 30)
    assert reminders(world.run("start")) == [RemindHandoff(new.id)]


# 18


def test_18_pause(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.set(pause_automation=True)
    world.at(FRI, 18, 0)
    assert world.run("start") == []
    assert world.run("wake") == []
    world.at(W1, 9, 0)
    assert world.run("start") == []
    world.set(pause_automation=False)
    world.at(W1, 9, 1)
    acts = world.run()
    assert PreparePacket("weekly", WEEK) in acts and ShowFocusDialog(W1) in acts


# 19


def test_19_login_questions(world: World) -> None:
    world.at(WED, 9, 0)
    assert ShowLoginQuestions() in world.run("start")
    assert world.hooks.login_shown == 1
    for trigger in ("tick", "wake"):
        assert ShowLoginQuestions() not in world.run(trigger)
    world.set(questions_per_login=0)
    assert ShowLoginQuestions() not in world.run("start")
    world.set(questions_per_login=3)
    qs.note_dismissed(world.repos, world.clock.now(), minutes=120)
    world.at(WED, 10, 0)
    assert ShowLoginQuestions() not in world.run("start")
    world.at(WED, 11, 1)
    assert ShowLoginQuestions() in world.run("start")


# 20


def test_20_two_ticks_in_one_minute(world: World) -> None:
    world.at(WEEK, 9, 0)
    first = world.run("start")
    world.clock.advance(seconds=20)
    second = world.run()
    assert ShowFocusDialog(WEEK) in first and second == []
    world.set_focus(FOCUS)
    world.at(FRI, 18, 0)
    assert len(packets(world.run())) == 1
    world.clock.advance(seconds=30)
    assert world.run() == []
    assert len(world.handoffs()) == 1


# 21


def test_21_prompt_time_moved(world: World) -> None:
    world.at(WEEK, 9, 5)
    world.set_focus(FOCUS)
    world.at(FRI, 17, 0)
    world.run()
    world.set(prompt_time="20:00")
    world.at(FRI, 19, 0)
    assert packets(world.run("start")) == []
    world.at(FRI, 19, 59)
    assert packets(world.run()) == []
    world.at(FRI, 20, 0)
    assert packets(world.run()) == [PreparePacket("weekly", WEEK)]


# 22


def test_22_two_packets_one_notification(world: World) -> None:
    blog_id = ready_week(world)
    world.at(W1, 9, 5)
    world.set_focus("This week's idea", W1)
    sent_before = len(world.backend.sent)
    world.at(FRI1, 18, 0)
    acts = world.run()
    assert [p.kind for p in packets(acts)] == ["weekly", "improve"]
    new = world.backend.sent[sent_before:]
    assert [s.title for s in new] == [strings.NOTIFY_TWO_READY]
    carried = world.repos.drafts.latest_for_blog(blog_id)
    assert carried is not None and carried.title in new[0].body
    assert "This week's idea" in new[0].body


def test_rollover_on_first_run_marks_week(world: World, repos: Repos) -> None:
    world.at(WEEK, 10, 0)
    assert Rollover(WEEK) in world.run("start")
    assert all(not isinstance(a, Rollover) for a in world.run("start"))
    assert at(WEEK).weekday() == 0
