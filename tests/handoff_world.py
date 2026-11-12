"""Helpers for hand-off dialog and drafts tests: a weekly blog with a prompt ready."""

from datetime import date

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Handoff
from tea.devtools import sample_replies
from tea.domain import weekly
from tea.handoff.importer import import_reply
from tea.settings import Settings

WEEK = date(2026, 11, 9)
FOCUS = "Why small teams ship faster than big ones"
TITLE = "Small teams need fewer documents, not better ones"


def weekly_handoff(repos: Repos, clock: Clock, settings: Settings | None = None) -> Handoff:
    settings = settings or Settings()
    weekly.save_focus(repos, settings, clock, WEEK, FOCUS)
    open_ = repos.handoffs.list(open_only=True, week_start=WEEK)
    if open_:
        return open_[-1]
    return weekly.prepare_packet(repos, settings, clock, "weekly", WEEK)


def pick_handoff(repos: Repos, clock: Clock, settings: Settings | None = None) -> Handoff:
    settings = settings or Settings()
    weekly.enter_pick_mode(repos, settings, WEEK)
    return weekly.prepare_packet(repos, settings, clock, "weekly_pick", WEEK)


def imported(repos: Repos, clock: Clock, reply: str = sample_replies.WEEKLY) -> Handoff:
    h = weekly_handoff(repos, clock)
    import_reply(repos, h.id, reply)
    got = repos.handoffs.get(h.id)
    assert got is not None
    return got
