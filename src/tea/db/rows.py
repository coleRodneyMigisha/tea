"""Typed rows returned by the repositories. JSON columns are decoded; flags become bools."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any


def _json(value: str | None) -> Any:
    return json.loads(value) if value else None


def _week(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Blog:
    id: int
    title: str
    topic: str
    scope_notes: str
    audience: str
    length: str
    allowed_sources: list[str]
    origin: str
    topic_origin: str
    status: str
    carried_weeks: int
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Blog":
        d = dict(r)
        d["allowed_sources"] = _json(d["allowed_sources"]) or []
        return cls(**d)


@dataclass(frozen=True)
class Week:
    week_start: date
    focus_text: str | None
    topic_origin: str
    pick_mode: bool
    focus_set_at: str | None
    blog_id: int | None
    trend_candidates: Any

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Week":
        d = dict(r)
        d["week_start"] = date.fromisoformat(d["week_start"])
        d["pick_mode"] = bool(d["pick_mode"])
        d["trend_candidates"] = _json(d["trend_candidates"])
        return cls(**d)


@dataclass(frozen=True)
class Question:
    id: int
    text: str
    kind: str
    options: list[Any]
    category: str
    origin: str
    week_start: date | None
    blog_id: int | None
    active: bool
    asked_count: int
    last_asked_at: str | None
    template_key: str | None
    bank_key: str | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Question":
        d = dict(r)
        d["options"] = _json(d["options"]) or []
        d["week_start"] = _week(d["week_start"])
        d["active"] = bool(d["active"])
        return cls(**d)


@dataclass(frozen=True)
class Answer:
    id: int
    question_id: int
    context: str
    week_start: date | None
    blog_id: int | None
    answer_text: str
    skipped: bool
    answered_at: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Answer":
        d = dict(r)
        d["week_start"] = _week(d["week_start"])
        d["skipped"] = bool(d["skipped"])
        return cls(**d)


@dataclass(frozen=True)
class Attachment:
    id: int
    blog_id: int
    filename: str
    stored_path: str
    kind: str
    size_bytes: int
    include_in_list: bool
    added_at: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Attachment":
        d = dict(r)
        d["include_in_list"] = bool(d["include_in_list"])
        return cls(**d)


@dataclass(frozen=True)
class Draft:
    id: int
    blog_id: int
    version: int
    kind: str
    title: str
    body_markdown: str
    edited_markdown: str | None
    raw_reply: str
    sources: list[Any]
    verification: list[dict[str, Any]]
    flags: list[str]
    changes: list[Any]
    parse_warnings: list[str]
    prompt_versions: dict[str, int]
    imported_at: str
    copied_at: str | None
    posted_at: str | None

    @property
    def is_used(self) -> bool:
        """DECISIONS D3: copied for Medium or marked posted."""
        return self.copied_at is not None or self.posted_at is not None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Draft":
        d = dict(r)
        for key in ("sources", "verification", "flags", "changes", "parse_warnings"):
            d[key] = _json(d[key]) or []
        d["prompt_versions"] = _json(d["prompt_versions"]) or {}
        return cls(**d)


@dataclass(frozen=True)
class Handoff:
    id: int
    kind: str
    blog_id: int | None
    week_start: date | None
    packet_text: str
    packet_words: int
    prompt_versions: dict[str, int]
    status: str
    created_at: str
    copied_at: str | None
    imported_at: str | None
    draft_id: int | None
    reminder_count: int
    last_reminder_at: str | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Handoff":
        d = dict(r)
        d["week_start"] = _week(d["week_start"])
        d["prompt_versions"] = _json(d["prompt_versions"]) or {}
        return cls(**d)


@dataclass(frozen=True)
class Job:
    kind: str
    week_start: date | None
    blog_id: int
    status: str
    last_attempt_at: str | None
    snoozed_until: str | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Job":
        d = dict(r)
        d["week_start"] = _week(d["week_start"])
        return cls(**d)
