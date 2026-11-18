"""Manual mode (SPEC 5): the New blog form, its scope session and the `manual` hand-off.

The form owns one blog row (origin `manual`, status `scoping`) from the moment the screen
needs it, because attached files are stored per blog. The row has no questions until the
owner presses Start questions; only then does the blog count as in progress. Cancel
deletes the row and tea's copies of its files.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Blog, Handoff, Question
from tea.domain import attachments, weekly
from tea.domain import questions as qs
from tea.settings import Settings

CONTEXT = "blog_scope"
SCOPING = "scoping"
LENGTHS = ("short", "standard", "long")
SOURCES = ("own_documents", "web", "academic")


@dataclass(frozen=True)
class Resume:
    """Where a scope session picks up: all its questions, the first one not yet answered
    or skipped, and the newest stored answer per question id as (text, skipped)."""

    questions: list[Question]
    start: int
    answered: dict[int, tuple[str, bool]] = field(default_factory=dict)


def scope_questions(repos: Repos, blog_id: int) -> list[Question]:
    return repos.questions.list(origin="blog", blog_id=blog_id)


def is_form(repos: Repos, blog: Blog) -> bool:
    return blog.status == SCOPING and not scope_questions(repos, blog.id)


def form_blog(repos: Repos) -> Blog:
    """The New blog form's row: the newest unstarted one, or a fresh one."""
    for blog in reversed(repos.blogs.list(status=SCOPING, origin="manual")):
        if is_form(repos, blog):
            return blog
    return repos.blogs.create("", "", "manual", status=SCOPING)


def start(
    repos: Repos,
    blog_id: int,
    *,
    topic: str,
    scope_notes: str,
    audience: str,
    allowed_sources: Sequence[str],
    length: str,
) -> list[Question]:
    """Save the form and create its 5 to 15 scope questions. Raises ValueError on an empty
    topic, and LookupError when the blog is gone."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic is empty")
    if length not in LENGTHS:
        raise ValueError(f"unknown length {length!r}")
    blog = repos.blogs.get(blog_id)
    if blog is None:
        raise LookupError(f"no blog with id {blog_id}")
    if scope_questions(repos, blog_id):
        return scope_questions(repos, blog_id)  # already started (a second click)
    sources = [s for s in SOURCES if s in allowed_sources]
    with repos.transaction():
        repos.blogs.update(
            blog_id, title=topic, topic=topic, scope_notes=scope_notes.strip(),
            audience=audience.strip(), allowed_sources=sources, length=length,
        )  # fmt: skip
        blog = repos.blogs.get(blog_id)
        assert blog is not None
        has_files = bool(repos.attachments.list_for_blog(blog_id, included_only=True))
        return qs.instantiate_scope(repos, blog, has_files=has_files)


def in_progress(repos: Repos) -> list[Blog]:
    """Started scope sessions, oldest first."""
    blogs = repos.blogs.list(status=SCOPING, origin="manual")
    return [b for b in blogs if scope_questions(repos, b.id)]


def resume(repos: Repos, blog_id: int) -> Resume:
    questions = scope_questions(repos, blog_id)
    ids = {q.id for q in questions}
    answered: dict[int, tuple[str, bool]] = {}
    for a in repos.answers.list(blog_id=blog_id):  # oldest first, so the newest wins
        if a.question_id in ids:
            answered[a.question_id] = (a.answer_text, a.skipped)
    start_at = next((i for i, q in enumerate(questions) if q.id not in answered), len(questions))
    return Resume(questions, start_at, answered)


def waiting(repos: Repos) -> list[Handoff]:
    """Open `manual` hand-offs, oldest first."""
    return [h for h in repos.handoffs.list(open_only=True) if h.kind == "manual"]


def finish(repos: Repos, settings: Settings, clock: Clock, blog_id: int) -> Handoff:
    """Prepare the `manual` hand-off (once) and mark the blog `prompt_ready`.

    Raises `packets.PacketError` when the packet cannot be built.
    """
    existing = [h for h in waiting(repos) if h.blog_id == blog_id]
    if existing:
        return existing[-1]
    with repos.transaction():
        handoff = weekly.prepare_packet(repos, settings, clock, "manual", None, blog_id)
        repos.blogs.set_status(blog_id, "prompt_ready")
    return handoff


def discard_form(repos: Repos, blog_id: int) -> None:
    """Cancel: delete an unstarted form row and tea's copies of its files."""
    blog = repos.blogs.get(blog_id)
    if blog is None or not is_form(repos, blog):
        return
    with repos.transaction():
        for att in repos.attachments.list_for_blog(blog_id):
            attachments.remove(repos, att.id)
        repos.blogs.delete(blog_id)
