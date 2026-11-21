"""`tea doctor`: environment checks. The Settings "Run checks" button shows the same report."""

import json
import os
import sqlite3
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtDBus import QDBusConnection
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tea import autostart, config, settings
from tea.db.connection import latest_version
from tea.handoff import prompts
from tea.ui import strings
from tea.ui.theme import (
    Mode,
    load_fonts,
    load_tokens,
    preferred_families,
    render_qss,
    resolved_families,
)

Status = Literal["ok", "warn", "fail"]
NOTIFY_SERVICE = "org.freedesktop.Notifications"


@dataclass(frozen=True)
class Check:
    status: Status
    text: str


def tray_available() -> bool:
    return QSystemTrayIcon.isSystemTrayAvailable()


def notifications_reachable() -> bool:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    iface = bus.interface()
    return iface is not None and bool(iface.isServiceRegistered(NOTIFY_SERVICE).value())


@dataclass(frozen=True)
class Probes:
    """The two checks that ask the desktop; tests swap them."""

    tray: Callable[[], bool] = tray_available
    notifications: Callable[[], bool] = notifications_reachable


def _font_source(resolved: str, wanted: str, bundled: list[str]) -> str:
    if resolved != wanted:
        return strings.DOCTOR_FONT_FALLBACK.format(wanted=wanted)
    return strings.DOCTOR_FONT_BUNDLED if wanted in bundled else strings.DOCTOR_FONT_SYSTEM


def _fonts() -> list[Check]:
    bundled = load_fonts()
    resolved = resolved_families()
    wanted = preferred_families()
    out = []
    for key, template in (("ui", strings.DOCTOR_UI_FONT), ("reading", strings.DOCTOR_READING_FONT)):
        source = _font_source(resolved[key], wanted[key], bundled)
        status: Status = "warn" if resolved[key] != wanted[key] else "ok"
        out.append(Check(status, template.format(family=resolved[key], source=source)))
    return out


def _database() -> Check:
    path = config.db_path()
    if not path.is_file():
        return Check("warn", strings.DOCTOR_DB_MISSING)
    latest = latest_version()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            verdict = conn.execute("PRAGMA integrity_check").fetchone()
            has_meta = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
            ).fetchone()
            row = (
                conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
                if has_meta
                else None
            )
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return Check("fail", strings.DOCTOR_DB_BAD.format(detail=f"{type(exc).__name__}"))
    if not verdict or verdict[0] != "ok":
        return Check("fail", strings.DOCTOR_DB_BAD.format(detail="integrity check failed"))
    version = int(row[0]) if row else 0
    if version > latest:
        return Check("fail", strings.DOCTOR_DB_NEWER.format(version=version, latest=latest))
    if version < latest:
        return Check("warn", strings.DOCTOR_DB_BEHIND.format(version=version, latest=latest))
    return Check("ok", strings.DOCTOR_DB_OK.format(version=version))


def _prompts() -> Check:
    try:
        found = prompts.all_templates()
    except prompts.PromptError as exc:
        return Check("fail", strings.DOCTOR_PROMPTS_BAD.format(detail=exc))
    if not found:
        return Check("fail", strings.DOCTOR_PROMPTS_BAD.format(detail="no templates found"))
    return Check("ok", strings.DOCTOR_PROMPTS_OK.format(count=len(found)))


def _templates() -> Check:
    try:
        tokens = load_tokens()
        with tempfile.TemporaryDirectory(prefix="tea-doctor-") as tmp:
            for mode in ("light", "dark"):
                render_qss(tokens, _mode(mode), 1.0, Path(tmp))
        for name in (autostart.AUTOSTART_NAME, autostart.LAUNCHER_NAME):
            text = (config.resource_dir("desktop") / name).read_text(encoding="utf-8")
            if autostart.PLACEHOLDER not in text:
                raise ValueError(f"{name} has no {autostart.PLACEHOLDER}")
        for name in ("interests.json",):
            json.loads((config.resource_dir("data") / name).read_text(encoding="utf-8"))
    except (OSError, KeyError, ValueError) as exc:
        return Check("fail", strings.DOCTOR_TEMPLATES_BAD.format(detail=_short(exc)))
    return Check("ok", strings.DOCTOR_TEMPLATES_OK)


def _mode(name: str) -> Mode:
    return "dark" if name == "dark" else "light"


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:160]


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024 or unit == "MB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _data() -> Check:
    uploads = config.uploads_dir()
    files = [p for p in uploads.rglob("*") if p.is_file()] if uploads.is_dir() else []
    total = sum(_file_size(p) for p in files)
    count = len(files)
    label = strings.DOCTOR_FILES.get(count) or strings.DOCTOR_FILES_MANY.format(count=count)
    return Check(
        "ok",
        strings.DOCTOR_DATA.format(
            db=human_size(_file_size(config.db_path())),
            uploads=human_size(total),
            files=label,
            log=human_size(_file_size(config.log_path())),
        ),
    )


def _settings() -> Check:
    path = config.settings_path()
    if not path.exists():
        return Check("ok", strings.DOCTOR_SETTINGS_DEFAULT)  # load() would write the file
    try:
        settings.load(path)
    except settings.SettingsError as exc:
        return Check("fail", strings.DOCTOR_SETTINGS_BAD.format(detail=exc))
    return Check("ok", strings.DOCTOR_SETTINGS_OK)


def _autostart() -> Check:
    if autostart.is_installed():
        return Check("ok", strings.DOCTOR_AUTOSTART_OK)
    return Check("warn", strings.DOCTOR_AUTOSTART_MISSING)


def run_checks(probes: Probes | None = None) -> list[Check]:
    """Every check, in the order they are shown. Needs a running QApplication."""
    probes = probes or Probes()
    checks = _fonts()
    checks.append(
        Check("ok", strings.DOCTOR_TRAY_OK)
        if probes.tray()
        else Check("warn", strings.DOCTOR_TRAY_MISSING)
    )
    checks.append(
        Check("ok", strings.DOCTOR_NOTIFY_OK)
        if probes.notifications()
        else Check("warn", strings.DOCTOR_NOTIFY_MISSING)
    )
    checks += [_database(), _settings(), _prompts(), _templates(), _data(), _autostart()]
    return checks


def report(checks: list[Check]) -> str:
    return "\n".join(f"{strings.DOCTOR_STATUS[c.status]:<5}{c.text}" for c in checks)


def doctor_lines(probes: Probes | None = None) -> list[str]:
    return report(run_checks(probes)).splitlines()


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == "fail" for c in checks) else 0


def run_doctor() -> int:
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    del app
    checks = run_checks()
    print(report(checks))
    return exit_code(checks)
