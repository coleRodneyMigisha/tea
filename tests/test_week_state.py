"""This week view model: ring state, progress, remaining time and the sentences around it."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from handoff_world import imported

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.domain import weekly
from tea.handoff.importer import import_reply
from tea.settings import Settings
from tea.ui import strings
from tea.ui.week_state import (
    WeekView,
    centre_text,
    progress,
    remaining_text,
    ring_sentence,
    short_clock,
    week_view,
)

TZ = ZoneInfo("Africa/Kampala")
WEEK = date(2026, 11, 9)


def t(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (t(9), 0.0),
        (t(11, 9), 0.5),  # Monday 00:00 to Friday 18:00 is 114 hours; 57 in
        (t(13, 18), 1.0),
        (t(14, 12), 1.0),
    ],
)
def test_progress(now: datetime, expected: float) -> None:
    assert progress(now, Settings()) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("delta", "text"),
    [
        (timedelta(days=2, hours=4, minutes=30), "2 days 4 hours"),
        (timedelta(days=1, hours=1), "1 day 1 hour"),
        (timedelta(days=3), "3 days"),
        (timedelta(hours=3, minutes=10), "3 hours 10 min"),
        (timedelta(hours=1), "1 hour"),
        (timedelta(minutes=45, seconds=30), "45 min"),
        (timedelta(seconds=20), "1 min"),
        (timedelta(0), "0 min"),
        (timedelta(minutes=-5), "0 min"),
    ],
)
def test_remaining_text(delta: timedelta, text: str) -> None:
    assert remaining_text(delta) == text


@pytest.mark.parametrize(
    ("hour", "minute", "text"),
    [(18, 0, "6 pm"), (9, 0, "9 am"), (20, 30, "8:30 pm"), (0, 0, "12 am")],
)
def test_short_clock(hour: int, minute: int, text: str) -> None:
    assert short_clock(datetime(2026, 11, 13, hour, minute, tzinfo=TZ)) == text


def view(repos: Repos, clock: FakeClock, settings: Settings | None = None) -> WeekView:
    return week_view(repos, settings or Settings(), clock.now())


def test_no_focus(repos: Repos, clock: FakeClock) -> None:
    clock.set(t(11, 10))
    v = view(repos, clock)
    assert (v.state, v.focus, v.pick_soon) == ("no_focus", None, False)
    assert centre_text(v) == strings.RING_NO_FOCUS


def test_pick_soon_on_thursday_morning(repos: Repos, clock: FakeClock) -> None:
    clock.set(t(12, 8))
    assert view(repos, clock).pick_soon
    assert not view(repos, clock, Settings(pick_enabled=False)).pick_soon
    clock.set(t(12, 9, 1))
    assert not view(repos, clock).pick_soon


def test_steeping_and_sentence(repos: Repos, clock: FakeClock) -> None:
    clock.set(t(9, 9))
    weekly.save_focus(repos, Settings(), clock, WEEK, "Small teams")
    clock.set(t(11, 13, 30))
    v = view(repos, clock)
    assert (v.state, v.focus) == ("steeping", "Small teams")
    assert centre_text(v) == "2 days 4 hours"
    assert ring_sentence(v) == "Prompt due Friday 6 pm, 2 days 4 hours left"


def test_pick_mode(repos: Repos, clock: FakeClock) -> None:
    clock.set(t(12, 9))
    weekly.enter_pick_mode(repos, Settings(), WEEK)
    v = view(repos, clock)
    assert v.state == "pick" and v.focus is None


def test_prompt_ready_then_copied_then_ready(repos: Repos, clock: FakeClock) -> None:
    s = Settings()
    clock.set(t(9, 9))
    weekly.save_focus(repos, s, clock, WEEK, "Small teams")
    clock.set(t(13, 18))
    h = weekly.prepare_packet(repos, s, clock, "weekly", WEEK)
    v = view(repos, clock)
    assert (v.state, v.copied, v.handoff_id) == ("prompt_ready", False, h.id)
    assert centre_text(v) == strings.RING_PROMPT_READY
    repos.handoffs.mark_copied(h.id)
    assert view(repos, clock).copied
    import_reply(repos, h.id, sample_replies.WEEKLY)
    v = view(repos, clock)
    assert (v.state, v.blog_id) == ("ready", h.blog_id)
    assert centre_text(v) == strings.RING_READY


def test_paused_hides_waiting_states_only(repos: Repos, clock: FakeClock) -> None:
    paused = Settings(pause_automation=True)
    clock.set(t(11, 10))
    assert view(repos, clock, paused).state == "paused"
    weekly.save_focus(repos, paused, clock, WEEK, "Small teams")
    assert view(repos, clock, paused).state == "paused"
    clock.set(t(13, 18))
    weekly.prepare_packet(repos, paused, clock, "weekly", WEEK)
    assert view(repos, clock, paused).state == "prompt_ready"


def test_answered_counts_this_weeks_answers(repos: Repos, clock: FakeClock) -> None:
    clock.set(t(10, 10))
    from tea.domain import questions as qs

    qs.seed_bank(repos)
    q = repos.questions.list(origin="bank")[0]
    qs.record_answer(repos, q, "login", "yes", week_start=WEEK)
    qs.record_answer(repos, q, "login", "", skipped=True, week_start=WEEK)
    assert view(repos, clock).answered == 1


def test_picked_topic_exposes_stored_candidates(repos: Repos, clock: FakeClock) -> None:
    clock.set(t(12, 9))
    weekly.enter_pick_mode(repos, Settings(), WEEK)

    clock.set(t(13, 18))
    handoff = weekly.prepare_packet(
        repos,
        Settings(),
        clock,
        "weekly_pick",
        WEEK,
    )

    import_reply(repos, handoff.id, sample_replies.WEEKLY_PICK)

    view = week_view(repos, Settings(), clock.now())

    assert view.topic_origin == "auto_trending"
    assert view.focus == "Right-to-repair rules for phones"
    assert view.trend_candidates == [
        {
            "n": 1,
            "topic": "Right-to-repair rules for phones",
            "angle": "What the new rules change for buyers",
            "why": "Covered by two national outlets this week",
            "urls": [
                "https://example.org/a",
                "https://example.org/b",
            ],
        },
        {
            "n": 2,
            "topic": "Four-day week trials",
            "angle": "What the trial data says",
            "why": "Reported by two business papers",
            "urls": ["https://example.org/c"],
        },
        {
            "n": 3,
            "topic": "Open data portals",
            "angle": "Why reuse stays low",
            "why": "",
            "urls": [],
        },
    ]


def test_carried_over_draft_is_exposed_in_week_view(
    repos: Repos,
    clock: FakeClock,
) -> None:
    clock.set(t(13, 18))
    handoff = imported(repos, clock)

    assert handoff.blog_id is not None
    repos.blogs.update(handoff.blog_id, carried_weeks=1)

    view = week_view(repos, Settings(), clock.now())

    assert view.carried_blog_id == handoff.blog_id
    assert view.carried_title == "Small teams need fewer documents, not better ones"
