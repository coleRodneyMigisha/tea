"""Status chip (UI_DESIGN 6): a pill with caption text and an icon, styled by its `state`.

Principle 3 asks for text plus color plus an icon. The icon is painted in the chip's own text
color (whatever the QSS state rule gives it), so the QSS stays the one place for chip colors.
"""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QIcon, QPainter, QPaintEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy

from tea.ui.theme import Theme

# Owner's mapping (2026-11-12, DEVIATIONS M6): state -> icon in assets/icons/.
CHIP_ICONS = {
    "scoping": "edit",
    "prompt": "clock",
    "ready": "check",
    "carried": "chevron",
    "posted": "external-link",
    "shelved": "pause",
    "pick": "week",
    "failed": "cross",
    "not_listed": "weak",
    "version": "drafts",  # version kind in the draft view's picker (M7, DEVIATIONS)
}


class Chip(QLabel):
    def __init__(self, theme: Theme, text: str, state: str) -> None:
        super().__init__(text)
        self.setObjectName("Chip")
        self.theme = theme
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._radius = -1
        self._icon = QIcon()
        self.set_state(text, state)
        self._icon_px = theme.type_px("caption")
        self._gap = theme.space(0)
        self.setContentsMargins(self._icon_px + self._gap, 0, 0, 0)

    def set_state(self, text: str, state: str) -> None:
        """Change the text and state in place (the QSS state rule and the icon follow)."""
        self.setText(text)
        self.setAccessibleName(text)
        self.setProperty("state", state)
        # Drawn in ink, then recolored to the text color at paint time.
        self._icon = QIcon(str(self.theme.icon_path(CHIP_ICONS[state], "ink")))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def icon_rect(self) -> QRect:
        """Where the icon is drawn: just left of the text, centred on it."""
        text = self.contentsRect()
        top = text.top() + (text.height() - self._icon_px) // 2
        return QRect(text.left() - self._gap - self._icon_px, top, self._icon_px, self._icon_px)

    def _tinted(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        side = round(self._icon_px * ratio)
        pixmap = self._icon.pixmap(side, side)
        pixmap.setDevicePixelRatio(ratio)
        p = QPainter(pixmap)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(pixmap.rect(), self.palette().color(self.foregroundRole()))
        p.end()
        return pixmap

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self.icon_rect(), self._tinted())
        p.end()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        # Qt draws square corners when a QSS radius exceeds half the height (the template's
        # 999), so a pill needs the radius set from the chip's own height.
        radius = self.height() // 2
        if radius != self._radius:
            self._radius = radius
            self.setStyleSheet(f"QLabel#Chip {{ border-radius: {radius}px; }}")
        super().resizeEvent(event)
