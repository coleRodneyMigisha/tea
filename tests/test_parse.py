"""handoff/parse: lenient reply parsing. It never raises."""

import random

import pytest

from tea.devtools.sample_replies import MALFORMED, WELL_FORMED
from tea.handoff.parse import ParsedReply, parse

TITLE = "Small teams need fewer documents, not better ones"


@pytest.mark.parametrize("kind", sorted(WELL_FORMED))
def test_well_formed_reply_for_each_kind(kind: str) -> None:
    r = parse(WELL_FORMED[kind])
    assert r.warnings == []
    assert r.title and r.draft_markdown and r.draft_markdown.startswith("# ")
    assert r.claims and r.sources and r.flags
    assert r.raw == WELL_FORMED[kind]
    assert bool(r.changes) == (kind in ("improve", "audit"))
    assert bool(r.topic) == (kind == "weekly_pick")


def test_weekly_fields() -> None:
    r = parse(WELL_FORMED["weekly"])
    assert r.title == TITLE
    assert r.draft_markdown is not None and r.draft_markdown.endswith("on-the-web/)")
    assert [c.status for c in r.claims] == ["supported", "weak"]
    assert r.claims[0].claim == "Most readers scan web pages rather than read word by word"
    assert r.claims[0].source.startswith("https://www.nngroup.com")
    assert r.claims[0].note == "1997 study"
    assert r.sources[0].title == "How Users Read on the Web"
    assert r.sources[0].publisher == "Nielsen Norman Group"
    assert r.sources[0].location.startswith("https://")
    assert r.flags == ["No first-hand story about a document that went unread was given."]


def test_pick_reply() -> None:
    r = parse(WELL_FORMED["weekly_pick"])
    assert r.topic == "Right-to-repair rules for phones"
    assert len(r.candidates) == 3
    first = r.candidates[0]
    assert (first.n, first.topic) == (1, "Right-to-repair rules for phones")
    assert first.angle == "What the new rules change for buyers"
    assert first.urls == ["https://example.org/a", "https://example.org/b"]
    short = r.candidates[2]  # fewer fields: kept with the missing parts empty
    assert (short.n, short.topic, short.angle, short.why, short.urls) == (
        3, "Open data portals", "Why reuse stays low", "", []
    )  # fmt: skip


def test_changes() -> None:
    r = parse(WELL_FORMED["improve"])
    assert r.changes == [
        "Added the story about the onboarding wiki from the new answers.",
        "Cut the closing summary paragraph.",
    ]


def test_tags_in_any_case_and_spacing() -> None:
    text = WELL_FORMED["weekly"].replace("<draft>", "<DRAFT >").replace("</draft>", "</ Draft>")
    text = text.replace("<verification>", "<Verification>")
    r = parse(text)
    assert r.title == TITLE and r.claims and r.warnings == []


def test_code_fence_around_whole_reply() -> None:
    r = parse("```xml\n" + WELL_FORMED["weekly"] + "```\n")
    assert r.title == TITLE and r.warnings == [] and len(r.claims) == 2


def test_code_fence_inside_draft_tag() -> None:
    text = WELL_FORMED["weekly"].replace("<draft>\n", "<draft>\n```markdown\n")
    text = text.replace("</draft>", "```\n</draft>")
    r = parse(text)
    assert r.draft_markdown is not None and r.draft_markdown.startswith("# ")
    assert "```" not in r.draft_markdown


def test_preamble_text() -> None:
    r = parse("Here is your draft, with the checks you asked for:\n\n" + WELL_FORMED["weekly"])
    assert r.title == TITLE and r.warnings == []
    assert r.draft_markdown is not None and "Here is" not in r.draft_markdown


def test_no_tags_at_all() -> None:
    r = parse(MALFORMED["no_tags"])
    assert r.warnings == ["no_draft_tag", "no_verification"]
    assert r.title == TITLE
    assert r.draft_markdown is not None and r.draft_markdown.startswith("# ")


def test_only_a_draft() -> None:
    r = parse(MALFORMED["only_draft"])
    assert r.warnings == ["no_draft_tag", "no_verification"]
    assert r.draft_markdown == MALFORMED["only_draft"].strip()


def test_missing_draft_tag_with_other_sections() -> None:
    r = parse(MALFORMED["no_draft_tag"])
    assert r.warnings == ["no_draft_tag"]
    assert r.title == TITLE
    assert r.draft_markdown is not None and "supported |" not in r.draft_markdown
    assert len(r.claims) == 2


def test_missing_verification() -> None:
    r = parse(MALFORMED["no_verification"])
    assert r.warnings == ["no_verification"]
    assert r.claims == [] and r.flags


def test_truncated_reply() -> None:
    r = parse(MALFORMED["truncated"])
    assert r.warnings == ["truncated:verification"]
    assert r.title == TITLE
    assert len(r.claims) == 1 and r.claims[0].claim == "Most readers scan"


def test_truncated_draft() -> None:
    r = parse("<draft>\n# Half a post\n\nIt stops mid")
    assert "truncated:draft" in r.warnings and "no_verification" in r.warnings
    assert r.title == "Half a post"
    assert r.draft_markdown == "# Half a post\n\nIt stops mid"


def test_unclosed_section_followed_by_another_is_not_truncation() -> None:
    r = parse("<draft>\n# T\n\nBody\n<verification>\nok | c | s | n\n</verification>")
    assert r.warnings == []
    assert r.draft_markdown == "# T\n\nBody"


def test_pipes_inside_claims() -> None:
    r = parse(MALFORMED["pipes_in_claims"])
    (claim,) = r.claims
    assert claim.status == "supported"
    assert claim.claim == "Tools like A | B and C | D are common"
    assert claim.source == "https://example.org/x"
    assert claim.note == "note"


def test_unknown_and_synonym_statuses() -> None:
    r = parse(MALFORMED["unknown_statuses"])
    assert [c.status for c in r.claims] == ["supported", "weak", "unsupported", "weak"]
    assert r.warnings == ["unknown_status"]
    assert "maybe" in r.claims[3].note and "unsure" in r.claims[3].note


@pytest.mark.parametrize(
    ("given", "status"),
    [("OK", "supported"), ("**Supported**", "supported"), ("Partially supported", "weak"),
     ("Unverified", "unsupported"), ("partial", "weak")],
)  # fmt: skip
def test_status_synonyms(given: str, status: str) -> None:
    r = parse(f"<draft>\n# T\n</draft>\n<verification>\n{given} | c | s | n\n</verification>")
    assert r.claims[0].status == status and r.warnings == []


def test_markdown_table_verification() -> None:
    table = (
        "| status | claim | source | note |\n|---|---|---|---|\n"
        "| supported | the claim | https://x.org | fine |\n"
    )
    r = parse(f"<draft>\n# T\n</draft>\n<verification>\n{table}</verification>")
    assert len(r.claims) == 1
    assert (r.claims[0].claim, r.claims[0].note) == ("the claim", "fine")


def test_short_verification_line() -> None:
    r = parse("<draft>\n# T\n</draft>\n<verification>\nweak | a claim\n</verification>")
    assert (r.claims[0].claim, r.claims[0].source, r.claims[0].note) == ("a claim", "", "")


def test_extra_unknown_tags_are_ignored() -> None:
    text = "<thinking>hmm</thinking>\n" + WELL_FORMED["weekly"] + "\n<extra>x</extra>\n"
    r = parse(text)
    assert r.title == TITLE and r.warnings == []


def test_empty_reply() -> None:
    for text in ("", "   \n\n", "```\n```"):
        r = parse(text)
        assert r.draft_markdown is None and r.title is None
        assert r.warnings == ["no_draft_tag", "no_verification"]
        assert r.raw == text


def test_raw_kept_verbatim() -> None:
    text = "\r\n  <draft>\r\n# T\r\n</draft>  \t"
    r = parse(text)
    assert r.raw == text
    assert r.title == "T"


def test_title_is_first_h1_only() -> None:
    r = parse("<draft>\n## Not this\n\n# This one #\n\n# Not this either\n</draft>")
    assert r.title == "This one"


def test_very_large_reply() -> None:
    body = "# Big\n\n" + ("A paragraph of text. " * 50 + "\n\n") * 4000
    claims = "".join(f"supported | claim {i} | src | n\n" for i in range(3000))
    r = parse(f"<draft>\n{body}</draft>\n<verification>\n{claims}</verification>")
    assert r.title == "Big" and len(r.claims) == 3000


def test_bad_types_and_garbage_never_raise() -> None:
    rng = random.Random(7)
    pieces = ["<draft>", "</draft>", "<verification>", "</verification>", "<topic>",
              "<topic_candidates>", "</topic_candidates>", "<sources>", "<flags>", "<changes>",
              " | ", "|", "\n", "# ", "```", "ok", "weird", "\x00", "é", "<", ">",
              "</"]  # fmt: skip
    for _ in range(500):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 40)))
        assert isinstance(parse(text), ParsedReply)
    assert isinstance(parse(None), ParsedReply)  # type: ignore[arg-type]
