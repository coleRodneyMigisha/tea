"""No hard-coded colors, font names or pixel sizes in widget code; microcopy voice rules."""

import json
import re
from pathlib import Path

from tea import config
from tea.ui import strings

UI = Path(__file__).resolve().parent.parent / "src" / "tea" / "ui"
TOKENS = json.loads((config.resource_dir("assets") / "design-tokens.json").read_text())
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{8}\b|#[0-9A-Fa-f]{3}\b")
PX = re.compile(r"\d\s*px\b")
SIZE_CALLS = re.compile(
    r"\b(setPixelSize|setPointSizeF?|setFixed(Width|Height|Size)|resize|setMinimum(Width|Height|Size)"
    r"|setMaximum(Width|Height|Size)|setIconSize|setContentsMargins|setSpacing)\(\s*[1-9]"
)
NAMED_COLOR = re.compile(
    r"QColor\(\s*['\"]|Qt\.GlobalColor|Qt\.(red|green|blue|black|white|gray)\b"
)


def _widget_files() -> list[Path]:
    return [p for p in UI.rglob("*.py") if p.name != "theme.py"]


def test_there_is_widget_code() -> None:
    assert len(_widget_files()) >= 5


def test_no_hex_colors_in_widgets() -> None:
    hits = [f"{p.name}: {m}" for p in _widget_files() for m in HEX.findall(p.read_text())]
    assert hits == []


def test_no_named_colors_in_widgets() -> None:
    hits = [p.name for p in _widget_files() if NAMED_COLOR.search(p.read_text())]
    assert hits == []


def test_no_font_names_in_widgets() -> None:
    names = {n for fam in TOKENS["font"].values() for n in fam if " " in n or n[0].isupper()}
    hits = [f"{p.name}: {n}" for p in _widget_files() for n in names if n in p.read_text()]
    assert hits == []


def test_no_pixel_sizes_in_widgets() -> None:
    hits = []
    for path in _widget_files():
        text = path.read_text()
        hits += [f"{path.name}: px" for _ in PX.findall(text)]
        hits += [f"{path.name}: {m.group(1)}" for m in SIZE_CALLS.finditer(text)]
    assert hits == []


def _texts() -> list[str]:
    return [v for k, v in vars(strings).items() if k.isupper() and isinstance(v, str)]


def test_strings_follow_voice_rules() -> None:
    for text in _texts():
        assert "!" not in text, text
        assert "oops" not in text.lower(), text
        assert all(ord(ch) < 0x2190 for ch in text), text  # no emoji or arrow glyphs


def test_empty_state_copy_matches_design() -> None:
    assert strings.EMPTY_DRAFTS == (
        "No drafts yet. Your first prompt is ready on Friday, or start one from New blog."
    )
    assert strings.EMPTY_FOCUS == (
        "Set a focus on Monday and tea prepares your prompt for Friday. "
        "If you don't, tea asks Claude to pick a trending topic."
    )
    assert [strings.NAV_WEEK, strings.NAV_NEW, strings.NAV_DRAFTS, strings.NAV_SETTINGS] == [
        "This week", "New blog", "Drafts", "Settings",
    ]  # fmt: skip
