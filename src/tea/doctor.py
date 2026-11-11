"""`tea doctor`: environment checks. M3 covers fonts and the tray; M10 adds the rest."""

import os

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tea.ui import strings
from tea.ui.theme import load_fonts, preferred_families, resolved_families


def _font_source(resolved: str, wanted: str, bundled: list[str]) -> str:
    if resolved != wanted:
        return strings.DOCTOR_FONT_FALLBACK.format(wanted=wanted)
    return strings.DOCTOR_FONT_BUNDLED if wanted in bundled else strings.DOCTOR_FONT_SYSTEM


def doctor_lines() -> list[str]:
    """Needs a running QApplication."""
    bundled = load_fonts()
    resolved = resolved_families()
    wanted = preferred_families()
    lines = [
        strings.DOCTOR_UI_FONT.format(
            family=resolved["ui"], source=_font_source(resolved["ui"], wanted["ui"], bundled)
        ),
        strings.DOCTOR_READING_FONT.format(
            family=resolved["reading"],
            source=_font_source(resolved["reading"], wanted["reading"], bundled),
        ),
    ]
    tray = QSystemTrayIcon.isSystemTrayAvailable()
    lines.append(strings.DOCTOR_TRAY_OK if tray else strings.DOCTOR_TRAY_MISSING)
    return lines


def run_doctor() -> int:
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    del app
    for line in doctor_lines():
        print(line)
    return 0
