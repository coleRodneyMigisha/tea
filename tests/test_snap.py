"""Snapshot tool (devtools/snap.py)."""

import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QImage

from tea.devtools import snap

SCREENS = ["this_week", "new_blog", "drafts", "settings"]


def test_registry_has_every_screen() -> None:
    for screen in SCREENS:
        assert "empty" in snap.REGISTRY[screen]


def test_all_writes_a_png_per_screen_and_theme(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tea.devtools.snap", "--all", "--out", str(tmp_path)],
        capture_output=True, text=True, timeout=300,  # 68 renders; slow under memory pressure
        env={**_env(), "QT_QPA_PLATFORM": "offscreen"},
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    for screen in SCREENS:
        for theme in ("light", "dark"):
            path = tmp_path / f"{screen}-empty-{theme}.png"
            assert path.is_file(), path
            image = QImage(str(path))
            assert (image.width(), image.height()) == (1120, 740)
    for name in ("question_popup", "answers_preview"):
        assert list(tmp_path.glob(f"{name}-*-light.png")), name
        assert list(tmp_path.glob(f"{name}-*-dark.png")), name


def test_single_screen_with_scale(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tea.devtools.snap", "drafts", "--theme", "dark",
         "--scale", "1.25", "--out", str(tmp_path)],
        capture_output=True, text=True, timeout=120, env=_env(),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    image = QImage(str(tmp_path / "drafts-empty-dark-125.png"))
    assert (image.width(), image.height()) == (1400, 925)


def test_paused_state_renders(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tea.devtools.snap", "this_week", "--state", "paused",
         "--out", str(tmp_path)],
        capture_output=True, text=True, timeout=120, env=_env(),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "this_week-paused-light.png").is_file()


def test_unknown_state_fails(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tea.devtools.snap", "drafts", "--state", "nope",
         "--out", str(tmp_path)],
        capture_output=True, text=True, timeout=120, env=_env(),
    )  # fmt: skip
    assert result.returncode != 0
    assert "nope" in result.stderr


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)
