"""Hand-drawn icons (UI_DESIGN section 7)."""

import re

import pytest
from PySide6.QtWidgets import QApplication

from tea import config
from tea.ui.theme import ICON_NAMES, Theme

ICONS = config.resource_dir("assets") / "icons"


def test_icon_list_matches_design() -> None:
    assert set(ICON_NAMES) == {
        "week", "new-blog", "drafts", "settings", "check", "weak", "cross", "copy",
        "edit", "external-link", "chevron", "drag-handle", "clock", "pause",
    }  # fmt: skip


@pytest.mark.parametrize("name", [*ICON_NAMES, "check-on-primary"])
def test_icon_is_a_20px_currentcolor_svg(name: str) -> None:
    svg = (ICONS / f"{name}.svg").read_text()
    assert 'viewBox="0 0 20 20"' in svg
    assert "currentColor" in svg
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", svg)
    assert 'stroke-width="1.75"' in svg
    assert 'stroke-linecap="round"' in svg


def test_icon_recolors_per_role(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="dark", scale=1.0)
    path = theme.icon_path("week", "primary")
    text = path.read_text()
    assert "#19CDE6" in text and "currentColor" not in text
    assert not theme.icon("week").isNull()


def test_app_icons_exist() -> None:
    assets = config.resource_dir("assets")
    assert (assets / "tea.svg").is_file()
    assert (assets / "tea-attention.svg").is_file()
