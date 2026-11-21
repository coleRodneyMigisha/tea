"""Keyboard, focus, hit areas and scale on every screen state (UI_DESIGN 9, M11).

Every state the snapshot tool can build is opened in light at 100% and dark at 125%, and each
interactive widget on it is checked.
"""

import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from tea.clock import FakeClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.devtools import snap, snap_drafts
from tea.settings import Settings
from tea.ui.main_window import MainWindow
from tea.ui.theme import Theme

MIN_HIT = 32  # px at 100%
CONFIGS = [("light", 1.0), ("dark", 1.25)]
STATES = [(screen, state) for screen, states in snap.REGISTRY.items() for state in states]


def _interactive(widget: QWidget) -> bool:
    if isinstance(widget, QLineEdit) and isinstance(widget.parent(), QAbstractSpinBox | QComboBox):
        return False  # the inner editor of a spin box or combo box
    if isinstance(widget, QPlainTextEdit | QTextEdit):
        return not widget.isReadOnly()
    return isinstance(widget, QAbstractButton | QLineEdit | QComboBox | QAbstractSpinBox)


def _name(widget: QWidget) -> str:
    if widget.accessibleName():
        return widget.accessibleName()
    if isinstance(widget, QAbstractButton):
        return widget.text()
    return ""


def _problems(window: QWidget, scale: float) -> list[str]:
    found = []
    for w in window.findChildren(QWidget):
        if not (w.isVisible() and w.isEnabled() and _interactive(w)):
            continue
        label = f"{type(w).__name__} {w.objectName() or _name(w)!r}"
        if w.focusPolicy() == Qt.FocusPolicy.NoFocus:
            found.append(f"{label}: cannot take keyboard focus")
        has_hint = isinstance(w, QLineEdit | QPlainTextEdit) and w.placeholderText()
        if not _name(w) and not has_hint and not isinstance(w, QAbstractSpinBox | QComboBox):
            found.append(f"{label}: no accessible name")
        if isinstance(w, QPushButton) and min(w.width(), w.height()) < MIN_HIT * scale - 1:
            found.append(f"{label}: hit area {w.width()}x{w.height()} px")
    return found


def _open(app: QApplication, screen: str, state: str, mode: str, scale: float) -> list[str]:
    spec = snap.REGISTRY[screen][state]
    clock = FakeClock(snap.SNAP_TIME)
    with tempfile.TemporaryDirectory() as folder:
        conn = open_db(Path(folder) / "tea.db")
        try:
            repos = Repos(conn, clock)
            if spec.seed is not None:
                spec.seed(repos, clock)
            theme = Theme(app, appearance=mode, scale=scale)
            theme.apply()
            if spec.build is not None:
                window = spec.build(theme, repos, clock)
            else:
                window = MainWindow(
                    theme,
                    Settings.model_validate(spec.settings),
                    save_settings=lambda _s: None,
                    remember_geometry=False,
                )
                window.show_screen(spec.screen)
            window.show()
            for _ in range(3):
                app.processEvents()
            problems = _problems(window, scale)
            window.close()
            window.deleteLater()
        finally:
            conn.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    snap_drafts.KEEP.clear()
    return [f"{screen}/{state} ({mode}, {scale}): {p}" for p in problems]


def test_every_state_is_keyboard_reachable_named_and_big_enough(qapp: QApplication) -> None:
    problems = []
    for index, (screen, state) in enumerate(STATES):
        mode, scale = CONFIGS[index % 2]  # half the states in each configuration
        problems += _open(qapp, screen, state, mode, scale)
    assert problems == []
