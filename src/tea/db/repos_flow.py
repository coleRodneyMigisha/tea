"""Repositories for the hand-off flow: drafts, handoffs and scheduler jobs."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from tea.clock import iso
from tea.db.base import Repo, dump, monday, where
from tea.db.connection import transaction
from tea.db.rows import Draft, Handoff, Job


class DraftRepo(Repo):
    def add(
        self,
        blog_id: int,
        title: str,
        body_markdown: str,
        raw_reply: str,
        prompt_versions: Mapping[str, int],
        *,
        kind: str = "new",
        version: int | None = None,
        sources: Sequence[Any] = (),
        verification: Sequence[Mapping[str, Any]] = (),
        flags: Sequence[str] = (),
        changes: Sequence[Any] = (),
        parse_warnings: Sequence[str] = (),
    ) -> Draft:
        """Store an imported draft. `version` defaults to the blog's next version number."""
        with transaction(self.conn):
            draft_id = self._insert(
                "drafts",
                {
                    "blog_id": blog_id,
                    "version": version if version is not None else self.next_version(blog_id),
                    "kind": kind,
                    "title": title,
                    "body_markdown": body_markdown,
                    "raw_reply": raw_reply,
                    "sources": dump(list(sources)),
                    "verification": dump([dict(v) for v in verification]),
                    "flags": dump(list(flags)),
                    "changes": dump(list(changes)),
                    "parse_warnings": dump(list(parse_warnings)),
                    "prompt_versions": dump(dict(prompt_versions)),
                    "imported_at": self._now(),
                },
            )
        draft = self.get(draft_id)
        assert draft is not None
        return draft

    def next_version(self, blog_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM drafts WHERE blog_id = ?", (blog_id,)
        ).fetchone()
        return int(row[0])

    def get(self, draft_id: int) -> Draft | None:
        return self._one(Draft.from_row, "SELECT * FROM drafts WHERE id = ?", (draft_id,))

    def list_for_blog(self, blog_id: int) -> list[Draft]:
        return self._all(
            Draft.from_row, "SELECT * FROM drafts WHERE blog_id = ? ORDER BY version", (blog_id,)
        )

    def latest_for_blog(self, blog_id: int) -> Draft | None:
        return self._one(
            Draft.from_row,
            "SELECT * FROM drafts WHERE blog_id = ? ORDER BY version DESC LIMIT 1",
            (blog_id,),
        )

    def set_edited(self, draft_id: int, markdown: str | None) -> None:
        """Save the owner's edits. `body_markdown` is never overwritten."""
        self.conn.execute(
            "UPDATE drafts SET edited_markdown = ? WHERE id = ?", (markdown, draft_id)
        )

    def mark_copied(self, draft_id: int) -> None:
        self.conn.execute("UPDATE drafts SET copied_at = ? WHERE id = ?", (self._now(), draft_id))

    def mark_posted(self, draft_id: int) -> None:
        self.conn.execute("UPDATE drafts SET posted_at = ? WHERE id = ?", (self._now(), draft_id))

    def delete(self, draft_id: int) -> None:
        self.conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))


class HandoffRepo(Repo):
    def create(
        self,
        kind: str,
        packet_text: str,
        packet_words: int,
        prompt_versions: Mapping[str, int],
        *,
        blog_id: int | None = None,
        week_start: date | None = None,
    ) -> Handoff:
        hid = self._insert(
            "handoffs",
            {
                "kind": kind,
                "blog_id": blog_id,
                "week_start": monday(week_start) if week_start else "",
                "packet_text": packet_text,
                "packet_words": packet_words,
                "prompt_versions": dump(dict(prompt_versions)),
                "created_at": self._now(),
            },
        )
        handoff = self.get(hid)
        assert handoff is not None
        return handoff

    def get(self, handoff_id: int) -> Handoff | None:
        return self._one(Handoff.from_row, "SELECT * FROM handoffs WHERE id = ?", (handoff_id,))

    def list(
        self,
        *,
        status: str | None = None,
        open_only: bool = False,
        blog_id: int | None = None,
        week_start: date | None = None,
        kind: str | None = None,
    ) -> list[Handoff]:
        """`open_only` means not yet imported and not superseded."""
        cond, args = where(
            {
                "status": status,
                "blog_id": blog_id,
                "week_start": monday(week_start) if week_start else None,
                "kind": kind,
            }
        )
        if open_only:
            cond += (" AND " if cond else " WHERE ") + "status IN ('prompt_ready', 'copied')"
        return self._all(Handoff.from_row, f"SELECT * FROM handoffs{cond} ORDER BY id", args)

    def latest(
        self, *, blog_id: int | None = None, week_start: date | None = None, kind: str | None = None
    ) -> Handoff | None:
        found = self.list(blog_id=blog_id, week_start=week_start, kind=kind)
        return found[-1] if found else None

    def mark_copied(self, handoff_id: int) -> None:
        self.conn.execute(
            "UPDATE handoffs SET status = 'copied', copied_at = ? WHERE id = ?",
            (self._now(), handoff_id),
        )

    def mark_imported(self, handoff_id: int, draft_id: int | None) -> None:
        self.conn.execute(
            "UPDATE handoffs SET status = 'imported', imported_at = ?, draft_id = ? WHERE id = ?",
            (self._now(), draft_id, handoff_id),
        )

    def mark_superseded(self, handoff_id: int) -> None:
        self.conn.execute("UPDATE handoffs SET status = 'superseded' WHERE id = ?", (handoff_id,))

    def record_reminder(self, handoff_id: int) -> None:
        self.conn.execute(
            "UPDATE handoffs SET reminder_count = reminder_count + 1, last_reminder_at = ?"
            " WHERE id = ?",
            (self._now(), handoff_id),
        )


class JobRepo(Repo):
    """Jobs are keyed by (kind, week_start, blog_id); '' and 0 stand for "none"."""

    @staticmethod
    def _key(kind: str, week_start: date | None, blog_id: int) -> tuple[str, str, int]:
        return kind, monday(week_start) if week_start else "", blog_id

    def get(self, kind: str, week_start: date | None = None, blog_id: int = 0) -> Job | None:
        return self._one(
            Job.from_row,
            "SELECT * FROM jobs WHERE kind = ? AND week_start = ? AND blog_id = ?",
            self._key(kind, week_start, blog_id),
        )

    def ensure(self, kind: str, week_start: date | None = None, blog_id: int = 0) -> Job:
        self.conn.execute(
            "INSERT INTO jobs (kind, week_start, blog_id) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            self._key(kind, week_start, blog_id),
        )
        job = self.get(kind, week_start, blog_id)
        assert job is not None
        return job

    def list(self, *, status: str | None = None) -> list[Job]:
        cond, args = where({"status": status})
        return self._all(
            Job.from_row, f"SELECT * FROM jobs{cond} ORDER BY week_start, kind, blog_id", args
        )

    def _set(
        self, column: str, value: Any, kind: str, week_start: date | None, blog_id: int
    ) -> None:
        self.ensure(kind, week_start, blog_id)
        self.conn.execute(
            f"UPDATE jobs SET {column} = ? WHERE kind = ? AND week_start = ? AND blog_id = ?",
            (value, *self._key(kind, week_start, blog_id)),
        )

    def record_attempt(self, kind: str, week_start: date | None = None, blog_id: int = 0) -> None:
        self._set("last_attempt_at", self._now(), kind, week_start, blog_id)

    def set_status(
        self, kind: str, status: str, week_start: date | None = None, blog_id: int = 0
    ) -> None:
        self._set("status", status, kind, week_start, blog_id)

    def snooze(
        self, kind: str, until: datetime | None, week_start: date | None = None, blog_id: int = 0
    ) -> None:
        self._set("snoozed_until", iso(until) if until else None, kind, week_start, blog_id)
