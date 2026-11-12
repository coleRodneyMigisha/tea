"""domain/drafts: the owner's actions on hand-offs and drafts."""

import pytest
from handoff_world import TITLE, WEEK, imported, pick_handoff, weekly_handoff

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.domain import drafts, questions
from tea.handoff import packets
from tea.handoff.importer import import_reply
from tea.settings import Settings


def _blog_id(repos: Repos, clock: FakeClock) -> int:
    h = imported(repos, clock)
    assert h.blog_id is not None
    return h.blog_id


def _latest(repos: Repos, blog_id: int) -> drafts.Draft:
    d = repos.drafts.latest_for_blog(blog_id)
    assert d is not None
    return d


# Copy prompt


def test_copy_prompt_marks_copied(repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    text = drafts.copy_prompt(repos, h.id)
    assert text == h.packet_text
    got = repos.handoffs.get(h.id)
    assert got is not None and got.status == "copied" and got.copied_at is not None


def test_copy_prompt_after_import_keeps_it_imported(repos: Repos, clock: FakeClock) -> None:
    h = imported(repos, clock)
    drafts.copy_prompt(repos, h.id)
    got = repos.handoffs.get(h.id)
    assert got is not None and got.status == "imported"


def test_copy_prompt_missing_handoff_raises_lookup(repos: Repos) -> None:
    with pytest.raises(LookupError):
        drafts.copy_prompt(repos, 999)


# Edits


def test_editing_never_overwrites_body_markdown(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    d = _latest(repos, blog_id)
    drafts.save_edit(repos, d.id, "# Mine\n\nMy own words.\n")
    after = _latest(repos, blog_id)
    assert after.body_markdown == d.body_markdown
    assert after.edited_markdown == "# Mine\n\nMy own words.\n"
    assert drafts.current_text(after) == "# Mine\n\nMy own words.\n"


def test_editing_back_to_the_import_clears_the_edit(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    d = _latest(repos, blog_id)
    drafts.save_edit(repos, d.id, "changed")
    drafts.save_edit(repos, d.id, d.body_markdown)
    assert _latest(repos, blog_id).edited_markdown is None


# Copy for Medium


def test_copy_for_medium_uses_edits_and_records_copied_at(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    d = _latest(repos, blog_id)
    drafts.save_edit(repos, d.id, "# Edited title\n\nBody.\n")
    out = drafts.copy_for_medium(repos, d.id)
    assert out.html.startswith("<h1>Edited title</h1>")
    after = _latest(repos, blog_id)
    assert after.copied_at is not None and after.is_used


# Mark as posted, shelve, revive, delete


def test_mark_posted_sets_status_and_stops_improve_questions(
    repos: Repos, clock: FakeClock
) -> None:
    blog_id = _blog_id(repos, clock)
    blog = repos.blogs.get(blog_id)
    assert blog is not None
    questions.instantiate_improve(repos, blog, TITLE)
    d = _latest(repos, blog_id)
    drafts.mark_posted(repos, d.id)
    after = repos.blogs.get(blog_id)
    assert after is not None and after.status == "posted"
    assert _latest(repos, blog_id).posted_at is not None
    assert not [q for q in repos.questions.list(origin="improve", blog_id=blog_id) if q.active]


def test_delete_a_version_keeps_the_others(repos: Repos, clock: FakeClock) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    import_reply(repos, h.id, sample_replies.WEEKLY)
    first, second = repos.drafts.list_for_blog(h.blog_id)
    drafts.delete_version(repos, second.id)
    assert [d.id for d in repos.drafts.list_for_blog(h.blog_id)] == [first.id]
    blog = repos.blogs.get(h.blog_id)
    assert blog is not None and blog.status == "ready"


def test_deleting_the_last_version_shelves_the_blog(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    drafts.delete_version(repos, _latest(repos, blog_id).id)
    blog = repos.blogs.get(blog_id)
    assert blog is not None and blog.status == "shelved"
    assert repos.drafts.list_for_blog(blog_id) == []


# Re-import, regenerate, second pass


def test_reimport_creates_a_new_version(repos: Repos, clock: FakeClock) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    import_reply(repos, h.id, sample_replies.WEEKLY)
    versions = repos.drafts.list_for_blog(h.blog_id)
    assert [(d.version, d.kind) for d in versions] == [(1, "new"), (2, "regenerated")]


def test_regenerate_makes_a_fresh_weekly_handoff(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    new, old = drafts.regenerate(repos, Settings(), clock, blog_id)
    assert new.kind == "weekly" and new.status == "prompt_ready" and new.blog_id == blog_id
    assert new.week_start == WEEK
    assert old is None  # the earlier one was already imported, nothing to supersede
    import_reply(repos, new.id, sample_replies.WEEKLY)
    assert _latest(repos, blog_id).kind == "regenerated"


def test_regenerate_supersedes_an_open_handoff(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    first, _ = drafts.regenerate(repos, Settings(), clock, blog_id)
    second, old = drafts.regenerate(repos, Settings(), clock, blog_id)
    assert old == first.id
    got = repos.handoffs.get(first.id)
    assert got is not None and got.status == "superseded"
    assert [h.id for h in repos.handoffs.list(open_only=True, blog_id=blog_id)] == [second.id]


def test_regenerate_after_a_pick_import_keeps_the_topic(repos: Repos, clock: FakeClock) -> None:
    h = pick_handoff(repos, clock)
    import_reply(repos, h.id, sample_replies.WEEKLY_PICK)
    assert h.blog_id is not None
    new, _ = drafts.regenerate(repos, Settings(), clock, h.blog_id)
    assert new.kind == "weekly"
    assert "Right-to-repair rules for phones" in new.packet_text


def test_regenerate_a_manual_blog(repos: Repos, clock: FakeClock) -> None:
    blog = repos.blogs.create("Tea at work", "Tea at work", "manual", status="ready")
    new, _ = drafts.regenerate(repos, Settings(), clock, blog.id)
    assert new.kind == "manual" and new.week_start is None


def test_second_pass_makes_an_audit_handoff(repos: Repos, clock: FakeClock) -> None:
    blog_id = _blog_id(repos, clock)
    audit, _ = drafts.second_pass(repos, Settings(), clock, blog_id)
    assert audit.kind == "audit" and audit.week_start == WEEK
    assert TITLE in audit.packet_text
    import_reply(repos, audit.id, sample_replies.AUDIT)
    assert _latest(repos, blog_id).kind == "checked"


def test_second_pass_without_a_draft_raises(repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    assert h.blog_id is not None
    with pytest.raises(packets.PacketError):
        drafts.second_pass(repos, Settings(), clock, h.blog_id)


# Pick mode: the owner types the topic Claude chose


def test_set_pick_topic_files_the_draft_under_it(repos: Repos, clock: FakeClock) -> None:
    h = pick_handoff(repos, clock)
    reply = sample_replies.WEEKLY_PICK.split("</topic>", 1)[1].split("</topic_candidates>", 1)[1]
    result = import_reply(repos, h.id, reply)
    assert result.needs_topic
    drafts.set_pick_topic(repos, h.id, "  Phone repair rules ")
    assert h.blog_id is not None
    blog = repos.blogs.get(h.blog_id)
    assert blog is not None
    assert (blog.topic, blog.topic_origin) == ("Phone repair rules", "auto_trending")
    w = repos.weeks.get(WEEK)
    assert w is not None and (w.focus_text, w.topic_origin) == (
        "Phone repair rules",
        "auto_trending",
    )


def test_set_pick_topic_never_overwrites_an_owner_focus(repos: Repos, clock: FakeClock) -> None:
    h = pick_handoff(repos, clock)
    import_reply(repos, h.id, "<draft>\n# A title\n\nText.\n</draft>")
    repos.weeks.set_focus(WEEK, "My own focus", "owner")
    drafts.set_pick_topic(repos, h.id, "Claude's topic")
    w = repos.weeks.get(WEEK)
    assert w is not None and w.focus_text == "My own focus"
    assert h.blog_id is not None
    blog = repos.blogs.get(h.blog_id)
    assert blog is not None and blog.topic == "Claude's topic"


def test_blank_pick_topic_is_ignored(repos: Repos, clock: FakeClock) -> None:
    h = pick_handoff(repos, clock)
    assert not drafts.set_pick_topic(repos, h.id, "   ")


# The continue prompt


def test_continue_prompt_is_the_prompt_file() -> None:
    text = drafts.continue_prompt()
    assert "cut off" in text and "closing tag" in text
    assert "{{" not in text


@pytest.mark.parametrize(
    ("flag", "shown"),
    [
        ("I couldn't search the web in this chat.", True),
        ("I was unable to browse, so I used your files.", True),
        ("No web access was available.", True),
        ("No claims needed a web search.", False),
        ("Searched three sources; no issues.", False),
    ],
)
def test_could_not_search_detection(flag: str, shown: bool) -> None:
    from tea.ui import import_notes

    assert import_notes.claude_could_not_search([flag]) is shown
