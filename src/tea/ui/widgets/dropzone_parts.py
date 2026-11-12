"""Pieces of the attachment dropzone: the painted drop box, row records and small helpers."""

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QPushButton, QSizePolicy, QWidget

from tea import workers
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.chip import Chip

KB = 1024
MB = 1024 * 1024
PROGRESS_STEPS = 1000  # the bar runs 0..1000 so sizes never overflow its int range


def format_size(size: int) -> str:
    if size >= MB:
        return strings.SIZE_MB.format(n=max(1, round(size / MB)))
    return strings.SIZE_KB.format(n=max(1, round(size / KB)))


def label(text: str, role: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if role:
        label.setProperty("role", role)
    return label


def button(text: str, variant: str = "quiet") -> QPushButton:
    button = QPushButton(text)
    button.setProperty("variant", variant)
    button.setAutoDefault(False)
    return button


def widest(button: QPushButton, texts: tuple[str, ...]) -> int:
    """The width that fits every label the button can show, so rows keep their columns."""
    current = button.text()
    widths = []
    for text in texts:
        button.setText(text)
        widths.append(button.sizeHint().width())
    button.setText(current)
    return max(widths)


class DropArea(QFrame):
    """The dashed box, painted here: QSS borders are whole pixels and the design wants 1.5."""

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.theme = theme
        self.drag_over = False

    def set_drag_over(self, on: bool) -> None:
        self.drag_over = on
        self.setProperty("drag", on)  # QSS darkens the text on the soft fill for contrast
        for child in (self, *self.findChildren(QWidget)):
            child.style().unpolish(child)
            child.style().polish(child)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.theme.stroke("dropzone_border")
        pen = QPen(self.theme.color("primary" if self.drag_over else "line"), width)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(self.theme.color("primary_soft") if self.drag_over else Qt.BrushStyle.NoBrush)
        inset = width / 2
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        radius = self.theme.radius("panel")
        p.drawRoundedRect(rect, radius, radius)
        p.end()


@dataclass
class FileRow:
    attachment_id: int
    widget: QWidget
    name: QLabel
    size: QLabel
    chip: Chip
    leave_button: QPushButton
    remove_button: QPushButton


@dataclass
class CopyRow:
    widget: QWidget
    name: QLabel
    size: QLabel
    bar: QProgressBar
    cancel_button: QPushButton
    job: workers.Job | None = None
