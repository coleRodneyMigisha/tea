"""Shared fixtures: every test gets its own data, config and state folders."""

import contextlib
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


@pytest.fixture(autouse=True)
def no_desktop_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach the owner's real notification server."""
    from tea import notify

    monkeypatch.setattr(notify.DBusBackend, "create", classmethod(lambda cls, parent=None: None))


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


@pytest.fixture(autouse=True)
def no_leftover_popups() -> Iterator[None]:
    """A question popup left open by a test keeps its 90 s timeout; firing in a later test,
    it would record the dismissal on a database that test already closed."""
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    from tea.ui.widgets.question_popup import QuestionPopup

    for widget in app.topLevelWidgets():
        if isinstance(widget, QuestionPopup):
            with contextlib.suppress(RuntimeError, TypeError):
                widget.finished.disconnect()
            widget.close()
            widget.deleteLater()


@pytest.fixture(autouse=True)
def no_desktop_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never ask the owner's desktop (gsettings) what it prefers."""
    from types import SimpleNamespace

    monkeypatch.setattr("tea.settings.desktop", SimpleNamespace(animations_disabled=lambda: False))
    monkeypatch.setattr("tea.ui.theme.desktop", SimpleNamespace(text_scaling_factor=lambda: 1.0))
