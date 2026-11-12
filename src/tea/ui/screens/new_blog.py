"""New blog screen (UI_DESIGN 3.2): one scrolling form in a panel, at most 720 wide.

The screen only holds the form and emits what the owner asked for; `ui/new_blog_flow.py`
owns the blog row, mounts the dropzone and runs the scope session.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tea.domain.manual import LENGTHS, SOURCES
from tea.ui import strings
from tea.ui.screens import Page, button, muted, panel
from tea.ui.theme import Theme
from tea.ui.widgets.dropzone import Dropzone

COVER_ROWS = 4


def _label(text: str, buddy: QWidget) -> QLabel:
    label = QLabel(text)
    label.setBuddy(buddy)
    return label


def _banner(theme: Theme, action: str) -> tuple[QFrame, QLabel, QPushButton]:
    frame = QFrame()
    frame.setObjectName("Banner")
    line = QHBoxLayout(frame)
    line.setContentsMargins(theme.space(3), theme.space(1), theme.space(1), theme.space(1))
    line.setSpacing(theme.space(2))
    label = muted("", "strong")
    line.addWidget(label, 1)
    act = button(action)
    act.setCursor(Qt.CursorShape.PointingHandCursor)
    line.addWidget(act)
    frame.hide()
    return frame, label, act


class NewBlogScreen(Page):
    start_requested = Signal()
    cancel_requested = Signal()
    resume_requested = Signal()
    open_handoff_requested = Signal()

    def __init__(self, theme: Theme) -> None:
        super().__init__(theme, strings.TITLE_NEW)
        self.dropzone: Dropzone | None = None
        self._copying = False

        scroll = QScrollArea()
        scroll.setObjectName("FormScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("Content")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.space(3))
        width = theme.size("form_max_width")

        self.progress_banner, self.progress_label, self.resume_button = _banner(
            theme, strings.RESUME
        )
        self.resume_button.clicked.connect(self.resume_requested)
        self.waiting_banner, self.waiting_label, self.open_handoff_button = _banner(
            theme, strings.OPEN_HANDOFF
        )
        self.waiting_label.setText(strings.PROMPT_WAITING)
        self.open_handoff_button.clicked.connect(self.open_handoff_requested)
        for banner in (self.progress_banner, self.waiting_banner):
            banner.setMaximumWidth(width)
            column.addWidget(banner)

        self.panel, form = panel(theme)
        self.panel.setMaximumWidth(width)
        form.setSpacing(theme.space(3))
        self._fields(form)
        self._sources(form)
        self.drop_slot = QVBoxLayout()
        form.addLayout(self.drop_slot)
        self._length(form)
        self.error = muted("", "error")
        self.error.hide()
        form.addWidget(self.error)
        actions = QHBoxLayout()
        actions.setSpacing(theme.space(1))
        actions.addStretch(1)
        self.cancel_button = button(strings.CANCEL)
        self.cancel_button.clicked.connect(self.cancel_requested)
        actions.addWidget(self.cancel_button)
        self.start_button = button(strings.START_QUESTIONS, "primary")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self._on_start)
        actions.addWidget(self.start_button)
        form.addLayout(actions)
        column.addWidget(self.panel)
        column.addStretch(1)
        scroll.setWidget(content)
        self.body.addWidget(scroll, 1)
        outer = self.layout()
        assert isinstance(outer, QVBoxLayout)
        outer.takeAt(outer.count() - 1)  # Page's trailing stretch: the scroll area fills instead
        outer.setStretch(outer.count() - 1, 1)
        self.reset("standard")

    # Layout

    def _fields(self, form: QVBoxLayout) -> None:
        grid = QGridLayout()
        grid.setHorizontalSpacing(self.theme.space(3))
        grid.setVerticalSpacing(self.theme.space(2))
        self.topic_edit = QLineEdit()
        self.topic_edit.setAccessibleName(strings.NEW_TOPIC)
        self.topic_edit.textChanged.connect(self._update_start)
        self.topic_edit.returnPressed.connect(self._on_start)
        self.cover_edit = QPlainTextEdit()
        self.cover_edit.setAccessibleName(strings.NEW_COVER)
        self.cover_edit.setTabChangesFocus(True)
        lines = self.cover_edit.fontMetrics().lineSpacing() * COVER_ROWS
        margins = self.cover_edit.contentsMargins()
        doc = int(self.cover_edit.document().documentMargin() * 2)
        self.cover_edit.setFixedHeight(lines + doc + margins.top() + margins.bottom())
        self.audience_edit = QLineEdit()
        self.audience_edit.setAccessibleName(strings.NEW_AUDIENCE)
        rows = (
            (strings.NEW_TOPIC, self.topic_edit),
            (strings.NEW_COVER, self.cover_edit),
            (strings.NEW_AUDIENCE, self.audience_edit),
        )
        for row, (text, edit) in enumerate(rows):
            top = edit is self.cover_edit
            align = Qt.AlignmentFlag.AlignLeft | (
                Qt.AlignmentFlag.AlignTop if top else Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(_label(text, edit), row, 0, align)
            grid.addWidget(edit, row, 1)
        grid.setColumnStretch(1, 1)
        form.addLayout(grid)

    def _sources(self, form: QVBoxLayout) -> None:
        heading = QLabel(strings.NEW_SOURCES)
        heading.setProperty("role", "strong")
        form.addWidget(heading)
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(4))
        self.source_boxes: dict[str, QCheckBox] = {}
        for key in SOURCES:
            box = QCheckBox(strings.SOURCE_LABELS[key])
            line.addWidget(box)
            self.source_boxes[key] = box
        line.addStretch(1)
        form.addLayout(line)

    def _length(self, form: QVBoxLayout) -> None:
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(3))
        label = QLabel(strings.NEW_LENGTH)
        label.setProperty("role", "strong")
        line.addWidget(label)
        segs = QHBoxLayout()
        segs.setSpacing(0)
        self.length_group = QButtonGroup(self)
        self.length_group.setExclusive(True)
        self.length_buttons: dict[str, QPushButton] = {}
        for i, key in enumerate(LENGTHS):
            b = QPushButton(strings.LENGTH_LABELS[key])
            b.setCheckable(True)
            b.setProperty("seg", "first" if i == 0 else "last" if i == len(LENGTHS) - 1 else "true")
            b.setProperty("wide", True)  # padded segments: the labels are words
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.length_group.addButton(b)
            segs.addWidget(b)
            self.length_buttons[key] = b
        label.setBuddy(self.length_buttons[LENGTHS[0]])
        line.addLayout(segs)
        line.addStretch(1)
        form.addLayout(line)

    # State

    def set_dropzone(self, dropzone: Dropzone) -> None:
        old, self.dropzone = self.dropzone, dropzone
        if old is not None:
            old.hide()
            self.drop_slot.removeWidget(old)
            old.deleteLater()
        self.drop_slot.addWidget(dropzone)
        dropzone.changed.connect(self._on_files)
        self._on_files()

    def reset(self, length: str) -> None:
        """An empty form for the next blog."""
        self.topic_edit.clear()
        self.cover_edit.clear()
        self.audience_edit.clear()
        for key, box in self.source_boxes.items():
            box.setChecked(key == "own_documents")
        self.length_buttons.get(length, self.length_buttons["standard"]).setChecked(True)
        self.show_error("")
        self._update_start()

    def values(self) -> dict[str, object]:
        length = next((k for k, b in self.length_buttons.items() if b.isChecked()), "standard")
        return {
            "topic": self.topic_edit.text(),
            "scope_notes": self.cover_edit.toPlainText(),
            "audience": self.audience_edit.text(),
            "allowed_sources": [k for k, b in self.source_boxes.items() if b.isChecked()],
            "length": length,
        }

    def set_banners(self, in_progress: str | None, waiting: bool) -> None:
        if in_progress is not None:
            self.progress_label.setText(strings.IN_PROGRESS.format(topic=in_progress))
        self.progress_banner.setVisible(in_progress is not None)
        self.waiting_banner.setVisible(waiting)

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def _on_files(self) -> None:
        self._copying = self.dropzone is not None and self.dropzone.copying()
        self._update_start()

    def _update_start(self) -> None:
        self.start_button.setEnabled(bool(self.topic_edit.text().strip()) and not self._copying)

    def _on_start(self) -> None:
        if self.start_button.isEnabled():
            self.start_requested.emit()
