import sqlite3
from pathlib import Path

import pytest

from tea.db.connection import connect, migrate, open_db, schema_version

ROOT = Path(__file__).resolve().parent.parent
DOC_SQL = ROOT / "docs" / "DATA_MODEL.sql"
MIGRATION = ROOT / "src" / "tea" / "migrations" / "001_initial.sql"


def _shape(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str, int, int]]]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        t: [(c[1], c[2], c[3], c[5]) for c in conn.execute(f"PRAGMA table_info({t})")]
        for t in sorted(tables)
    }


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        )
    }


def test_migration_file_is_copy_of_docs() -> None:
    assert MIGRATION.read_text() == DOC_SQL.read_text()


def test_schema_matches_data_model(conn: sqlite3.Connection) -> None:
    reference = sqlite3.connect(":memory:")
    reference.executescript(DOC_SQL.read_text())
    assert _shape(conn) == _shape(reference)
    assert _indexes(conn) == _indexes(reference)
    assert set(_shape(conn)) == {
        "meta",
        "blogs",
        "weeks",
        "attachments",
        "questions",
        "answers",
        "drafts",
        "handoffs",
        "jobs",
    }


def test_schema_version_recorded(conn: sqlite3.Connection) -> None:
    assert schema_version(conn) == 1


def test_migrations_idempotent(db_path: Path) -> None:
    first = open_db(db_path)
    first.execute(
        "INSERT INTO blogs (title, topic, origin, created_at, updated_at) "
        "VALUES ('t', 'x', 'manual', 'now', 'now')"
    )
    before = _shape(first)
    first.close()
    second = open_db(db_path)
    assert migrate(second) == []
    assert migrate(second) == []
    assert _shape(second) == before
    assert schema_version(second) == 1
    assert second.execute("SELECT COUNT(*) FROM blogs").fetchone()[0] == 1
    second.close()


def test_fresh_migrate_reports_applied(db_path: Path) -> None:
    conn = connect(db_path)
    assert schema_version(conn) == 0
    assert migrate(conn) == [1]
    conn.close()


def test_pragmas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_foreign_keys_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO attachments (blog_id, filename, stored_path, kind, size_bytes, added_at)"
            " VALUES (999, 'a', 'b', 'pdf', 1, 'now')"
        )


def test_check_constraints(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO blogs (title, topic, origin, created_at, updated_at)"
            " VALUES ('t', 'x', 'robot', 'now', 'now')"
        )


def test_second_connection_sees_writes(db_path: Path, conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO blogs (title, topic, origin, created_at, updated_at)"
        " VALUES ('t', 'x', 'manual', 'now', 'now')"
    )
    worker = connect(db_path)
    assert worker.execute("SELECT COUNT(*) FROM blogs").fetchone()[0] == 1
    assert worker.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    worker.close()


def test_failed_migration_rolls_back(db_path: Path, tmp_path: Path) -> None:
    folder = tmp_path / "migs"
    folder.mkdir()
    (folder / "001_a.sql").write_text(
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "INSERT INTO meta VALUES ('schema_version', '1');"
    )
    (folder / "002_b.sql").write_text("CREATE TABLE ok (x); CREATE TABLE broken (;")
    conn = connect(db_path)
    with pytest.raises(sqlite3.Error):
        migrate(conn, folder)
    assert schema_version(conn) == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='ok'").fetchone() is None
    conn.close()
