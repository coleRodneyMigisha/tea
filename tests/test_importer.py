"""handoff/importer: versions, kinds, raw reply, pick mode, statuses."""

from datetime import date

import pytest

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools.sample_replies import MALFORMED, WELL_FORMED
from tea.handoff.importer import import_reply

WEEK = date(2026, 11, 9)


def _handoff(repos: Repos, kind: str, blog_id: int, week: date | None = WEEK) -> int:
    versions = {"packet_draft": 1, "research_on": 1}
    return repos.handoffs.create(kind, "prompt", 1, versions, blog_id=blog_id, week_start=week).id


@pytest.fixture
def blog_id(repos: Repos) -> int:
    blog = repos.blogs.create("Focus", "Focus", "weekly", status="prompt_ready")
    repos.weeks.set_focus(WEEK, "Focus")
    repos.weeks.set_blog(WEEK, blog.id)
    return blog.id


def test_first_import_creates_version_one(repos: Repos, blog_id: int) -> None:
    hid = _handoff(repos, "weekly", blog_id)
    result = import_reply(repos, hid, WELL_FORMED["weekly"])
    d = result.draft
    assert (d.version, d.kind, d.blog_id) == (1, "new", blog_id)
    assert d.title == "Small teams need fewer documents, not better ones"
    assert d.body_markdown.startswith("# Small teams")
    assert d.raw_reply == WELL_FORMED["weekly"]
    assert d.prompt_versions == {"packet_draft": 1, "research_on": 1}
    assert d.verification[0] == {
        "status": "supported",
        "claim": "Most readers scan web pages rather than read word by word",
        "source": "https://www.nngroup.com/articles/how-users-read-on-the-web/",
        "note": "1997 study",
    }
    assert d.sources[0]["publisher"] == "Nielsen Norman Group"
    assert d.flags and d.changes == [] and d.parse_warnings == []
    assert result.warnings == [] and not result.needs_topic


def test_handoff_marked_imported(repos: Repos, blog_id: int) -> None:
    hid = _handoff(repos, "weekly", blog_id)
    result = import_reply(repos, hid, WELL_FORMED["weekly"])
    h = repos.handoffs.get(hid)
    assert h is not None
    assert (h.status, h.draft_id) == ("imported", result.draft.id)
    assert h.imported_at is not None


@pytest.mark.parametrize("status", ["queued", "prompt_ready", "scoping", "shelved"])
def test_blog_becomes_ready(repos: Repos, blog_id: int, status: str) -> None:
    repos.blogs.set_status(blog_id, status)
    import_reply(repos, _handoff(repos, "weekly", blog_id), WELL_FORMED["weekly"])
    blog = repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "ready"


def test_reimport_creates_new_version(repos: Repos, blog_id: int, clock: FakeClock) -> None:
    hid = _handoff(repos, "weekly", blog_id)
    first = import_reply(repos, hid, WELL_FORMED["weekly"]).draft
    clock.advance(minutes=1)
    second = import_reply(repos, hid, WELL_FORMED["weekly"] + "\n").draft
    assert (first.version, second.version) == (1, 2)
    assert second.kind == "regenerated"
    h = repos.handoffs.get(hid)
    assert h is not None and h.draft_id == second.id
    assert len(repos.drafts.list_for_blog(blog_id)) == 2


@pytest.mark.parametrize(
    ("kind", "draft_kind"),
    [("weekly", "new"), ("weekly_pick", "new"), ("manual", "new"), ("improve", "improved"),
     ("audit", "checked")],
)  # fmt: skip
def test_draft_kind_from_handoff_kind(
    repos: Repos, blog_id: int, kind: str, draft_kind: str
) -> None:
    result = import_reply(repos, _handoff(repos, kind, blog_id), WELL_FORMED[kind])
    assert result.draft.kind == draft_kind


def test_improve_stores_changes(repos: Repos, blog_id: int) -> None:
    import_reply(repos, _handoff(repos, "weekly", blog_id), WELL_FORMED["weekly"])
    d = import_reply(repos, _handoff(repos, "improve", blog_id), WELL_FORMED["improve"]).draft
    assert d.version == 2 and d.kind == "improved"
    assert len(d.changes) == 2


def test_pick_mode_sets_focus_topic_title_and_candidates(repos: Repos) -> None:
    blog = repos.blogs.create("", "", "weekly", status="prompt_ready")
    repos.weeks.set_pick_mode(WEEK, True)
    repos.weeks.set_blog(WEEK, blog.id)
    result = import_reply(
        repos, _handoff(repos, "weekly_pick", blog.id), WELL_FORMED["weekly_pick"]
    )
    week = repos.weeks.get(WEEK)
    assert week is not None
    assert week.focus_text == "Right-to-repair rules for phones"
    assert week.topic_origin == "auto_trending"
    assert week.focus_set_at is not None
    assert len(week.trend_candidates) == 3
    assert week.trend_candidates[0] == {
        "n": 1,
        "topic": "Right-to-repair rules for phones",
        "angle": "What the new rules change for buyers",
        "why": "Covered by two national outlets this week",
        "urls": ["https://example.org/a", "https://example.org/b"],
    }
    b = repos.blogs.get(blog.id)
    assert b is not None
    assert b.topic == "Right-to-repair rules for phones"
    assert b.title == "What the new phone repair rules mean for you"
    assert b.topic_origin == "auto_trending"
    assert b.status == "ready"
    assert result.draft.title == b.title and not result.needs_topic


def test_pick_mode_without_topic_asks_owner(repos: Repos) -> None:
    blog = repos.blogs.create("", "", "weekly")
    repos.weeks.set_pick_mode(WEEK, True)
    result = import_reply(repos, _handoff(repos, "weekly_pick", blog.id), WELL_FORMED["weekly"])
    assert result.needs_topic
    assert "no_topic" in result.warnings and "no_topic" in result.draft.parse_warnings
    week = repos.weeks.get(WEEK)
    assert week is not None and week.focus_text is None
    b = repos.blogs.get(blog.id)
    assert b is not None and b.topic == "" and b.status == "ready"


def test_non_pick_kind_leaves_week_alone(repos: Repos, blog_id: int) -> None:
    import_reply(repos, _handoff(repos, "weekly", blog_id), WELL_FORMED["weekly_pick"])
    week = repos.weeks.get(WEEK)
    assert week is not None
    assert (week.focus_text, week.topic_origin, week.trend_candidates) == ("Focus", "owner", None)


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_malformed_replies_import_with_warnings(repos: Repos, blog_id: int, name: str) -> None:
    result = import_reply(repos, _handoff(repos, "weekly", blog_id), MALFORMED[name])
    assert result.draft.raw_reply == MALFORMED[name]
    assert result.draft.parse_warnings == result.parsed.warnings


def test_empty_reply_still_stores_raw_and_falls_back_to_blog_title(
    repos: Repos, blog_id: int
) -> None:
    result = import_reply(repos, _handoff(repos, "weekly", blog_id), "")
    assert result.draft.title == "Focus"
    assert result.draft.body_markdown == ""
    assert "no_draft_tag" in result.warnings


def test_untitled_fallback(repos: Repos) -> None:
    blog = repos.blogs.create("", "", "weekly")
    result = import_reply(repos, _handoff(repos, "weekly", blog.id), "just text")
    assert result.draft.title == "Untitled draft"


def test_unknown_handoff_raises_lookup_error(repos: Repos) -> None:
    with pytest.raises(LookupError):
        import_reply(repos, 999, WELL_FORMED["weekly"])
