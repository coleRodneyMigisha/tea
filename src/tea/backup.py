"""Export and restore a backup: a zip of the database and the uploads folder (SPEC 8).

Layout of the zip: `tea.db` and `uploads/<blog id>/<file>`, so unzipping it into the data folder
is also a restore. The export reads the database with SQLite's backup API, so rows still in the
write-ahead log are included and the running app is not disturbed. Run it in a worker.
"""

import os
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tea import config
from tea.clock import Clock
from tea.ui import strings
from tea.workers import Cancelled

DB_NAME = "tea.db"
UPLOADS_NAME = "uploads"


class BackupError(RuntimeError):
    """The backup could not be written or restored; the message says why."""


def default_name(clock: Clock) -> str:
    return f"tea-backup-{clock.now().date().isoformat()}.zip"


def _snapshot_db(source: Path, target: Path) -> None:
    src = sqlite3.connect(source, timeout=10)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def export_backup(
    dest: Path,
    progress: Callable[[int, int], Any] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Write the zip to `dest` (through a `.part` file, so a failed export leaves nothing)."""
    del progress  # byte counts can pass Qt's int range; the owner sees "Saving backup"
    db = config.db_path()
    if not db.is_file():
        raise BackupError(strings.BACKUP_NO_DB)
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    try:
        with tempfile.TemporaryDirectory(prefix="tea-backup-") as tmp:
            snapshot = Path(tmp) / DB_NAME
            _snapshot_db(db, snapshot)
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(snapshot, DB_NAME)
                uploads = config.uploads_dir()
                files = (
                    sorted(p for p in uploads.rglob("*") if p.is_file()) if uploads.is_dir() else []
                )
                for path in files:
                    if cancelled is not None and cancelled():
                        raise Cancelled
                    z.write(path, f"{UPLOADS_NAME}/{path.relative_to(uploads).as_posix()}")
        os.replace(part, dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return dest


def _safe_name(name: str) -> bool:
    parts = Path(name).parts
    return bool(parts) and not Path(name).is_absolute() and ".." not in parts and "\\" not in name


def restore_backup(archive: Path, data_dir: Path) -> None:
    """Unpack a backup into `data_dir`, which must not hold a database or uploads yet."""
    archive, data_dir = Path(archive), Path(data_dir)
    try:
        z = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(strings.BACKUP_NOT_A_BACKUP) from exc
    with z:
        names = z.namelist()
        if any(not _safe_name(n) for n in names):
            raise BackupError(strings.BACKUP_UNSAFE)
        if DB_NAME not in names:
            raise BackupError(strings.BACKUP_NOT_A_BACKUP)
        uploads = data_dir / UPLOADS_NAME
        if (data_dir / DB_NAME).exists() or (uploads.is_dir() and any(uploads.iterdir())):
            raise BackupError(strings.BACKUP_TARGET_USED)
        data_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".tea-restore-", dir=data_dir))
        try:
            for info in z.infolist():
                top = Path(info.filename).parts[0]
                if info.is_dir() or top not in (DB_NAME, UPLOADS_NAME):
                    continue
                out = staging / info.filename
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, out.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            _check_database(staging / DB_NAME)
            for item in staging.iterdir():
                if item.name == UPLOADS_NAME and uploads.is_dir():
                    uploads.rmdir()  # empty, checked above
                os.replace(item, data_dir / item.name)
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def _check_database(path: Path) -> None:
    try:
        conn = sqlite3.connect(path)
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(strings.BACKUP_NOT_A_BACKUP) from exc
    if not ok or ok[0] != "ok":
        raise BackupError(strings.BACKUP_NOT_A_BACKUP)
