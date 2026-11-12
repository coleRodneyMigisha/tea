"""The owner's actions on hand-offs and drafts: copy, edit, post, regenerate, check, delete.

The hand-off dialog and the Drafts screen call these; none of them touch Qt. `body_markdown`
is never changed: edits go to `edited_markdown` (SPEC 7).
"""

import logging

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Draft, Handoff
from tea.domain import improve, medium, weekly
from tea.handoff import packets, prompts
from tea.handoff.importer import pick_applies
from tea.logging_setup import log_event
from tea.settings import Settings

__all__ = ["Draft"]

CONTINUE_PROMPT = "continue"
_DRAFT_KINDS = ("weekly", "weekly_pick", "manual", "improve")


def current_text(draft: Draft) -> str:
    """What the owner sees and copies: their edits if any, else the imported text."""
    return draft.edited_markdown if draft.edited_markdown is not None else draft.body_markdown


def _handoff(repos: Repos, handoff_id: int) -> Handoff:
    h = repos.handoffs.get(handoff_id)
    if h is None:
        raise LookupError(f"no hand-off with id {handoff_id}")
    return h


def _draft(repos: Repos, draft_id: int) -> Draft:
    d = repos.drafts.get(draft_id)
    if d is None:
        raise LookupError(f"no draft with id {draft_id}")
    return d


# Hand-off dialog


def copy_prompt(repos: Repos, handoff_id: int) -> str:
    """The prompt text for the clipboard. Marks a waiting hand-off `copied`."""
    h = _handoff(repos, handoff_id)
    if h.status == "prompt_ready":
        repos.handoffs.mark_copied(h.id)
    log_event("prompt_copied", handoff=h.id)
    return h.packet_text


def continue_prompt() -> str:
    """The prompt asking Claude to send a cut-off reply again (prompts/continue.md)."""
    return prompts.render(CONTINUE_PROMPT, {}).text.strip() + "\n"


def set_pick_topic(repos: Repos, handoff_id: int, topic: str) -> bool:
    """File a pick-mode draft under the topic the owner typed (SPEC 3.3).

    The week's focus is set only when the owner has not set one (as on import).
    """
    topic = " ".join(topic.split())
    h = _handoff(repos, handoff_id)
    if not topic or h.blog_id is None:
        return False
    with repos.transaction():
        repos.blogs.update(h.blog_id, topic=topic, topic_origin="auto_trending")
        if h.week_start is not None and pick_applies(repos, h.status, h.week_start):
            repos.weeks.set_focus(h.week_start, topic, "auto_trending")
    log_event("pick_topic_set", handoff=h.id)
    return True


# Draft view


def save_edit(repos: Repos, draft_id: int, text: str) -> None:
    d = _draft(repos, draft_id)
    repos.drafts.set_edited(d.id, None if text == d.body_markdown else text)


def copy_for_medium(repos: Repos, draft_id: int) -> medium.MediumCopy:
    """Render for the clipboard and record `copied_at` (the draft counts as used)."""
    d = _draft(repos, draft_id)
    out = medium.render(current_text(d))
    repos.drafts.mark_copied(d.id)
    log_event("copied_for_medium", draft=d.id)
    return out


def _supersede_open(repos: Repos, blog_id: int, kinds: tuple[str, ...]) -> int | None:
    last = None
    for h in repos.handoffs.list(open_only=True, blog_id=blog_id):
        if h.kind in kinds:
            repos.handoffs.mark_superseded(h.id)
            last = h.id
    return last


def _stop_improving(repos: Repos, blog_id: int) -> None:
    for q in repos.questions.list(origin="improve", blog_id=blog_id):
        repos.questions.set_active(q.id, False)


def mark_posted(repos: Repos, draft_id: int) -> None:
    d = _draft(repos, draft_id)
    with repos.transaction():
        repos.drafts.mark_posted(d.id)
        repos.blogs.set_status(d.blog_id, "posted")
        _stop_improving(repos, d.blog_id)
        _supersede_open(repos, d.blog_id, packets.KINDS)
    log_event("draft_posted", draft=d.id)


def shelve(repos: Repos, blog_id: int) -> None:
    with repos.transaction():
        improve.shelve(repos, blog_id)
        _supersede_open(repos, blog_id, packets.KINDS)


def revive(repos: Repos, settings: Settings, blog_id: int) -> None:
    improve.revive(repos, settings, blog_id)


def delete_version(repos: Repos, draft_id: int) -> None:
    """Delete one version. With none left, the blog is shelved so nothing more is prepared."""
    d = _draft(repos, draft_id)
    with repos.transaction():
        repos.drafts.delete(d.id)
        if not repos.drafts.list_for_blog(d.blog_id):
            improve.shelve(repos, d.blog_id)
    log_event("draft_deleted", draft=d.id)


def _regenerate_kind(repos: Repos, blog_id: int) -> str:
    blog = repos.blogs.get(blog_id)
    if blog is None:
        raise LookupError(f"no blog with id {blog_id}")
    if blog.origin == "manual":
        return "manual"
    return "weekly" if blog.topic.strip() else "weekly_pick"


def regenerate(
    repos: Repos, settings: Settings, clock: Clock, blog_id: int
) -> tuple[Handoff, int | None]:
    """A fresh writing prompt for the blog; returns it and the hand-off it superseded."""
    kind = _regenerate_kind(repos, blog_id)
    with repos.transaction():
        old = _supersede_open(repos, blog_id, _DRAFT_KINDS)
        week = packets.week_of(repos, blog_id)
        new = weekly.prepare_packet(repos, settings, clock, kind, week, blog_id)
    log_event("handoff_regenerated", handoff=new.id, kind=kind)
    return new, old


def second_pass(
    repos: Repos, settings: Settings, clock: Clock, blog_id: int
) -> tuple[Handoff, int | None]:
    """An `audit` hand-off for the blog's latest draft (Second-pass check, SPEC 3.3)."""
    with repos.transaction():
        old = _supersede_open(repos, blog_id, ("audit",))
        week = packets.week_of(repos, blog_id)
        new = weekly.prepare_packet(repos, settings, clock, "audit", week, blog_id)
    log_event("handoff_audit", logging.INFO, handoff=new.id)
    return new, old
