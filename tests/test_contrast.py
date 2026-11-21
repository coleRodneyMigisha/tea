"""WCAG contrast of the text pairs the theme really paints (UI_DESIGN 9, M11)."""

import json

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QWidget

from tea import config
from tea.ui.theme import Theme

COLORS = json.loads((config.resource_dir("assets") / "design-tokens.json").read_text())["color"]

# (text role, background role): every pairing in assets/theme.qss.tmpl and the widgets.
PAIRS = [
    ("ink", "bg"),
    ("ink", "surface"),
    ("ink", "surface_raised"),
    ("ink", "primary_soft"),
    ("muted", "bg"),
    ("muted", "surface"),
    ("muted", "surface_raised"),
    ("primary", "surface"),
    ("primary", "surface_raised"),
    ("primary_ink", "primary"),
    ("primary_ink", "primary_hover"),
    ("attention", "surface"),
    ("attention", "surface_raised"),
    ("attention", "attention_soft"),
    ("amber", "surface"),
    ("amber", "surface_raised"),
    ("amber", "amber_soft"),
]


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    r, g, b = (int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def ratio(fg: str, bg: str) -> float:
    light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_ratio_of_black_on_white_is_21() -> None:
    assert ratio("#000000", "#FFFFFF") == pytest.approx(21.0)


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg"), PAIRS)
def test_text_pair_reaches_4_5(mode: str, fg: str, bg: str) -> None:
    colors = COLORS[mode]
    assert ratio(colors[fg], colors[bg]) >= 4.5, f"{mode}: {fg} on {bg}"


def _extreme_pixel(widget: QWidget, background: QColor) -> QColor:
    """The painted pixel furthest in lightness from the background."""
    image = widget.grab().toImage()
    pixels = (image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height()))
    return max(pixels, key=lambda c: abs(c.lightnessF() - background.lightnessF()))


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("kind", [QLineEdit, QPlainTextEdit])
def test_placeholder_text_is_the_muted_colour(
    qapp: QApplication, mode: str, kind: type[QWidget]
) -> None:
    """Qt fades placeholders by default (3.19:1 light); the QSS paints them in full muted."""
    theme = Theme(qapp, mode)
    theme.apply()
    box = kind()
    box.setPlaceholderText("Paste the whole reply here")  # type: ignore[attr-defined]
    box.resize(400, 80)
    box.show()
    background = theme.color("surface_raised")
    painted = _extreme_pixel(box, background)
    assert painted == theme.color("muted")
    assert ratio(painted.name(), background.name()) >= 4.5
