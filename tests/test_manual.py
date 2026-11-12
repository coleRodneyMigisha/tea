"""domain/manual: the New blog form row, scope sessions, resume and the manual hand-off."""

import itertools
import re
from pathlib import Path

import pytest

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.domain import attachments, manual
from tea.domain import questions as qs
from tea.settings import Settings

SOURCES = ("own_documents", "web", "academic")


def _start(repos: Repos, **fields: object) -> int:
    blog = manual.form_blog(repos)
    values: dict[str, object] = {
        "topic": "Green tea at work",
        "scope_notes": "",
        "audience": "",
        "allowed_sources": ["own_documents"],
        "length": "standard",
    }
    values.update(fields)
    manual.start(repos, blog.id, **values)  # type: ignore[arg-type]
    return blog.id


def _answer(repos: Repos, blog_id: int, n: int, *, skip_at: int | None = None) -> None:
    for i, q in enumerate(manual.resume(repos, blog_id).questions[:n]):
        qs.record_answer(
            repos, q, manual.CONTEXT, "" if i == skip_at else f"answer {i}",
            skipped=i == skip_at, blog_id=blog_id,
        )  # fmt: skip


# The form row


def test_form_blog_is_reused_until_questions_start(repos: Repos) -> None:
    first = manual.form_blog(repos)
    assert (first.origin, first.status) == ("manual", "scoping")
    assert manual.form_blog(repos).id == first.id
    assert manual.in_progress(repos) == []
    _start(repos)
    assert manual.form_blog(repos).id != first.id


def test_start_requires_a_topic(repos: Repos) -> None:
    blog = manual.form_blog(repos)
    with pytest.raises(ValueError):
        manual.start(
            repos, blog.id, topic="   ", scope_notes="", audience="",
            allowed_sources=[], length="standard",
        )  # fmt: skip
    assert repos.questions.list(origin="blog", blog_id=blog.id) == []


def test_start_saves_the_form(repos: Repos) -> None:
    bid = _start(
        repos, topic="  Tea  ", scope_notes="Cover it", audience="Office staff",
        allowed_sources=["web", "own_documents"], length="long",
    )  # fmt: skip
    blog = repos.blogs.get(bid)
    assert blog is not None
    assert (blog.title, blog.topic, blog.scope_notes, blog.audience) == (
        "Tea", "Tea", "Cover it", "Office staff",
    )  # fmt: skip
    assert (blog.length, blog.status) == ("long", "scoping")
    assert sorted(blog.allowed_sources) == ["own_documents", "web"]
    assert manual.in_progress(repos)[-1].id == bid


def test_start_twice_does_not_duplicate_questions(repos: Repos) -> None:
    bid = _start(repos)
    count = len(repos.questions.list(origin="blog", blog_id=bid))
    manual.start(
        repos, bid, topic="Green tea at work", scope_notes="", audience="",
        allowed_sources=["own_documents"], length="standard",
    )  # fmt: skip
    assert len(repos.questions.list(origin="blog", blog_id=bid)) == count
    assert len(repos.blogs.list(origin="manual")) == 1


@pytest.mark.parametrize(
    ("sources", "length", "notes", "audience", "files"),
    list(
        itertools.product(
            [list(c) for n in range(4) for c in itertools.combinations(SOURCES, n)],
            ["short", "standard", "long"],
            ["", "notes"],
            ["", "readers"],
            [False, True],
        )
    ),
)
def test_question_count_within_5_and_15(
    repos: Repos, sources: list[str], length: str, notes: str, audience: str, files: bool,
    tmp_path: Path,
) -> None:  # fmt: skip
    blog = manual.form_blog(repos)
    if files:
        src = tmp_path / "notes.txt"
        src.write_text("x")
        attachments.add(repos, blog.id, src)
    manual.start(
        repos, blog.id, topic="T", scope_notes=notes, audience=audience,
        allowed_sources=sources, length=length,
    )  # fmt: skip
    n = len(manual.resume(repos, blog.id).questions)
    assert qs.SCOPE_MIN <= n <= qs.SCOPE_MAX


def test_left_out_files_do_not_count_as_files(repos: Repos, tmp_path: Path) -> None:
    blog = manual.form_blog(repos)
    src = tmp_path / "notes.txt"
    src.write_text("x")
    att = attachments.add(repos, blog.id, src)
    attachments.set_included(repos, att.id, False)
    manual.start(
        repos, blog.id, topic="T", scope_notes="", audience="",
        allowed_sources=["own_documents"], length="standard",
    )  # fmt: skip
    keys = {q.template_key for q in manual.resume(repos, blog.id).questions}
    assert "s-files-parts" not in keys


# Resume


def test_resume_starts_at_the_first_question(repos: Repos) -> None:
    bid = _start(repos)
    r = manual.resume(repos, bid)
    assert r.start == 0 and r.answered == {}


def test_resume_lands_after_answers_and_skips(repos: Repos) -> None:
    bid = _start(repos)
    _answer(repos, bid, 3, skip_at=1)
    r = manual.resume(repos, bid)
    assert r.start == 3
    q = r.questions
    assert r.answered == {
        q[0].id: ("answer 0", False), q[1].id: ("", True), q[2].id: ("answer 2", False),
    }  # fmt: skip


def test_resume_lands_on_a_gap(repos: Repos) -> None:
    bid = _start(repos)
    r = manual.resume(repos, bid)
    for i in (0, 2):
        qs.record_answer(repos, r.questions[i], manual.CONTEXT, "a", blog_id=bid)
    assert manual.resume(repos, bid).start == 1


def test_resume_uses_the_newest_answer(repos: Repos) -> None:
    bid = _start(repos)
    q = manual.resume(repos, bid).questions[0]
    qs.record_answer(repos, q, manual.CONTEXT, "first", blog_id=bid)
    qs.record_answer(repos, q, manual.CONTEXT, "second", blog_id=bid)
    assert manual.resume(repos, bid).answered[q.id] == ("second", False)


def test_resume_when_everything_is_answered(repos: Repos) -> None:
    bid = _start(repos)
    n = len(manual.resume(repos, bid).questions)
    _answer(repos, bid, n)
    assert manual.resume(repos, bid).start == n


# Finishing


def test_finish_makes_one_manual_handoff(repos: Repos, clock: FakeClock) -> None:
    bid = _start(repos)
    h = manual.finish(repos, Settings(), clock, bid)
    assert (h.kind, h.blog_id, h.status, h.week_start) == ("manual", bid, "prompt_ready", None)
    blog = repos.blogs.get(bid)
    assert blog is not None and blog.status == "prompt_ready"
    assert manual.in_progress(repos) == []
    again = manual.finish(repos, Settings(), clock, bid)
    assert again.id == h.id
    assert len(repos.handoffs.list(blog_id=bid)) == 1
    assert [w.id for w in manual.waiting(repos)] == [h.id]


def test_finish_includes_scope_answers(repos: Repos, clock: FakeClock) -> None:
    bid = _start(repos)
    _answer(repos, bid, 2)
    h = manual.finish(repos, Settings(), clock, bid)
    assert "answer 0" in h.packet_text and "answer 1" in h.packet_text


@pytest.mark.parametrize(
    ("sources", "block"),
    [
        ([], "research_off"),
        (["own_documents"], "research_off"),
        (["web"], "research_on"),
        (["academic"], "research_on"),
        (["own_documents", "web"], "research_on"),
        (["own_documents", "academic"], "research_on"),
        (list(SOURCES), "research_on"),
    ],
)
def test_allowed_sources_pick_the_research_block(
    repos: Repos, clock: FakeClock, sources: list[str], block: str
) -> None:
    bid = _start(repos, allowed_sources=sources)
    h = manual.finish(repos, Settings(), clock, bid)
    assert block in h.prompt_versions
    other = "research_on" if block == "research_off" else "research_off"
    assert other not in h.prompt_versions


def test_my_documents_only_prompt_never_mentions_web_search(repos: Repos, clock: FakeClock) -> None:
    bid = _start(repos, allowed_sources=["own_documents"])
    text = manual.finish(repos, Settings(), clock, bid).packet_text
    assert not re.search(r"\b(search|web)", text, re.IGNORECASE)


def test_waiting_lists_only_open_manual_handoffs(repos: Repos, clock: FakeClock) -> None:
    weekly = repos.blogs.create("W", "W", "weekly")
    repos.handoffs.create("weekly", "p", 1, {}, blog_id=weekly.id)
    bid = _start(repos)
    h = manual.finish(repos, Settings(), clock, bid)
    assert [w.id for w in manual.waiting(repos)] == [h.id]
    repos.handoffs.mark_imported(h.id, None)
    assert manual.waiting(repos) == []


# Cancel


def test_discard_form_removes_row_and_files(repos: Repos, tmp_path: Path) -> None:
    blog = manual.form_blog(repos)
    src = tmp_path / "notes.txt"
    src.write_text("x")
    att = attachments.add(repos, blog.id, src)
    stored = Path(att.stored_path)
    assert stored.exists()
    manual.discard_form(repos, blog.id)
    assert repos.blogs.get(blog.id) is None
    assert not stored.exists()
    assert src.exists()  # the owner's original is never touched


def test_discard_form_keeps_a_started_blog(repos: Repos) -> None:
    bid = _start(repos)
    manual.discard_form(repos, bid)
    assert repos.blogs.get(bid) is not None
