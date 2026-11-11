"""Render screens and states to PNG for visual review (dev only).

    python -m tea.devtools.snap <screen> --theme light|dark [--state NAME] [--scale 1.25]
    python -m tea.devtools.snap --all

Runs headless (QT_QPA_PLATFORM=offscreen) with a FakeClock and its own temporary data,
config and state folders, so it never touches the owner's data. Files are written to
`.snapshots/<screen>-<state>-<theme>[-<scale%>].png`.

Later milestones register their screens and states with `register()`.
"""

import argparse
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tea.clock import Clock, FakeClock
from tea.db.repos import Repos
from tea.devtools import snap_week, snap_widgets

SNAP_TIME = datetime(2026, 11, 11, 10, 0, tzinfo=ZoneInfo("Africa/Kampala"))  # a Wednesday
THEMES = ("light", "dark")

Seed = Callable[[Repos, Clock], None]
# Builds a standalone widget (popup, dialog) instead of showing a main-window screen.
Build = Callable[[Any, Repos, Clock], Any]


@dataclass(frozen=True)
class State:
    """How to reach a state: the screen to show, sample data to seed, settings to change."""

    screen: str
    seed: Seed | None = None
    settings: dict[str, object] = field(default_factory=dict)
    build: Build | None = None
    keep_focus: bool = False  # show the focus ring of whatever has focus


REGISTRY: dict[str, dict[str, State]] = {}


def register(screen: str, state: str, spec: State) -> None:
    REGISTRY.setdefault(screen, {})[state] = spec


for _screen in ("this_week", "new_blog", "drafts", "settings"):
    register(_screen, "empty", State(_screen))
register("this_week", "paused", State("this_week", settings={"pause_automation": True}))
snap_widgets.register_all(register, State)
snap_week.register_all(register, State)  # replaces the M3 this_week empty and paused states


def _isolate() -> tempfile.TemporaryDirectory[str]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    tmp = tempfile.TemporaryDirectory(prefix="tea-snap-")
    for name in ("DATA", "CONFIG", "STATE", "RUNTIME"):
        folder = Path(tmp.name) / name.lower()
        folder.mkdir()
        os.environ[f"TEA_{name}_DIR"] = str(folder)
    return tmp


def _file_name(screen: str, state: str, theme: str, scale: float) -> str:
    suffix = "" if scale == 1.0 else f"-{round(scale * 100)}"
    return f"{screen}-{state}-{theme}{suffix}.png"


def render(screen: str, state: str, theme_name: str, scale: float, out: Path) -> Path:
    """Render one snapshot. Needs a QApplication (see `main`)."""
    from PySide6.QtWidgets import QApplication

    from tea.db.connection import open_db
    from tea.settings import Settings
    from tea.ui.main_window import MainWindow
    from tea.ui.theme import Theme

    spec = REGISTRY[screen][state]
    clock = FakeClock(SNAP_TIME)
    db_dir = tempfile.TemporaryDirectory(prefix="tea-snap-db-")  # a fresh database per render
    conn = open_db(Path(db_dir.name) / "tea.db")
    try:
        repos = Repos(conn, clock)
        if spec.seed is not None:
            spec.seed(repos, clock)
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        theme = Theme(app, appearance=theme_name, scale=scale)
        theme.apply()
        if spec.build is not None:
            window = spec.build(theme, repos, clock)
        else:
            settings = Settings.model_validate(spec.settings)
            window = MainWindow(
                theme, settings, save_settings=lambda _s: None, remember_geometry=False
            )
            window.show_screen(spec.screen)
        window.show()
        for _ in range(3):
            app.processEvents()
        focused = app.focusWidget()
        if focused is not None and not spec.keep_focus:
            focused.clearFocus()  # at-rest look; focus rings get their own states later
        app.processEvents()
        image = snap_widgets.grab_on_background(window, theme)
    finally:
        conn.close()
        db_dir.cleanup()
    out.mkdir(parents=True, exist_ok=True)
    path = out / _file_name(screen, state, theme_name, scale)
    if not image.save(str(path), "PNG"):
        raise OSError(f"could not write {path}")
    window.close()
    window.deleteLater()
    app.processEvents()
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tea.devtools.snap")
    parser.add_argument("screen", nargs="?", help=f"one of: {', '.join(REGISTRY)}")
    parser.add_argument("--theme", choices=THEMES, default="light")
    parser.add_argument("--state", default="empty")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--all", action="store_true", help="every screen, state and theme")
    parser.add_argument("--out", default=".snapshots", help="output folder")
    args = parser.parse_args(argv)

    if args.all:
        jobs = [(s, st, t) for s in REGISTRY for st in REGISTRY[s] for t in THEMES]
    elif args.screen in REGISTRY:
        if args.state not in REGISTRY[args.screen]:
            known = ", ".join(REGISTRY[args.screen])
            parser.error(f"unknown state {args.state!r} for {args.screen} (known: {known})")
        jobs = [(args.screen, args.state, args.theme)]
    else:
        parser.error(f"choose a screen ({', '.join(REGISTRY)}) or --all")

    tmp = _isolate()
    from PySide6.QtWidgets import QApplication

    from tea.ui.theme import load_fonts

    app = QApplication.instance() or QApplication(["tea-snap"])
    load_fonts()
    try:
        for screen, state, theme_name in jobs:
            print(render(screen, state, theme_name, args.scale, Path(args.out)))
    finally:
        del app
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
