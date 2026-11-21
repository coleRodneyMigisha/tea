"""Export and restore a backup (M10): a zip of the database and the uploads."""

import sqlite3
import zipfile
from pathlib import Path

import pytest

from tea import backup, config
from tea.clock import FakeClock
from tea.db.connection import open_db
from tea.db.repos import Repos


def _populate(clock: FakeClock) -> int:
    conn = open_db(config.db_path())
    repos = Repos(conn, clock)
    blog = repos.blogs.create("Small teams", "Small teams", "manual")
    folder = config.uploads_dir() / str(blog.id)
    folder.mkdir(parents=True)
    (folder / "report.pdf").write_bytes(b"%PDF fake" * 1000)
    conn.close()
    return blog.id


def test_export_holds_the_database_and_uploads(clock: FakeClock, tmp_path: Path) -> None:
    blog_id = _populate(clock)
    out = backup.export_backup(tmp_path / "b.zip")
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    assert "tea.db" in names
    assert f"uploads/{blog_id}/report.pdf" in names
    assert not list(tmp_path.glob("*.part"))


def test_export_includes_rows_still_in_the_wal(clock: FakeClock, tmp_path: Path) -> None:
    conn = open_db(config.db_path())  # stays open: the newest rows may sit in tea.db-wal
    Repos(conn, clock).blogs.create("Fresh", "Fresh", "manual")
    out = backup.export_backup(tmp_path / "b.zip")
    conn.close()
    target = tmp_path / "restored"
    backup.restore_backup(out, target)
    check = sqlite3.connect(target / "tea.db")
    assert check.execute("SELECT count(*) FROM blogs WHERE topic = 'Fresh'").fetchone()[0] == 1
    check.close()


def test_backup_restores_into_a_fresh_data_dir_and_the_app_reads_it(
    clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blog_id = _populate(clock)
    out = backup.export_backup(tmp_path / "b.zip")
    fresh = tmp_path / "fresh-data"
    backup.restore_backup(out, fresh)
    monkeypatch.setenv("TEA_DATA_DIR", str(fresh))
    conn = open_db(config.db_path())
    blog = Repos(conn, clock).blogs.get(blog_id)
    conn.close()
    assert blog is not None and blog.topic == "Small teams"
    assert (config.uploads_dir() / str(blog_id) / "report.pdf").read_bytes() == b"%PDF fake" * 1000


def test_restore_refuses_a_folder_that_already_holds_a_database(
    clock: FakeClock, tmp_path: Path
) -> None:
    _populate(clock)
    out = backup.export_backup(tmp_path / "b.zip")
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "tea.db").write_bytes(b"x")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(out, existing)
    assert (existing / "tea.db").read_bytes() == b"x"


def test_restore_rejects_a_zip_without_a_database(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("notes.txt", "hi")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad, tmp_path / "t")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(tmp_path / "missing.zip", tmp_path / "t")


def test_restore_rejects_paths_that_leave_the_folder(tmp_path: Path) -> None:
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("tea.db", "x")
        z.writestr("../outside.txt", "x")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(evil, tmp_path / "t")
    assert not (tmp_path / "outside.txt").exists()


def test_export_can_be_cancelled(clock: FakeClock, tmp_path: Path) -> None:
    _populate(clock)
    with pytest.raises(Exception):  # noqa: B017, PT011 (workers.Cancelled)
        backup.export_backup(tmp_path / "b.zip", cancelled=lambda: True)
    assert not (tmp_path / "b.zip").exists()
    assert not list(tmp_path.glob("*.part"))


def test_default_name_uses_the_date(clock: FakeClock) -> None:
    assert backup.default_name(clock) == "tea-backup-2026-11-13.zip"


def test_export_without_a_database_says_so(tmp_path: Path) -> None:
    with pytest.raises(backup.BackupError):
        backup.export_backup(tmp_path / "b.zip")
