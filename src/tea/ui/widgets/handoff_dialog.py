"""Hand-off dialog (UI_DESIGN 3.5, SPEC 3.1 and 3.3).

Three steps: copy the prompt, open Claude, paste the reply. After import it shows a summary
with import notes and the recovery buttons. The dialog is non-modal and can be closed at any
time: `HandoffFlow` keeps the pasted text and whether Claude was opened, and the hand-off
stays under Waiting in Drafts.
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Handoff
from tea.domain import attachments, drafts, weekly
from tea.handoff import packets
from tea.handoff.importer import import_reply
from tea.logging_setup import log_event
from tea.settings import Settings
from tea.ui import clipboard, strings
from tea.ui.screens import button, muted
from tea.ui.theme import Theme
from tea.ui.widgets.handoff_parts import ImportSummary, PromptViewer, StepRow
from tea.ui.widgets.toast import Toast

PASTE_ROWS = 12


class HandoffDialog(QDialog):
    imported = Signal(int)  # blog id
    open_draft_requested = Signal(int)  # blog id
    switch_requested = Signal(int)  # a new hand-off to show instead (audit recovery)
    pasted_changed = Signal(str)
    claude_opened = Signal()

    def __init__(
        self,
        theme: Theme,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        handoff_id: int,
        *,
        pasted: str = "",
        claude_opened: bool = False,
        debug: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.theme, self.repos, self.clock, self._settings = theme, repos, clock, settings
        self.handoff_id = handoff_id
        self._opened = claude_opened
        self._paste_mode = False
        self.prompt_viewer: PromptViewer | None = None
        self.setModal(False)
        self.setFixedWidth(theme.size("handoff_dialog_width"))
        h = self._handoff()

        outer = QVBoxLayout(self)
        pad = theme.space(5)
        outer.setContentsMargins(pad, pad, pad, pad)
        outer.setSpacing(theme.space(4))
        heading = QVBoxLayout()
        heading.setSpacing(theme.space(0))
        title = strings.HANDOFF_TITLES.get(h.kind, strings.HANDOFF_TITLES["weekly"])
        self.setWindowTitle(title)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        heading.addWidget(self.title_label)
        self.subtitle_label = muted(weekly.handoff_title(repos, h) or strings.CHIP_PICK)
        heading.addWidget(self.subtitle_label)
        outer.addLayout(heading)

        self._build_step1(outer, h)
        self._build_step2(outer)
        self._build_step3(outer, debug)
        self._build_summary()
        self.step3.body.addWidget(self.summary)
        outer.addStretch(1)

        self.toast = Toast(theme, self)
        if pasted:
            self.paste_box.setPlainText(pasted)
        self.refresh()

    # Building

    def _build_step1(self, outer: QVBoxLayout, h: Handoff) -> None:
        self.step1 = StepRow(self.theme, 1, strings.STEP_COPY)
        self.copy_button = button(strings.COPY_PROMPT, "primary")
        self.copy_button.clicked.connect(self._copy_prompt)
        self.step1.action.addWidget(self.copy_button)
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(2))
        self.words_label = muted(strings.PROMPT_WORDS.format(words=f"{h.packet_words:,}"))
        self.words_label.setProperty("role", "caption")
        line.addWidget(self.words_label)
        self.view_prompt_button = button(strings.VIEW_PROMPT, "quiet")
        self.view_prompt_button.clicked.connect(self._view_prompt)
        line.addWidget(self.view_prompt_button)
        line.addStretch(1)
        self.step1.body.addLayout(line)
        self.attach_label = muted(strings.ATTACH_FILES)
        self.step1.body.addWidget(self.attach_label)
        self.folder_buttons: list[QPushButton] = []
        self._file_labels: list[QLabel] = []
        files = (
            self.repos.attachments.list_for_blog(h.blog_id, included_only=True)
            if h.blog_id is not None
            else []
        )
        grid = QGridLayout()  # names in one column, the buttons lined up beside them
        grid.setHorizontalSpacing(self.theme.space(2))
        grid.setVerticalSpacing(0)
        for i, a in enumerate(files):
            name = QLabel(a.filename)
            self._file_labels.append(name)
            grid.addWidget(name, i, 0)
            show = button(strings.SHOW_IN_FOLDER, "quiet")
            show.setAccessibleName(f"{strings.SHOW_IN_FOLDER}: {a.filename}")
            show.clicked.connect(lambda _=False, b=a.blog_id: self._show_folder(b))
            self.folder_buttons.append(show)
            grid.addWidget(show, i, 1)
        grid.setColumnStretch(2, 1)
        self.step1.body.addLayout(grid)
        self.attach_label.setVisible(bool(files))
        outer.addWidget(self.step1)

    def _build_step2(self, outer: QVBoxLayout) -> None:
        self.step2 = StepRow(self.theme, 2, strings.STEP_OPEN)
        self.open_claude_button = button(strings.OPEN_CLAUDE)
        self.open_claude_button.clicked.connect(self._open_claude)
        self.step2.action.addWidget(self.open_claude_button)
        self.hint_label = muted(strings.WEB_SEARCH_HINT)
        self.step2.body.addWidget(self.hint_label)
        outer.addWidget(self.step2)

    def _build_step3(self, outer: QVBoxLayout, debug: bool) -> None:
        self.step3 = StepRow(self.theme, 3, strings.STEP_PASTE)
        self.paste_area = QWidget()
        col = QVBoxLayout(self.paste_area)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(self.theme.space(2))
        self.paste_box = QPlainTextEdit()
        self.paste_box.setAccessibleName(strings.PASTE_ACCESSIBLE)
        self.paste_box.setPlaceholderText(strings.PASTE_PLACEHOLDER)
        rows = self.paste_box.fontMetrics().lineSpacing() * PASTE_ROWS
        self.paste_box.setFixedHeight(rows + self.theme.space(4))
        self.paste_box.textChanged.connect(self._text_changed)
        col.addWidget(self.paste_box)
        self.error_label = muted(strings.HANDOFF_GONE, "error")
        self.error_label.hide()
        col.addWidget(self.error_label)
        buttons = QHBoxLayout()
        buttons.setSpacing(self.theme.space(2))
        self.paste_clipboard_button = button(strings.PASTE_FROM_CLIPBOARD, "quiet")
        self.paste_clipboard_button.clicked.connect(self._paste_clipboard)
        buttons.addWidget(self.paste_clipboard_button)
        self.sample_button: QPushButton | None = None
        if debug:
            self.sample_button = button(strings.PASTE_SAMPLE, "quiet")
            self.sample_button.clicked.connect(self._paste_sample)
            buttons.addWidget(self.sample_button)
        buttons.addStretch(1)
        self.import_button = button(strings.IMPORT_DRAFT, "primary")
        self.import_button.clicked.connect(self._import)
        buttons.addWidget(self.import_button)
        col.addLayout(buttons)
        self.step3.body.addWidget(self.paste_area)
        outer.addWidget(self.step3)

    def _build_summary(self) -> None:
        t = self.theme
        # Step body width: dialog minus its margins, the step marker and the grid gap.
        width = t.size("handoff_dialog_width") - 2 * t.space(5) - t.space(4) - t.space(3)
        self.summary = ImportSummary(t, width)
        sm = self.summary
        self.summary_label, self.picked_label, self.notes_frame = (
            sm.summary_label,
            sm.picked_label,
            sm.notes_frame,
        )
        self.audit_button, self.continue_button = sm.audit_button, sm.continue_button
        self.topic_edit, self.topic_save_button = sm.topic_edit, sm.topic_save_button
        self.paste_different_button, self.open_draft_button = (
            sm.paste_different_button,
            sm.open_draft_button,
        )
        self.audit_button.clicked.connect(self._copy_audit)
        self.continue_button.clicked.connect(self._copy_continue)
        self.topic_edit.returnPressed.connect(self._save_topic)
        self.topic_save_button.clicked.connect(self._save_topic)
        self.paste_different_button.clicked.connect(self._paste_different)
        self.open_draft_button.clicked.connect(self._open_draft)

    # State

    def _handoff(self) -> Handoff:
        h = self.repos.handoffs.get(self.handoff_id)
        if h is None:
            raise LookupError(f"no hand-off with id {self.handoff_id}")
        return h

    def step_done(self, step: int) -> bool:
        return (self.step1, self.step2, self.step3)[step - 1].marker.done

    def file_names(self) -> list[str]:
        return [label.text() for label in self._file_labels]

    def note_lines(self) -> list[str]:
        return self.summary.note_lines()

    def recoveries(self) -> list[str]:
        return self.summary.recoveries()

    def refresh(self) -> None:
        h = self._handoff()
        imported = h.status == "imported" and h.draft_id is not None
        draft = self.repos.drafts.get(h.draft_id) if h.draft_id is not None else None
        copied = h.copied_at is not None or imported
        self.step1.marker.set_done(copied)
        # Once copied, the next step's button carries the emphasis.
        self.copy_button.setProperty("variant", "" if copied else "primary")
        self.copy_button.style().unpolish(self.copy_button)
        self.copy_button.style().polish(self.copy_button)
        self.step2.marker.set_done(self._opened or imported)
        self.step3.marker.set_done(draft is not None)
        show_summary = draft is not None and not self._paste_mode
        self.paste_area.setVisible(not show_summary)
        self.summary.setVisible(show_summary)
        self.import_button.setEnabled(bool(self.paste_box.toPlainText().strip()))
        if draft is None:
            self._fit()
            return
        blog = self.repos.blogs.get(draft.blog_id)
        self.summary.show_draft(draft, h.kind, blog.topic if blog is not None else "")
        self._fit()

    def _fit(self) -> None:
        """Grow or shrink to the content (wrapped notes change the height)."""
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self.adjustSize()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        # Before the first show, wrapped labels report a stale height; fit once more.
        QTimer.singleShot(0, self._fit)

    # Actions

    def _copy_prompt(self) -> None:
        clipboard.set_plain(drafts.copy_prompt(self.repos, self.handoff_id))
        self.toast.show_message(strings.PROMPT_COPIED)
        self.refresh()

    def _view_prompt(self) -> None:
        if self.prompt_viewer is None:
            self.prompt_viewer = PromptViewer(self.theme, self._handoff().packet_text, self)
        self.prompt_viewer.show()
        self.prompt_viewer.raise_()

    def _show_folder(self, blog_id: int) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(attachments.blog_dir(blog_id))))

    def _open_claude(self) -> None:
        QDesktopServices.openUrl(QUrl(self._settings().claude_url))
        log_event("claude_opened", handoff=self.handoff_id)
        self._opened = True
        self.claude_opened.emit()
        self.refresh()

    def _text_changed(self) -> None:
        self.import_button.setEnabled(bool(self.paste_box.toPlainText().strip()))
        self.pasted_changed.emit(self.paste_box.toPlainText())

    def _paste_clipboard(self) -> None:
        self.paste_box.setPlainText(clipboard.text())
        self.paste_box.setFocus()

    def _paste_sample(self) -> None:
        from tea.devtools import sample_replies

        kind = self._handoff().kind
        self.paste_box.setPlainText(sample_replies.WELL_FORMED.get(kind, sample_replies.WEEKLY))

    def _import(self) -> None:
        text = self.paste_box.toPlainText()
        if not text.strip():
            return
        try:
            result = import_reply(self.repos, self.handoff_id, text)
        except LookupError:
            log_event("import_failed", logging.WARNING, error="LookupError")
            self._paste_mode = True
            self.refresh()
            self.error_label.show()
            return
        self._paste_mode = False
        self.refresh()
        self.open_draft_button.setFocus()
        self.imported.emit(result.draft.blog_id)

    def _paste_different(self) -> None:
        self._paste_mode = True
        self.refresh()
        self.paste_box.setFocus()

    def _open_draft(self) -> None:
        h = self._handoff()
        if h.blog_id is not None:
            self.open_draft_requested.emit(h.blog_id)
        self.close()

    def _copy_audit(self) -> None:
        h = self._handoff()
        if h.blog_id is None:
            return
        try:
            new, _ = drafts.second_pass(self.repos, self._settings(), self.clock, h.blog_id)
        except (packets.PacketError, LookupError) as exc:
            log_event("audit_prompt_failed", logging.WARNING, error=type(exc).__name__)
            return
        clipboard.set_plain(drafts.copy_prompt(self.repos, new.id))
        self.toast.show_message(strings.PROMPT_COPIED)
        self.switch_requested.emit(new.id)

    def _copy_continue(self) -> None:
        clipboard.set_plain(drafts.continue_prompt())
        self.toast.show_message(strings.PROMPT_COPIED)
        self._paste_mode = True
        self.paste_box.clear()
        self.refresh()
        self.paste_box.setFocus()

    def _save_topic(self) -> None:
        if drafts.set_pick_topic(self.repos, self.handoff_id, self.topic_edit.text()):
            self.refresh()
            self.subtitle_label.setText(weekly.handoff_title(self.repos, self._handoff()))
