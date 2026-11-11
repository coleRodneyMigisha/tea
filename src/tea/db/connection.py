"""Open the database (WAL, foreign_keys=ON) and run migrations.

Connections run in autocommit mode; group statements with `transaction()`.
Every worker thread opens its own connection with `connect()`.
"""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection with tea's pragmas. Does not migrate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def open_db(path: Path) -> sqlite3.Connection:
    """Open the app database and bring its schema up to date."""
    conn = connect(path)
    migrate(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """All-or-nothing block. Nests safely (savepoints)."""
    conn.execute("SAVEPOINT tea_tx")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK TO tea_tx")
        conn.execute("RELEASE tea_tx")
        raise
    conn.execute("RELEASE tea_tx")


def schema_version(conn: sqlite3.Connection) -> int:
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if not has_meta:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row else 0


def _migrations(folder: Path) -> list[tuple[int, Path]]:
    found = []
    for path in folder.iterdir():
        match = _MIGRATION_NAME.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    return sorted(found)


def migrate(conn: sqlite3.Connection, folder: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply every migration newer than meta.schema_version, each in its own transaction.

    Returns the versions applied (empty when already up to date).
    """
    applied = []
    current = schema_version(conn)
    for version, path in _migrations(folder):
        if version <= current:
            continue
        script = (
            "BEGIN;\n"
            f"{path.read_text(encoding='utf-8')}\n;\n"
            "INSERT OR REPLACE INTO meta (key, value) "
            f"VALUES ('schema_version', '{version}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        applied.append(version)
    return applied
