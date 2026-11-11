"""Weekly focus dialog (UI_DESIGN 4, "Focus dialog"): a centred, non-modal QDialog."""

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from tea.ui import strings
from tea.ui.theme import Theme

EDITOR_ROWS = 3


def _label(text: str, role: str | None = None, name: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if role:
        label.setProperty("role", role)
    if name:
        label.setObjectName(name)
    return label


class FocusDialog(QDialog):
    focus_saved = Signal(str)
    dismissed = Signal()

    def __init__(self, theme: Theme, *, current: str = "", carried: bool = False) -> None:
        super().__init__()
        self.setWindowTitle(strings.FOCUS_TITLE)
        self.setModal(False)
        self.setFixedWidth(theme.size("dialog_width"))
        layout = QVBoxLayout(self)
        pad = theme.space(4)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(theme.space(2))

        self.title = _label(strings.FOCUS_TITLE, name="DialogTitle")
        layout.addWidget(self.title)
        self.editor = QPlainTextEdit(current)
        self.editor.setObjectName("FocusEditor")  # QSS: the owner's own words are serif
        self.editor.setAccessibleName(strings.FOCUS_TITLE)
        self.editor.setTabChangesFocus(True)
        rows = self.editor.fontMetrics().lineSpacing() * EDITOR_ROWS
        margins = self.editor.contentsMargins()
        frame = 2 * self.editor.frameWidth() + margins.top() + margins.bottom()
        doc_margin = round(self.editor.document().documentMargin())
        height = rows + frame + doc_margin + doc_margin
        self.editor.setFixedHeight(height)
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor)
        self.hint = _label(strings.FOCUS_HINT, role="muted")
        layout.addWidget(self.hint)
        self.carried_line = _label(strings.FOCUS_CARRIED, role="muted")
        self.carried_line.setVisible(carried)
        layout.addWidget(self.carried_line)

        row = QHBoxLayout()
        row.setSpacing(theme.space(1))
        row.addStretch(1)
        self.later_button = QPushButton(strings.FOCUS_LATER)
        self.later_button.setProperty("variant", "quiet")
        self.later_button.setAutoDefault(False)
        self.later_button.clicked.connect(self.reject)
        row.addWidget(self.later_button)
        self.save_button = QPushButton(strings.FOCUS_SAVE)
        self.save_button.setProperty("variant", "primary")
        self.save_button.setAutoDefault(False)
        self.save_button.clicked.connect(self._save)
        row.addWidget(self.save_button)
        layout.addLayout(row)

        self.editor.textChanged.connect(self._sync)
        self._sync()
        self.editor.setFocus()

    def text(self) -> str:
        return self.editor.toPlainText().strip()

    def _sync(self) -> None:
        self.save_button.setEnabled(bool(self.text()))

    def _save(self) -> None:
        text = self.text()
        if not text:
            return
        self.focus_saved.emit(text)
        self.accept()

    def reject(self) -> None:
        self.dismissed.emit()
        super().reject()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if watched is self.editor and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            if ctrl and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._save()
                return True
        return super().eventFilter(watched, event)
