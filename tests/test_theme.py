"""Theme rendering from tokens (UI_DESIGN, M3)."""

import json
import logging
import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from tea import config
from tea.ui import theme as theme_mod
from tea.ui.theme import Theme, load_tokens, render_qss, resolve_mode

TOKENS = json.loads((config.resource_dir("assets") / "design-tokens.json").read_text())


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_rendered_qss_has_no_unresolved_tokens(mode: str, tmp_path: Path) -> None:
    qss = render_qss(load_tokens(), mode, scale=1.0, icon_dir=tmp_path)
    assert "{{" not in qss and "}}" not in qss
    assert TOKENS["color"][mode]["bg"] in qss
    assert TOKENS["color"][mode]["primary"] in qss


def test_light_and_dark_differ(tmp_path: Path) -> None:
    tokens = load_tokens()
    assert render_qss(tokens, "light", 1.0, tmp_path) != render_qss(tokens, "dark", 1.0, tmp_path)


def test_font_families_are_quoted_with_generic_last(tmp_path: Path) -> None:
    qss = render_qss(load_tokens(), "light", 1.0, tmp_path)
    assert '"JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace' in qss
    assert '"Newsreader", "Noto Serif", "Liberation Serif", serif' in qss


def test_scale_multiplies_pixel_sizes(tmp_path: Path) -> None:
    tokens = load_tokens()
    base = render_qss(tokens, "light", 1.0, tmp_path)
    big = render_qss(tokens, "light", 1.25, tmp_path)
    assert "font-size: 14px" in base
    assert "font-size: 18px" in big  # 14 * 1.25 = 17.5, rounded half up
    assert "font-size: 30px" in base and "font-size: 38px" in big  # display, 37.5 rounds up
    sizes = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)px", big)]
    assert all(n >= 1 for n in sizes if n)


def test_icon_urls_point_at_recolored_files(tmp_path: Path) -> None:
    qss = render_qss(load_tokens(), "dark", 1.0, tmp_path)
    assert ":/icons/" not in qss
    match = re.search(r"url\(([^)]+check-on-primary-[0-9a-f]+-[0-9a-f]+\.svg)\)", qss)
    assert match
    svg = Path(match.group(1)).read_text()
    assert TOKENS["color"]["dark"]["primary_ink"] in svg
    assert "currentColor" not in svg


@pytest.mark.parametrize(
    ("appearance", "scheme", "expected"),
    [
        ("light", Qt.ColorScheme.Dark, "light"),
        ("dark", Qt.ColorScheme.Light, "dark"),
        ("system", Qt.ColorScheme.Dark, "dark"),
        ("system", Qt.ColorScheme.Light, "light"),
        ("system", Qt.ColorScheme.Unknown, "light"),
    ],
)
def test_resolve_mode(appearance: str, scheme: Qt.ColorScheme, expected: str) -> None:
    assert resolve_mode(appearance, scheme) == expected


def test_theme_applies_stylesheet_and_palette(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="dark", scale=1.0)
    theme.apply()
    assert TOKENS["color"]["dark"]["bg"] in qapp.styleSheet()
    window = qapp.palette().color(QPalette.ColorRole.Window).name().upper()
    assert window == TOKENS["color"]["dark"]["bg"]
    text = qapp.palette().color(QPalette.ColorRole.Text).name().upper()
    assert text == TOKENS["color"]["dark"]["ink"]


def test_system_mode_follows_desktop_changes(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="system", scale=1.0)
    theme.apply()
    seen: list[str] = []
    theme.changed.connect(lambda: seen.append(theme.mode))
    theme.on_color_scheme_changed(Qt.ColorScheme.Dark)
    assert theme.mode == "dark"
    theme.on_color_scheme_changed(Qt.ColorScheme.Light)
    assert theme.mode == "light"
    assert seen == ["dark", "light"]
    assert TOKENS["color"]["light"]["bg"] in qapp.styleSheet()


def test_fixed_mode_ignores_desktop_changes(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    theme.on_color_scheme_changed(Qt.ColorScheme.Dark)
    assert theme.mode == "light"


def test_set_appearance_switches_mode(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    theme.set_appearance("dark")
    assert theme.mode == "dark"
    assert TOKENS["color"]["dark"]["bg"] in qapp.styleSheet()


def test_bundled_fonts_register(qapp: QApplication) -> None:
    families = theme_mod.load_fonts()
    assert "JetBrains Mono" in families
    assert "Newsreader" in families


@pytest.mark.parametrize("family", ["JetBrains Mono", "Newsreader"])
def test_bundled_fonts_have_real_weights(qapp: QApplication, family: str) -> None:
    from PySide6.QtGui import QFontDatabase

    theme_mod.load_fonts()
    weights = {QFontDatabase.weight(family, s) for s in QFontDatabase.styles(family)}
    assert {400, 500, 600, 700} <= weights


def test_missing_font_logs_warning_and_does_not_raise(
    qapp: QApplication, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "Broken.ttf").write_bytes(b"not a font")
    logger = logging.getLogger("tea")
    logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger="tea"):
            families = theme_mod.load_fonts(tmp_path)
    finally:
        logger.propagate = False
    assert families == []
    assert "font_load_failed" in caplog.text
    assert "Broken" not in caplog.text


def test_resolved_families_report(qapp: QApplication) -> None:
    theme_mod.load_fonts()
    resolved = theme_mod.resolved_families()
    assert resolved["ui"] == "JetBrains Mono"
    assert resolved["reading"] == "Newsreader"


def test_sizes_come_from_tokens_and_scale(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="light", scale=1.25)
    assert theme.size("rail_width") == round(TOKENS["window"]["rail_width"] * 1.25)
    assert theme.size("min_width") == round(TOKENS["window"]["min_width"] * 1.25)
    assert theme.space(1) == 10  # 8 * 1.25
    assert theme.icon_size().width() == 25  # 20 * 1.25


def test_steep_stops_depend_on_mode(qapp: QApplication) -> None:
    theme = Theme(qapp, appearance="light", scale=1.0)
    assert theme.steep_stops()[0][1].name().upper() == "#DCE8CF"
    theme.set_appearance("dark")
    assert theme.steep_stops()[0][1].name().upper() == "#19CDE6"


def test_default_scale_uses_logical_dpi(qapp: QApplication) -> None:
    screen = qapp.primaryScreen()
    theme = Theme(qapp, appearance="light")
    assert theme.scale == pytest.approx(screen.logicalDotsPerInch() / 96)


def _contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_shell_text_pairs_meet_contrast_floor(mode: str) -> None:
    c = TOKENS["color"][mode]
    pairs = [("ink", "bg"), ("ink", "surface"), ("muted", "bg"), ("muted", "surface"),
             ("ink", "primary_soft"), ("primary_ink", "primary")]  # fmt: skip
    for fg, bg in pairs:
        assert _contrast(c[fg], c[bg]) >= 4.5, (mode, fg, bg)


def test_paused_footer_text_is_not_amber(tmp_path: Path) -> None:
    qss = render_qss(load_tokens(), "light", 1.0, tmp_path)
    rule = next(line for line in qss.splitlines() if 'RailFooter[state="paused"]' in line)
    assert TOKENS["color"]["light"]["amber"] not in rule


def test_button_variants_keep_a_focus_ring(tmp_path: Path) -> None:
    """The plain :focus rule loses to variant rules, so each variant needs its own."""
    qss = render_qss(load_tokens(), "light", scale=1.0, icon_dir=tmp_path)
    for variant in ("quiet", "primary", "danger"):
        rule = qss.split(f'QPushButton[variant="{variant}"]:focus', 1)[1].split("}", 1)[0]
        assert "border: 2px solid" in rule, variant
