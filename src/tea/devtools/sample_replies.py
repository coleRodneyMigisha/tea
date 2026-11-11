"""Sample pasted replies: one well-formed reply per hand-off kind, plus malformed ones.

Used by tests and by `python -m tea.devtools.sample_data --write-replies DIR`.
"""

_DRAFT = """\
# Small teams need fewer documents, not better ones

Most small teams write more documents than anyone reads. This post shows how to tell
which documents earn their keep, and how to drop the rest without losing what matters.

## Why most documents go unread

A document is useful only when someone opens it at the moment they need it. Teams of
five rarely have that moment, because the answer is usually one message away.

## Three questions before you write anything

Ask who will read it, when, and what they will do differently. If you cannot name a
reader, the page is a diary entry.

## Sources

- [Writing for the web](https://www.nngroup.com/articles/how-users-read-on-the-web/)
"""

_VERIFICATION = """\
supported | Most readers scan web pages rather than read word by word | https://www.nngroup.com/articles/how-users-read-on-the-web/ | 1997 study
weak | Teams of five rarely need written specs | my answers | opinion, framed as such
"""  # noqa: E501

_SOURCES = """\
- How Users Read on the Web | Nielsen Norman Group | https://www.nngroup.com/articles/how-users-read-on-the-web/
"""  # noqa: E501

_FLAGS = """\
- No first-hand story about a document that went unread was given.
"""

WEEKLY = f"""\
<draft>
{_DRAFT}</draft>

<verification>
{_VERIFICATION}</verification>

<sources>
{_SOURCES}</sources>

<flags>
{_FLAGS}</flags>
"""

MANUAL = WEEKLY.replace("Small teams need fewer documents", "Manual: fewer documents")

WEEKLY_PICK = """\
<topic>Right-to-repair rules for phones</topic>

<topic_candidates>
1 | Right-to-repair rules for phones | What the new rules change for buyers | Covered by two national outlets this week | https://example.org/a; https://example.org/b
2 | Four-day week trials | What the trial data says | Reported by two business papers | https://example.org/c
3 | Open data portals | Why reuse stays low
</topic_candidates>

<draft>
# What the new phone repair rules mean for you

The new rules make it easier to fix your own phone. Here is what changes and when.

## Spare parts must stay on sale

Makers now have to sell parts for several years after a model launches.
</draft>

<verification>
supported | Makers must sell parts for several years | https://example.org/a | as reported
</verification>

<sources>
- Repair rules explained | Example News | https://example.org/a
</sources>

<flags>
- Could not confirm the exact start date.
</flags>
"""  # noqa: E501

_CHANGES = """\
<changes>
- Added the story about the onboarding wiki from the new answers.
- Cut the closing summary paragraph.
</changes>
"""

IMPROVE = WEEKLY.replace("<verification>", _CHANGES + "\n<verification>", 1)
AUDIT = IMPROVE

WELL_FORMED: dict[str, str] = {
    "weekly": WEEKLY,
    "weekly_pick": WEEKLY_PICK,
    "manual": MANUAL,
    "improve": IMPROVE,
    "audit": AUDIT,
}

MALFORMED: dict[str, str] = {
    # No tags at all, with a chatty preamble line.
    "no_tags": "Here is your draft:\n\n" + _DRAFT,
    # Other sections are tagged, the draft is not.
    "no_draft_tag": f"{_DRAFT}\n<verification>\n{_VERIFICATION}</verification>\n",
    "no_verification": f"<draft>\n{_DRAFT}</draft>\n\n<flags>\n{_FLAGS}</flags>\n",
    # Cut off mid-way through the verification table.
    "truncated": f"<draft>\n{_DRAFT}</draft>\n\n<verification>\nsupported | Most readers scan",
    "pipes_in_claims": (
        f"<draft>\n{_DRAFT}</draft>\n<verification>\n"
        "supported | Tools like A | B and C | D are common | https://example.org/x | note\n"
        "</verification>\n"
    ),
    "unknown_statuses": (
        f"<draft>\n{_DRAFT}</draft>\n<verification>\n"
        "Verified | claim one | https://example.org/1 | ok\n"
        "partially | claim two | R2 | thin\n"
        "not supported | claim three | none | cut\n"
        "maybe | claim four | none | unsure\n"
        "</verification>\n"
    ),
    "only_draft": _DRAFT,
}
