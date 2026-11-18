"""`tea packet` and `tea import-reply` against a temporary database (sample data)."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", *args], capture_output=True, text=True, timeout=60)


@pytest.fixture
def replies(tmp_dirs: Path) -> Path:
    folder = tmp_dirs / "replies"
    seeded = _run("tea.devtools.sample_data", "--write-replies", str(folder))
    assert seeded.returncode == 0, seeded.stderr
    return folder


def _db(tmp_dirs: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_dirs / "data" / "tea.db")
    conn.row_factory = sqlite3.Row
    return conn


def test_seeding_twice_refuses(replies: Path) -> None:
    again = _run("tea.devtools.sample_data")
    assert again.returncode == 1 and "already has blogs" in again.stderr


def test_packet_weekly_prints_a_complete_prompt(replies: Path, tmp_dirs: Path) -> None:
    out = _run("tea", "packet", "--kind", "weekly")
    assert out.returncode == 0, out.stderr
    assert out.stdout.startswith("I am a writer.")
    assert "{{" not in out.stdout and "\n\n\n" not in out.stdout
    assert "<topic_pick>" not in out.stdout
    assert "handoff 1" in out.stderr and "words" in out.stderr
    row = _db(tmp_dirs).execute("SELECT kind, status, packet_text FROM handoffs").fetchone()
    assert (row["kind"], row["status"]) == ("weekly", "prompt_ready")
    assert row["packet_text"] == out.stdout


def test_packet_pick_and_improve(replies: Path) -> None:
    pick = _run("tea", "packet", "--kind", "weekly_pick")
    assert pick.returncode == 0, pick.stderr
    assert "<topic_pick>" in pick.stdout
    improve = _run("tea", "packet", "--kind", "improve")
    assert improve.returncode == 0, improve.stderr
    assert "<previous_draft>" in improve.stdout
    assert "Wikis rot because nobody owns a page." in improve.stdout
    new = improve.stdout.split("<new_answers>")[1].split("</new_answers>")[0]
    assert "I would start with the cost." in new
    assert "Most specs I wrote" not in improve.stdout  # this week's focus answer


def test_new_packet_supersedes_open_handoffs_for_the_week(replies: Path, tmp_dirs: Path) -> None:
    assert _run("tea", "packet").returncode == 0
    assert _run("tea", "packet", "--kind", "weekly_pick").returncode == 0
    rows = _db(tmp_dirs).execute("SELECT id, status FROM handoffs ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [(1, "superseded"), (2, "prompt_ready")]


def test_packet_default_kind_is_weekly(replies: Path) -> None:
    out = _run("tea", "packet")
    assert out.returncode == 0 and "<topic_pick>" not in out.stdout


def test_packet_for_week_without_blog_fails_cleanly(replies: Path) -> None:
    out = _run("tea", "packet", "--week", "2020-01-06")
    assert out.returncode == 1
    assert "Traceback" not in out.stderr and "2020-01-06" in out.stderr


def test_packet_rejects_bad_week(replies: Path) -> None:
    out = _run("tea", "packet", "--week", "not-a-date")
    assert out.returncode != 0 and "Traceback" not in out.stderr


def test_import_reply_round_trip(replies: Path, tmp_dirs: Path) -> None:
    # Thursday with no focus: the week is in pick mode, so `tea packet` picks weekly_pick.
    with _db(tmp_dirs) as db:
        db.execute("UPDATE weeks SET focus_text = NULL, pick_mode = 1 WHERE blog_id = 1")
    packet = _run("tea", "packet")
    assert packet.returncode == 0 and "weekly_pick" in packet.stderr
    out = _run("tea", "import-reply", str(replies / "reply_weekly_pick.txt"))
    assert out.returncode == 0, out.stderr
    assert "version 1" in out.stdout and "What the new phone repair rules" in out.stdout
    db = _db(tmp_dirs)
    assert db.execute("SELECT status FROM handoffs WHERE id = 1").fetchone()[0] == "imported"
    week = db.execute("SELECT * FROM weeks WHERE focus_text LIKE 'Right-to-repair%'").fetchone()
    assert week["topic_origin"] == "auto_trending"


def test_import_reply_reports_warnings(replies: Path) -> None:
    assert _run("tea", "packet").returncode == 0
    out = _run("tea", "import-reply", str(replies / "malformed_truncated.txt"))
    assert out.returncode == 0, out.stderr
    assert "truncated:verification" in out.stdout


def test_import_reply_without_open_handoff_fails(replies: Path) -> None:
    out = _run("tea", "import-reply", str(replies / "reply_weekly.txt"))
    assert out.returncode == 1 and "Traceback" not in out.stderr


def test_import_reply_missing_file_fails(replies: Path, tmp_dirs: Path) -> None:
    assert _run("tea", "packet").returncode == 0
    out = _run("tea", "import-reply", str(tmp_dirs / "nope.txt"))
    assert out.returncode == 1 and "Traceback" not in out.stderr


def test_seeding_ignores_the_new_blog_form_row(tmp_dirs: Path) -> None:
    """`make run` creates the New blog form's empty row; seeding must still work (M8)."""
    from tea import config
    from tea.clock import SystemClock
    from tea.db.connection import open_db
    from tea.db.repos import Repos
    from tea.domain import manual

    conn = open_db(config.db_path())
    manual.form_blog(Repos(conn, SystemClock()))
    conn.close()
    seeded = _run("tea.devtools.sample_data")
    assert seeded.returncode == 0, seeded.stderr
