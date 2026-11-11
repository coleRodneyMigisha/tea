"""domain/questions: seeding, templates, scope selection, weighting, mix, cooldown, recording."""

import itertools
import json
import random
from datetime import date, timedelta

import pytest

from tea import config
from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.db.rows import Blog, Question
from tea.domain import questions as qs

WEEK = date(2026, 11, 9)  # the conftest clock is Friday 13 November 2026


def _bank_keys() -> list[str]:
    data = json.loads((config.resource_dir("data") / "question_bank.json").read_text())
    return [q["bank_key"] for q in data["questions"]]


# Seeding


def test_seed_bank_inserts_every_question_once(repos: Repos) -> None:
    added = qs.seed_bank(repos)
    assert added == len(_bank_keys())
    assert qs.seed_bank(repos) == 0
    rows = repos.questions.list(origin="bank")
    assert sorted(q.bank_key or "" for q in rows) == sorted(_bank_keys())
    assert all(q.template_key == q.bank_key for q in rows)


def test_seed_bank_keeps_existing_rows_untouched(repos: Repos) -> None:
    qs.seed_bank(repos)
    first = repos.questions.get_by_bank_key("aud-who")
    assert first is not None
    repos.questions.mark_asked(first.id)
    repos.questions.delete(repos.questions.list(origin="bank")[0].id)
    assert qs.seed_bank(repos) == 1
    again = repos.questions.get_by_bank_key("aud-who")
    assert again is not None and again.id == first.id and again.asked_count == 1


def test_seed_scale_questions_have_two_labels(repos: Repos) -> None:
    qs.seed_bank(repos)
    scales = [q for q in repos.questions.list(origin="bank") if q.kind == "scale"]
    assert scales and all(len(q.options) == 2 for q in scales)


# Templates


def test_fill_replaces_known_placeholders() -> None:
    assert qs.fill('About "{focus}"?', {"focus": "tea"}) == 'About "tea"?'


@pytest.mark.parametrize("text", ["About {topic}?", "About {focus} and {title}", "{}"])
def test_fill_rejects_unknown_placeholders(text: str) -> None:
    with pytest.raises(qs.TemplateError):
        qs.fill(text, {"focus": "tea"})


def test_fill_does_not_expand_braces_in_values() -> None:
    assert qs.fill("On {focus}", {"focus": "{title}"}) == "On {title}"


def test_focus_templates_instantiate_for_the_week(repos: Repos) -> None:
    made = qs.instantiate_focus(repos, WEEK, "remote work")
    assert len(made) == 9
    assert all(q.origin == "week" and q.week_start == WEEK for q in made)
    assert all("remote work" in q.text and "{" not in q.text for q in made)
    assert {q.template_key for q in made} >= {"f-position", "f-evidence"}
    scale = next(q for q in made if q.kind == "scale")
    assert scale.options == ["Mostly my experience", "Mostly named sources"]


def test_focus_instantiation_is_idempotent(repos: Repos) -> None:
    first = qs.instantiate_focus(repos, WEEK, "remote work")
    second = qs.instantiate_focus(repos, WEEK, "remote work")
    assert [q.id for q in first] == [q.id for q in second]
    assert len(repos.questions.list(origin="week")) == 9


def test_changed_focus_replaces_questions_and_keeps_old_answers(repos: Repos) -> None:
    old = qs.instantiate_focus(repos, WEEK, "remote work")
    repos.answers.add(old[0].id, "monday", "an answer", week_start=WEEK)
    new = qs.instantiate_focus(repos, WEEK, "hybrid work")
    assert all("hybrid work" in q.text for q in new)
    assert len(repos.questions.list(origin="week")) == 9
    assert repos.questions.get(old[0].id) is not None
    assert not repos.questions.get(old[0].id).active  # type: ignore[union-attr]
    assert len(repos.answers.list()) == 1


def test_improve_templates_use_the_draft_title(repos: Repos) -> None:
    blog = repos.blogs.create("Wikis rot", "Wikis", "weekly")
    made = qs.instantiate_improve(repos, blog, "Why wikis rot")
    assert len(made) == 6
    assert all(q.origin == "improve" and q.blog_id == blog.id for q in made)
    assert all(q.category == "improve" for q in made)
    assert all('"Why wikis rot"' in q.text for q in made)
    assert [q.id for q in qs.instantiate_improve(repos, blog, "Why wikis rot")] == [
        q.id for q in made
    ]


def test_template_with_unknown_placeholder_is_rejected(repos: Repos) -> None:
    bad = {"key": "x", "category": "scope", "kind": "text", "text": "On {nope}", "options": []}
    with pytest.raises(qs.TemplateError):
        qs.instantiate(repos, [bad], {"topic": "t"}, origin="blog", blog_id=None)


# Scope selection


def _blog(repos: Repos, **kw: object) -> Blog:
    values: dict[str, object] = {
        "title": "T",
        "topic": "Tea",
        "origin": "manual",
        "scope_notes": "some scope",
        "audience": "readers",
    }
    values.update(kw)
    title, topic, origin = values.pop("title"), values.pop("topic"), values.pop("origin")
    return repos.blogs.create(str(title), str(topic), str(origin), **values)  # type: ignore[arg-type]


COMBOS = list(
    itertools.product(
        [False, True],  # files
        [False, True],  # web
        [False, True],  # academic
        ["short", "standard", "long"],
        [False, True],  # empty scope
        [False, True],  # empty audience
    )
)


@pytest.mark.parametrize(("files", "web", "academic", "length", "no_scope", "no_aud"), COMBOS)
def test_scope_selection_gives_5_to_15_in_order(
    files: bool, web: bool, academic: bool, length: str, no_scope: bool, no_aud: bool
) -> None:
    conditions = qs.scope_conditions(
        has_files=files,
        allowed_sources=[s for s, on in (("web", web), ("academic", academic)) if on],
        length=length,
        scope_notes="" if no_scope else "x",
        audience=" " if no_aud else "x",
    )
    chosen = qs.select_scope_templates(
        qs.load_templates("scope_question_templates.json"), conditions
    )
    assert 5 <= len(chosen) <= 15
    orders = [t["order"] for t in chosen]
    assert orders == sorted(orders)
    assert all(t["applies"] in conditions for t in chosen)
    keys = {t["key"] for t in chosen}
    if no_aud and len(chosen) < 15:
        assert "s-audience" in keys
    if not files:
        assert not keys & {"s-files-parts", "s-files-avoid"}


def test_scope_conditions_read_the_options() -> None:
    c = qs.scope_conditions(
        has_files=True, allowed_sources=["web"], length="long", scope_notes="", audience="x"
    )
    assert c == {"always", "has_files", "web", "long", "scope_empty"}


def test_scope_selection_caps_at_15_dropping_highest_order() -> None:
    every = {"always", "scope_empty", "audience_empty", "has_files", "web", "academic", "long"}
    chosen = qs.select_scope_templates(qs.load_templates("scope_question_templates.json"), every)
    assert len(chosen) == 15
    assert chosen[0]["key"] == "s-reader" and chosen[1]["key"] == "s-audience"
    assert "s-long-structure" not in {t["key"] for t in chosen}


def test_scope_selection_tops_up_with_always_templates() -> None:
    templates = [
        {"key": f"a{i}", "order": i, "applies": "always", "category": "scope", "kind": "text",
         "text": "x", "options": []}
        for i in range(8)
    ] + [
        {"key": "w", "order": 1, "applies": "web", "category": "scope", "kind": "text",
         "text": "x", "options": []}
    ]  # fmt: skip
    # Only 3 conditional templates hold: the rule adds the lowest-order unused always ones.
    chosen = qs.select_scope_templates(templates, {"web"})
    assert [t["key"] for t in chosen] == ["a0", "w", "a1", "a2", "a3"]  # back in order


def test_instantiate_scope_creates_blog_questions_with_topic(repos: Repos) -> None:
    blog = _blog(repos, topic="Green tea", allowed_sources=["web"], length="short")
    made = qs.instantiate_scope(repos, blog, has_files=False)
    assert 5 <= len(made) <= 15
    assert all(q.origin == "blog" and q.blog_id == blog.id and q.category == "scope" for q in made)
    assert any("Green tea" in q.text for q in made)
    assert all("{" not in q.text for q in made)
    assert [q.id for q in qs.instantiate_scope(repos, blog, has_files=False)] == [
        q.id for q in made
    ]


def test_pending_scope_skips_answered_and_skipped(repos: Repos) -> None:
    blog = _blog(repos)
    made = qs.instantiate_scope(repos, blog, has_files=False)
    qs.record_answer(repos, made[0], "blog_scope", "a", blog_id=blog.id)
    qs.record_answer(repos, made[1], "blog_scope", "", skipped=True, blog_id=blog.id)
    pending = qs.pending_scope(repos, blog, has_files=False)
    assert [q.id for q in pending] == [q.id for q in made[2:]]


# Weighting


def _q(asked_count: int = 0, last: str | None = None, qid: int = 1) -> Question:
    return Question(
        id=qid, text="t", kind="text", options=[], category="voice", origin="bank",
        week_start=None, blog_id=None, active=True, asked_count=asked_count,
        last_asked_at=last, template_key=None, bank_key=None,
    )  # fmt: skip


def test_weight_rises_with_time_and_falls_with_count(clock: FakeClock) -> None:
    now = clock.now()
    days = lambda n: (now - timedelta(days=n)).isoformat()  # noqa: E731
    assert qs.weight(_q(1, days(30)), now) > qs.weight(_q(1, days(15)), now)
    assert qs.weight(_q(1, days(30)), now) > qs.weight(_q(4, days(30)), now)
    assert qs.weight(_q(0, None), now) == qs.weight(_q(0, days(400)), now)
    assert qs.weight(_q(0, None), now) > qs.weight(_q(0, days(59)), now)
    assert qs.weight(_q(0, days(0)), now) > 0


def test_weighted_pick_prefers_heavier_questions(clock: FakeClock) -> None:
    now = clock.now()
    fresh = _q(0, None, qid=1)
    tired = _q(9, (now - timedelta(days=15)).isoformat(), qid=2)
    rng = random.Random(1)
    wins = sum(qs.weighted_pick([fresh, tired], now, rng).id == 1 for _ in range(500))
    assert wins > 450


# Login session


def _seeded(repos: Repos) -> Repos:
    qs.seed_bank(repos)
    return repos


def test_login_session_has_count_bank_questions_without_repeats(
    repos: Repos, clock: FakeClock
) -> None:
    _seeded(repos)
    for seed in range(20):
        chosen = qs.select_login(repos, clock.now(), random.Random(seed), 5, WEEK)
        assert len(chosen) == 5
        assert len({q.id for q in chosen}) == 5
        assert all(q.origin == "bank" for q in chosen)


def test_login_mix_is_one_improve_one_focus_rest_bank(repos: Repos, clock: FakeClock) -> None:
    _seeded(repos)
    qs.instantiate_focus(repos, WEEK, "remote work")
    blog = repos.blogs.create("Wikis", "Wikis", "weekly")
    qs.instantiate_improve(repos, blog, "Wikis")
    for seed in range(20):
        chosen = qs.select_login(repos, clock.now(), random.Random(seed), 3, WEEK)
        assert [q.origin for q in chosen] == ["improve", "week", "bank"]


def test_login_mix_with_count_one_takes_improve(repos: Repos, clock: FakeClock) -> None:
    _seeded(repos)
    qs.instantiate_focus(repos, WEEK, "remote work")
    blog = repos.blogs.create("Wikis", "Wikis", "weekly")
    qs.instantiate_improve(repos, blog, "Wikis")
    chosen = qs.select_login(repos, clock.now(), random.Random(0), 1, WEEK)
    assert [q.origin for q in chosen] == ["improve"]


def test_login_ignores_other_weeks_focus_and_inactive(repos: Repos, clock: FakeClock) -> None:
    _seeded(repos)
    qs.instantiate_focus(repos, WEEK - timedelta(days=7), "old focus")
    blog = repos.blogs.create("Wikis", "Wikis", "weekly")
    for q in qs.instantiate_improve(repos, blog, "Wikis"):
        repos.questions.set_active(q.id, False)
    chosen = qs.select_login(repos, clock.now(), random.Random(0), 3, WEEK)
    assert [q.origin for q in chosen] == ["bank", "bank", "bank"]


def test_empty_slots_fill_from_other_pools(repos: Repos, clock: FakeClock) -> None:
    qs.instantiate_focus(repos, WEEK, "remote work")  # no bank, no improve
    chosen = qs.select_login(repos, clock.now(), random.Random(0), 3, WEEK)
    assert len(chosen) == 3 and all(q.origin == "week" for q in chosen)


def _ask(repos: Repos, q: Question) -> None:
    qs.record_answer(repos, q, "login", "x")


def test_fourteen_day_rule(repos: Repos, clock: FakeClock) -> None:
    repos.questions.create("A", "text", "voice", "bank", bank_key="a")
    repos.questions.create("B", "text", "voice", "bank", bank_key="b")
    repos.questions.create("C", "text", "voice", "bank", bank_key="c")
    a = repos.questions.get_by_bank_key("a")
    assert a is not None
    _ask(repos, a)
    clock.advance(days=13, hours=23)
    for seed in range(30):
        chosen = qs.select_login(repos, clock.now(), random.Random(seed), 2, WEEK)
        assert a.id not in {q.id for q in chosen}
    clock.advance(hours=2)
    seen = {
        q.id
        for seed in range(60)
        for q in qs.select_login(repos, clock.now(), random.Random(seed), 2, WEEK)
    }
    assert a.id in seen


def test_exhausted_pool_allows_recent_questions_least_needed(
    repos: Repos, clock: FakeClock
) -> None:
    for key in "abc":
        repos.questions.create(key, "text", "voice", "bank", bank_key=key)
    a = repos.questions.get_by_bank_key("a")
    b = repos.questions.get_by_bank_key("b")
    assert a is not None and b is not None
    _ask(repos, a)
    _ask(repos, b)
    clock.advance(days=1)
    chosen = qs.select_login(repos, clock.now(), random.Random(0), 3, WEEK)
    assert len(chosen) == 3
    assert chosen[0].bank_key == "c"  # fresh questions come before re-asked ones


def test_fresh_bank_beats_recent_improve_question(repos: Repos, clock: FakeClock) -> None:
    _seeded(repos)
    blog = repos.blogs.create("Wikis", "Wikis", "weekly")
    for q in qs.instantiate_improve(repos, blog, "Wikis"):
        _ask(repos, q)
    clock.advance(days=2)
    chosen = qs.select_login(repos, clock.now(), random.Random(0), 3, WEEK)
    assert all(q.origin == "bank" for q in chosen)


def test_no_questions_at_all_gives_empty_session(repos: Repos, clock: FakeClock) -> None:
    assert qs.select_login(repos, clock.now(), random.Random(0), 3, WEEK) == []
    _seeded(repos)
    assert qs.select_login(repos, clock.now(), random.Random(0), 0, WEEK) == []


# Recording


def test_record_answer_marks_asked(repos: Repos, clock: FakeClock) -> None:
    q = repos.questions.create("A", "text", "voice", "bank", bank_key="a")
    a = qs.record_answer(repos, q, "login", "  hello ", week_start=WEEK)
    assert a.answer_text == "  hello " and not a.skipped and a.week_start == WEEK
    after = repos.questions.get(q.id)
    assert after is not None and after.asked_count == 1 and after.last_asked_at is not None


def test_skip_is_stored_as_skipped(repos: Repos) -> None:
    q = repos.questions.create("A", "text", "voice", "bank", bank_key="a")
    a = qs.record_answer(repos, q, "login", "typed then skipped", skipped=True)
    assert a.skipped and a.answer_text == ""
    after = repos.questions.get(q.id)
    assert after is not None and after.asked_count == 1


# Cooldown and the once-per-start rule


def test_cooldown_after_dismissal(repos: Repos, clock: FakeClock) -> None:
    assert qs.login_allowed(repos, clock.now())
    qs.note_dismissed(repos, clock.now(), minutes=120)
    assert not qs.login_allowed(repos, clock.now())
    clock.advance(minutes=119)
    assert not qs.login_allowed(repos, clock.now())
    clock.advance(minutes=1)
    assert qs.login_allowed(repos, clock.now())


def test_completed_session_sets_no_cooldown(repos: Repos, clock: FakeClock) -> None:
    qs.note_dismissed(repos, clock.now(), minutes=120)
    qs.note_completed(repos, clock.now())
    assert qs.login_allowed(repos, clock.now())
    job = repos.jobs.get("login_questions")
    assert job is not None and job.last_attempt_at is not None
