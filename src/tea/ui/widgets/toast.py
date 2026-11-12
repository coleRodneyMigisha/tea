"""Toast: a short message at the bottom of a window that hides itself (UI_DESIGN 6).

It is a child label, not a window, so it never takes focus. Screen readers get the text
through the label's accessible name.
"""

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

from tea.ui.theme import Theme

SHOW_MS = 2400


class Toast(QLabel):
    def __init__(self, theme: Theme, parent: QWidget) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        parent.installEventFilter(self)
        self.hide()

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.setAccessibleName(text)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._timer.start(SHOW_MS)

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - self.theme.space(4)
        self.move(max(0, x), max(0, y))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return False
