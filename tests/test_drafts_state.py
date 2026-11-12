"""Drafts list view model: groups, order, dates."""

from datetime import datetime, timedelta

from handoff_world import TITLE, imported, weekly_handoff

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain import drafts
from tea.settings import Settings
from tea.ui import drafts_state as ds
from tea.ui import strings


def _names(repos: Repos, clock: FakeClock) -> list[str]:
    return [g.name for g in ds.groups(repos, clock.now())]


def test_empty(repos: Repos, clock: FakeClock) -> None:
    assert ds.groups(repos, clock.now()) == []


def test_waiting_then_ready(repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    groups = ds.groups(repos, clock.now())
    assert [g.name for g in groups] == [strings.GROUP_WAITING]
    e = groups[0].entries[0]
    assert (e.kind, e.id, e.chip_text) == (ds.HANDOFF, h.id, strings.CHIP_PROMPT_READY)
    assert e.when == "Fri 5:59 pm"
    imported(repos, clock)
    groups = ds.groups(repos, clock.now())
    assert [g.name for g in groups] == [strings.GROUP_READY]
    assert groups[0].entries[0].title == TITLE


def test_carried_posted_shelved(repos: Repos, clock: FakeClock) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    repos.blogs.update(h.blog_id, carried_weeks=1)
    assert _names(repos, clock) == [strings.GROUP_CARRIED]
    drafts.shelve(repos, h.blog_id)
    assert _names(repos, clock) == [strings.GROUP_SHELVED]
    drafts.revive(repos, Settings(), h.blog_id)
    assert _names(repos, clock) == [strings.GROUP_CARRIED]
    d = repos.drafts.latest_for_blog(h.blog_id)
    assert d is not None
    drafts.mark_posted(repos, d.id)
    assert _names(repos, clock) == [strings.GROUP_POSTED]


def test_regenerate_shows_waiting_and_ready(repos: Repos, clock: FakeClock) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    drafts.regenerate(repos, Settings(), clock, h.blog_id)
    assert _names(repos, clock) == [strings.GROUP_WAITING, strings.GROUP_READY]


def test_when_text_formats() -> None:
    now = datetime.fromisoformat("2026-11-13T18:00:00+03:00")
    assert ds.when_text("2026-11-13T18:02:00+03:00", now + timedelta(minutes=5)) == "Fri 6:02 pm"
    assert ds.when_text("2026-11-13T18:00:00+03:00", now, long=True) == "Friday 6 pm"
    assert ds.when_text("2026-11-01T09:00:00+03:00", now) == "1 Nov"
    assert ds.when_text("2025-11-01T09:00:00+03:00", now) == "1 Nov 2025"


def test_reading_minutes() -> None:
    assert ds.reading_minutes(1184) == 6
    assert ds.reading_minutes(10) == 1
