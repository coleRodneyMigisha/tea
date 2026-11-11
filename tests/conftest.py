"""Shared fixtures: every test gets its own data, config and state folders."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection
from zoneinfo import ZoneInfo

import pytest

from tea.clock import FakeClock
from tea.db.connection import open_db
from tea.db.repos import Repos

KAMPALA = ZoneInfo("Africa/Kampala")


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("DATA", "CONFIG", "STATE", "RUNTIME"):
        folder = tmp_path / name.lower()
        monkeypatch.setenv(f"TEA_{name}_DIR", str(folder))
    monkeypatch.delenv("TEA_DEBUG", raising=False)
    monkeypatch.delenv("TEA_NOW", raising=False)
    return tmp_path


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 13, 17, 59, tzinfo=KAMPALA))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "tea.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[Connection]:
    connection = open_db(db_path)
    yield connection
    connection.close()


@pytest.fixture
def repos(conn: Connection, clock: FakeClock) -> Repos:
    return Repos(conn, clock)
