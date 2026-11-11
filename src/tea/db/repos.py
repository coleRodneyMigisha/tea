"""Repositories for weeks, blogs, questions, answers, attachments, drafts, handoffs, jobs.

Each repository wraps one connection. Timestamps come from the injected clock.
Week starts are passed as dates and stored as YYYY-MM-DD Mondays.
"""

import sqlite3
from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any

from tea.clock import Clock, iso
from tea.db.base import Repo, dump, monday, where
from tea.db.connection import transaction
from tea.db.repos_flow import DraftRepo, HandoffRepo, JobRepo
from tea.db.rows import Answer, Attachment, Blog, Question, Week


class BlogRepo(Repo):
    _UPDATABLE = frozenset(
        {"title", "topic", "scope_notes", "audience", "length", "allowed_sources"}
        | {"topic_origin", "status", "carried_weeks"}
    )

    def create(
        self,
        title: str,
        topic: str,
        origin: str,
        *,
        scope_notes: str = "",
        audience: str = "",
        length: str = "standard",
        allowed_sources: Sequence[str] = (),
        topic_origin: str = "owner",
        status: str = "queued",
    ) -> Blog:
        now = self._now()
        blog_id = self._insert(
            "blogs",
            {
                "title": title,
                "topic": topic,
                "scope_notes": scope_notes,
                "audience": audience,
                "length": length,
                "allowed_sources": dump(list(allowed_sources)),
                "origin": origin,
                "topic_origin": topic_origin,
                "status": status,
                "created_at": now,
                "updated_at": now,
            },
        )
        blog = self.get(blog_id)
        assert blog is not None
        return blog

    def get(self, blog_id: int) -> Blog | None:
        return self._one(Blog.from_row, "SELECT * FROM blogs WHERE id = ?", (blog_id,))

    def list(self, *, status: str | None = None, origin: str | None = None) -> list[Blog]:
        cond, args = where({"status": status, "origin": origin})
        return self._all(Blog.from_row, f"SELECT * FROM blogs{cond} ORDER BY id", args)

    def update(self, blog_id: int, **fields: Any) -> None:
        unknown = set(fields) - self._UPDATABLE
        if unknown:
            raise ValueError(f"cannot update blog fields: {sorted(unknown)}")
        if "allowed_sources" in fields:
            fields["allowed_sources"] = dump(list(fields["allowed_sources"]))
        fields["updated_at"] = self._now()
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE blogs SET {sets} WHERE id = ?", [*fields.values(), blog_id])

    def set_status(self, blog_id: int, status: str) -> None:
        self.update(blog_id, status=status)

    def delete(self, blog_id: int) -> None:
        self.conn.execute("DELETE FROM blogs WHERE id = ?", (blog_id,))


class WeekRepo(Repo):
    def get(self, week: date) -> Week | None:
        return self._one(Week.from_row, "SELECT * FROM weeks WHERE week_start = ?", (monday(week),))

    def ensure(self, week: date) -> Week:
        self.conn.execute(
            "INSERT INTO weeks (week_start) VALUES (?) ON CONFLICT DO NOTHING", (monday(week),)
        )
        row = self.get(week)
        assert row is not None
        return row

    def list(self) -> list[Week]:
        return self._all(Week.from_row, "SELECT * FROM weeks ORDER BY week_start")

    def _set(self, week: date, **fields: Any) -> None:
        self.ensure(week)
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE weeks SET {sets} WHERE week_start = ?", [*fields.values(), monday(week)]
        )

    def set_focus(self, week: date, text: str | None, topic_origin: str = "owner") -> None:
        set_at = self._now() if text is not None else None
        self._set(week, focus_text=text, topic_origin=topic_origin, focus_set_at=set_at)

    def set_pick_mode(self, week: date, on: bool) -> None:
        self._set(week, pick_mode=int(on))

    def set_blog(self, week: date, blog_id: int | None) -> None:
        self._set(week, blog_id=blog_id)

    def set_trend_candidates(self, week: date, data: Any) -> None:
        self._set(week, trend_candidates=None if data is None else dump(data))

    def delete(self, week: date) -> None:
        self.conn.execute("DELETE FROM weeks WHERE week_start = ?", (monday(week),))


class QuestionRepo(Repo):
    def create(
        self,
        text: str,
        kind: str,
        category: str,
        origin: str,
        *,
        options: Sequence[Any] = (),
        week_start: date | None = None,
        blog_id: int | None = None,
        template_key: str | None = None,
        bank_key: str | None = None,
    ) -> Question:
        qid = self._insert(
            "questions",
            {
                "text": text,
                "kind": kind,
                "options": dump(list(options)),
                "category": category,
                "origin": origin,
                "week_start": monday(week_start) if week_start else None,
                "blog_id": blog_id,
                "template_key": template_key,
                "bank_key": bank_key,
            },
        )
        q = self.get(qid)
        assert q is not None
        return q

    def get(self, question_id: int) -> Question | None:
        return self._one(Question.from_row, "SELECT * FROM questions WHERE id = ?", (question_id,))

    def get_by_bank_key(self, bank_key: str) -> Question | None:
        return self._one(
            Question.from_row, "SELECT * FROM questions WHERE bank_key = ?", (bank_key,)
        )

    def list(
        self,
        *,
        origin: str | None = None,
        week_start: date | None = None,
        blog_id: int | None = None,
        active_only: bool = True,
    ) -> list[Question]:
        cond, args = where(
            {
                "origin": origin,
                "week_start": monday(week_start) if week_start else None,
                "blog_id": blog_id,
                "active": 1 if active_only else None,
            }
        )
        return self._all(Question.from_row, f"SELECT * FROM questions{cond} ORDER BY id", args)

    def mark_asked(self, question_id: int) -> None:
        self.conn.execute(
            "UPDATE questions SET asked_count = asked_count + 1, last_asked_at = ? WHERE id = ?",
            (self._now(), question_id),
        )

    def set_active(self, question_id: int, active: bool) -> None:
        self.conn.execute(
            "UPDATE questions SET active = ? WHERE id = ?", (int(active), question_id)
        )

    def delete(self, question_id: int) -> None:
        self.conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))


class AnswerRepo(Repo):
    def add(
        self,
        question_id: int,
        context: str,
        answer_text: str = "",
        *,
        skipped: bool = False,
        week_start: date | None = None,
        blog_id: int | None = None,
    ) -> Answer:
        aid = self._insert(
            "answers",
            {
                "question_id": question_id,
                "context": context,
                "week_start": monday(week_start) if week_start else None,
                "blog_id": blog_id,
                "answer_text": answer_text,
                "skipped": int(skipped),
                "answered_at": self._now(),
            },
        )
        a = self.get(aid)
        assert a is not None
        return a

    def get(self, answer_id: int) -> Answer | None:
        return self._one(Answer.from_row, "SELECT * FROM answers WHERE id = ?", (answer_id,))

    def list(
        self,
        *,
        blog_id: int | None = None,
        week_start: date | None = None,
        since: datetime | None = None,
    ) -> list[Answer]:
        cond, args = where(
            {"blog_id": blog_id, "week_start": monday(week_start) if week_start else None}
        )
        if since is not None:
            # julianday() understands the stored offsets, so this compares instants.
            cond += (" AND " if cond else " WHERE ") + "julianday(answered_at) >= julianday(?)"
            args.append(iso(since))
        return self._all(Answer.from_row, f"SELECT * FROM answers{cond} ORDER BY id", args)

    def delete(self, answer_id: int) -> None:
        self.conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))


class AttachmentRepo(Repo):
    def add(
        self, blog_id: int, filename: str, stored_path: str, kind: str, size_bytes: int
    ) -> Attachment:
        att_id = self._insert(
            "attachments",
            {
                "blog_id": blog_id,
                "filename": filename,
                "stored_path": stored_path,
                "kind": kind,
                "size_bytes": size_bytes,
                "added_at": self._now(),
            },
        )
        att = self.get(att_id)
        assert att is not None
        return att

    def get(self, attachment_id: int) -> Attachment | None:
        return self._one(
            Attachment.from_row, "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        )

    def list_for_blog(self, blog_id: int, *, included_only: bool = False) -> list[Attachment]:
        cond, args = where({"blog_id": blog_id, "include_in_list": 1 if included_only else None})
        return self._all(Attachment.from_row, f"SELECT * FROM attachments{cond} ORDER BY id", args)

    def count_for_blog(self, blog_id: int) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM attachments WHERE blog_id = ?", (blog_id,))
        return int(row.fetchone()[0])

    def set_included(self, attachment_id: int, included: bool) -> None:
        self.conn.execute(
            "UPDATE attachments SET include_in_list = ? WHERE id = ?",
            (int(included), attachment_id),
        )

    def delete(self, attachment_id: int) -> None:
        self.conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))


class Repos:
    """All repositories over one connection. Workers build their own with `connect()`."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self.conn = conn
        self.blogs = BlogRepo(conn, clock)
        self.weeks = WeekRepo(conn, clock)
        self.questions = QuestionRepo(conn, clock)
        self.answers = AnswerRepo(conn, clock)
        self.attachments = AttachmentRepo(conn, clock)
        self.drafts = DraftRepo(conn, clock)
        self.handoffs = HandoffRepo(conn, clock)
        self.jobs = JobRepo(conn, clock)

    def transaction(self) -> AbstractContextManager[None]:
        return transaction(self.conn)


__all__ = [
    "AnswerRepo",
    "AttachmentRepo",
    "BlogRepo",
    "DraftRepo",
    "HandoffRepo",
    "JobRepo",
    "QuestionRepo",
    "Repos",
    "WeekRepo",
]
