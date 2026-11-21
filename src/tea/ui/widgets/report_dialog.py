"""Read-only text dialog: the `tea doctor` report from Settings > About > Run checks."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from tea.ui import strings
from tea.ui.theme import Theme

EXTRA_ROWS = 10
MAX_ROWS = 28


class ReportDialog(QDialog):
    def __init__(self, theme: Theme, title: str, text: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setModal(False)
        self.setMinimumWidth(theme.size("dialog_width"))
        column = QVBoxLayout(self)
        pad = theme.space(4)
        column.setContentsMargins(pad, pad, pad, pad)
        column.setSpacing(theme.space(2))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName(title)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setPlainText(text)
        rows = min(text.count("\n") + EXTRA_ROWS, MAX_ROWS)  # wrapped lines need a few more
        self.text.setMinimumHeight(self.text.fontMetrics().lineSpacing() * rows)
        column.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(strings.CLOSE)
        close.setProperty("variant", "primary")
        close.clicked.connect(self.close)
        row.addWidget(close)
        column.addLayout(row)
