"""Main window screens and the shared page scaffold."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from tea.ui.theme import Theme


class Page(QWidget):
    """A screen: a title at the top-left, content below, left-aligned."""

    def __init__(self, theme: Theme, title: str) -> None:
        super().__init__()
        self.theme = theme
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.space(5), theme.space(5), theme.space(5), theme.space(5))
        outer.setSpacing(theme.space(4))
        heading = QLabel(title)
        heading.setProperty("role", "title")
        heading.setAccessibleName(title)
        outer.addWidget(heading)
        self.body = QVBoxLayout()
        self.body.setSpacing(theme.space(3))
        outer.addLayout(self.body)
        outer.addStretch(1)


def panel(theme: Theme) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Panel")
    layout = QVBoxLayout(frame)
    pad = theme.size("panel_padding")
    layout.setContentsMargins(pad, pad, pad, pad)
    layout.setSpacing(theme.space(1))
    return frame, layout


def muted(text: str, role: str = "muted") -> QLabel:
    label = QLabel(text)
    label.setProperty("role", role)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return label
