"""The "What Claude will be told about you" preview: the answers section as a prompt has it."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from tea.clock import Clock
from tea.db.repos import Repos
from tea.domain.weeks import week_start
from tea.handoff.answers import answers_section
from tea.settings import Settings
from tea.ui import strings
from tea.ui.theme import Theme


def preview_text(repos: Repos, clock: Clock, settings: Settings) -> str:
    """The owner's general answers plus this week's focus answers, capped as in a packet."""
    week = week_start(clock.now())
    return answers_section(repos, blog=None, week=week, max_words=settings.max_answer_words)


class AnswersPreview(QDialog):
    def __init__(self, theme: Theme, text: str) -> None:
        super().__init__()
        self.setWindowTitle(strings.PREVIEW_TITLE)
        self.setMinimumWidth(theme.size("dialog_width"))
        layout = QVBoxLayout(self)
        pad = theme.space(4)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(theme.space(2))

        title = QLabel(strings.PREVIEW_TITLE)
        title.setObjectName("DialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        intro = QLabel(strings.PREVIEW_INTRO)
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.view = QPlainTextEdit(text)
        self.view.setReadOnly(True)
        self.view.setAccessibleName(strings.PREVIEW_TITLE)
        self.view.setMinimumHeight(theme.size("popup_min_height"))
        layout.addWidget(self.view, 1)
        self.empty_label = QLabel(strings.PREVIEW_EMPTY)
        self.empty_label.setProperty("role", "muted")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self._spacer = layout.count()
        layout.addStretch(1)  # keeps the empty state at the top when the text box is hidden
        has_text = bool(text.strip())
        tall = "popup_max_height" if has_text else "popup_min_height"
        self.resize(theme.size("dialog_width"), theme.size(tall))
        self.view.setHidden(not has_text)
        self.empty_label.setHidden(has_text)
        if has_text:
            layout.setStretch(self._spacer, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(strings.PREVIEW_CLOSE)
        close.setProperty("variant", "primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
