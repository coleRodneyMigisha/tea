"""Draft view (SPEC 7, UI_DESIGN 3.3): header, actions, versions, reading or editing, drawer."""

import logging
import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Draft
from tea.domain import drafts, medium
from tea.logging_setup import log_event
from tea.settings import Settings
from tea.ui import clipboard, drafts_state, strings
from tea.ui.screens import button, muted
from tea.ui.theme import Theme
from tea.ui.widgets.check_drawer import CheckDrawer
from tea.ui.widgets.chip import Chip
from tea.ui.widgets.markdown_editor import MarkdownEditor
from tea.ui.widgets.markdown_view import MarkdownView
from tea.ui.widgets.toast import Toast


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "draft"


class DraftView(QWidget):
    regenerate_requested = Signal(int)  # blog id
    second_pass_requested = Signal(int)  # blog id
    changed = Signal()  # status, copy or edit changed what the list shows

    def __init__(
        self, theme: Theme, repos: Repos, clock: Clock, settings: Callable[[], Settings]
    ) -> None:
        super().__init__()
        self.theme, self.repos, self.clock, self._settings = theme, repos, clock, settings
        self.blog_id: int | None = None
        self.draft: Draft | None = None
        self.versions: list[Draft] = []
        self._latest_id: int | None = None
        self._rendered: tuple[int, str, tuple[str, ...]] | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(theme.space(2))
        self._build_header(outer)
        self._build_actions(outer)
        self._build_versions(outer)
        self.edited_note = muted(strings.EDITED_NOTE, "caption")
        outer.addWidget(self.edited_note)
        self.status_note = muted("", "caption")
        outer.addWidget(self.status_note)
        content = QHBoxLayout()
        content.setSpacing(theme.space(3))
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(theme.size("reading_min"))
        self.reader = MarkdownView(theme)
        self.editor = MarkdownEditor(theme)
        self.editor.saved.connect(self._save_edit)
        self.stack.addWidget(self.reader)
        self.stack.addWidget(self.editor)
        content.addWidget(self.stack, 1)
        self.drawer = CheckDrawer(theme)
        self.drawer.claim_clicked.connect(self._find_claim)
        self.drawer_button.toggled.connect(self.drawer.setVisible)
        content.addWidget(self.drawer)
        outer.addLayout(content, 1)
        self.toast = Toast(theme, self)

    # Building

    def _build_header(self, outer: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(self.theme.space(2))
        self.chip_box = QHBoxLayout()
        row.addLayout(self.chip_box)
        self.chip: Chip | None = None
        self.title_label = QLabel()
        self.title_label.setProperty("role", "title")
        self.title_label.setWordWrap(True)
        row.addWidget(self.title_label, 1)
        outer.addLayout(row)
        self.meta_label = muted("", "caption")
        outer.addWidget(self.meta_label)

    def _build_actions(self, outer: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(self.theme.space(1))
        self.copy_medium_button = button(strings.COPY_FOR_MEDIUM, "primary")
        self.copy_medium_button.clicked.connect(self.copy_for_medium)
        row.addWidget(self.copy_medium_button)
        self.copy_md_button = button(strings.COPY_MARKDOWN, "quiet")
        self.copy_md_button.clicked.connect(self._copy_markdown)
        row.addWidget(self.copy_md_button)
        self.edit_button = button(strings.EDIT, "quiet")
        self.edit_button.clicked.connect(self.toggle_edit)
        row.addWidget(self.edit_button)
        self.regenerate_button = button(strings.REGENERATE, "quiet")
        self.regenerate_button.clicked.connect(self._regenerate)
        row.addWidget(self.regenerate_button)
        self.more_button = button(strings.MORE, "quiet")
        self.menu = QMenu(self)
        self.second_pass_action = self.menu.addAction(strings.SECOND_PASS)
        self.second_pass_action.triggered.connect(self._second_pass)
        self.posted_action = self.menu.addAction(strings.MARK_POSTED)
        self.posted_action.triggered.connect(self._mark_posted)
        self.shelve_action = self.menu.addAction(strings.SHELVE)
        self.shelve_action.triggered.connect(self._shelve)
        self.revive_action = self.menu.addAction(strings.REVIVE)
        self.revive_action.triggered.connect(self._revive)
        self.menu.addSeparator()
        self.export_action = self.menu.addAction(strings.EXPORT_MD)
        self.export_action.triggered.connect(self._export)
        self.delete_action = self.menu.addAction(strings.DELETE)
        self.delete_action.triggered.connect(self._delete)
        self.more_button.setMenu(self.menu)
        row.addWidget(self.more_button)
        row.addStretch(1)
        outer.addLayout(row)
        self.after_copy_label = muted(strings.AFTER_COPY, "caption")
        self.after_copy_label.hide()
        outer.addWidget(self.after_copy_label)

    def _build_versions(self, outer: QVBoxLayout) -> None:
        """Version picker on the left (with more than one version), drawer toggle right."""
        tools = QHBoxLayout()
        tools.setSpacing(self.theme.space(2))
        self.version_row = QWidget()
        row = QHBoxLayout(self.version_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.theme.space(2))
        self.version_combo = QComboBox()
        self.version_combo.setAccessibleName(strings.VERSION_LABEL.format(n=""))
        self.version_combo.activated.connect(self._pick_version)
        row.addWidget(self.version_combo)
        self.version_chip_box = QHBoxLayout()
        row.addLayout(self.version_chip_box)
        self.version_chip: Chip | None = None
        self.edited_marker = muted(strings.EDITED_MARKER, "caption")
        row.addWidget(self.edited_marker)
        tools.addWidget(self.version_row)
        tools.addStretch(1)
        self.drawer_button = button(strings.DRAWER_TOGGLE, "quiet")
        self.drawer_button.setCheckable(True)
        tools.addWidget(self.drawer_button)
        outer.addLayout(tools)

    # Loading

    def load(self, blog_id: int, draft_id: int | None = None) -> None:
        self.editor.flush()
        same_blog = blog_id == self.blog_id
        self.blog_id = blog_id
        self.versions = self.repos.drafts.list_for_blog(blog_id)
        if not self.versions:
            self.draft = None
            return
        # Keep the chosen version across refreshes, unless a newer version arrived.
        keep = same_blog and self.draft is not None and self._latest_id == self.versions[-1].id
        wanted = (
            draft_id if draft_id is not None else (self.draft.id if keep and self.draft else None)
        )
        self._latest_id = self.versions[-1].id
        found = next((d for d in self.versions if d.id == wanted), self.versions[-1])
        new_draft = self.draft is None or self.draft.id != found.id
        self.draft = found
        if new_draft:
            self.after_copy_label.hide()
            self.stack.setCurrentWidget(self.reader)
            self.edit_button.setText(strings.EDIT)
            self.drawer_button.setChecked(found.copied_at is None)  # open for new drafts
            self.drawer.setVisible(self.drawer_button.isChecked())
        self._show()

    def _show(self) -> None:
        d = self.draft
        blog = self.repos.blogs.get(self.blog_id) if self.blog_id is not None else None
        if d is None or blog is None:
            return
        text, state = drafts_state.chip_for(drafts_state.blog_group(blog, self.versions[-1]))
        self.chip = self._replace_chip(self.chip_box, self.chip, text, state)
        self.title_label.setText(d.title)
        self.meta_label.setText(drafts_state.draft_meta(d, self.clock.now()))
        self._fill_versions()
        self.edited_note.setVisible(d.edited_markdown is not None)
        body = drafts.current_text(d)
        # The list refreshes every minute; re-render only when the text changed, so the
        # reader keeps its scroll and claim highlight and the drawer its scroll.
        key = (d.id, body, tuple(d.parse_warnings))
        if self.editing():
            if self.editor.text() != body and not self.editor.pending():
                self.editor.load(body)
        elif key != self._rendered:
            self.reader.set_markdown(body)
        if key != self._rendered:
            self.drawer.set_draft(d, medium.warnings(body))
            self._rendered = key
        posted, shelved = blog.status == "posted", blog.status == "shelved"
        self.status_note.setText(drafts_state.status_note(self.repos, blog))
        self.status_note.setVisible(bool(self.status_note.text()))
        self.posted_action.setVisible(not posted)
        self.shelve_action.setVisible(not shelved and not posted)
        self.revive_action.setVisible(shelved)

    def _replace_chip(self, box: QHBoxLayout, old: Chip | None, text: str, state: str) -> Chip:
        if old is not None:
            old.set_state(text, state)
            return old
        chip = Chip(self.theme, text, state)
        box.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        return chip

    def _fill_versions(self) -> None:
        d = self.draft
        assert d is not None
        self.version_row.setVisible(len(self.versions) > 1)
        self.version_combo.clear()
        for v in self.versions:
            kind = strings.VERSION_KINDS.get(v.kind, v.kind)
            entry = (
                strings.VERSION_ENTRY_EDITED
                if v.edited_markdown is not None
                else strings.VERSION_ENTRY
            )
            self.version_combo.addItem(entry.format(n=v.version, kind=kind), v.id)
        self.version_combo.setCurrentIndex(self.versions.index(d))
        kind = strings.VERSION_KINDS.get(d.kind, d.kind)
        self.version_chip = self._replace_chip(
            self.version_chip_box, self.version_chip, kind, "version"
        )
        self.edited_marker.setVisible(d.edited_markdown is not None)

    def version_entries(self) -> list[str]:
        return [self.version_combo.itemText(i) for i in range(self.version_combo.count())]

    def _pick_version(self, index: int) -> None:
        if self.blog_id is not None and 0 <= index < len(self.versions):
            self.load(self.blog_id, self.versions[index].id)

    # Actions

    def editing(self) -> bool:
        return self.stack.currentWidget() is self.editor

    def copy_for_medium(self) -> None:
        if self.draft is None:
            return
        self.editor.flush()
        out = drafts.copy_for_medium(self.repos, self.draft.id)
        clipboard.set_rich(out.html, out.plain)
        self.toast.show_message(strings.COPIED_FOR_MEDIUM)
        self.after_copy_label.show()
        self._reload()
        self.changed.emit()

    def _copy_markdown(self) -> None:
        if self.draft is None:
            return
        self.editor.flush()
        self._reload()
        if self.draft is not None:
            clipboard.set_plain(drafts.current_text(self.draft))
        self.toast.show_message(strings.MARKDOWN_COPIED)

    def toggle_edit(self) -> None:
        if self.draft is None:
            return
        if self.editing():
            self.editor.flush()
            self.stack.setCurrentWidget(self.reader)
            self.edit_button.setText(strings.EDIT)
            self._rendered = None  # the reader shows the text from before editing
            self._reload()
        else:
            self.editor.load(drafts.current_text(self.draft))
            self.stack.setCurrentWidget(self.editor)
            self.edit_button.setText(strings.PREVIEW)
            self.editor.setFocus()

    def _save_edit(self, text: str) -> None:
        if self.draft is None:
            return
        drafts.save_edit(self.repos, self.draft.id, text)
        log_event("draft_edited", draft=self.draft.id)
        # A light refresh: rebuilding the drawer every 2 seconds would reset its scroll.
        self.versions = self.repos.drafts.list_for_blog(self.draft.blog_id)
        self.draft = next((d for d in self.versions if d.id == self.draft.id), None)
        if self.draft is None:
            return
        edited = self.draft.edited_markdown is not None
        self.edited_note.setVisible(edited)
        self.edited_marker.setVisible(edited)
        self.meta_label.setText(drafts_state.draft_meta(self.draft, self.clock.now()))
        self.drawer.set_medium_warnings(medium.warnings(text))

    def _reload(self) -> None:
        if self.blog_id is not None:
            self.versions = self.repos.drafts.list_for_blog(self.blog_id)
            current = self.draft.id if self.draft is not None else None
            self.draft = next((d for d in self.versions if d.id == current), None)
            self._show()

    def _find_claim(self, claim: str) -> None:
        if self.editing():
            self.toggle_edit()
        self.reader.highlight(claim)

    def _regenerate(self) -> None:
        if self.blog_id is not None:
            self.editor.flush()
            self.regenerate_requested.emit(self.blog_id)

    def _second_pass(self) -> None:
        if self.blog_id is not None:
            self.editor.flush()
            self.second_pass_requested.emit(self.blog_id)

    def _mark_posted(self) -> None:
        if self.draft is not None:
            self.editor.flush()
            drafts.mark_posted(self.repos, self.draft.id)
            self._reload()
            self.changed.emit()

    def _shelve(self) -> None:
        if self.blog_id is not None:
            drafts.shelve(self.repos, self.blog_id)
            self._reload()
            self.changed.emit()

    def _revive(self) -> None:
        if self.blog_id is not None:
            drafts.revive(self.repos, self._settings(), self.blog_id)
            self._reload()
            self.changed.emit()

    def export_path(self, suggested: Path) -> Path | None:
        """Ask where to save. Tests replace this."""
        name, _ = QFileDialog.getSaveFileName(
            self, strings.EXPORT_TITLE, str(suggested), strings.EXPORT_FILTER
        )
        return Path(name) if name else None

    def _export(self) -> None:
        if self.draft is None:
            return
        self.editor.flush()
        self._reload()
        if self.draft is None:
            return
        path = self.export_path(Path.home() / f"{_slug(self.draft.title)}.md")
        if path is None:
            return
        try:
            path.write_text(drafts.current_text(self.draft), encoding="utf-8")
        except OSError as exc:
            log_event("export_failed", logging.WARNING, error=type(exc).__name__)
            self.toast.show_message(strings.EXPORT_FAILED.format(name=path.name))
            return
        log_event("draft_exported", draft=self.draft.id)

    def confirm_delete(self, text: str) -> bool:
        """Ask before deleting. Tests replace this."""
        box = QMessageBox(QMessageBox.Icon.Warning, strings.DELETE_TITLE, text, parent=self)
        delete = box.addButton(strings.DELETE, QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(strings.CANCEL, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is delete

    def _delete(self) -> None:
        d = self.draft
        if d is None:
            return
        last = len(self.versions) == 1
        text = (strings.DELETE_LAST_BODY if last else strings.DELETE_BODY).format(
            n=d.version, title=d.title
        )
        if not self.confirm_delete(text):
            return
        self.editor.timer.stop()
        drafts.delete_version(self.repos, d.id)
        self.draft = None
        if self.blog_id is not None:
            self.load(self.blog_id)
        self.changed.emit()
