"""Why dialog: explain the topic selected by tea."""

from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QShowEvent, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tea.ui import strings
from tea.ui.theme import Theme


def _label(text: str, role: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if role is not None:
        label.setProperty("role", role)
    return label


class WhyDialog(QDialog):
    """Show Claude's shortlisted candidates for a topic picked by tea."""

    def __init__(
        self,
        theme: Theme,
        *,
        topic: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self.setWindowTitle(strings.WHY_TITLE)
        self.setModal(False)
        self._slack = theme.space(0)  # Qt scrolls by whole lines; a little room keeps the bar away
        self.setFixedWidth(theme.size("dialog_width"))

        self.candidate_cards: list[QPlainTextEdit] = []
        self.link_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        pad = theme.space(4)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(theme.space(2))

        layout.addWidget(_label(strings.WHY_TITLE, "strong"))

        self.topic_label = _label(topic, "display")
        layout.addWidget(self.topic_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(theme.space(2))

        for candidate in candidates:
            card = QPlainTextEdit()
            card.setReadOnly(True)
            card.setProperty("role", "panel")
            card.setPlainText(
                self._candidate_text(candidate),
            )
            content_layout.addWidget(card)
            self.candidate_cards.append(card)

            urls = candidate.get("urls", [])
            if not isinstance(urls, list):
                urls = []

            if urls:
                source_label = _label(strings.WHY_SOURCES, "strong")
                content_layout.addWidget(source_label)

            for url in urls:
                if not isinstance(url, str) or not url:
                    continue
                button = QPushButton(url)
                button.setProperty("variant", "quiet")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda _checked=False, value=url: QDesktopServices.openUrl(QUrl(value))
                )
                content_layout.addWidget(button)
                self.link_buttons.append(button)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_button = QPushButton(strings.CLOSE)
        close_button.setProperty("variant", "primary")
        close_button.setAutoDefault(False)
        close_button.clicked.connect(self.close)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_cards)  # after the layout has given the cards their width

    def _fit_cards(self) -> None:
        """Make each box as tall as its wrapped text, so short text leaves no empty space."""
        for card in self.candidate_cards:
            measure = QTextDocument()  # a rich-text document reports its height in pixels
            measure.setDefaultFont(card.font())
            measure.setDocumentMargin(card.document().documentMargin())
            measure.setTextWidth(card.viewport().width())
            measure.setPlainText(card.toPlainText())
            frame = card.height() - card.viewport().height()
            card.setFixedHeight(round(measure.size().height()) + frame + self._slack)

    @staticmethod
    def _candidate_text(candidate: dict[str, Any]) -> str:
        topic = str(candidate.get("topic", "")).strip()
        angle = str(candidate.get("angle", "")).strip()
        why = str(candidate.get("why", "")).strip()

        lines = [topic]
        if angle:
            lines.append(f"{strings.WHY_ANGLE}: {angle}")
        if why:
            lines.append(f"{strings.WHY_REASON}: {why}")
        return "\n".join(lines)
