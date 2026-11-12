"""Drafts list view model (UI_DESIGN 3.3): groups, entries, dates and reading time."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from tea.db.repos import Repos
from tea.db.rows import Blog, Draft
from tea.domain import weekly
from tea.domain.drafts import current_text
from tea.ui import strings
from tea.ui.week_state import short_clock

WORDS_PER_MINUTE = 200
HANDOFF = "handoff"
BLOG = "blog"
GROUP_ORDER = (
    strings.GROUP_WAITING,
    strings.GROUP_READY,
    strings.GROUP_CARRIED,
    strings.GROUP_POSTED,
    strings.GROUP_SHELVED,
)
CHIPS = {
    strings.GROUP_WAITING: (strings.CHIP_PROMPT_READY, "prompt"),
    strings.GROUP_READY: (strings.CHIP_READY, "ready"),
    strings.GROUP_CARRIED: (strings.CHIP_CARRIED, "carried"),
    strings.GROUP_POSTED: (strings.CHIP_POSTED, "posted"),
    strings.GROUP_SHELVED: (strings.CHIP_SHELVED, "shelved"),
}


@dataclass(frozen=True)
class Entry:
    kind: str  # HANDOFF or BLOG
    id: int  # hand-off id or blog id
    title: str
    when: str
    chip_text: str
    chip_state: str
    sort_at: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.kind, self.id)


@dataclass(frozen=True)
class Group:
    name: str
    entries: list[Entry]


def when_text(at: str, now: datetime, *, long: bool = False) -> str:
    """ "Fri 6:02 pm" within the last week, else "6 Nov" (or "6 Nov 2025" in another year)."""
    when = datetime.fromisoformat(at)
    if timedelta(0) <= now - when < timedelta(days=6):
        days = strings.WEEKDAY_LONG if long else strings.WEEKDAY_SHORT
        return f"{days[when.weekday()]} {short_clock(when)}"
    month = strings.MONTH_SHORT[when.month - 1]
    if when.year == now.year:
        return strings.DATE_SHORT.format(day=when.day, month=month)
    return strings.DATE_YEAR.format(day=when.day, month=month, year=when.year)


def word_count(draft: Draft) -> int:
    return len(current_text(draft).split())


def reading_minutes(words: int) -> int:
    return max(1, round(words / WORDS_PER_MINUTE))


def draft_meta(draft: Draft, now: datetime) -> str:
    words = word_count(draft)
    return strings.DRAFT_META.format(
        when=when_text(draft.imported_at, now, long=True),
        words=f"{words:,}",
        minutes=reading_minutes(words),
    )


def blog_group(blog: Blog, latest: Draft) -> str:
    if blog.status == "posted":
        return strings.GROUP_POSTED
    if blog.status == "shelved":
        return strings.GROUP_SHELVED
    if blog.carried_weeks >= 1 and not latest.is_used:
        return strings.GROUP_CARRIED
    return strings.GROUP_READY


def chip_for(group: str) -> tuple[str, str]:
    return CHIPS[group]


def groups(repos: Repos, now: datetime) -> list[Group]:
    found: dict[str, list[Entry]] = {name: [] for name in GROUP_ORDER}
    blogs = {b.id: b for b in repos.blogs.list()}
    for h in repos.handoffs.list(open_only=True):
        blog = blogs.get(h.blog_id) if h.blog_id is not None else None
        if blog is None or blog.status == "shelved":
            continue
        text, state = CHIPS[strings.GROUP_WAITING]
        title = weekly.handoff_title(repos, h) or strings.CHIP_PICK
        found[strings.GROUP_WAITING].append(
            Entry(HANDOFF, h.id, title, when_text(h.created_at, now), text, state, h.created_at)
        )
    for blog in blogs.values():
        latest = repos.drafts.latest_for_blog(blog.id)
        if latest is None:
            continue
        name = blog_group(blog, latest)
        text, state = CHIPS[name]
        at = latest.imported_at
        found[name].append(
            Entry(BLOG, blog.id, latest.title or blog.title, when_text(at, now), text, state, at)
        )
    out = []
    for name in GROUP_ORDER:
        entries = sorted(found[name], key=lambda e: datetime.fromisoformat(e.sort_at), reverse=True)
        if entries:
            out.append(Group(name, entries))
    return out
