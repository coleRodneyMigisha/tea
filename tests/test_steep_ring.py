"""Steep ring: progress 0, 0.5 and 1, every state, settle animation, accessible name."""

import math

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.ui.theme import Theme
from tea.ui.widgets.steep_ring import STATES, SteepRing


@pytest.fixture(params=["light", "dark"])
def theme(request: pytest.FixtureRequest, qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance=request.param, scale=1.0)
    t.apply()
    return t


def make(qtbot: QtBot, theme: Theme, reduce_motion: bool = True) -> SteepRing:
    ring = SteepRing(theme, reduce_motion=reduce_motion)
    qtbot.addWidget(ring)
    ring.show()
    return ring


def pixel(img: QImage, ring: SteepRing, clock_deg: float) -> QColor:
    """Colour in the middle of the stroke at an angle measured clockwise from 12 o'clock."""
    dpr = img.devicePixelRatio()
    side = ring.width()
    r = (side - ring.stroke) / 2
    rad = math.radians(clock_deg)
    x = side / 2 + r * math.sin(rad)
    y = side / 2 - r * math.cos(rad)
    return img.pixelColor(round(x * dpr), round(y * dpr))


def close(a: QColor, b: QColor, tol: int = 40) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


def test_size_from_theme(qtbot: QtBot, theme: Theme) -> None:
    ring = make(qtbot, theme)
    assert ring.width() == ring.height() == theme.size("ring")
    assert ring.stroke == theme.size("ring_stroke")


@pytest.mark.parametrize(("value", "lit", "dark"), [(0.0, [], [90, 270]), (0.5, [90], [270]),
                                                     (1.0, [90, 270], [])])  # fmt: skip
def test_progress_draws_clockwise(
    qtbot: QtBot, theme: Theme, value: float, lit: list[int], dark: list[int]
) -> None:
    ring = make(qtbot, theme)
    ring.set_state("steeping", value, "2 days", "until your prompt")
    img = ring.grab().toImage()
    track = theme.color("line")
    for deg in lit:
        assert not close(pixel(img, ring, deg), track), deg
    for deg in dark:
        assert close(pixel(img, ring, deg), track, tol=12), deg


@pytest.mark.parametrize("state", STATES)
def test_every_state_renders(qtbot: QtBot, theme: Theme, state: str) -> None:
    ring = make(qtbot, theme)
    ring.set_state(state, 0.5, "centre", "caption")
    assert not ring.grab().toImage().isNull()
    assert ring.dashed == (state == "no_focus")


def test_full_states_use_solid_colours(qtbot: QtBot, theme: Theme) -> None:
    stops = [c for _, c in theme.steep_stops()]
    ring = make(qtbot, theme)
    ring.set_state("prompt_ready", 1.0, "Prompt ready", "")
    img = ring.grab().toImage()
    assert close(pixel(img, ring, 90), stops[2]) and close(pixel(img, ring, 270), stops[2])
    ring.set_state("ready", 1.0, "Draft ready", "")
    img = ring.grab().toImage()
    assert close(pixel(img, ring, 180), stops[3])


def test_paused_shows_only_the_track(qtbot: QtBot, theme: Theme) -> None:
    ring = make(qtbot, theme)
    ring.set_state("paused", 0.8, "Paused", "")
    img = ring.grab().toImage()
    for deg in (45, 180, 300):
        assert close(pixel(img, ring, deg), theme.color("line"), tol=12)


def test_settle_animation(qtbot: QtBot, theme: Theme) -> None:
    ring = make(qtbot, theme, reduce_motion=False)
    ring.set_state("steeping", 0.4, "x", "")
    assert ring.displayed == pytest.approx(0.4)
    ring.set_state("prompt_ready", 1.0, "Prompt ready", "")
    assert ring.animation is not None
    assert ring.animation.duration() == theme.motion_ms("ring_settle")
    assert ring.displayed < 1.0
    qtbot.waitUntil(lambda: ring.displayed == pytest.approx(1.0), timeout=2000)


def test_settle_skipped_with_reduce_motion(qtbot: QtBot, theme: Theme) -> None:
    ring = make(qtbot, theme, reduce_motion=True)
    ring.set_state("steeping", 0.4, "x", "")
    ring.set_state("ready", 1.0, "Draft ready", "")
    assert ring.animation is None and ring.displayed == pytest.approx(1.0)


def test_no_animation_without_a_state_change(qtbot: QtBot, theme: Theme) -> None:
    ring = make(qtbot, theme, reduce_motion=False)
    ring.set_state("prompt_ready", 1.0, "Prompt ready", "")  # first paint: no settle
    assert ring.animation is None
    ring.set_state("prompt_ready", 1.0, "Prompt ready", "")
    assert ring.animation is None


def test_accessible_name(qtbot: QtBot, theme: Theme) -> None:
    ring = make(qtbot, theme)
    ring.set_state("steeping", 0.5, "2 days", "until your prompt", sentence="Prompt due soon")
    assert ring.accessibleName() == "Prompt due soon"


def test_end_cap_keeps_the_arc_colour_near_full(qtbot: QtBot, theme: Theme) -> None:
    """At 0.99 the end sits by 12 o'clock, where the gradient wraps to the first stop."""
    ring = make(qtbot, theme)
    ring.set_state("steeping", 0.99, "1 hour", "")
    img = ring.grab().toImage()
    last = theme.steep_stops()[-1][1]
    assert close(pixel(img, ring, 0.99 * 360), last, tol=30)
