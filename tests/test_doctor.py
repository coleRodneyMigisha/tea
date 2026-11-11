"""tea doctor (partial in M3: fonts and tray)."""

import os
import subprocess
import sys

from PySide6.QtWidgets import QApplication

from tea.doctor import doctor_lines


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
