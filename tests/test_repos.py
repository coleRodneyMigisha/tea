import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tea.clock import FakeClock
from tea.db.connection import connect
from tea.db.repos import Repos

KAMPALA = ZoneInfo("Africa/Kampala")
WS = date(2026, 11, 9)
NOW = "2026-11-13T17:59:00+03:00"


def _blog(repos: Repos, **kw: object) -> int:
    fields: dict[str, object] = {"title": "T", "topic": "AI", "origin": "weekly"}
    fields.update(kw)
    return repos.blogs.create(**fields).id  # type: ignore[arg-type]


def _draft(repos: Repos, blog_id: int, **kw: object) -> int:
    fields: dict[str, object] = {
        "blog_id": blog_id,
        "title": "Draft",
        "body_markdown": "# Draft\n\nBody",
        "raw_reply": "<draft>...</draft>",
        "prompt_versions": {"packet_draft": 1},
    }
    fields.update(kw)
    return repos.drafts.add(**fields).id  # type: ignore[arg-type]


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


# blogs


def test_blog_create_defaults(repos: Repos) -> None:
    b = repos.blogs.create(title="T", topic="AI", origin="manual")
    assert (b.length, b.status, b.topic_origin, b.carried_weeks) == (
        "standard",
        "queued",
        "owner",
        0,
    )
    assert b.allowed_sources == []
    assert b.created_at == b.updated_at == NOW
    assert repos.blogs.get(b.id) == b


def test_blog_create_all_fields(repos: Repos) -> None:
    b = repos.blogs.create(
        title="T",
        topic="",
        origin="weekly",
        scope_notes="n",
        audience="devs",
        length="long",
        allowed_sources=["web", "academic"],
        topic_origin="auto_trending",
        status="scoping",
    )
    assert b.allowed_sources == ["web", "academic"]
    assert (b.length, b.status, b.topic_origin, b.audience) == (
        "long",
        "scoping",
        "auto_trending",
        "devs",
    )


def test_blog_get_missing(repos: Repos) -> None:
    assert repos.blogs.get(42) is None


def test_blog_update_and_status(repos: Repos, clock: FakeClock) -> None:
    b = repos.blogs.create(title="T", topic="AI", origin="weekly")
    clock.advance(minutes=5)
    repos.blogs.update(b.id, title="New", allowed_sources=["web"], carried_weeks=1)
    repos.blogs.set_status(b.id, "ready")
    got = repos.blogs.get(b.id)
    assert got is not None
    assert (got.title, got.allowed_sources, got.carried_weeks, got.status) == (
        "New",
        ["web"],
        1,
        "ready",
    )
    assert got.updated_at == "2026-11-13T18:04:00+03:00"
    assert got.created_at == NOW


def test_blog_update_rejects_unknown_field(repos: Repos) -> None:
    b = repos.blogs.create(title="T", topic="AI", origin="weekly")
    with pytest.raises(ValueError):
        repos.blogs.update(b.id, id=5)
    with pytest.raises(ValueError):
        repos.blogs.update(b.id, created_at="x")


def test_blog_bad_status_rejected(repos: Repos) -> None:
    b = repos.blogs.create(title="T", topic="AI", origin="weekly")
    with pytest.raises(sqlite3.IntegrityError):
        repos.blogs.set_status(b.id, "lost")


def test_blog_list_filters(repos: Repos) -> None:
    a = _blog(repos, origin="weekly", status="ready")
    b = _blog(repos, origin="manual", status="ready")
    c = _blog(repos, origin="weekly", status="shelved")
    assert [x.id for x in repos.blogs.list()] == [a, b, c]
    assert [x.id for x in repos.blogs.list(status="ready")] == [a, b]
    assert [x.id for x in repos.blogs.list(origin="weekly")] == [a, c]
    assert [x.id for x in repos.blogs.list(status="ready", origin="manual")] == [b]


def test_blog_delete_cascades_everywhere(repos: Repos, conn: sqlite3.Connection) -> None:
    bid = _blog(repos)
    repos.weeks.ensure(WS)
    repos.weeks.set_blog(WS, bid)
    q = repos.questions.create(text="Q", kind="text", category="scope", origin="blog", blog_id=bid)
    repos.answers.add(q.id, "blog_scope", "A", blog_id=bid)
    repos.attachments.add(bid, "f.pdf", "/x/f.pdf", "pdf", 10)
    did = _draft(repos, bid)
    repos.handoffs.create("weekly", "packet", 1, {"packet_draft": 1}, blog_id=bid, week_start=WS)
    repos.blogs.delete(bid)
    for table in ("blogs", "weeks", "questions", "answers", "attachments", "drafts", "handoffs"):
        assert _count(conn, table) == 0, table
    assert repos.drafts.get(did) is None


# weeks


def test_week_ensure_is_idempotent(repos: Repos) -> None:
    w = repos.weeks.ensure(WS)
    assert w.week_start == WS
    assert (w.focus_text, w.pick_mode, w.topic_origin, w.blog_id) == (None, False, "owner", None)
    repos.weeks.set_pick_mode(WS, True)
    assert repos.weeks.ensure(WS).pick_mode is True


def test_week_ensure_normalises_to_monday(repos: Repos) -> None:
    assert repos.weeks.ensure(date(2026, 11, 13)).week_start == WS


def test_week_get_missing(repos: Repos) -> None:
    assert repos.weeks.get(WS) is None


def test_week_set_focus(repos: Repos) -> None:
    repos.weeks.ensure(WS)
    repos.weeks.set_focus(WS, "Edge AI", topic_origin="auto_trending")
    w = repos.weeks.get(WS)
    assert w is not None
    assert (w.focus_text, w.topic_origin, w.focus_set_at) == ("Edge AI", "auto_trending", NOW)


def test_week_set_focus_creates_row(repos: Repos) -> None:
    repos.weeks.set_focus(WS, "Edge AI")
    w = repos.weeks.get(WS)
    assert w is not None and w.focus_text == "Edge AI" and w.topic_origin == "owner"


def test_week_clear_focus(repos: Repos) -> None:
    repos.weeks.set_focus(WS, "Edge AI")
    repos.weeks.set_focus(WS, None)
    w = repos.weeks.get(WS)
    assert w is not None and w.focus_text is None and w.focus_set_at is None


def test_week_trend_candidates_json(repos: Repos) -> None:
    data = {"candidates": [{"topic": "x", "urls": ["https://a"]}]}
    repos.weeks.set_trend_candidates(WS, data)
    w = repos.weeks.get(WS)
    assert w is not None and w.trend_candidates == data


def test_week_set_blog_and_list(repos: Repos) -> None:
    bid = _blog(repos)
    repos.weeks.set_blog(WS, bid)
    repos.weeks.ensure(date(2026, 11, 2))
    weeks = repos.weeks.list()
    assert [w.week_start for w in weeks] == [date(2026, 11, 2), WS]
    assert weeks[1].blog_id == bid


def test_week_delete_cascades_questions(repos: Repos, conn: sqlite3.Connection) -> None:
    repos.weeks.ensure(WS)
    repos.questions.create(text="Q", kind="text", category="voice", origin="week", week_start=WS)
    repos.weeks.delete(WS)
    assert _count(conn, "questions") == 0


# questions


def test_question_create_and_get(repos: Repos) -> None:
    q = repos.questions.create(
        text="How formal?",
        kind="scale",
        category="voice",
        origin="bank",
        options=["casual", "formal"],
        bank_key="voice.formality",
        template_key="voice.formality",
    )
    assert q.options == ["casual", "formal"]
    assert (q.active, q.asked_count, q.last_asked_at) == (True, 0, None)
    assert repos.questions.get(q.id) == q
    assert repos.questions.get_by_bank_key("voice.formality") == q
    assert repos.questions.get_by_bank_key("nope") is None


def test_question_bank_key_unique(repos: Repos) -> None:
    repos.questions.create(text="Q", kind="text", category="voice", origin="bank", bank_key="k")
    with pytest.raises(sqlite3.IntegrityError):
        repos.questions.create(
            text="Q2", kind="text", category="voice", origin="bank", bank_key="k"
        )


def test_question_bad_category(repos: Repos) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repos.questions.create(text="Q", kind="text", category="mood", origin="bank")


def test_question_mark_asked(repos: Repos, clock: FakeClock) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    repos.questions.mark_asked(q.id)
    clock.advance(days=1)
    repos.questions.mark_asked(q.id)
    got = repos.questions.get(q.id)
    assert got is not None
    assert got.asked_count == 2
    assert got.last_asked_at == "2026-11-14T17:59:00+03:00"


def test_question_set_active_and_list(repos: Repos) -> None:
    bid = _blog(repos)
    repos.weeks.ensure(WS)
    a = repos.questions.create(text="A", kind="text", category="voice", origin="bank")
    b = repos.questions.create(
        text="B", kind="text", category="scope", origin="week", week_start=WS
    )
    c = repos.questions.create(
        text="C", kind="text", category="improve", origin="improve", blog_id=bid
    )
    repos.questions.set_active(a.id, False)
    assert [q.id for q in repos.questions.list()] == [b.id, c.id]
    assert [q.id for q in repos.questions.list(active_only=False)] == [a.id, b.id, c.id]
    assert [q.id for q in repos.questions.list(origin="week")] == [b.id]
    assert [q.id for q in repos.questions.list(week_start=WS)] == [b.id]
    assert [q.id for q in repos.questions.list(blog_id=bid)] == [c.id]


def test_question_delete_cascades_answers(repos: Repos, conn: sqlite3.Connection) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    repos.answers.add(q.id, "login", "yes")
    repos.questions.delete(q.id)
    assert _count(conn, "answers") == 0


# answers


def test_answer_add_and_get(repos: Repos) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    a = repos.answers.add(q.id, "monday", "Plain words", week_start=WS)
    assert (a.answer_text, a.skipped, a.week_start, a.blog_id, a.answered_at) == (
        "Plain words",
        False,
        WS,
        None,
        NOW,
    )
    assert repos.answers.get(a.id) == a


def test_answer_skipped(repos: Repos) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    a = repos.answers.add(q.id, "login", skipped=True)
    assert a.skipped is True and a.answer_text == ""


def test_answer_bad_context(repos: Repos) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    with pytest.raises(sqlite3.IntegrityError):
        repos.answers.add(q.id, "lunch", "x")


def test_answer_unknown_question(repos: Repos) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repos.answers.add(999, "login", "x")


def test_answer_lists(repos: Repos, clock: FakeClock) -> None:
    bid = _blog(repos)
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    a1 = repos.answers.add(q.id, "login", "1")
    clock.advance(hours=1)
    a2 = repos.answers.add(q.id, "blog_scope", "2", blog_id=bid)
    clock.advance(hours=1)
    a3 = repos.answers.add(q.id, "monday", "3", week_start=WS)
    assert [a.id for a in repos.answers.list()] == [a1.id, a2.id, a3.id]
    assert [a.id for a in repos.answers.list(blog_id=bid)] == [a2.id]
    assert [a.id for a in repos.answers.list(week_start=WS)] == [a3.id]
    since = datetime(2026, 11, 13, 18, 30, tzinfo=KAMPALA)
    assert [a.id for a in repos.answers.list(since=since)] == [a2.id, a3.id]


def test_answer_since_compares_instants_not_strings(repos: Repos, clock: FakeClock) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    a = repos.answers.add(q.id, "login", "x")  # 17:59 +03:00 == 14:59 UTC
    utc = clock.now().astimezone(UTC)
    assert [x.id for x in repos.answers.list(since=utc - timedelta(minutes=1))] == [a.id]
    assert repos.answers.list(since=utc + timedelta(minutes=1)) == []


def test_answer_delete(repos: Repos) -> None:
    q = repos.questions.create(text="Q", kind="text", category="voice", origin="bank")
    a = repos.answers.add(q.id, "login", "x")
    repos.answers.delete(a.id)
    assert repos.answers.get(a.id) is None


# attachments


def test_attachment_add_list_include(repos: Repos) -> None:
    bid = _blog(repos)
    a = repos.attachments.add(bid, "Paper.PDF", "/up/1/Paper.PDF", "pdf", 1234)
    b = repos.attachments.add(bid, "notes.md", "/up/1/notes.md", "md", 10)
    assert (a.include_in_list, a.added_at, a.size_bytes) == (True, NOW, 1234)
    assert repos.attachments.get(a.id) == a
    assert repos.attachments.count_for_blog(bid) == 2
    repos.attachments.set_included(b.id, False)
    assert [x.id for x in repos.attachments.list_for_blog(bid)] == [a.id, b.id]
    assert [x.id for x in repos.attachments.list_for_blog(bid, included_only=True)] == [a.id]
    repos.attachments.delete(a.id)
    assert repos.attachments.count_for_blog(bid) == 1


def test_attachment_needs_blog(repos: Repos) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repos.attachments.add(999, "f", "/f", "pdf", 1)


# drafts


def test_draft_versions_increment_per_blog(repos: Repos) -> None:
    b1, b2 = _blog(repos), _blog(repos)
    d1 = repos.drafts.get(_draft(repos, b1))
    d2 = repos.drafts.get(_draft(repos, b1, kind="improved"))
    d3 = repos.drafts.get(_draft(repos, b2))
    assert d1 and d2 and d3
    assert (d1.version, d2.version, d3.version) == (1, 2, 1)
    assert d2.kind == "improved"
    assert repos.drafts.next_version(b1) == 3


def test_draft_json_fields_and_defaults(repos: Repos) -> None:
    bid = _blog(repos)
    d = repos.drafts.add(
        blog_id=bid,
        title="T",
        body_markdown="body",
        raw_reply="raw | with pipes",
        prompt_versions={"packet_draft": 2, "block_research": 1},
        sources=["https://a"],
        verification=[{"status": "ok", "claim": "c", "source": "s", "note": ""}],
        flags=["no web"],
        changes=["tightened intro"],
        parse_warnings=["missing_sources"],
    )
    got = repos.drafts.get(d.id)
    assert got == d
    assert got.prompt_versions == {"packet_draft": 2, "block_research": 1}
    assert got.verification[0]["status"] == "ok"
    assert (got.edited_markdown, got.copied_at, got.posted_at, got.imported_at) == (
        None,
        None,
        None,
        NOW,
    )
    assert got.raw_reply == "raw | with pipes"
    assert got.is_used is False


def test_draft_unique_blog_version(repos: Repos) -> None:
    bid = _blog(repos)
    _draft(repos, bid, version=1)
    with pytest.raises(sqlite3.IntegrityError):
        _draft(repos, bid, version=1)


def test_draft_edit_copy_post(repos: Repos) -> None:
    bid = _blog(repos)
    did = _draft(repos, bid)
    repos.drafts.set_edited(did, "mine")
    repos.drafts.mark_copied(did)
    d = repos.drafts.get(did)
    assert d is not None and d.edited_markdown == "mine" and d.copied_at == NOW and d.is_used
    assert d.body_markdown == "# Draft\n\nBody"
    repos.drafts.set_edited(did, None)
    repos.drafts.mark_posted(did)
    d = repos.drafts.get(did)
    assert d is not None and d.edited_markdown is None and d.posted_at == NOW


def test_draft_latest_and_list(repos: Repos) -> None:
    bid = _blog(repos)
    assert repos.drafts.latest_for_blog(bid) is None
    a, b = _draft(repos, bid), _draft(repos, bid)
    assert [d.id for d in repos.drafts.list_for_blog(bid)] == [a, b]
    latest = repos.drafts.latest_for_blog(bid)
    assert latest is not None and latest.id == b


def test_draft_delete_clears_handoff_link(repos: Repos) -> None:
    bid = _blog(repos)
    did = _draft(repos, bid)
    h = repos.handoffs.create("manual", "p", 1, {}, blog_id=bid)
    repos.handoffs.mark_imported(h.id, did)
    repos.drafts.delete(did)
    got = repos.handoffs.get(h.id)
    assert got is not None and got.draft_id is None and got.status == "imported"


# handoffs


def test_handoff_create_defaults(repos: Repos) -> None:
    h = repos.handoffs.create("weekly", "packet text", 2, {"packet_draft": 1}, week_start=WS)
    assert (h.status, h.blog_id, h.week_start, h.reminder_count) == ("prompt_ready", None, WS, 0)
    assert h.prompt_versions == {"packet_draft": 1}
    assert h.created_at == NOW
    assert repos.handoffs.get(h.id) == h


def test_handoff_bad_kind(repos: Repos) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repos.handoffs.create("email", "p", 1, {})


def test_handoff_lifecycle(repos: Repos, clock: FakeClock) -> None:
    bid = _blog(repos)
    h = repos.handoffs.create("weekly", "p", 1, {}, blog_id=bid, week_start=WS)
    repos.handoffs.mark_copied(h.id)
    clock.advance(hours=2)
    repos.handoffs.record_reminder(h.id)
    repos.handoffs.record_reminder(h.id)
    did = _draft(repos, bid)
    repos.handoffs.mark_imported(h.id, did)
    got = repos.handoffs.get(h.id)
    assert got is not None
    assert (got.status, got.copied_at, got.draft_id, got.reminder_count) == (
        "imported",
        NOW,
        did,
        2,
    )
    assert got.imported_at == got.last_reminder_at == "2026-11-13T19:59:00+03:00"


def test_handoff_supersede_and_lists(repos: Repos) -> None:
    bid = _blog(repos)
    old = repos.handoffs.create("weekly", "p", 1, {}, blog_id=bid, week_start=WS)
    new = repos.handoffs.create("weekly_pick", "p2", 1, {}, blog_id=bid, week_start=WS)
    other = repos.handoffs.create("manual", "m", 1, {})
    repos.handoffs.mark_superseded(old.id)
    assert [h.id for h in repos.handoffs.list()] == [old.id, new.id, other.id]
    assert [h.id for h in repos.handoffs.list(open_only=True)] == [new.id, other.id]
    assert [h.id for h in repos.handoffs.list(blog_id=bid)] == [old.id, new.id]
    assert [h.id for h in repos.handoffs.list(week_start=WS, kind="weekly")] == [old.id]
    assert [h.id for h in repos.handoffs.list(status="superseded")] == [old.id]
    latest = repos.handoffs.latest(blog_id=bid)
    assert latest is not None and latest.id == new.id
    assert repos.handoffs.latest(kind="audit") is None


# jobs


def test_job_ensure_get_and_defaults(repos: Repos) -> None:
    assert repos.jobs.get("weekly_packet", WS) is None
    j = repos.jobs.ensure("weekly_packet", WS)
    assert (j.kind, j.week_start, j.blog_id, j.status) == ("weekly_packet", WS, 0, "pending")
    assert repos.jobs.ensure("weekly_packet", WS) == j


def test_job_primary_key_unique(repos: Repos, conn: sqlite3.Connection) -> None:
    repos.jobs.ensure("improve_packet", WS, blog_id=3)
    repos.jobs.ensure("improve_packet", WS, blog_id=4)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO jobs (kind, week_start, blog_id) VALUES ('improve_packet', ?, 3)",
            (WS.isoformat(),),
        )


def test_job_without_week(repos: Repos) -> None:
    j = repos.jobs.ensure("login_questions")
    assert j.week_start is None
    assert repos.jobs.get("login_questions") == j


def test_job_bad_kind(repos: Repos) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repos.jobs.ensure("make_coffee", WS)


def test_job_attempt_status_snooze(repos: Repos, clock: FakeClock) -> None:
    repos.jobs.ensure("focus_prompt", WS)
    repos.jobs.record_attempt("focus_prompt", WS)
    until = clock.now() + timedelta(hours=2)
    repos.jobs.snooze("focus_prompt", until, WS)
    j = repos.jobs.get("focus_prompt", WS)
    assert j is not None and j.last_attempt_at == NOW
    assert j.snoozed_until == "2026-11-13T19:59:00+03:00"
    repos.jobs.set_status("focus_prompt", "done", WS)
    j = repos.jobs.get("focus_prompt", WS)
    assert j is not None and j.status == "done"
    repos.jobs.snooze("focus_prompt", None, WS)
    j = repos.jobs.get("focus_prompt", WS)
    assert j is not None and j.snoozed_until is None


def test_job_list_pending(repos: Repos) -> None:
    repos.jobs.ensure("focus_prompt", WS)
    repos.jobs.ensure("pick_mode", WS)
    repos.jobs.set_status("pick_mode", "dismissed", WS)
    assert [j.kind for j in repos.jobs.list(status="pending")] == ["focus_prompt"]
    assert len(repos.jobs.list()) == 2


# connections


def test_worker_connection_shares_data(repos: Repos, db_path: Path, clock: FakeClock) -> None:
    bid = _blog(repos)
    worker = Repos(connect(db_path), clock)
    worker.attachments.add(bid, "f.pdf", "/f.pdf", "pdf", 5)
    assert repos.attachments.count_for_blog(bid) == 1
    worker.conn.close()


def test_transaction_rolls_back(repos: Repos) -> None:
    with pytest.raises(RuntimeError), repos.transaction():
        _blog(repos)
        raise RuntimeError("boom")
    assert repos.blogs.list() == []
