"""Attachment drop zone (UI_DESIGN 3.2): drop or choose files, leave out, remove, progress.

Files are copied by `workers` into the blog's uploads folder; the row is written on the GUI
thread when a copy finishes, so workers never touch SQLite. tea never opens the files.
"""

from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tea import config, workers
from tea.db.repos import Repos
from tea.db.rows import Attachment
from tea.domain import attachments
from tea.logging_setup import log_event
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.chip import Chip
from tea.ui.widgets.dropzone_parts import (
    PROGRESS_STEPS,
    CopyRow,
    DropArea,
    FileRow,
    format_size,
)
from tea.ui.widgets.dropzone_parts import button as _button
from tea.ui.widgets.dropzone_parts import label as _label
from tea.ui.widgets.dropzone_parts import widest as _widest


class Dropzone(QWidget):
    changed = Signal()

    def __init__(self, theme: Theme, repos: Repos, blog_id: int) -> None:
        super().__init__()
        self.theme = theme
        self.repos = repos
        self.blog_id = blog_id
        self.rows: list[FileRow] = []
        self.copy_rows: list[CopyRow] = []
        self.setAcceptDrops(True)
        self.setAccessibleName(strings.DROP_ACCESSIBLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space(1))

        self.area = DropArea(theme)
        inner = QVBoxLayout(self.area)
        pad = theme.space(3)
        inner.setContentsMargins(pad, pad, pad, pad)
        inner.setSpacing(theme.space(0))
        lead_row = QHBoxLayout()
        lead_row.setSpacing(theme.space(0))
        self.lead = _label(strings.DROP_LEAD, role="strong")
        self.lead.setWordWrap(False)
        lead_row.addWidget(self.lead)
        self.choose_button = QPushButton(strings.DROP_CHOOSE)
        self.choose_button.setObjectName("DropChoose")
        self.choose_button.setAutoDefault(False)
        self.choose_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose_button.clicked.connect(self.choose)
        lead_row.addWidget(self.choose_button)
        lead_row.addStretch(1)
        inner.addLayout(lead_row)
        self.hint = _label(strings.DROP_HINT, role="caption")
        self.hint.setWordWrap(False)  # wrapped labels let the box shrink when messages show
        inner.addWidget(self.hint)
        layout.addWidget(self.area)

        inset = theme.space(1)  # messages and rows share one left edge
        self.error_row = QWidget()
        error_line = QHBoxLayout(self.error_row)
        error_line.setContentsMargins(inset, 0, 0, 0)
        error_line.setSpacing(theme.space(1))
        self.error_icon = QLabel()
        self.error_icon.setPixmap(theme.icon("cross", "attention").pixmap(theme.icon_size()))
        error_line.addWidget(self.error_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.error = _label("", role="error")
        error_line.addWidget(self.error, 1)
        self.error_row.setVisible(False)
        layout.addWidget(self.error_row)
        self.notice = _label(strings.FIRST_FILE_ADDED, role="muted")
        self.notice.setContentsMargins(inset, 0, 0, 0)
        self.notice.setVisible(False)
        layout.addWidget(self.notice)

        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(theme.space(0))
        layout.addLayout(self.list_box)
        self.copy_box = QVBoxLayout()
        self.copy_box.setSpacing(theme.space(0))
        layout.addLayout(self.copy_box)

        folder_row = QHBoxLayout()
        self.show_folder_button = _button(strings.SHOW_IN_FOLDER)
        self.show_folder_button.clicked.connect(self.show_in_folder)
        folder_row.addWidget(self.show_folder_button)
        folder_row.addStretch(1)
        layout.addLayout(folder_row)
        self.refresh()
        # A copy that outlives the widget is cancelled; its closures check `_alive()`.
        jobs = self.copy_rows

        def cancel_jobs() -> None:
            for entry in jobs:
                if entry.job is not None:
                    entry.job.cancel()

        self.destroyed.connect(cancel_jobs)

    def _alive(self) -> bool:
        return shiboken6.isValid(self)

    # -- state ----------------------------------------------------------------------------

    @property
    def drag_over(self) -> bool:
        return self.area.drag_over

    def copying(self) -> bool:
        return bool(self.copy_rows)

    def refresh(self) -> None:
        for row in self.rows:
            self.list_box.removeWidget(row.widget)
            row.widget.deleteLater()
        self.rows = [self._file_row(a) for a in self.repos.attachments.list_for_blog(self.blog_id)]
        for row in self.rows:
            self.list_box.addWidget(row.widget)
            row.widget.show()  # a layout only shows new children on the next event loop pass
        self.show_folder_button.setVisible(bool(self.rows))
        self._tab_order()

    def _tab_order(self) -> None:
        """Tab follows the screen: the box, each file row, copies in flight, the folder."""
        chain: list[QWidget] = [self.choose_button]
        for row in self.rows:
            chain += [row.leave_button, row.remove_button]
        chain += [c.cancel_button for c in self.copy_rows]
        chain.append(self.show_folder_button)
        for first, second in zip(chain, chain[1:], strict=False):
            QWidget.setTabOrder(first, second)

    def _row(self, attachment_id: int) -> FileRow | None:
        return next((r for r in self.rows if r.attachment_id == attachment_id), None)

    def _file_row(self, att: Attachment) -> FileRow:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(self.theme.space(1), 0, 0, 0)
        row.setSpacing(self.theme.space(2))
        name = _label(att.filename)
        name.setWordWrap(False)
        name.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        row.addWidget(name)
        chip = Chip(self.theme, strings.NOT_LISTED, "not_listed")
        row.addWidget(chip)
        # Only after it has a parent: a parentless visible chip flashes up as its own
        # window and takes focus from the dropzone.
        chip.setVisible(not att.include_in_list)
        row.addStretch(1)
        size = _label(format_size(att.size_bytes), role="muted")
        size.setWordWrap(False)
        row.addWidget(size)
        leave = _button(strings.LEAVE_OUT if att.include_in_list else strings.INCLUDE_FILE)
        leave.setMinimumWidth(_widest(leave, (strings.LEAVE_OUT, strings.INCLUDE_FILE)))
        leave.clicked.connect(lambda: self._toggle(att.id, not att.include_in_list))
        row.addWidget(leave)
        remove = _button(strings.REMOVE_FILE)
        remove.clicked.connect(lambda: self._remove(att.id))
        row.addWidget(remove)
        return FileRow(att.id, widget, name, size, chip, leave, remove)

    # -- actions --------------------------------------------------------------------------

    def choose(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, strings.CHOOSE_FILES_TITLE)
        self.add_paths([Path(p) for p in paths])

    def add_paths(self, paths: list[Path]) -> None:
        messages: list[str] = []
        for path in paths:
            if not path.is_file():
                continue  # folders and vanished files are skipped
            try:
                message = attachments.check(
                    self.repos, self.blog_id, path, pending=len(self.copy_rows)
                )
                if message is None:
                    self._start_copy(path)
            except OSError as exc:
                log_event("attachment_copy_failed", blog_id=self.blog_id, error=type(exc).__name__)
                message = strings.COPY_FAILED.format(name=path.name)
            if message is not None and message not in messages:
                messages.append(message)
            if message == strings.TOO_MANY_FILES:
                break
        self._set_error("\n".join(messages))

    def copy_row(self, name: str, size_bytes: int, visible: bool = True) -> CopyRow:
        """A progress row for a copy in flight (also used by the snapshot tool)."""
        widget = QWidget()
        line = QHBoxLayout(widget)
        line.setContentsMargins(self.theme.space(1), 0, 0, 0)
        line.setSpacing(self.theme.space(2))
        label = _label(name)
        label.setWordWrap(False)
        line.addWidget(label)
        bar = QProgressBar()
        bar.setRange(0, PROGRESS_STEPS)
        bar.setTextVisible(False)
        bar.setAccessibleName(name)
        line.addWidget(bar, 1)
        size = _label(format_size(size_bytes), role="muted")
        size.setWordWrap(False)
        line.addWidget(size)
        cancel = _button(strings.CANCEL_COPY)
        # As wide as Leave out plus Remove, so the size lines up with the file rows.
        probe = _button(strings.REMOVE_FILE)
        leave_width = _widest(probe, (strings.LEAVE_OUT, strings.INCLUDE_FILE))
        cancel.setMinimumWidth(leave_width + line.spacing() + probe.sizeHint().width())
        probe.deleteLater()
        line.addWidget(cancel)
        entry = CopyRow(widget, label, size, bar, cancel)
        self.copy_rows.append(entry)
        self.copy_box.addWidget(widget)
        widget.setVisible(visible)
        self._tab_order()
        return entry

    def _start_copy(self, path: Path) -> None:
        size_bytes = path.stat().st_size  # before reserving, so a vanished file leaks nothing
        target = attachments.reserve(self.blog_id, path.name)
        big = size_bytes >= config.SHOW_COPY_PROGRESS_BYTES
        entry = self.copy_row(target.final.name, size_bytes, visible=big)
        bar, cancel = entry.bar, entry.cancel_button

        def progress(done: int, total: int) -> None:
            if not self._alive():
                return
            bar.setValue(round(PROGRESS_STEPS * done / total) if total else PROGRESS_STEPS)

        def finished(size: object) -> None:
            assert isinstance(size, int)
            attachments.record(self.repos, self.blog_id, target, size)
            log_event("attachment_added", blog_id=self.blog_id, size=size)
            if not self._alive():
                return  # stored and listed; the next dropzone for this blog shows it
            self._drop_copy(entry)
            if attachments.notice_due(self.repos):
                attachments.notice_shown(self.repos)
                self.notice.setVisible(True)
            self.refresh()
            self.changed.emit()

        def failed(exc: BaseException) -> None:
            attachments.release(target)
            if isinstance(exc, attachments.CopyCancelled):
                log_event("attachment_copy_cancelled", blog_id=self.blog_id)
            else:
                log_event("attachment_copy_failed", blog_id=self.blog_id, error=type(exc).__name__)
            if not self._alive():
                return
            self._drop_copy(entry)
            if isinstance(exc, attachments.AttachmentLimitError):
                self._set_error(exc.message)
            elif not isinstance(exc, attachments.CopyCancelled):
                self._set_error(strings.COPY_FAILED.format(name=path.name))

        entry.job = workers.run(
            attachments.copy_file, path, target,
            on_done=finished, on_error=failed, on_progress=progress,
        )  # fmt: skip
        cancel.clicked.connect(entry.job.cancel)
        cancel.clicked.connect(lambda: cancel.setEnabled(False))

    def _drop_copy(self, entry: CopyRow) -> None:
        if entry in self.copy_rows:
            self.copy_rows.remove(entry)
        self.copy_box.removeWidget(entry.widget)
        entry.widget.deleteLater()

    def cancel_all(self) -> None:
        for entry in self.copy_rows:
            if entry.job is not None:
                entry.job.cancel()

    def _toggle(self, attachment_id: int, included: bool) -> None:
        attachments.set_included(self.repos, attachment_id, included)
        self.refresh()
        row = self._row(attachment_id)
        if row is not None:
            row.leave_button.setFocus()  # the pressed button was rebuilt; keep keyboard place
        self.changed.emit()

    def _remove(self, attachment_id: int) -> None:
        index = next((i for i, r in enumerate(self.rows) if r.attachment_id == attachment_id), 0)
        attachments.remove(self.repos, attachment_id)
        self._set_error("")
        self.refresh()
        if self.rows:
            self.rows[min(index, len(self.rows) - 1)].remove_button.setFocus()
        else:
            self.choose_button.setFocus()
        self.changed.emit()

    def show_in_folder(self) -> None:
        folder = attachments.blog_dir(self.blog_id)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error_row.setVisible(bool(text))

    # -- drag and drop --------------------------------------------------------------------

    @staticmethod
    def _local_paths(event: QDragEnterEvent | QDropEvent) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt override)
        if self._local_paths(event):
            event.acceptProposedAction()
            self.area.set_drag_over(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 (Qt override)
        self.area.set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt override)
        self.area.set_drag_over(False)
        paths = self._local_paths(event)
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)
