"""What the This week screen shows (UI_DESIGN 3.1), worked out from the database without Qt.

Ring states, in order of precedence: Prompt ready and Ready (the work exists, so they show
even while paused), then Paused, then No focus, Pick mode and Steeping.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from tea.db.repos import Repos
from tea.domain.weekly import WEEKLY_KINDS, elapsed, pick_time, week_blog
from tea.domain.weeks import prompt_due, week_start
from tea.settings import Settings
from tea.ui import strings

OPEN = ("prompt_ready", "copied")


@dataclass(frozen=True)
class WeekView:
    state: str  # no_focus | steeping | pick | prompt_ready | ready | paused
    progress: float
    due: datetime
    remaining: timedelta
    focus: str | None
    topic_origin: str
    carried_blog_id: int | None
    carried_title: str | None
    trend_candidates: list[dict[str, Any]]
    pick_mode: bool
    pick_soon: bool  # pick day, before pick time: "tea will ask Claude to pick a topic at 9 am"
    pick_time: datetime
    copied: bool
    handoff_id: int | None
    blog_id: int | None
    answered: int


def progress(now: datetime, settings: Settings) -> float:
    """(now - Monday 00:00) / (prompt time - Monday 00:00), clamped to 0..1."""
    tz = now.tzinfo
    assert tz is not None
    monday = datetime.combine(week_start(now), datetime.min.time(), tzinfo=tz)
    due = prompt_due(monday.date(), settings, tz)
    span = elapsed(due, monday).total_seconds()
    if span <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed(now, monday).total_seconds() / span))


def _plural(forms: tuple[str, str], n: int) -> str:
    return (forms[0] if n == 1 else forms[1]).format(n=n)


def remaining_text(delta: timedelta) -> str:
    """ "2 days 4 hours", "3 hours 10 min", "45 min". Whole minutes, never "0" before due."""
    seconds = delta.total_seconds()
    minutes = max(0, int(seconds // 60))
    if seconds > 0 and minutes == 0:
        minutes = 1
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days:
        parts = [_plural(strings.DAYS, days)] + ([_plural(strings.HOURS, hours)] if hours else [])
    elif hours:
        parts = [_plural(strings.HOURS, hours)] + ([strings.MINUTES.format(n=mins)] if mins else [])
    else:
        parts = [strings.MINUTES.format(n=mins)]
    return " ".join(parts)


def short_clock(when: datetime) -> str:
    """ "6 pm", "8:30 pm"."""
    hour = when.hour % 12 or 12
    suffix = strings.AM if when.hour < 12 else strings.PM
    return f"{hour} {suffix}" if when.minute == 0 else f"{hour}:{when.minute:02d} {suffix}"


def week_view(repos: Repos, settings: Settings, now: datetime) -> WeekView:
    tz = now.tzinfo
    assert tz is not None
    this = week_start(now)
    w = repos.weeks.get(this)
    focus = w.focus_text if w is not None else None
    pick_mode = bool(w and w.pick_mode)
    blog = week_blog(repos, this)
    due = prompt_due(this, settings, tz)
    pick_at = pick_time(this, settings, tz)

    carried_blog_id: int | None = None
    carried_title: str | None = None

    for candidate in reversed(repos.blogs.list(origin="weekly", status="ready")):
        if candidate.carried_weeks < 1:
            continue
        draft = repos.drafts.latest_for_blog(candidate.id)
        if draft is None:
            continue
        carried_blog_id = candidate.id
        carried_title = draft.title
        break

    handoff = None
    for h in repos.handoffs.list(open_only=True, week_start=this):
        if h.kind in WEEKLY_KINDS:
            handoff = h
    ready = blog is not None and blog.status == "ready" and handoff is None
    if handoff is not None:
        state = "prompt_ready"
    elif ready:
        state = "ready"
    elif settings.pause_automation:
        state = "paused"
    elif focus:
        state = "steeping"
    elif pick_mode:
        state = "pick"
    else:
        state = "no_focus"
    pick_soon = (
        state == "no_focus"
        and settings.pick_enabled
        and now.date() == pick_at.date()
        and elapsed(now, pick_at) < timedelta(0)
    )
    answered = sum(1 for a in repos.answers.list(week_start=this) if not a.skipped)
    return WeekView(
        state=state,
        progress=1.0 if state in ("prompt_ready", "ready") else progress(now, settings),
        due=due,
        remaining=elapsed(due, now),
        focus=focus,
        topic_origin=w.topic_origin if w is not None else "owner",
        trend_candidates=list(w.trend_candidates or []) if w is not None else [],
        carried_blog_id=carried_blog_id,
        carried_title=carried_title,
        pick_mode=pick_mode,
        pick_soon=pick_soon,
        pick_time=pick_at,
        copied=handoff is not None and handoff.status == "copied",
        handoff_id=handoff.id if handoff is not None else None,
        blog_id=blog.id if blog is not None else None,
        answered=answered,
    )


def centre_text(v: WeekView) -> str:
    return {
        "no_focus": strings.RING_NO_FOCUS,
        "prompt_ready": strings.RING_PROMPT_READY,
        "ready": strings.RING_READY,
        "paused": strings.RING_PAUSED,
    }.get(v.state, remaining_text(v.remaining))


def centre_caption(v: WeekView) -> str:
    return strings.RING_UNTIL if v.state in ("steeping", "pick") else ""


def caption_text(v: WeekView) -> str:
    """The muted line under the ring's button, or ''."""
    if v.state == "prompt_ready" and v.copied:
        return strings.WAITING_FOR_REPLY
    if v.pick_soon:
        return strings.PICK_SOON.format(time=short_clock(v.pick_time))
    return ""


def ring_sentence(v: WeekView) -> str:
    """accessibleName for the ring: "Prompt due Friday 6 pm, 2 days 4 hours left"."""
    day, time = strings.WEEKDAY_LONG[v.due.weekday()], short_clock(v.due)
    left = remaining_text(v.remaining)
    if v.state == "prompt_ready":
        return strings.RING_SENTENCE_COPIED if v.copied else strings.RING_PROMPT_READY
    if v.state == "ready":
        return strings.RING_READY
    if v.state == "paused":
        return strings.RING_PAUSED
    if v.state == "no_focus":
        return strings.RING_SENTENCE_NO_FOCUS.format(day=day, time=time)
    if v.state == "pick":
        return strings.RING_SENTENCE_PICK.format(day=day, time=time, left=left)
    return strings.RING_SENTENCE.format(day=day, time=time, left=left)
