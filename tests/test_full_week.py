"""A full simulated fortnight on a FakeClock, and a grep of its log for owner content (M11).

Week 1 (Mon 9 Nov 2026): login questions, the focus dialog ignored, pick mode on Thursday,
Friday's pick prompt, a reminder, an import with an attached file and an edit. Week 2: the
unused draft is carried over, the owner answers its improvement questions, and on Friday an
improvement prompt is prepared and imported. The log is then searched for every canary text
the owner typed, pasted or named.
"""

import logging
import random
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from sched_world import W1, WEEK, World

from tea import config
from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.domain import attachments, drafts, weekly
from tea.domain import questions as qs
from tea.domain.weeks import week_start
from tea.handoff import packets
from tea.logging_setup import setup_logging
from tea.scheduler import (
    EnterPickMode,
    PreparePacket,
    RemindHandoff,
    Rollover,
    ShowFocusDialog,
    ShowLoginQuestions,
)
from tea.ui import strings

THU, FRI, SAT = (WEEK + timedelta(days=n) for n in (3, 4, 5))
FRI1 = W1 + timedelta(days=4)

# Text that must reach the prompts and the database but never the log.
ANSWER = "CANARY-answer I once lost a week to a spec nobody read"
FOCUS = "CANARY-focus why wikis rot"
STYLE = "CANARY-style never use exclamation marks"
FILE_NAME = "CANARY-file-budget.pdf"
EDIT = "CANARY-edit My own sentence, added by hand."
IMPROVE_ANSWER = "CANARY-improve I would start with the cost"
BROKEN_PASTE = "CANARY-paste some text that is not a reply at all"
CANARIES = [ANSWER, FOCUS, STYLE, FILE_NAME, EDIT, IMPROVE_ANSWER, BROKEN_PASTE]


@pytest.fixture
def world(qapp: QApplication, repos: Repos, clock: FakeClock) -> Iterator[World]:
    log = setup_logging(logging.DEBUG)
    yield World(repos, clock, style_notes=STYLE)
    for handler in logging.getLogger("tea").handlers:
        handler.flush()
    assert log.exists()


def _log_text() -> str:
    return config.log_path().read_text(encoding="utf-8")


def _flush() -> None:
    for handler in logging.getLogger("tea").handlers:
        handler.flush()


def _answer_login_questions(world: World, count: int = 3) -> None:
    now = world.clock.now()
    chosen = qs.select_login(world.repos, now, random.Random(1), count, week_start(now))
    assert len(chosen) == count
    for question in chosen:
        qs.record_answer(
            world.repos, question, "login", f"{ANSWER} ({question.id})",
            week_start=week_start(now),
        )  # fmt: skip


def simulate(world: World, tmp_path: Path) -> dict[str, int]:
    """Run the fortnight and check each step. Returns ids for the caller's later checks."""
    repos, clock = world.repos, world.clock

    # Monday 08:00: a login before the focus time shows the login questions only.
    world.at(WEEK, 8, 0)
    acts = world.run("start")
    assert ShowLoginQuestions() in acts and not any(isinstance(a, ShowFocusDialog) for a in acts)
    _answer_login_questions(world)

    # Monday 09:05: the focus dialog appears; the owner does not set a focus.
    world.at(WEEK, 9, 5)
    assert ShowFocusDialog(WEEK) in world.run("start")
    assert world.hooks.focus_shown == [WEEK]
    world.at(WEEK + timedelta(days=2), 12, 0)
    assert world.run() == []  # Wednesday is quiet

    # Thursday 09:00: no focus, so the week enters pick mode and the owner is told.
    world.at(THU, 9, 0)
    assert EnterPickMode(WEEK) in world.run()
    assert strings.NOTIFY_PICK in world.titles()

    # Friday 18:00: one pick prompt, with the owner's answers and style notes inside.
    world.at(FRI, 18, 0)
    assert [a for a in world.run() if isinstance(a, PreparePacket)] == [
        PreparePacket("weekly_pick", WEEK)
    ]
    [prompt] = world.handoffs(kind="weekly_pick")
    assert ANSWER in prompt.packet_text and STYLE in prompt.packet_text
    assert "<topic_pick>" in prompt.packet_text
    assert strings.NOTIFY_PROMPT_READY in world.titles()

    # Friday 21:00 login: a reminder, once.
    world.at(FRI, 21, 0)
    assert [a for a in world.run("start") if isinstance(a, RemindHandoff)] == [
        RemindHandoff(prompt.id)
    ]
    assert strings.NOTIFY_REMINDER in world.titles()

    # Saturday: the owner attaches a file, pastes a wrong text first, then the real reply.
    world.at(SAT, 10, 0)
    blog_id = prompt.blog_id
    assert blog_id is not None
    source = tmp_path / FILE_NAME
    source.write_text("pretend pdf")
    attachments.add(repos, blog_id, source)
    packet_with_file = packets.build("weekly_pick", repos, world.settings, clock, week=WEEK)
    assert FILE_NAME in packet_with_file.text
    from tea.handoff.importer import import_reply

    broken = import_reply(repos, prompt.id, BROKEN_PASTE)
    assert broken.warnings  # kept and explained, never raised
    reply = sample_replies.WEEKLY_PICK.replace(
        "Makers now have to sell parts", f"{EDIT} Makers now have to sell parts"
    )
    result = import_reply(repos, prompt.id, reply)
    draft = result.draft
    drafts.save_edit(repos, draft.id, drafts.current_text(draft) + "\n\n" + EDIT + "\n")
    w = repos.weeks.get(WEEK)
    assert w is not None and w.focus_text == "Right-to-repair rules for phones"  # the pick set it
    assert w.topic_origin == "auto_trending" and len(w.trend_candidates) == 3
    world.at(SAT, 14, 0)
    assert not [a for a in world.run("start") if isinstance(a, RemindHandoff)]  # imported: none

    # Monday of week 2: the unused draft is carried over; its improvement questions appear.
    world.at(W1, 0, 1)
    assert Rollover(W1, carry=(blog_id,)) in world.run()
    blog = repos.blogs.get(blog_id)
    assert blog is not None and blog.carried_weeks == 1
    improve_qs = repos.questions.list(origin="improve", blog_id=blog_id)
    assert improve_qs
    world.at(W1, 9, 5)
    world.set_focus(FOCUS, W1)
    qs.record_answer(repos, improve_qs[0], "login", IMPROVE_ANSWER, week_start=W1, blog_id=blog_id)

    # Friday of week 2: a weekly prompt and an improvement prompt, in one pass.
    world.at(FRI1, 18, 0)
    made = [a for a in world.run() if isinstance(a, PreparePacket)]
    assert made == [PreparePacket("weekly", W1), PreparePacket("improve", W1, blog_id)]
    [improve] = world.handoffs(kind="improve")
    text = improve.packet_text
    assert EDIT in text and "<owner_edited>yes</owner_edited>" in text
    new = text.split("<new_answers>")[1].split("</new_answers>")[0]
    assert IMPROVE_ANSWER in new and ANSWER not in new  # only answers given after the draft
    assert weekly.handoff_title(repos, improve)

    world.import_for(improve, "improve")
    versions = repos.drafts.list_for_blog(blog_id)
    assert [d.version for d in versions] == [1, 2, 3] and versions[-1].kind == "improved"
    return {"blog_id": blog_id}


def test_the_fortnight_runs_as_the_spec_says(world: World, tmp_path: Path) -> None:
    ids = simulate(world, tmp_path)
    blog = world.repos.blogs.get(ids["blog_id"])
    assert blog is not None and blog.status == "ready"
    assert len(world.live("weekly_pick")) == 1 and len(world.live("improve")) == 1
    # One prompt-ready notification per pass, never one per hand-off.
    assert world.titles().count(strings.NOTIFY_TWO_READY) == 1


def test_the_log_of_that_fortnight_holds_no_owner_content(world: World, tmp_path: Path) -> None:
    simulate(world, tmp_path)
    _flush()
    log = _log_text()
    assert "scheduler_ran" in log and "reply_imported" in log  # the log is not simply empty
    leaked = [c for c in CANARIES if c in log]
    assert leaked == []
    for word in ("Right-to-repair", "wikis", "phone repair", "budget", "exclamation"):
        assert word not in log, word


def test_logs_hold_only_event_names_ids_and_counts(world: World, tmp_path: Path) -> None:
    simulate(world, tmp_path)
    _flush()
    for line in _log_text().splitlines():
        # "<date> <time> <LEVEL> tea[.module] event key=value ..."
        fields = line.split(" ", 4)[-1].split(" ")
        assert fields[0].replace("_", "").isalnum(), line
        for token in fields[1:]:
            assert "=" in token, f"free text in a log line: {line}"
