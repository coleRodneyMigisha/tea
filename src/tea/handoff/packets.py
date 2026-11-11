"""Build a packet (the prompt text) for each hand-off kind from DB state (ARCHITECTURE 5)."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Attachment, Blog, Draft
from tea.handoff import answers, prompts
from tea.settings import Settings

KINDS = ("weekly", "weekly_pick", "manual", "improve", "audit")
LENGTH_WORDS = {"short": "600 to 900", "standard": "1,000 to 1,500", "long": "1,800 to 2,500"}
SOURCE_NAMES = {
    "own_documents": "my documents",
    "web": "web sources",
    "academic": "academic papers",
}
RECENT_WEEKS = 8
TOPIC_PICKED_NOTE = "Topic picked by tea. No answers were given for this focus."


class PacketError(ValueError):
    """The packet cannot be built: no such blog, no weekly blog for the week, no draft."""


@dataclass(frozen=True)
class Packet:
    text: str
    words: int
    kind: str
    prompt_versions: dict[str, int]
    attachments: list[Attachment] = field(default_factory=list)
    blog_id: int | None = None
    week_start: date | None = None


def collapse(text: str) -> str:
    """Blank out whitespace-only lines, collapse 3+ newlines to 2, end with one newline."""
    text = re.sub(r"[ \t]+\n", "\n", text.replace("\r\n", "\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def build(
    kind: str,
    repos: Repos,
    settings: Settings,
    clock: Clock,
    *,
    blog_id: int | None = None,
    week: date | None = None,
) -> Packet:
    if kind not in KINDS:
        raise PacketError(f"unknown hand-off kind {kind!r}")
    blog = _blog(repos, blog_id, week)
    week = week_of(repos, blog.id)  # the blog's own week, never the caller's (improve, audit)
    builder = _Builder(kind, repos, settings, clock, blog, week)
    text = builder.text()
    return Packet(
        text=text,
        words=len(text.split()),
        kind=kind,
        prompt_versions=builder.versions,
        attachments=builder.files,
        blog_id=blog.id,
        week_start=week,
    )


def _blog(repos: Repos, blog_id: int | None, week: date | None) -> Blog:
    if blog_id is None:
        w = repos.weeks.get(week) if week is not None else None
        if w is None or w.blog_id is None:
            raise PacketError(f"no weekly blog for the week of {week}")
        blog_id = w.blog_id
    blog = repos.blogs.get(blog_id)
    if blog is None:
        raise PacketError(f"no blog with id {blog_id}")
    return blog


def week_of(repos: Repos, blog_id: int) -> date | None:
    """The week a weekly blog belongs to, or None (manual blogs)."""
    return next((w.week_start for w in repos.weeks.list() if w.blog_id == blog_id), None)


class _Builder:
    def __init__(
        self,
        kind: str,
        repos: Repos,
        settings: Settings,
        clock: Clock,
        blog: Blog,
        week: date | None,
    ) -> None:
        self.kind, self.repos, self.settings, self.clock = kind, repos, settings, clock
        self.blog, self.week = blog, week
        self.versions: dict[str, int] = {}
        self.files: list[Attachment] = []

    def _render(self, name: str, values: dict[str, str]) -> str:
        out = prompts.render(name, values)
        self.versions[out.name] = out.version
        return out.text

    def _block(self, name: str, values: dict[str, str]) -> str:
        """An optional block, followed by a blank line so neighbouring blocks stay apart."""
        return self._render(name, values).strip() + "\n"

    def text(self) -> str:
        if self.kind == "improve":
            return collapse(self._improve())
        if self.kind == "audit":
            return collapse(self._audit())
        return collapse(self._draft())

    # Shared pieces

    def _answers(self) -> str:
        return answers.answers_section(
            self.repos, blog=self.blog, week=self.week, max_words=self.settings.max_answer_words
        )

    def _style_notes(self) -> str:
        return self.settings.style_notes.strip() if self.settings.include_style_notes else ""

    def _length(self) -> str:
        return LENGTH_WORDS.get(self.blog.length, LENGTH_WORDS["standard"])

    def _attachments(self) -> str:
        self.files = self.repos.attachments.list_for_blog(self.blog.id, included_only=True)
        if not self.files:
            return ""
        file_list = "\n".join(f"- {a.filename}" for a in self.files)
        return self._block("blocks/attachments", {"file_list": file_list})

    def _latest_draft(self) -> Draft:
        draft = self.repos.drafts.latest_for_blog(self.blog.id)
        if draft is None:
            raise PacketError(f"blog {self.blog.id} has no draft to {self.kind}")
        return draft

    # Kinds

    def _draft(self) -> str:
        pick = self.kind == "weekly_pick"
        values = {
            "brief": self._brief(pick),
            "answers_section": self._answers(),
            "style_notes": self._style_notes(),
            "attachments_section": self._attachments(),
            "pick_section": self._pick() if pick else "",
            "research_section": self._research(force_on=pick),
            "length_words": self._length(),
            "topic_origin_note": self._topic_origin_note(),
        }
        return self._render("packet_draft", values)

    def _improve(self) -> str:
        draft = self._latest_draft()
        since = datetime.fromisoformat(draft.imported_at)
        values = {
            "previous_markdown": (draft.edited_markdown or draft.body_markdown).strip(),
            "owner_edited": "yes" if draft.edited_markdown is not None else "no",
            "new_answers": answers.new_answers(
                self.repos,
                blog=self.blog,
                week=self.week,
                since=since,
                max_words=self.settings.max_answer_words,
            ),
            "answers_section": self._answers(),
            "style_notes": self._style_notes(),
            "attachments_section": self._attachments(),
            "length_words": self._length(),
        }
        return self._render("packet_improve", values)

    def _audit(self) -> str:
        draft = self._latest_draft()
        values = {
            "draft_markdown": (draft.edited_markdown or draft.body_markdown).strip(),
            "answers_section": self._answers(),
            "attachments_section": self._attachments(),
            "length_words": self._length(),
        }
        return self._render("packet_audit", values)

    # Sections of packet_draft

    def _brief(self, pick: bool) -> str:
        b = self.blog
        w = self.repos.weeks.get(self.week) if self.week else None
        topic = b.topic or (w.focus_text if w and w.focus_text else "")
        if pick or not topic:
            topic = "not chosen yet. Choose one as described in <topic_pick>."
        lines = [f"Topic: {topic}"]
        if b.title and b.title != b.topic and not pick:
            lines.append(f"Working title: {b.title}")
        if b.scope_notes.strip():
            lines.append(f"What it should cover: {b.scope_notes.strip()}")
        if b.audience.strip():
            lines.append(f"Who it is for: {b.audience.strip()}")
        lines.append(f"Length: {b.length}, {self._length()} words")
        return "\n".join(lines)

    def _research(self, *, force_on: bool) -> str:
        allowed = self.blog.allowed_sources
        if force_on or {"web", "academic"} & set(allowed):
            types = [
                SOURCE_NAMES[s] for s in SOURCE_NAMES if s in allowed or force_on and s == "web"
            ]
            return self._block("blocks/research_on", {"allowed_types": ", ".join(types)})
        return self._block("blocks/research_off", {})

    def _topic_origin_note(self) -> str:
        if self.blog.topic_origin != "auto_trending":
            return ""
        return "" if answers.has_focus_answers(self.repos, week=self.week) else TOPIC_PICKED_NOTE

    def _pick(self) -> str:
        off_limits = answers.boundaries(self.repos, blog=self.blog, week=self.week)
        today = self.clock.now()
        values = {
            "interests": ", ".join(self.settings.interests) or "none given",
            "region": self.settings.region.strip() or "not set",
            "today": f"{today:%A} {today.day} {today:%B %Y}",
            "recent_topics": "; ".join(self._recent_topics(today)) or "none",
            "off_limits": "; ".join(off_limits) or "none given",
        }
        return self._block("blocks/pick_topic", values)

    def _recent_topics(self, now: datetime) -> list[str]:
        """Focus of the previous 8 weeks, plus topics of blogs drafted in the last 8 weeks."""
        current = self.week or now.date() - timedelta(days=now.weekday())
        earliest = current - timedelta(weeks=RECENT_WEEKS)
        topics = [
            w.focus_text
            for w in self.repos.weeks.list()
            if w.focus_text and earliest <= w.week_start < current
        ]
        cutoff = now - timedelta(weeks=RECENT_WEEKS)
        for blog in self.repos.blogs.list():
            if blog.id == self.blog.id or not blog.topic:
                continue
            drafts = self.repos.drafts.list_for_blog(blog.id)
            if any(datetime.fromisoformat(d.imported_at) >= cutoff for d in drafts):
                topics.append(blog.topic)
        seen: set[str] = set()
        unique = []
        for t in topics:
            if t.strip().lower() not in seen:
                seen.add(t.strip().lower())
                unique.append(t.strip())
        return unique
