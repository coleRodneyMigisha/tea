"""Status chip (UI_DESIGN 6): a pill with caption text, styled by its `state` property."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy


class Chip(QLabel):
    def __init__(self, text: str, state: str) -> None:
        super().__init__(text)
        self.setObjectName("Chip")
        self.setProperty("state", state)
        self.setAccessibleName(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._radius = -1

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        # Qt draws square corners when a QSS radius exceeds half the height (the template's
        # 999), so a pill needs the radius set from the chip's own height.
        radius = self.height() // 2
        if radius != self._radius:
            self._radius = radius
            self.setStyleSheet(f"QLabel#Chip {{ border-radius: {radius}px; }}")
        super().resizeEvent(event)
