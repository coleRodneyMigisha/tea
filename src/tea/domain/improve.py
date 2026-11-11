"""Week rollover: carry, shelve, most-recent-only, improvement questions (ARCHITECTURE 4).

`plan_rollover` is pure, so the scheduler can plan a rollover and act on its result in the
same pass. `apply_rollover` writes the plan. Nothing here ever deletes a blog or a draft.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from tea.db.repos import Repos
from tea.domain import questions as qs
from tea.settings import Settings

ROLLOVER_KEY = "rollover_done_{week}"


@dataclass(frozen=True)
class BlogInfo:
    """What rollover and the improve rule need to know about one weekly blog."""

    id: int
    week_start: date
    status: str
    carried_weeks: int
    used: bool  # any version copied for Medium or marked posted (D3)
    has_draft: bool


@dataclass(frozen=True)
class RolloverPlan:
    carry: tuple[int, ...] = ()  # stays ready, carried_weeks + 1, improvement questions
    shelve: tuple[int, ...] = ()  # older candidates: only the most recent carries
    expire: tuple[int, ...] = ()  # carried_weeks + 1 went past the limit: shelved


def plan_rollover(blogs: Sequence[BlogInfo], week: date, limit: int) -> RolloverPlan:
    """The plan for the first evaluate in `week`: ready, unused weekly drafts from before it."""
    candidates = sorted(
        (b for b in blogs if b.week_start < week and b.status == "ready" and b.has_draft
         and not b.used),
        key=lambda b: (b.week_start, b.id),
    )  # fmt: skip
    if not candidates:
        return RolloverPlan()
    newest, older = candidates[-1], candidates[:-1]
    shelve = tuple(b.id for b in older)
    if newest.carried_weeks + 1 > limit:
        return RolloverPlan(shelve=shelve, expire=(newest.id,))
    return RolloverPlan(carry=(newest.id,), shelve=shelve)


def is_carried(b: BlogInfo, week: date) -> bool:
    """A carried-over, unshelved draft that gets an improve prompt in `week`."""
    return (
        b.week_start < week
        and b.status == "ready"
        and b.carried_weeks >= 1
        and b.has_draft
        and not b.used
    )


def rollover_done(repos: Repos, week: date) -> bool:
    return repos.meta.get(ROLLOVER_KEY.format(week=week.isoformat())) is not None


def apply_rollover(repos: Repos, week: date, plan: RolloverPlan) -> None:
    with repos.transaction():
        for blog_id in plan.carry:
            blog = repos.blogs.get(blog_id)
            if blog is None:
                continue
            repos.blogs.update(blog_id, carried_weeks=blog.carried_weeks + 1)
            add_improve_questions(repos, blog_id)
        for blog_id in plan.expire:
            blog = repos.blogs.get(blog_id)
            if blog is not None:
                repos.blogs.update(blog_id, carried_weeks=blog.carried_weeks + 1)
                shelve(repos, blog_id)
        for blog_id in plan.shelve:
            shelve(repos, blog_id)
        repos.meta.set(ROLLOVER_KEY.format(week=week.isoformat()), "done")


def add_improve_questions(repos: Repos, blog_id: int) -> None:
    blog = repos.blogs.get(blog_id)
    draft = repos.drafts.latest_for_blog(blog_id)
    if blog is None or draft is None:
        return
    qs.instantiate_improve(repos, blog, draft.title or blog.title)


def shelve(repos: Repos, blog_id: int) -> None:
    """Keep the draft; stop automatic work and its improvement questions."""
    with repos.transaction():
        if repos.blogs.get(blog_id) is None:
            return
        repos.blogs.set_status(blog_id, "shelved")
        for q in repos.questions.list(origin="improve", blog_id=blog_id):
            repos.questions.set_active(q.id, False)


def revive(repos: Repos, settings: Settings, blog_id: int) -> None:
    """Carry a shelved draft for one more week: next Friday it gets an improve prompt."""
    with repos.transaction():
        if repos.blogs.get(blog_id) is None:
            return
        # At the next rollover carried_weeks + 1 passes the limit, so it shelves again.
        carried = max(settings.carry_over_weeks, 1)
        repos.blogs.update(blog_id, status="ready", carried_weeks=carried)
        add_improve_questions(repos, blog_id)
