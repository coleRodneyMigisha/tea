"""handoff/answers: grouping, newest per question, skipped, cap, new answers."""

from datetime import date

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.db.rows import Blog
from tea.handoff import answers

WEEK = date(2026, 11, 9)


def _bank(repos: Repos, category: str, text: str, key: str) -> int:
    return repos.questions.create(text, "text", category, "bank", bank_key=key).id


def _blog(repos: Repos, title: str = "B") -> Blog:
    return repos.blogs.create(title, title, "weekly")


def _section(repos: Repos, blog: Blog | None = None, week: date | None = WEEK, cap: int = 6000):
    return answers.answers_section(repos, blog=blog, week=week, max_words=cap)


def test_line_format(repos: Repos) -> None:
    q = _bank(repos, "voice", "How do you sound?", "k1")
    repos.answers.add(q, "login", "Dry.")
    assert "Q: How do you sound? / A: Dry." in _section(repos)


def test_grouping_order(repos: Repos) -> None:
    blog = _blog(repos)
    order = ["boundaries", "experience", "evidence", "structure", "audience", "voice"]
    for i, cat in enumerate(order):  # created in reverse, so order must come from the rule
        repos.answers.add(_bank(repos, cat, f"{cat} question", f"k{i}"), "login", f"{cat} answer")
    scope = repos.questions.create("Scope q", "text", "scope", "blog", blog_id=blog.id)
    repos.answers.add(scope.id, "blog_scope", "scope answer", blog_id=blog.id)
    imp = repos.questions.create("Improve q", "text", "improve", "improve", blog_id=blog.id)
    repos.answers.add(imp.id, "login", "improve answer")
    text = _section(repos, blog=blog)
    positions = [text.index(f"{cat} answer") for cat in answers.CATEGORY_ORDER]
    assert positions == sorted(positions)
    assert answers.CATEGORY_ORDER == (
        "voice", "audience", "structure", "evidence", "experience", "boundaries", "scope", "improve"
    )  # fmt: skip


def test_newest_answer_per_question(repos: Repos, clock: FakeClock) -> None:
    q = _bank(repos, "voice", "Voice?", "k1")
    repos.answers.add(q, "login", "old answer")
    clock.advance(days=1)
    repos.answers.add(q, "login", "new answer")
    text = _section(repos)
    assert "new answer" in text
    assert "old answer" not in text
    assert text.count("Q: Voice?") == 1


def test_skipped_excluded(repos: Repos, clock: FakeClock) -> None:
    only_skipped = _bank(repos, "voice", "Skipped question", "k1")
    repos.answers.add(only_skipped, "login", skipped=True)
    later_skip = _bank(repos, "audience", "Audience?", "k2")
    repos.answers.add(later_skip, "login", "real answer")
    clock.advance(days=1)
    repos.answers.add(later_skip, "login", skipped=True)
    text = _section(repos)
    assert "Skipped question" not in text
    assert "real answer" in text  # a later skip does not erase an earlier answer


def test_empty_when_no_answers(repos: Repos) -> None:
    assert _section(repos) == ""


def test_scope_and_focus_answers_belong_to_their_blog_and_week(repos: Repos) -> None:
    mine, other = _blog(repos, "mine"), _blog(repos, "other")
    for blog in (mine, other):
        q = repos.questions.create(f"scope {blog.title}", "text", "scope", "blog", blog_id=blog.id)
        repos.answers.add(q.id, "blog_scope", f"answer {blog.title}", blog_id=blog.id)
    for week, label in ((WEEK, "this"), (date(2026, 11, 2), "last")):
        repos.weeks.ensure(week)
        q = repos.questions.create(f"focus {label}", "text", "experience", "week", week_start=week)
        repos.answers.add(q.id, "monday", f"focus answer {label}", week_start=week)
    text = _section(repos, blog=mine)
    assert "answer mine" in text and "answer other" not in text
    assert "focus answer this" in text and "focus answer last" not in text


def test_cap_drops_oldest_first(repos: Repos, clock: FakeClock) -> None:
    for i in range(5):
        repos.answers.add(_bank(repos, "voice", f"Q{i}", f"k{i}"), "login", f"A{i} " + "w " * 40)
        clock.advance(hours=1)
    text = _section(repos, cap=150)
    assert "A0 " not in text and "A1 " not in text
    assert all(f"A{i} " in text for i in (2, 3, 4))
    assert len(text.split()) <= 150


def test_cap_never_drops_boundaries(repos: Repos, clock: FakeClock) -> None:
    for i in range(3):
        q = _bank(repos, "boundaries", f"B{i}", f"b{i}")
        repos.answers.add(q, "login", f"limit{i} " + "w " * 100)
    clock.advance(days=1)
    for i in range(3):
        repos.answers.add(
            _bank(repos, "voice", f"V{i}", f"v{i}"), "login", f"voice{i} " + "w " * 50
        )
    text = _section(repos, cap=200)
    assert all(f"limit{i}" in text for i in range(3))
    assert not any(f"voice{i}" in text for i in range(3))


def test_new_answers_only_after_since(repos: Repos, clock: FakeClock) -> None:
    blog = _blog(repos)
    old = _bank(repos, "voice", "Old q", "k1")
    repos.answers.add(old, "login", "before")
    cutoff = clock.now()
    same_second = _bank(repos, "audience", "Same q", "k2")
    repos.answers.add(same_second, "login", "at the cutoff")
    clock.advance(minutes=1)
    imp = repos.questions.create("Improve q", "text", "improve", "improve", blog_id=blog.id)
    repos.answers.add(imp.id, "login", "after")
    text = answers.new_answers(repos, blog=blog, week=WEEK, since=cutoff, max_words=6000)
    assert "after" in text
    assert "before" not in text and "at the cutoff" not in text


def test_new_answers_empty_when_nothing_new(repos: Repos, clock: FakeClock) -> None:
    repos.answers.add(_bank(repos, "voice", "Q", "k"), "login", "A")
    clock.advance(minutes=1)
    assert answers.new_answers(repos, blog=None, week=WEEK, since=clock.now(), max_words=99) == ""


def test_scale_answer_shows_its_labels(repos: Repos) -> None:
    q = repos.questions.create(
        "How formal?", "scale", "voice", "bank", options=["Casual", "Formal"], bank_key="s"
    )
    repos.answers.add(q.id, "login", "2")
    assert "A: 2 (on a scale from Casual to Formal)" in _section(repos)


def test_multiline_answer_stays_on_one_line(repos: Repos) -> None:
    repos.answers.add(_bank(repos, "voice", "Q", "k"), "login", "line one\n\nline two")
    assert "A: line one line two" in _section(repos)


def test_boundaries_texts(repos: Repos) -> None:
    repos.answers.add(_bank(repos, "boundaries", "Never?", "k"), "login", "No politics.")
    repos.answers.add(_bank(repos, "voice", "Voice?", "v"), "login", "Dry.")
    assert answers.boundaries(repos, blog=None, week=WEEK) == ["No politics."]
