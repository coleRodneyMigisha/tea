"""Status chip (UI_DESIGN 6, principle 3): pill, caption text and an icon in the text color."""

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea import config
from tea.ui.theme import Theme
from tea.ui.widgets.chip import CHIP_ICONS, Chip

STATES = ["scoping", "prompt", "ready", "carried", "posted", "shelved", "pick", "failed",
          "not_listed"]  # fmt: skip


@pytest.fixture(params=["light", "dark"])
def theme(request: pytest.FixtureRequest, qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance=request.param, scale=1.0)
    t.apply()
    return t


def test_owner_mapping() -> None:
    assert CHIP_ICONS == {
        "scoping": "edit", "prompt": "clock", "ready": "check", "carried": "chevron",
        "posted": "external-link", "shelved": "pause", "pick": "week", "failed": "cross",
        "not_listed": "weak", "version": "drafts",
    }  # fmt: skip
    icons = config.resource_dir("assets") / "icons"
    assert all((icons / f"{name}.svg").is_file() for name in CHIP_ICONS.values())


@pytest.mark.parametrize("state", STATES)
def test_icon_drawn_in_text_color_left_of_text(qtbot: QtBot, theme: Theme, state: str) -> None:
    chip = Chip(theme, "Ready", state)
    qtbot.addWidget(chip)
    chip.show()
    qtbot.waitExposed(chip)
    assert chip.text() == "Ready" and chip.accessibleName() == "Ready"
    image = chip.grab().toImage()
    ink = chip.palette().color(chip.foregroundRole())
    area = chip.icon_rect()
    assert area.right() < chip.contentsRect().left()  # the icon sits before the text
    hits = 0
    for x in range(area.left(), area.right() + 1):
        for y in range(area.top(), area.bottom() + 1):
            if _close(QColor(image.pixelColor(x, y)), ink):
                hits += 1
    assert hits >= 4, state


def test_chip_grows_to_fit_the_icon(qtbot: QtBot, theme: Theme) -> None:
    chip = Chip(theme, "Not listed", "not_listed")
    qtbot.addWidget(chip)
    plain_width = chip.fontMetrics().horizontalAdvance("Not listed")
    assert chip.sizeHint().width() >= plain_width + theme.type_px("caption")


# A thin icon stroke is mostly blended pixels; the darker amber (4.5:1) sits far from its pill.
CLOSE = 120


def _close(a: QColor, b: QColor) -> bool:
    return (
        abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue()) < CLOSE
    )  # anti-aliased strokes blend toward the pill
