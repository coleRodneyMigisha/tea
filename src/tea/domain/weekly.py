"""The weekly blog: focus, pick mode, packet preparation and regenerate (SPEC 4).

The scheduler decides *when*; these functions do the work and keep the database consistent.
"""

from datetime import UTC, date, datetime, timedelta, tzinfo

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Blog, Handoff
from tea.domain import questions as qs
from tea.domain.weeks import pick_due, prompt_due
from tea.handoff import packets
from tea.settings import Settings

# Owner decision (M5): weekly posts may use the owner's files and web research.
WEEKLY_SOURCES = ("own_documents", "web")
WEEKLY_KINDS = ("weekly", "weekly_pick")
CATCH_UP = timedelta(days=7)  # SPEC 4.3: prepared at the first start or wake within 7 days
FOCUS_JOB = "focus_prompt"
PICK_JOB = "pick_mode"
NO_FOCUS_JOB = "no_focus_notice"


def elapsed(now: datetime, since: datetime) -> timedelta:
    """Real time between two instants (offsets honoured even when both share one tzinfo)."""
    return now.astimezone(UTC) - since.astimezone(UTC)


def in_catch_up(now: datetime, due: datetime) -> bool:
    return timedelta(0) <= elapsed(now, due) <= CATCH_UP


def pick_time(week: date, settings: Settings, tz: tzinfo) -> datetime:
    """When pick mode starts: the pick time, or the prompt time if that comes first."""
    return min(pick_due(week, settings, tz), prompt_due(week, settings, tz))


def week_blog(repos: Repos, week: date) -> Blog | None:
    w = repos.weeks.get(week)
    return repos.blogs.get(w.blog_id) if w is not None and w.blog_id is not None else None


def _new_blog(repos: Repos, settings: Settings, week: date, topic: str, origin: str) -> Blog:
    blog = repos.blogs.create(
        topic, topic, "weekly",
        length=settings.default_length, allowed_sources=WEEKLY_SOURCES, topic_origin=origin,
    )  # fmt: skip
    repos.weeks.set_blog(week, blog.id)
    return blog


def save_focus(
    repos: Repos, settings: Settings, clock: Clock, week: date, text: str
) -> Handoff | None:
    """Set the owner's focus for `week`: week row, blog, focus questions, end of pick mode.

    If the focus changed while a weekly prompt for the week was waiting, that prompt is
    superseded, and a new `weekly` one is prepared at once when the prompt time has passed.
    Returns that new hand-off, if any.
    """
    text = text.strip()
    if not text:
        raise ValueError("focus is empty")
    with repos.transaction():
        w = repos.weeks.ensure(week)
        changed = w.focus_text != text or w.topic_origin != "owner"
        topic_changed = w.focus_text != text
        if changed:
            repos.weeks.set_focus(week, text, "owner")
        repos.weeks.set_pick_mode(week, False)
        blog = week_blog(repos, week)
        redo = False
        if blog is None:
            _new_blog(repos, settings, week, text, "owner")
        elif repos.drafts.latest_for_blog(blog.id) is not None:
            # A draft is already imported: keep it, and start a new weekly blog for the new topic.
            if topic_changed:
                _new_blog(repos, settings, week, text, "owner")
                redo = True
        else:
            repos.blogs.update(blog.id, title=text, topic=text, topic_origin="owner")
        qs.instantiate_focus(repos, week, text)
        repos.jobs.set_status(FOCUS_JOB, "done", week)
        superseded = False
        if changed:
            for h in repos.handoffs.list(open_only=True, week_start=week):
                if h.kind in WEEKLY_KINDS:
                    repos.handoffs.mark_superseded(h.id)
                    superseded = True
    if redo:
        return prepare_packet(repos, settings, clock, "weekly", week)
    if superseded and in_catch_up(clock.now(), prompt_due(week, settings, clock.tz())):
        return prepare_packet(repos, settings, clock, "weekly", week)
    return None


def enter_pick_mode(repos: Repos, settings: Settings, week: date) -> None:
    """Friday's prompt will ask Claude to pick the topic. Creates the week's blog if needed."""
    with repos.transaction():
        repos.weeks.ensure(week)
        repos.weeks.set_pick_mode(week, True)
        if week_blog(repos, week) is None:
            _new_blog(repos, settings, week, "", "auto_trending")
        repos.jobs.set_status(PICK_JOB, "done", week)


def note_focus_shown(repos: Repos, week: date) -> bool:
    """Record that the focus dialog was pushed. True the first time this week."""
    job = repos.jobs.get(FOCUS_JOB, week)
    repos.jobs.record_attempt(FOCUS_JOB, week)
    return job is None or job.last_attempt_at is None


def dismiss_focus(repos: Repos, clock: Clock, week: date, *, minutes: int) -> None:
    """Not now: the dialog stays away for `minutes`, then returns at the next login or wake."""
    with repos.transaction():
        repos.jobs.set_status(FOCUS_JOB, "dismissed", week)
        repos.jobs.snooze(FOCUS_JOB, clock.now() + timedelta(minutes=minutes), week)


def note_no_focus(repos: Repos, week: date) -> None:
    repos.jobs.set_status(NO_FOCUS_JOB, "done", week)


def prepare_packet(
    repos: Repos,
    settings: Settings,
    clock: Clock,
    kind: str,
    week: date | None,
    blog_id: int | None = None,
) -> Handoff:
    """Build the prompt and store it as a `prompt_ready` hand-off for `week`.

    Raises `packets.PacketError` when the packet cannot be built.
    """
    packet = packets.build(kind, repos, settings, clock, blog_id=blog_id, week=week)
    with repos.transaction():
        handoff = repos.handoffs.create(
            kind, packet.text, packet.words, packet.prompt_versions,
            blog_id=packet.blog_id, week_start=week,
        )  # fmt: skip
        blog = repos.blogs.get(packet.blog_id) if packet.blog_id is not None else None
        if kind in WEEKLY_KINDS and blog is not None and blog.status == "queued":
            repos.blogs.set_status(blog.id, "prompt_ready")
        if kind == "improve":
            repos.jobs.set_status("improve_packet", "done", week, packet.blog_id or 0)
        elif kind in WEEKLY_KINDS:
            repos.jobs.set_status("weekly_packet", "done", week)
    return handoff


def regenerate(repos: Repos, settings: Settings, clock: Clock, handoff_id: int) -> Handoff:
    """Supersede a hand-off and prepare a fresh one of the same kind."""
    old = repos.handoffs.get(handoff_id)
    if old is None:
        raise LookupError(f"no hand-off with id {handoff_id}")
    kind = old.kind
    if kind == "weekly_pick" and old.week_start is not None:
        w = repos.weeks.get(old.week_start)
        if w is not None and w.focus_text and w.topic_origin == "owner":
            kind = "weekly"
    with repos.transaction():
        repos.handoffs.mark_superseded(old.id)
        return prepare_packet(repos, settings, clock, kind, old.week_start, old.blog_id)


def handoff_title(repos: Repos, handoff: Handoff) -> str:
    """The working title or topic for notifications; '' while Claude has not picked one."""
    blog = repos.blogs.get(handoff.blog_id) if handoff.blog_id is not None else None
    if blog is None:
        return ""
    if handoff.kind == "improve":
        draft = repos.drafts.latest_for_blog(blog.id)
        if draft is not None and draft.title:
            return draft.title
    return blog.title or blog.topic
