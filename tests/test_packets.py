"""handoff/packets: each kind renders cleanly; optional blocks follow the rules."""

import re
from pathlib import Path

import pytest

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools.sample_data import SampleIds, seed
from tea.handoff import packets
from tea.handoff.packets import Packet, PacketError
from tea.settings import Settings

KINDS = ["weekly", "weekly_pick", "manual", "improve", "audit"]


@pytest.fixture
def ids(repos: Repos, clock: FakeClock) -> SampleIds:
    return seed(repos, clock)


@pytest.fixture
def settings() -> Settings:
    return Settings(interests=["software teams", "writing"], region="East Africa")


def _build(kind: str, repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds) -> Packet:
    if kind in ("weekly", "weekly_pick"):
        return packets.build(kind, repos, settings, clock, week=ids.week)
    blog = {"manual": ids.manual_blog}.get(kind, ids.carried_blog)
    return packets.build(kind, repos, settings, clock, blog_id=blog)


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_renders_cleanly(
    kind: str, repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    p = _build(kind, repos, settings, clock, ids)
    assert p.kind == kind
    assert "{{" not in p.text and "}}" not in p.text
    assert "\n\n\n" not in p.text
    assert not re.search(r"\n[ \t]+\n", p.text)
    assert p.text == p.text.strip() + "\n"
    assert p.words == len(p.text.split())
    assert all(v >= 1 for v in p.prompt_versions.values())


def test_prompt_versions_name_main_prompt_and_blocks(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    weekly = _build("weekly", repos, settings, clock, ids)
    assert weekly.prompt_versions == {"packet_draft": 2, "research_on": 2}
    pick = _build("weekly_pick", repos, settings, clock, ids)
    assert pick.prompt_versions == {"packet_draft": 2, "pick_topic": 1, "research_on": 2}
    manual = _build("manual", repos, settings, clock, ids)
    assert manual.prompt_versions == {"packet_draft": 2, "attachments": 1, "research_off": 2}
    assert _build("improve", repos, settings, clock, ids).prompt_versions == {"packet_improve": 1}
    assert _build("audit", repos, settings, clock, ids).prompt_versions == {"packet_audit": 1}


def test_pick_block_only_in_weekly_pick(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    for kind in KINDS:
        p = _build(kind, repos, settings, clock, ids)
        assert ("<topic_pick>" in p.text) == (kind == "weekly_pick"), kind


def test_pick_block_contents(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    text = _build("weekly_pick", repos, settings, clock, ids).text
    assert "My interests: software teams, writing" in text
    assert "Region (optional): East Africa" in text
    assert "Today's date: Friday 13 November 2026" in text
    assert "Onboarding wikis" in text  # last week's focus is a recent topic
    assert "Off limits: Never name my employer or clients." in text
    assert "Topic: not chosen yet" in text


def test_recent_topics_window_is_eight_weeks(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    from datetime import timedelta

    repos.weeks.set_focus(ids.week - timedelta(weeks=8), "Eight weeks ago")
    repos.weeks.set_focus(ids.week - timedelta(weeks=9), "Nine weeks ago")
    text = _build("weekly_pick", repos, settings, clock, ids).text
    assert "Eight weeks ago" in text and "Nine weeks ago" not in text


def test_pick_defaults_when_nothing_known(repos: Repos, clock: FakeClock) -> None:
    blog = repos.blogs.create("", "", "weekly", allowed_sources=["web"])
    p = packets.build("weekly_pick", repos, Settings(), clock, blog_id=blog.id)
    assert "My interests: none given" in p.text
    assert "Topics I have already written about recently (do not repeat): none" in p.text
    assert "Off limits: none given" in p.text


def test_research_on_lists_allowed_types(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    text = _build("weekly", repos, settings, clock, ids).text
    assert "Allowed source types: my documents, web sources, academic papers." in text
    assert "Do not add outside sources" not in text
    assert "Link web sources inline" in text


def test_research_off_when_web_and_academic_off(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    text = _build("manual", repos, settings, clock, ids).text
    assert "<research>\nWrite only from my attached files" in text
    assert not re.search(r"\b(search|web)", text, re.IGNORECASE)  # "<research>" is fine
    assert "research the topic" not in text.lower()


def test_academic_alone_turns_research_on(repos: Repos, clock: FakeClock) -> None:
    blog = repos.blogs.create("T", "T", "manual", allowed_sources=["academic"])
    p = packets.build("manual", repos, Settings(), clock, blog_id=blog.id)
    assert p.prompt_versions["research_on"] == 2


def test_pick_mode_always_researches(repos: Repos, clock: FakeClock) -> None:
    """Picking a trending topic needs web search, whatever the blog's sources say."""
    blog = repos.blogs.create("", "", "weekly", allowed_sources=[])
    p = packets.build("weekly_pick", repos, Settings(), clock, blog_id=blog.id)
    assert "research_on" in p.prompt_versions
    assert "Do not add outside sources" not in p.text


def test_attachments_block_only_with_included_files(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    p = _build("manual", repos, settings, clock, ids)
    assert "<attached_files>" in p.text
    assert "- keshav-how-to-read.pdf" in p.text
    assert [a.filename for a in p.attachments] == ["keshav-how-to-read.pdf"]
    att = repos.attachments.list_for_blog(ids.manual_blog)[0]
    repos.attachments.set_included(att.id, False)
    p = _build("manual", repos, settings, clock, ids)
    assert "<attached_files>" not in p.text and p.attachments == []
    assert "attachments" not in p.prompt_versions


def test_left_out_files_never_reach_the_packet(
    repos: Repos, settings: Settings, clock: FakeClock, tmp_path: Path
) -> None:
    from tea.domain import attachments

    blog = repos.blogs.create("Tea", "Tea", "manual", allowed_sources=["own_documents"])
    src = tmp_path / "src"
    src.mkdir()
    added = []
    for name in ("keep-one.pdf", "skip-me.docx", "keep-two.txt", "notes.docx", "notes.docx"):
        path = src / name
        path.write_bytes(b"x")
        added.append(attachments.add(repos, blog.id, path))
    attachments.set_included(repos, added[1].id, False)
    attachments.set_included(repos, added[3].id, False)
    p = packets.build("manual", repos, settings, clock, blog_id=blog.id)
    assert [a.filename for a in p.attachments] == ["keep-one.pdf", "keep-two.txt", "notes (2).docx"]
    assert "- keep-one.pdf\n- keep-two.txt\n- notes (2).docx" in p.text
    assert "skip-me" not in p.text
    assert "- notes.docx" not in p.text


def test_brief(repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds) -> None:
    text = _build("manual", repos, settings, clock, ids).text
    assert "Topic: How to read an academic paper in 20 minutes" in text
    assert "Working title: Reading papers faster" in text
    assert "What it should cover: Skimming order" in text
    assert "Who it is for: Graduate students" in text
    assert "Length: short, 600 to 900 words" in text
    assert "Target length: 600 to 900 words." in text


def test_answers_and_style_notes(repos: Repos, clock: FakeClock, ids: SampleIds) -> None:
    settings = Settings(style_notes="I never use exclamation marks.")
    text = packets.build("weekly", repos, settings, clock, week=ids.week).text
    assert "Q: Who reads your posts? / A: Engineers" in text
    assert "Most specs I wrote were never opened." in text  # focus answer
    assert "I never use exclamation marks." in text
    settings.include_style_notes = False
    text = packets.build("weekly", repos, settings, clock, week=ids.week).text
    assert "exclamation" not in text


def test_answer_cap_comes_from_settings(repos: Repos, clock: FakeClock, ids: SampleIds) -> None:
    repos.answers.add(
        repos.questions.create("Long?", "text", "voice", "bank", bank_key="long").id,
        "login",
        "word " * 400,
    )
    small = packets.build("weekly", repos, Settings(max_answer_words=200), clock, week=ids.week)
    big = packets.build("weekly", repos, Settings(max_answer_words=5000), clock, week=ids.week)
    assert small.words < big.words


def test_improve_contains_previous_draft_and_only_new_answers(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    text = _build("improve", repos, settings, clock, ids).text
    assert "Wikis rot because nobody owns a page." in text  # the owner's edited version
    assert "<owner_edited>yes</owner_edited>" in text
    new = text.split("<new_answers>")[1].split("</new_answers>")[0]
    assert "I would start with the cost." in new
    assert "Engineers and team leads" not in new
    assert "Engineers and team leads" in text  # still in all_my_answers


def test_improve_uses_body_when_not_edited(repos: Repos, clock: FakeClock) -> None:
    blog = repos.blogs.create("T", "T", "weekly")
    repos.drafts.add(blog.id, "T", "# T\n\nOriginal body.\n", "raw", {"packet_draft": 1})
    text = packets.build("improve", repos, Settings(), clock, blog_id=blog.id).text
    assert "Original body." in text
    assert "<owner_edited>no</owner_edited>" in text


def test_audit_contains_latest_draft(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    text = _build("audit", repos, settings, clock, ids).text
    assert "Wikis rot because nobody owns a page." in text


def test_topic_origin_note(repos: Repos, clock: FakeClock) -> None:
    blog = repos.blogs.create("T", "Picked topic", "weekly", topic_origin="auto_trending")
    text = packets.build("weekly", repos, Settings(), clock, blog_id=blog.id).text
    assert "<context>Topic picked by tea. No answers were given for this focus.</context>" in text
    owner = repos.blogs.create("T", "Mine", "weekly")
    text = packets.build("weekly", repos, Settings(), clock, blog_id=owner.id).text
    assert "Topic picked by tea" not in text


def test_errors(repos: Repos, clock: FakeClock, ids: SampleIds) -> None:
    from datetime import date

    with pytest.raises(PacketError):
        packets.build("weekly", repos, Settings(), clock, week=date(2020, 1, 6))
    with pytest.raises(PacketError):
        packets.build("improve", repos, Settings(), clock, blog_id=ids.manual_blog)  # no draft
    with pytest.raises(PacketError):
        packets.build("manual", repos, Settings(), clock, blog_id=9999)
    with pytest.raises(PacketError):
        packets.build("nope", repos, Settings(), clock, blog_id=ids.manual_blog)


def test_collapse_blank_runs() -> None:
    assert packets.collapse("a\n\n\n\nb\n  \n\n\nc\n\n") == "a\n\nb\n\nc\n"


def test_improve_uses_the_blogs_own_week(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    """Focus answers of the current week must not leak into last week's carried draft."""
    p = packets.build("improve", repos, settings, clock, blog_id=ids.carried_blog, week=ids.week)
    assert "Most specs I wrote were never opened." not in p.text
    assert p.week_start == ids.carried_week


def test_blocks_are_separated_by_a_blank_line(
    repos: Repos, settings: Settings, clock: FakeClock, ids: SampleIds
) -> None:
    text = _build("weekly_pick", repos, settings, clock, ids).text
    assert "</topic_pick>\n\n<research>" in text
