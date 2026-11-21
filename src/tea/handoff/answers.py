"""Build the grouped "my answers" section of a packet (ARCHITECTURE section 5).

Which answers count for a blog: bank questions (the owner's general voice), focus questions
for the blog's week, and scope and improvement questions for the blog itself.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

from tea.db.repos import Repos
from tea.db.rows import Answer, Blog, Question

CATEGORY_ORDER = (
    "voice",
    "audience",
    "structure",
    "evidence",
    "experience",
    "boundaries",
    "scope",
    "improve",
)
LABELS = {
    "voice": "Voice",
    "audience": "Audience",
    "structure": "Structure",
    "evidence": "Evidence",
    "experience": "Experience",
    "boundaries": "Boundaries",
    "scope": "Scope of this post",
    "improve": "About the previous draft",
}
_SPACE = re.compile(r"\s+")
SCALE_POINTS = ("1", "2", "3", "4", "5")  # a scale answer is stored as one of these


@dataclass(frozen=True)
class Item:
    question: Question
    answer: Answer
    answered_at: datetime

    @property
    def category(self) -> str:
        return self.question.category

    @property
    def line(self) -> str:
        text = _SPACE.sub(" ", self.answer.answer_text).strip()
        q = self.question
        if q.kind == "scale" and len(q.options) == 2 and text in SCALE_POINTS:
            low, high = q.options
            text = f"{text} of {SCALE_POINTS[-1]} (1 = {low}, {SCALE_POINTS[-1]} = {high})"
        return f"Q: {_SPACE.sub(' ', q.text).strip()} / A: {text}"


def _belongs(q: Question, blog: Blog | None, week: date | None) -> bool:
    if q.origin == "bank":
        return True
    if q.origin == "week":
        return week is not None and q.week_start == week
    return blog is not None and q.blog_id == blog.id


def collect(
    repos: Repos, *, blog: Blog | None, week: date | None, since: datetime | None = None
) -> list[Item]:
    """Newest non-skipped answer per relevant question, optionally only those after `since`."""
    questions = {q.id: q for q in repos.questions.list(active_only=False)}
    newest: dict[int, Item] = {}
    for a in repos.answers.list():
        q = questions.get(a.question_id)
        if q is None or a.skipped or not a.answer_text.strip() or not _belongs(q, blog, week):
            continue
        when = datetime.fromisoformat(a.answered_at)
        if since is not None and when <= since:
            continue
        current = newest.get(q.id)
        if current is None or (when, a.id) > (current.answered_at, current.answer.id):
            newest[q.id] = Item(q, a, when)
    return list(newest.values())


def _words(text: str) -> int:
    return len(text.split())


def render(items: list[Item], max_words: int) -> str:
    """Group in CATEGORY_ORDER. Over the cap, drop the oldest non-boundaries answers first."""
    droppable = sorted(
        (i for i in items if i.category != "boundaries"), key=lambda i: (i.answered_at, i.answer.id)
    )

    def without_oldest(count: int) -> list[Item]:
        gone = {id(i) for i in droppable[:count]}
        return [i for i in items if id(i) not in gone]

    # Fewest drops that fit the cap. Words only fall as more are dropped, so bisect: a long
    # history must not be re-rendered once per dropped answer.
    low, high = 0, len(droppable)
    while low < high:
        mid = (low + high) // 2
        if _words(_format(without_oldest(mid))) > max_words:
            low = mid + 1
        else:
            high = mid
    return _format(without_oldest(low))


def _format(items: list[Item]) -> str:
    groups = []
    for category in CATEGORY_ORDER:
        lines = [
            i.line for i in sorted(items, key=lambda i: i.question.id) if i.category == category
        ]
        if lines:
            groups.append("\n".join([LABELS[category], *lines]))
    return "\n\n".join(groups)


def answers_section(repos: Repos, *, blog: Blog | None, week: date | None, max_words: int) -> str:
    return render(collect(repos, blog=blog, week=week), max_words)


def new_answers(
    repos: Repos, *, blog: Blog | None, week: date | None, since: datetime, max_words: int
) -> str:
    """Only answers given after `since` (the previous version's imported_at)."""
    return render(collect(repos, blog=blog, week=week, since=since), max_words)


def boundaries(repos: Repos, *, blog: Blog | None, week: date | None) -> list[str]:
    """The owner's boundaries answers, oldest first (used as pick-mode off-limits)."""
    items = [i for i in collect(repos, blog=blog, week=week) if i.category == "boundaries"]
    items.sort(key=lambda i: (i.answered_at, i.answer.id))
    return [_SPACE.sub(" ", i.answer.answer_text).strip() for i in items]


def has_focus_answers(repos: Repos, *, week: date | None) -> bool:
    return any(i.question.origin == "week" for i in collect(repos, blog=None, week=week))
