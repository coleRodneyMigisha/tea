"""Fixtures: sample blogs, questions and answers, and sample replies (see sample_replies).

`python -m tea.devtools.sample_data` seeds the database in TEA_DATA_DIR (or the real one),
so `tea packet` and `tea import-reply` have something to work on.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from tea import config
from tea.clock import Clock, FakeClock, SystemClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.devtools.sample_replies import MALFORMED, WELL_FORMED
from tea.domain.weeks import week_start

FOCUS = "Why small teams should write fewer documents"
CARRIED_TITLE = "What onboarding wikis get wrong"

# (bank_key, category, kind, text, options, answer); None as answer = skipped.
BANK: list[tuple[str, str, str, str, list[str], str | None]] = [
    ("s-voice-1", "voice", "text", "Describe your writing voice in a sentence.", [],
     "Plain and a bit dry. I like short sentences."),
    ("s-voice-2", "voice", "scale", "How formal should your writing feel?",
     ["Like talking to a friend", "Like a journal article"], "2"),
    ("s-aud-1", "audience", "text", "Who reads your posts?", [],
     "Engineers and team leads at small companies."),
    ("s-str-1", "structure", "choice", "How should a post open?",
     ["With the answer", "With a story"], "With the answer"),
    ("s-evd-1", "evidence", "text", "What counts as good evidence for you?", [],
     "Published studies and things I have seen first-hand."),
    ("s-exp-1", "experience", "text", "What have you worked on recently?", [], None),
    ("s-bnd-1", "boundaries", "text", "What should never appear in your posts?", [],
     "Never name my employer or clients."),
]  # fmt: skip


@dataclass(frozen=True)
class SampleIds:
    week: date
    weekly_blog: int
    carried_week: date
    carried_blog: int
    carried_draft: int
    manual_blog: int


def seed(repos: Repos, clock: Clock) -> SampleIds:
    """Create a current weekly blog, a carried-over draft, and a manual blog."""
    week = week_start(clock.now())
    prev = week - timedelta(days=7)
    with repos.transaction():
        _seed_bank(repos)
        weekly = repos.blogs.create(
            FOCUS, FOCUS, "weekly", allowed_sources=["own_documents", "web", "academic"]
        )
        repos.weeks.set_focus(week, FOCUS)
        repos.weeks.set_blog(week, weekly.id)
        q = repos.questions.create(
            f'What is your real position on "{FOCUS}"?', "text", "experience", "week",
            week_start=week, template_key="f-position",
        )  # fmt: skip
        repos.answers.add(q.id, "monday", "Most specs I wrote were never opened.", week_start=week)

        carried = repos.blogs.create(
            CARRIED_TITLE, "Onboarding wikis", "weekly", allowed_sources=["web"], status="ready"
        )
        repos.weeks.set_focus(prev, "Onboarding wikis")
        repos.weeks.set_blog(prev, carried.id)
        draft = repos.drafts.add(
            carried.id,
            CARRIED_TITLE,
            f"# {CARRIED_TITLE}\n\nWikis rot because nobody owns them.\n",
            WELL_FORMED["weekly"],
            {"packet_draft": 1},
        )
        repos.drafts.set_edited(
            draft.id, f"# {CARRIED_TITLE}\n\nWikis rot because nobody owns a page.\n"
        )
        improve_q = repos.questions.create(
            f'Which part of the draft "{CARRIED_TITLE}" sounds least like you?', "text",
            "improve", "improve", blog_id=carried.id, template_key="i-least-you",
        )  # fmt: skip

        manual = repos.blogs.create(
            "Reading papers faster", "How to read an academic paper in 20 minutes", "manual",
            scope_notes="Skimming order, what to skip, when to stop.",
            audience="Graduate students", length="short", allowed_sources=["own_documents"],
        )  # fmt: skip
        scope_q = repos.questions.create(
            "What is the one thing a reader should take away?", "text", "scope", "blog",
            blog_id=manual.id,
        )  # fmt: skip
        repos.answers.add(scope_q.id, "blog_scope", "Read the figures first.", blog_id=manual.id)
        repos.attachments.add(manual.id, "keshav-how-to-read.pdf", "/dev/null", "pdf", 120_000)
    # Answered after the carried draft was imported, so it counts as a new answer.
    _later(clock)
    repos.answers.add(improve_q.id, "login", "The opening line. I would start with the cost.")
    return SampleIds(week, weekly.id, prev, carried.id, draft.id, manual.id)


def _seed_bank(repos: Repos) -> None:
    for key, category, kind, text, options, answer in BANK:
        q = repos.questions.create(text, kind, category, "bank", options=options, bank_key=key)
        if answer is None:
            repos.answers.add(q.id, "login", skipped=True)
        else:
            repos.answers.add(q.id, "login", answer)


def _later(clock: Clock) -> None:
    if isinstance(clock, FakeClock):
        clock.advance(minutes=5)


def write_replies(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for prefix, replies in (("reply", WELL_FORMED), ("malformed", MALFORMED)):
        for name, text in replies.items():
            path = folder / f"{prefix}_{name}.txt"
            path.write_text(text, encoding="utf-8")
            written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tea.devtools.sample_data")
    parser.add_argument("--write-replies", metavar="DIR", help="also write sample replies here")
    args = parser.parse_args(argv)
    path = config.db_path()
    conn = open_db(path)
    try:
        # Start a little in the past so the "new" answer lands after the carried draft's import.
        system_clock = SystemClock()
        clock = FakeClock(system_clock.now() - timedelta(minutes=10))
        repos = Repos(conn, clock)
        if repos.blogs.list():
            print(f"{path} already has blogs; not seeding.", file=sys.stderr)
            return 1
        ids = seed(repos, clock)
    finally:
        conn.close()
    print(f"Seeded {path}: {ids}")
    if args.write_replies:
        for reply in write_replies(Path(args.write_replies)):
            print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
