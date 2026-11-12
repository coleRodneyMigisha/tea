"""Pieces of the hand-off dialog: a numbered step, the prompt viewer, summary text."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tea.db.rows import Draft
from tea.domain import drafts
from tea.ui import import_notes, strings
from tea.ui.screens import button, clear_layout, muted
from tea.ui.theme import Theme

FLAGGED = ("weak", "unsupported")


class StepMarker(QLabel):
    """The step number, or a check icon once the step's action happened."""

    def __init__(self, theme: Theme, number: int) -> None:
        super().__init__(str(number))
        self.theme = theme
        self.number = number
        self.setObjectName("StepMarker")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side = theme.space(4)
        self.setFixedSize(side, side)
        self.done = False
        self.set_done(False)

    def set_done(self, done: bool) -> None:
        self.done = done
        self.setProperty("done", "true" if done else "false")
        if done:
            side = self.theme.type_px("body")
            self.setPixmap(self.theme.icon("check", "primary").pixmap(side, side))
            self.setAccessibleName(f"{self.number} {strings.STEP_DONE}")
        else:
            self.setText(str(self.number))
            self.setAccessibleName(str(self.number))
        self.style().unpolish(self)
        self.style().polish(self)


class StepRow(QWidget):
    """Marker, title and body on the left; the step's button on the right."""

    def __init__(self, theme: Theme, number: int, title: str) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(theme.space(3))
        grid.setVerticalSpacing(theme.space(1))
        self.marker = StepMarker(theme, number)
        grid.addWidget(self.marker, 0, 0, Qt.AlignmentFlag.AlignTop)
        self.title = QLabel(title)
        self.title.setProperty("role", "strong")
        grid.addWidget(self.title, 0, 1, Qt.AlignmentFlag.AlignVCenter)
        self.action = QHBoxLayout()
        self.action.setSpacing(theme.space(1))
        grid.addLayout(self.action, 0, 2, Qt.AlignmentFlag.AlignRight)
        self.body = QVBoxLayout()
        self.body.setSpacing(theme.space(1))
        grid.addLayout(self.body, 1, 1, 1, 2)
        grid.setColumnStretch(1, 1)


class PromptViewer(QDialog):
    """Read-only view of the prompt text ("View prompt")."""

    def __init__(self, theme: Theme, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.VIEW_PROMPT_TITLE)
        self.setModal(False)
        layout = QVBoxLayout(self)
        pad = theme.space(4)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(theme.space(3))
        self.text_view = QPlainTextEdit(text)
        self.text_view.setReadOnly(True)
        self.text_view.setAccessibleName(strings.VIEW_PROMPT_TITLE)
        layout.addWidget(self.text_view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(strings.CLOSE)
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        self.resize(theme.size("handoff_dialog_width"), theme.size("popup_max_height"))


class ImportSummary(QWidget):
    """After import: the summary line, Claude's pick, import notes and recovery buttons."""

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.space(2))
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        col.addWidget(self.summary_label)
        self.picked_label = QLabel()
        self.picked_label.setProperty("role", "strong")
        self.picked_label.setWordWrap(True)
        col.addWidget(self.picked_label)

        self.notes_frame = QFrame()
        self.notes_frame.setObjectName("ImportNotes")
        notes = QVBoxLayout(self.notes_frame)
        m = theme.space(3)
        notes.setContentsMargins(m, m, m, m)
        notes.setSpacing(theme.space(2))
        self._notes_box = QVBoxLayout()
        self._notes_box.setSpacing(theme.space(1))
        notes.addLayout(self._notes_box)
        recover = QHBoxLayout()
        recover.setSpacing(theme.space(2))
        self.audit_button = button(strings.COPY_AUDIT_PROMPT)
        recover.addWidget(self.audit_button)
        self.continue_button = button(strings.COPY_CONTINUE_PROMPT)
        recover.addWidget(self.continue_button)
        recover.addStretch(1)
        notes.addLayout(recover)
        topic = QHBoxLayout()
        topic.setSpacing(theme.space(2))
        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText(strings.PICK_TOPIC_PLACEHOLDER)
        self.topic_edit.setAccessibleName(strings.PICK_TOPIC_PLACEHOLDER)
        self.topic_edit.textChanged.connect(self._topic_changed)
        topic.addWidget(self.topic_edit, 1)
        self.topic_save_button = button(strings.SAVE_TOPIC)
        topic.addWidget(self.topic_save_button)
        notes.addLayout(topic)
        col.addWidget(self.notes_frame)

        actions = QHBoxLayout()
        actions.setSpacing(theme.space(2))
        self.paste_different_button = button(strings.PASTE_DIFFERENT, "quiet")
        actions.addWidget(self.paste_different_button)
        actions.addStretch(1)
        self.open_draft_button = button(strings.OPEN_DRAFT, "primary")
        actions.addWidget(self.open_draft_button)
        col.addLayout(actions)

    def show_draft(self, draft: Draft, kind: str, topic: str) -> None:
        self.summary_label.setText(summary_text(draft))
        self.picked_label.setText(strings.CLAUDE_PICKED.format(topic=topic))
        self.picked_label.setVisible(kind == "weekly_pick" and bool(topic))
        found = import_notes.notes(draft.parse_warnings, draft.flags)
        clear_layout(self._notes_box)
        for line in found.lines:
            self._notes_box.addWidget(muted(line, "body"))
        need_topic = import_notes.TOPIC in found.recoveries and not topic
        self.audit_button.setVisible(import_notes.AUDIT in found.recoveries)
        self.continue_button.setVisible(import_notes.CONTINUE in found.recoveries)
        self.topic_edit.setVisible(need_topic)
        self.topic_save_button.setVisible(need_topic)
        self._topic_changed(self.topic_edit.text())
        self.notes_frame.setVisible(bool(found.lines))

    def note_lines(self) -> list[str]:
        out = []
        for i in range(self._notes_box.count()):
            item = self._notes_box.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, QLabel):
                out.append(w.text())
        return out

    def recoveries(self) -> list[str]:
        shown = []
        if not self.audit_button.isHidden():
            shown.append(import_notes.AUDIT)
        if not self.continue_button.isHidden():
            shown.append(import_notes.CONTINUE)
        if not self.topic_edit.isHidden():
            shown.append(import_notes.TOPIC)
        return shown

    def _topic_changed(self, text: str) -> None:
        self.topic_save_button.setEnabled(bool(text.strip()))


def flagged_claims(draft: Draft) -> int:
    return sum(1 for c in draft.verification if c.get("status") in FLAGGED)


def summary_text(draft: Draft) -> str:
    words = f"{len(drafts.current_text(draft).split()):,}"
    claims = flagged_claims(draft)
    if claims == 1:
        return strings.IMPORT_SUMMARY_ONE.format(title=draft.title, words=words)
    return strings.IMPORT_SUMMARY.format(title=draft.title, words=words, claims=claims)
