"""Render QSS and QPalette from the design tokens, load fonts, recolor icons.

This is the only UI module that may name colors, font families or pixel sizes.
Everything else asks the `Theme` for them.
"""

import hashlib
import json
import logging
import re
from functools import cache
from pathlib import Path
from typing import Any, Literal

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QGuiApplication, QIcon, QPalette

from tea import config
from tea.logging_setup import log_event

Mode = Literal["light", "dark"]
Appearance = Literal["system", "light", "dark"]
Tokens = dict[str, Any]

ICON_NAMES = (
    "week", "new-blog", "drafts", "settings", "check", "weak", "cross", "copy",
    "edit", "external-link", "chevron", "drag-handle", "clock", "pause",
)  # fmt: skip

# Sizes from UI_DESIGN that the token file does not carry.
_EXTRA_PX = {"icon": 20, "wordmark_icon": 28, "wordmark": 24, "panel_padding": 20}
# Icons referenced from the QSS template, and the color role each is drawn in.
_QSS_ICON_ROLES = {"check-on-primary": "primary_ink"}
_GENERIC_FAMILIES = {"serif", "sans-serif", "monospace"}
_TOKEN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
_PX = re.compile(r"(\d+(?:\.\d+)?)px")
_QSS_ICON = re.compile(r"url\(:/icons/([a-z0-9-]+)\.svg\)")
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def assets_dir() -> Path:
    return config.resource_dir("assets")


@cache
def _cached_tokens(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_tokens(path: Path | None = None) -> Tokens:
    tokens: Tokens = json.loads(_cached_tokens(path or assets_dir() / "design-tokens.json"))
    return tokens


def resolve_mode(appearance: str, scheme: Qt.ColorScheme) -> Mode:
    if appearance == "dark":
        return "dark"
    if appearance == "light":
        return "light"
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def _round(value: float) -> int:
    """Round half up, so 17.5 becomes 18 on every platform."""
    return int(value + 0.5)


def _family_list(names: list[str]) -> str:
    return ", ".join(n if n in _GENERIC_FAMILIES else f'"{n}"' for n in names)


def _variables(tokens: Tokens, mode: Mode) -> dict[str, str]:
    values: dict[str, str] = dict(tokens["color"][mode])
    values["font_ui"] = _family_list(tokens["font"]["ui"])
    values["font_reading"] = _family_list(tokens["font"]["reading"])
    values["font_mono"] = _family_list(tokens["font"]["mono"])
    for name, size in tokens["type_scale_px"].items():
        values[f"px_{name}"] = str(size)
    for name, radius in tokens["radius_px"].items():
        values[f"r_{name}"] = str(radius)
    return values


def _scale_px(qss: str, scale: float) -> str:
    if scale == 1.0:
        return qss

    def repl(match: re.Match[str]) -> str:
        value = float(match.group(1))
        return f"{max(1, _round(value * scale)) if value else 0}px"

    return _PX.sub(repl, qss)


def recolor_svg(name: str, color: str) -> str:
    text = (assets_dir() / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    return text.replace("currentColor", color)


def write_icon(name: str, color: str, folder: Path) -> Path:
    """Write a recolored copy once and return its path.

    The file name carries a hash of the result, so a changed source SVG gets a new copy.
    """
    folder.mkdir(parents=True, exist_ok=True)
    text = recolor_svg(name, color)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    path = folder / f"{name}-{color.lstrip('#').lower()}-{digest}.svg"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return path


def render_qss(tokens: Tokens, mode: Mode, scale: float, icon_dir: Path) -> str:
    raw = (assets_dir() / "theme.qss.tmpl").read_text(encoding="utf-8")
    template = _COMMENT.sub("", raw)
    values = _variables(tokens, mode)
    missing: set[str] = set()

    def token(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return match.group(0)
        return values[key]

    qss = _TOKEN.sub(token, template)
    if missing:
        raise KeyError(f"theme template uses unknown tokens: {sorted(missing)}")

    def icon(match: re.Match[str]) -> str:
        name = match.group(1)
        color = values[_QSS_ICON_ROLES.get(name, "ink")]
        return f"url({write_icon(name, color, icon_dir).as_posix()})"

    return _scale_px(_QSS_ICON.sub(icon, qss), scale)


def build_palette(tokens: Tokens, mode: Mode) -> QPalette:
    c = {k: QColor(v) for k, v in tokens["color"][mode].items() if v.startswith("#")}
    role = QPalette.ColorRole
    palette = QPalette()
    pairs = {
        role.Window: c["bg"], role.WindowText: c["ink"], role.Base: c["surface_raised"],
        role.AlternateBase: c["surface"], role.Text: c["ink"], role.Button: c["surface_raised"],
        role.ButtonText: c["ink"], role.Highlight: c["primary_soft"],
        role.HighlightedText: c["ink"], role.ToolTipBase: c["ink"], role.ToolTipText: c["bg"],
        role.PlaceholderText: c["muted"], role.Link: c["primary"], role.BrightText: c["attention"],
        role.Light: c["surface_raised"], role.Midlight: c["surface"], role.Mid: c["line"],
        role.Dark: c["line"], role.Shadow: c["line"],
    }  # fmt: skip
    for r, color in pairs.items():
        palette.setColor(r, color)
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(disabled, r, c["muted"])
    return palette


def load_fonts(folder: Path | None = None) -> list[str]:
    """Register bundled fonts. A file that fails is logged and skipped."""
    folder = folder or assets_dir() / "fonts"
    families: list[str] = []
    files = sorted(folder.glob("*.ttf")) + sorted(folder.glob("*.otf"))
    for index, path in enumerate(files):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log_event("font_load_failed", logging.WARNING, index=index)
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    if not files:
        log_event("font_folder_empty", logging.WARNING)
    return families


FontKind = Literal["ui", "reading", "mono"]


def font_for(kind: FontKind, px: int, tokens: Tokens | None = None) -> QFont:
    font = QFont()
    font.setFamilies((tokens or load_tokens())["font"][kind])
    font.setPixelSize(px)
    return font


def resolved_families() -> dict[str, str]:
    """The family Qt actually picks for each role (for `tea doctor`)."""
    tokens = load_tokens()
    kinds: tuple[FontKind, ...] = ("ui", "reading", "mono")
    body = tokens["type_scale_px"]["body"]
    return {kind: QFontInfo(font_for(kind, body, tokens)).family() for kind in kinds}


def preferred_families() -> dict[str, str]:
    tokens = load_tokens()
    return {kind: tokens["font"][kind][0] for kind in ("ui", "reading", "mono")}


def screen_scale() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.logicalDotsPerInch() / 96 if screen else 1.0


class Theme(QObject):
    """The active look. Emits `changed` after a new stylesheet is applied."""

    changed = Signal()

    def __init__(
        self,
        app: QGuiApplication,
        appearance: str = "system",
        scale: float | None = None,
        tokens: Tokens | None = None,
    ) -> None:
        super().__init__()
        self._app = app
        self.tokens = tokens or load_tokens()
        self.appearance = appearance
        self.scale = scale if scale is not None else screen_scale()
        self.mode: Mode = resolve_mode(appearance, app.styleHints().colorScheme())
        self.icon_dir = config.icon_cache_dir()
        self._listening = False

    # Applying

    def apply(self) -> None:
        """Set stylesheet, palette and default font, and follow the desktop in System mode."""
        if not self._listening:
            self._app.styleHints().colorSchemeChanged.connect(self.on_color_scheme_changed)
            self._listening = True
        self._apply_mode()

    def _apply_mode(self) -> None:
        self._app.setPalette(build_palette(self.tokens, self.mode))
        self._app.setFont(self.font("ui", "body"))
        set_sheet = getattr(self._app, "setStyleSheet", None)
        if set_sheet is not None:
            set_sheet(render_qss(self.tokens, self.mode, self.scale, self.icon_dir / self.mode))
        self.changed.emit()

    def on_color_scheme_changed(self, scheme: Qt.ColorScheme) -> None:
        mode = resolve_mode(self.appearance, scheme)
        if mode != self.mode:
            self.mode = mode
            self._apply_mode()

    def set_appearance(self, appearance: str) -> None:
        self.appearance = appearance
        self.mode = resolve_mode(appearance, self._app.styleHints().colorScheme())
        self._apply_mode()

    # Lookups for widgets

    def px(self, value: float) -> int:
        return max(1, _round(value * self.scale)) if value else 0

    def size(self, key: str) -> int:
        """A window, popup or extra size by key, scaled (for example `rail_width`)."""
        for group in (self.tokens["window"], self.tokens["popup"], _EXTRA_PX):
            if key in group:
                return self.px(group[key])
        raise KeyError(key)

    def space(self, step: int) -> int:
        """Spacing scale step: 0 is 4 px, 1 is 8 px, up to 6 (48 px)."""
        return self.px(self.tokens["spacing_px"][step])

    def type_px(self, name: str) -> int:
        return self.px(self.tokens["type_scale_px"][name])

    def icon_size(self) -> QSize:
        side = self.size("icon")
        return QSize(side, side)

    def color(self, role: str) -> QColor:
        return QColor(self.tokens["color"][self.mode][role])

    def font(self, kind: FontKind, size: str) -> QFont:
        return font_for(kind, self.type_px(size), self.tokens)

    def steep_stops(self) -> list[tuple[float, QColor]]:
        key = "steep_stops_dark" if self.mode == "dark" else "steep_stops"
        return [(stop["at"], QColor(stop["hex"])) for stop in self.tokens["color"][key]]

    def icon_path(self, name: str, role: str = "muted") -> Path:
        return write_icon(name, self.tokens["color"][self.mode][role], self.icon_dir / self.mode)

    def icon(self, name: str, role: str = "muted", on_role: str | None = None) -> QIcon:
        """A recolored icon; `on_role` colors the checked state."""
        icon = QIcon(str(self.icon_path(name, role)))
        if on_role:
            icon.addFile(
                str(self.icon_path(name, on_role)), QSize(), QIcon.Mode.Normal, QIcon.State.On
            )
        return icon

    def app_icon(self, attention: bool = False) -> QIcon:
        return QIcon(str(assets_dir() / ("tea-attention.svg" if attention else "tea.svg")))
