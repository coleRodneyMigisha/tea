"""tea doctor (partial in M3: fonts and tray)."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tea import config, doctor
from tea.db.connection import open_db
from tea.doctor import doctor_lines
from tea.ui import strings


def test_doctor_reports_fonts_and_tray(qapp: QApplication) -> None:
    lines = doctor_lines()
    text = "\n".join(lines)
    assert "UI font: JetBrains Mono (bundled)" in text
    assert "Reading font: Newsreader (bundled)" in text
    assert "Tray:" in text


def test_doctor_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tea", "doctor"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert "UI font:" in result.stdout
    assert "Reading font:" in result.stdout


# M10: the full report, one test per mocked condition (Settings "Run checks" shows it too)


def _probes(tray: bool = True, notifications: bool = True) -> doctor.Probes:
    return doctor.Probes(tray=lambda: tray, notifications=lambda: notifications)


def _find(checks: list[doctor.Check], prefix: str) -> doctor.Check:
    found = [c for c in checks if c.text.startswith(prefix)]
    assert len(found) == 1, (prefix, [c.text for c in checks])
    return found[0]


def test_missing_tray_is_reported(qapp: QApplication) -> None:
    c = _find(doctor.run_checks(_probes(tray=False)), "Tray:")
    assert c.status == "warn"
    assert c.text == strings.DOCTOR_TRAY_MISSING
    assert _find(doctor.run_checks(_probes(tray=True)), "Tray:").status == "ok"


def test_unreachable_notification_service_is_reported(qapp: QApplication) -> None:
    c = _find(doctor.run_checks(_probes(notifications=False)), "Notifications:")
    assert c.status == "warn"
    assert "not reachable" in c.text
    assert _find(doctor.run_checks(_probes()), "Notifications:").status == "ok"


def test_missing_fonts_are_reported(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "load_fonts", lambda: [])
    monkeypatch.setattr(
        doctor, "resolved_families", lambda: {"ui": "DejaVu Sans", "reading": "Serif"}
    )
    checks = doctor.run_checks(_probes())
    ui = _find(checks, "UI font:")
    assert ui.status == "warn"
    assert "DejaVu Sans (fallback, wanted JetBrains Mono)" in ui.text
    assert "Serif (fallback, wanted Newsreader)" in _find(checks, "Reading font:").text


def test_no_database_yet_is_not_an_error(qapp: QApplication) -> None:
    c = _find(doctor.run_checks(_probes()), "Database:")
    assert c.status == "warn"
    assert not config.db_path().exists()  # checking never creates it


def test_healthy_migrated_database(qapp: QApplication) -> None:
    open_db(config.db_path()).close()
    c = _find(doctor.run_checks(_probes()), "Database:")
    assert c.status == "ok"
    assert "healthy" in c.text and "migrated" in c.text


def test_database_behind_on_migrations(qapp: QApplication) -> None:
    conn = open_db(config.db_path())
    conn.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
    conn.close()
    c = _find(doctor.run_checks(_probes()), "Database:")
    assert c.status == "warn"
    assert "migrat" in c.text


def test_corrupt_database_fails(qapp: QApplication) -> None:
    config.db_path().parent.mkdir(parents=True)
    config.db_path().write_bytes(b"this is not a database" * 200)
    c = _find(doctor.run_checks(_probes()), "Database:")
    assert c.status == "fail"
    assert doctor.exit_code(doctor.run_checks(_probes())) == 1


def test_prompts_valid_and_broken(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _find(doctor.run_checks(_probes()), "Prompts:")
    assert good.status == "ok" and "valid" in good.text
    broken = tmp_path / "prompts"
    broken.mkdir()
    (broken / "packet_draft.md").write_text("no header here")
    monkeypatch.setattr("tea.handoff.prompts.prompts_dir", lambda: broken)
    bad = _find(doctor.run_checks(_probes()), "Prompts:")
    assert bad.status == "fail"
    assert "packet_draft.md" in bad.text


def test_templates_are_checked(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _find(doctor.run_checks(_probes()), "Templates:").status == "ok"

    def boom(*_a: object, **_k: object) -> str:
        raise KeyError("unknown token")

    monkeypatch.setattr(doctor, "render_qss", boom)
    assert _find(doctor.run_checks(_probes()), "Templates:").status == "fail"


def test_data_folder_sizes(qapp: QApplication) -> None:
    open_db(config.db_path()).close()
    up = config.uploads_dir() / "1"
    up.mkdir(parents=True)
    (up / "a.bin").write_bytes(b"x" * 3000)
    (up / "b.bin").write_bytes(b"x" * 1000)
    c = _find(doctor.run_checks(_probes()), "Data:")
    assert "uploads 3.9 KB in 2 files" in c.text
    assert "database" in c.text


def test_broken_settings_file_fails(qapp: QApplication) -> None:
    config.settings_path().parent.mkdir(parents=True)
    config.settings_path().write_text('{"claude_url": "http://example.com"}')
    assert _find(doctor.run_checks(_probes()), "Settings:").status == "fail"


def test_settings_file_not_created_by_checking(qapp: QApplication) -> None:
    c = _find(doctor.run_checks(_probes()), "Settings:")
    assert c.status == "ok"
    assert not config.settings_path().exists()


def test_autostart_line_follows_the_entries(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert _find(doctor.run_checks(_probes()), "Autostart:").status == "warn"
    from tea import autostart

    autostart.install(tea_bin="/opt/bin/tea")
    assert _find(doctor.run_checks(_probes()), "Autostart:").status == "ok"


def test_report_is_readable_text(qapp: QApplication) -> None:
    text = doctor.report(doctor.run_checks(_probes(tray=False)))
    lines = text.splitlines()
    assert any(line.startswith("OK ") for line in lines)
    assert any(line.startswith("WARN ") and "Tray:" in line for line in lines)
    assert doctor.doctor_lines(_probes(tray=False)) == lines


def test_database_check_does_not_modify_the_file(qapp: QApplication) -> None:
    open_db(config.db_path()).close()
    before = config.db_path().read_bytes()
    doctor.run_checks(_probes())
    assert config.db_path().read_bytes() == before
    sqlite3.connect(config.db_path()).close()
