"""Every message in UI_DESIGN 8 reads as written and is reachable from real code (M11)."""

import re
from pathlib import Path

import pytest

from tea.db.rows import Draft
from tea.ui import strings
from tea.ui.widgets.handoff_parts import summary_text

# (constant in strings.py, the text in UI_DESIGN 8). The disclosure notice is left out:
# the owner dropped that feature (DEVIATIONS M1).
MESSAGES = [
    ("COPIED_FOR_MEDIUM", "Copied for Medium"),
    ("AFTER_COPY", "Copied. Mark as posted when it's live."),
    ("PROMPT_COPIED", "Prompt copied"),
    ("WEB_SEARCH_HINT", "Turn on web search in Claude if you want it to research."),
    ("ATTACH_FILES", "Attach these files in Claude:"),
    ("FIRST_FILE_ADDED", "tea only stores these. You attach them to the Claude chat yourself."),
    ("FILE_TOO_LARGE", "{name} is over 50 MB. Choose a smaller file or split it."),
    ("TOO_MANY_FILES", "A blog can have up to 20 files. Remove one to add another."),
    ("WAITING_FOR_REPLY", "Waiting for Claude's reply"),
    ("IMPORT_SUMMARY", "Imported {title}: {words} words, {claims} claims to check."),
    (
        "PARSE_NO_DRAFT",
        "The reply had no draft section, so tea used the whole reply as the draft. "
        "Check the start and end.",
    ),
    (
        "PARSE_NO_VERIFICATION",
        "The reply had no verification section. You can copy a prompt that asks Claude to add one.",
    ),
    (
        "PARSE_TRUNCATED",
        "The reply looks cut off at the end. You can copy a prompt asking Claude to continue.",
    ),
    ("PARSE_UNKNOWN_STATUS", "Some claims had an unclear status and are marked as weak."),
    ("PICK_NO_TOPIC", "Type the topic Claude chose, so tea can file the draft under it."),
    (
        "CLAUDE_NO_SEARCH",
        "Claude said it couldn't search the web. Check the claims before posting, "
        "or set your own topic.",
    ),
    (
        "NO_QUESTIONS_LEFT",
        "You've answered every question for now. New ones arrive with next week's focus.",
    ),
    (
        "EMPTY_DRAFTS",
        "No drafts yet. Your first prompt is ready on Friday, or start one from New blog.",
    ),
    ("AUTO_TOPIC", "Picked by tea because you hadn't set a focus."),
    ("AUTO_TOPIC_NOTE", "Topic picked by tea. No answers were given for this focus."),
    (
        "CARRIED_OVER",
        "Carried over from last week. An improvement prompt is prepared on Friday.",
    ),
    ("SHELVED", "Shelved. tea won't prepare anything for this draft unless you revive it."),
]

SRC = Path(strings.__file__).parents[1]


def _code_outside_strings() -> str:
    skip = {"strings.py", "strings_settings.py"}
    return "\n".join(p.read_text() for p in SRC.rglob("*.py") if p.name not in skip)


@pytest.mark.parametrize(("name", "text"), MESSAGES, ids=[m[0] for m in MESSAGES])
def test_text_matches_ui_design(name: str, text: str) -> None:
    assert getattr(strings, name) == text


@pytest.mark.parametrize("name", [m[0] for m in MESSAGES])
def test_message_is_used_by_a_real_code_path(name: str) -> None:
    pattern = rf"\b(strings\.)?{name}\b"
    assert re.search(pattern, _code_outside_strings()), f"{name} is never shown"


def _draft(claims: int, words: int) -> Draft:
    return Draft(
        id=1,
        blog_id=1,
        version=1,
        kind="weekly",
        title="Small teams",
        body_markdown=" ".join(["word"] * words),
        edited_markdown=None,
        raw_reply="",
        sources=[],
        verification=[{"claim": f"c{i}", "status": "weak"} for i in range(claims)],
        flags=[],
        changes=[],
        parse_warnings=[],
        prompt_versions={},
        imported_at="2026-11-13T18:05:00+03:00",
        copied_at=None,
        posted_at=None,
    )


def test_import_summary_reads_like_the_doc() -> None:
    assert summary_text(_draft(6, 1184)) == "Imported Small teams: 1,184 words, 6 claims to check."
