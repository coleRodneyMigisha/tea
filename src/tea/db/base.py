"""Shared repository plumbing: row helpers, JSON encoding, week normalisation."""

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, TypeVar

from tea.clock import Clock, iso

T = TypeVar("T")


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def monday(day: date) -> str:
    return date.fromordinal(day.toordinal() - day.weekday()).isoformat()


def where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    """Build a WHERE clause from column=value pairs, skipping None values."""
    used = {k: v for k, v in filters.items() if v is not None}
    if not used:
        return "", []
    return " WHERE " + " AND ".join(f"{k} = ?" for k in used), list(used.values())


class Repo:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self.conn = conn
        self.clock = clock

    def _now(self) -> str:
        return iso(self.clock.now())

    def _one(
        self, make: Callable[[sqlite3.Row], T], sql: str, args: Sequence[Any] = ()
    ) -> T | None:
        row = self.conn.execute(sql, args).fetchone()
        return make(row) if row else None

    def _all(self, make: Callable[[sqlite3.Row], T], sql: str, args: Sequence[Any] = ()) -> list[T]:
        return [make(r) for r in self.conn.execute(sql, args)]

    def _insert(self, table: str, values: dict[str, Any]) -> int:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cur = self.conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values())
        )
        assert cur.lastrowid is not None
        return cur.lastrowid
