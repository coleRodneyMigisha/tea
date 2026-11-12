"""Parse warnings and Claude's flags in plain words (UI_DESIGN 8), and the recovery each needs.

The hand-off dialog's summary and the Check before posting drawer both use this.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from tea.handoff.importer import NO_TOPIC
from tea.ui import strings

AUDIT = "audit"  # copy an audit prompt that adds the missing verification
CONTINUE = "continue"  # copy a "continue" prompt for a cut-off reply
TOPIC = "topic"  # type the topic Claude chose (pick mode)

# A flag saying Claude could not search, for example "I couldn't search the web".
_NO_SEARCH = re.compile(
    r"\b(could ?n[o']?t|can ?n[o']?t|unable to|was not able to|wasn't able to)\b"
    r"[^.]{0,40}\b(search|brows|web access|internet)"
    r"|\bno (web|internet) access\b|\bwithout (web|internet) access\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Notes:
    lines: list[str]
    recoveries: list[str]


def claude_could_not_search(flags: Sequence[str]) -> bool:
    return any(_NO_SEARCH.search(f) for f in flags)


def notes(warnings: Sequence[str], flags: Sequence[str] = ()) -> Notes:
    lines: list[str] = []
    recoveries: list[str] = []

    def add(line: str, recovery: str | None = None) -> None:
        if line not in lines:
            lines.append(line)
        if recovery and recovery not in recoveries:
            recoveries.append(recovery)

    for code in warnings:
        if code == "no_draft_tag":
            add(strings.PARSE_NO_DRAFT)
        elif code == "no_verification":
            add(strings.PARSE_NO_VERIFICATION, AUDIT)
        elif code.startswith("truncated"):
            add(strings.PARSE_TRUNCATED, CONTINUE)
        elif code == "unknown_status":
            add(strings.PARSE_UNKNOWN_STATUS)
        elif code == NO_TOPIC:
            add(strings.PICK_NO_TOPIC, TOPIC)
    if claude_could_not_search(flags):
        add(strings.CLAUDE_NO_SEARCH)
    return Notes(lines, recoveries)


def medium_lines(codes: Sequence[str]) -> list[str]:
    return [strings.MEDIUM_WARNINGS[c] for c in codes if c in strings.MEDIUM_WARNINGS]
