"""Dev and recovery commands: `tea packet` and `tea import-reply` (ARCHITECTURE 12)."""

import argparse
import sys
from datetime import date

from tea import config, settings
from tea.clock import Clock, SystemClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.domain.weeks import week_start
from tea.handoff import packets
from tea.handoff.importer import import_reply


def _fail(message: str) -> int:
    print(f"tea: {message}", file=sys.stderr)
    return 1


def _carried_blog(repos: Repos, before: date) -> int | None:
    """The most recent weekly blog from an earlier week whose latest draft is unused."""
    for w in sorted(repos.weeks.list(), key=lambda w: w.week_start, reverse=True):
        if w.week_start >= before or w.blog_id is None:
            continue
        draft = repos.drafts.latest_for_blog(w.blog_id)
        if draft is not None and not draft.is_used:
            return w.blog_id
    return None


def run_packet(args: argparse.Namespace, clock: Clock | None = None) -> int:
    clock = clock or SystemClock()
    try:
        week = week_start(date.fromisoformat(args.week)) if args.week else week_start(clock.now())
    except ValueError:
        return _fail(f"--week must be a date like 2026-11-09, not {args.week!r}")
    try:
        conf = settings.load()
    except settings.SettingsError as exc:
        return _fail(str(exc))
    conn = open_db(config.db_path())
    try:
        repos = Repos(conn, clock)
        kind = args.kind or _default_kind(repos, week)
        blog_id = None
        if kind == "improve":
            blog_id = _carried_blog(repos, week)
            if blog_id is None:
                return _fail(f"no carried-over draft before the week of {week}")
        try:
            packet = packets.build(kind, repos, conf, clock, blog_id=blog_id, week=week)
        except packets.PacketError as exc:
            return _fail(str(exc))
        for old in repos.handoffs.list(open_only=True, blog_id=packet.blog_id, week_start=week):
            repos.handoffs.mark_superseded(old.id)
        handoff = repos.handoffs.create(
            kind,
            packet.text,
            packet.words,
            packet.prompt_versions,
            blog_id=packet.blog_id,
            week_start=week,
        )
    finally:
        conn.close()
    sys.stdout.write(packet.text)
    print(f"handoff {handoff.id}, {packet.kind}, {packet.words} words", file=sys.stderr)
    return 0


def _default_kind(repos: Repos, week: date) -> str:
    w = repos.weeks.get(week)
    return "weekly_pick" if w is not None and w.pick_mode and not w.focus_text else "weekly"


def run_import(args: argparse.Namespace, clock: Clock | None = None) -> int:
    clock = clock or SystemClock()
    try:
        with open(args.file, encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        return _fail(f"could not read {args.file}: {exc.strerror}")
    conn = open_db(config.db_path())
    try:
        repos = Repos(conn, clock)
        handoff_id = args.handoff
        if handoff_id is None:
            open_ones = repos.handoffs.list(open_only=True)
            if not open_ones:
                return _fail("no hand-off is waiting for a reply; run `tea packet` first")
            handoff_id = open_ones[-1].id
        try:
            result = import_reply(repos, handoff_id, text)
        except LookupError as exc:
            return _fail(str(exc))
    finally:
        conn.close()
    d = result.draft
    print(f"Imported hand-off {result.handoff_id} as draft {d.id}, version {d.version} ({d.kind})")
    print(f"Title: {d.title}")
    print(f"Words: {len(d.body_markdown.split())}, claims: {len(d.verification)}")
    flagged = sum(1 for c in d.verification if c["status"] != "supported")
    print(f"Claims flagged: {flagged}, flags: {len(d.flags)}")
    print(f"Warnings: {', '.join(result.warnings) or 'none'}")
    return 0
