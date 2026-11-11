"""Job evaluation and catch-up: the pure half of the scheduler (ARCHITECTURE 4).

`load_state` reads the database once; `evaluate(now, state)` returns the actions due, in the
order they must run. Within one pass, evaluate applies its own actions to its working copy
of the state, so a rollover is seen by the improve rule and pick mode by the packet rule
(TESTING scenario 6). The Qt shell that runs it lives in `scheduler_runner.py`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, tzinfo
from typing import Literal

from tea.db.repos import Repos
from tea.domain import improve
from tea.domain.improve import BlogInfo, is_carried, plan_rollover
from tea.domain.questions import LOGIN_JOB
from tea.domain.weekly import (
    FOCUS_JOB,
    NO_FOCUS_JOB,
    PICK_JOB,
    WEEKLY_KINDS,
    elapsed,
    in_catch_up,
)
from tea.domain.weeks import focus_due, pick_due, prompt_due, week_start
from tea.settings import Settings

Trigger = Literal["start", "tick", "wake"]
REMINDER_PAUSE = timedelta(hours=2)  # D6: at most one reminder per 2 hours
OPEN = ("prompt_ready", "copied")


# Actions


@dataclass(frozen=True)
class ShowFocusDialog:
    week: date


@dataclass(frozen=True)
class EnterPickMode:
    week: date


@dataclass(frozen=True)
class PreparePacket:
    kind: str
    week: date
    blog_id: int | None = None  # set for `improve`; weekly packets use the week's blog


@dataclass(frozen=True)
class ShowLoginQuestions:
    pass


@dataclass(frozen=True)
class RemindHandoff:
    handoff_id: int


@dataclass(frozen=True)
class NotifyNoFocus:
    week: date


@dataclass(frozen=True)
class Rollover:
    week: date
    carry: tuple[int, ...] = ()
    shelve: tuple[int, ...] = ()
    expire: tuple[int, ...] = ()


Action = (
    ShowFocusDialog
    | EnterPickMode
    | PreparePacket
    | ShowLoginQuestions
    | RemindHandoff
    | NotifyNoFocus
    | Rollover
)


# State


@dataclass(frozen=True)
class WeekInfo:
    week_start: date
    focus: str | None
    pick_mode: bool
    blog_id: int | None


@dataclass(frozen=True)
class HandoffInfo:
    id: int
    kind: str
    status: str
    week_start: date | None
    blog_id: int | None
    created_at: datetime
    last_reminder_at: datetime | None


@dataclass(frozen=True)
class JobInfo:
    status: str = "pending"
    last_attempt_at: datetime | None = None
    snoozed_until: datetime | None = None


@dataclass(frozen=True)
class SchedulerState:
    settings: Settings
    trigger: Trigger
    weeks: Mapping[date, WeekInfo] = field(default_factory=dict)  # this week and last
    blogs: tuple[BlogInfo, ...] = ()  # weekly blogs
    handoffs: tuple[HandoffInfo, ...] = ()  # not superseded: open ones, this week's, last week's
    jobs: Mapping[tuple[str, date], JobInfo] = field(default_factory=dict)
    rollover_done: frozenset[date] = frozenset()
    login_snoozed_until: datetime | None = None
    handoff_dialog_open: bool = False
    focus_dialog_open: bool = False
    tz: tzinfo | None = None

    def job(self, kind: str, week: date) -> JobInfo:
        return self.jobs.get((kind, week), JobInfo())


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def load_state(
    repos: Repos,
    settings: Settings,
    trigger: Trigger,
    *,
    now: datetime,
    tz: tzinfo,
    handoff_dialog_open: bool = False,
    focus_dialog_open: bool = False,
) -> SchedulerState:
    this = week_start(now.astimezone(tz))
    last = this - timedelta(days=7)
    weeks = {}
    for wk in (last, this):
        w = repos.weeks.get(wk)
        if w is not None:
            weeks[wk] = WeekInfo(wk, w.focus_text, w.pick_mode, w.blog_id)

    week_of = {w.blog_id: w.week_start for w in repos.weeks.list() if w.blog_id is not None}
    blogs = []
    for b in repos.blogs.list(origin="weekly"):
        if b.id not in week_of:
            continue
        drafts = repos.drafts.list_for_blog(b.id) if b.status == "ready" else []
        used = any(d.is_used for d in drafts)
        blogs.append(BlogInfo(b.id, week_of[b.id], b.status, b.carried_weeks, used, bool(drafts)))

    found = {h.id: h for h in repos.handoffs.list(open_only=True)}
    for wk in (last, this):
        found.update((h.id, h) for h in repos.handoffs.list(week_start=wk))
    handoffs = tuple(
        HandoffInfo(h.id, h.kind, h.status, h.week_start, h.blog_id,
                    datetime.fromisoformat(h.created_at), _when(h.last_reminder_at))
        for h in sorted(found.values(), key=lambda h: h.id)
        if h.status != "superseded"
    )  # fmt: skip

    jobs = {}
    for kind in (FOCUS_JOB, PICK_JOB, NO_FOCUS_JOB):
        j = repos.jobs.get(kind, this)
        if j is not None:
            jobs[(kind, this)] = JobInfo(j.status, _when(j.last_attempt_at), _when(j.snoozed_until))
    login = repos.jobs.get(LOGIN_JOB)
    return SchedulerState(
        settings=settings,
        trigger=trigger,
        weeks=weeks,
        blogs=tuple(blogs),
        handoffs=handoffs,
        jobs=jobs,
        rollover_done=frozenset({this}) if improve.rollover_done(repos, this) else frozenset(),
        login_snoozed_until=_when(login.snoozed_until) if login else None,
        handoff_dialog_open=handoff_dialog_open,
        focus_dialog_open=focus_dialog_open,
        tz=tz,
    )


# Evaluation


def _after(now: datetime, moment: datetime | None) -> bool:
    return moment is None or elapsed(now, moment) >= timedelta(0)


def _project_rollover(blogs: list[BlogInfo], plan: improve.RolloverPlan) -> list[BlogInfo]:
    out = []
    for b in blogs:
        if b.id in plan.carry:
            b = replace(b, carried_weeks=b.carried_weeks + 1)
        elif b.id in plan.expire:
            b = replace(b, carried_weeks=b.carried_weeks + 1, status="shelved")
        elif b.id in plan.shelve:
            b = replace(b, status="shelved")
        out.append(b)
    return out


def _focus_due(now: datetime, week: WeekInfo, state: SchedulerState, tz: tzinfo) -> bool:
    s = state.settings
    start = focus_due(week.week_start, s, tz)
    # Monday to Wednesday: until pick mode can start; with the pick switch off, until the prompt.
    end = pick_due(week.week_start, s, tz) if s.pick_enabled else prompt_due(week.week_start, s, tz)
    if week.focus or week.pick_mode or state.focus_dialog_open:
        return False
    if not (_after(now, start) and elapsed(now, end) < timedelta(0)):
        return False
    job = state.job(FOCUS_JOB, week.week_start)
    if job.status == "done" or not _after(now, job.snoozed_until):
        return False
    # Pushed once when it falls due; after that only at a login or a wake.
    return job.last_attempt_at is None or state.trigger in ("start", "wake")


def evaluate(now: datetime, state: SchedulerState, tz: tzinfo | None = None) -> list[Action]:
    s = state.settings
    if s.pause_automation:
        return []  # owner actions (save focus, regenerate) do not go through evaluate
    zone = tz or state.tz or now.tzinfo
    assert zone is not None
    now = now.astimezone(zone)
    this = week_start(now)
    weeks = dict(state.weeks)
    blogs = list(state.blogs)
    out: list[Action] = []

    if this not in state.rollover_done:
        plan = plan_rollover(blogs, this, s.carry_over_weeks)
        out.append(Rollover(this, plan.carry, plan.shelve, plan.expire))
        blogs = _project_rollover(blogs, plan)

    week = weeks.get(this, WeekInfo(this, None, False, None))
    if _focus_due(now, week, state, zone):
        out.append(ShowFocusDialog(this))

    if (
        s.pick_enabled
        and not week.focus
        and not week.pick_mode
        and _after(now, pick_due(this, s, zone))
        and state.job(PICK_JOB, this).status != "done"
    ):
        out.append(EnterPickMode(this))
        week = replace(week, pick_mode=True)
        weeks[this] = week

    if (
        state.trigger == "start"
        and s.questions_per_login > 0
        and _after(now, state.login_snoozed_until)
    ):
        out.append(ShowLoginQuestions())

    for wk in (this - timedelta(days=7), this):
        info = weeks.get(wk)
        if info is None or not (info.focus or info.pick_mode):
            continue
        if not in_catch_up(now, prompt_due(wk, s, zone)):
            continue
        if any(h.kind in WEEKLY_KINDS and h.week_start == wk for h in state.handoffs):
            continue
        kind = "weekly_pick" if info.pick_mode and not info.focus else "weekly"
        out.append(PreparePacket(kind, wk))

    if in_catch_up(now, prompt_due(this, s, zone)):
        for b in blogs:
            if is_carried(b, this) and not any(
                h.kind == "improve" and h.blog_id == b.id and h.week_start == this
                for h in state.handoffs
            ):
                out.append(PreparePacket("improve", this, b.id))
        if not week.focus and not week.pick_mode and state.job(NO_FOCUS_JOB, this).status != "done":
            out.append(NotifyNoFocus(this))

    if s.reminders_enabled and state.trigger in ("start", "wake") and not state.handoff_dialog_open:
        shelved = {b.id for b in blogs if b.status == "shelved"}
        for h in state.handoffs:
            if h.status not in OPEN or h.blog_id in shelved:
                continue
            since = h.last_reminder_at or h.created_at
            if elapsed(now, since) >= REMINDER_PAUSE:
                out.append(RemindHandoff(h.id))
    return out
