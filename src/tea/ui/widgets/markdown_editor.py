"""Markdown editor for the draft view (UI_DESIGN 3.3): same serif, size and column as reading.

Changes are saved at most every 2 seconds (`saved` carries the text); `flush` saves at once.
It edits plain text: pasted formatting is dropped so the draft stays Markdown.
"""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QResizeEvent, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from tea.ui.theme import Theme

AUTOSAVE_MS = 2000
PERCENT = 100


class MarkdownEditor(QTextEdit):
    saved = Signal(str)

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme = theme
        self.setProperty("reading", "true")
        self.setAcceptRichText(False)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(AUTOSAVE_MS)
        self.timer.timeout.connect(self.flush)
        self._loading = False
        self._dirty = False
        self.textChanged.connect(self._changed)

    def load(self, text: str) -> None:
        self.timer.stop()
        self._loading = True
        self.document().setDefaultFont(self.theme.font("reading", "reading_body"))
        self.setPlainText(text)
        self._spacing()
        self._loading = False
        self._dirty = False
        self.moveCursor(QTextCursor.MoveOperation.Start)
        self._centre()

    def text(self) -> str:
        return self.toPlainText()

    def flush(self) -> None:
        self.timer.stop()
        if self._dirty:
            self._dirty = False
            self.saved.emit(self.toPlainText())

    def pending(self) -> bool:
        return self._dirty

    def _changed(self) -> None:
        if self._loading:
            return
        self._dirty = True
        if not self.timer.isActive():
            self.timer.start()

    def _spacing(self) -> None:
        fmt = QTextBlockFormat()
        line = round(self.theme.line_height("reading") * PERCENT)
        fmt.setLineHeight(line, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)

    def _centre(self) -> None:
        side = max(0, (self.width() - self.theme.reading_measure()) // 2)
        self.setViewportMargins(side, 0, side, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        self._centre()
        super().resizeEvent(event)
