"""Drafts screen (UI_DESIGN 3.3): grouped list on the left, the draft or a waiting hand-off.

The list is 300 wide and narrows first (down to 220) when the window is tight; the reading
column keeps at least 320 with the drawer open (owner approved, M7). `DraftsFlow` fills it.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from tea.ui import strings
from tea.ui.drafts_state import Entry, Group
from tea.ui.screens import muted, panel
from tea.ui.theme import Theme
from tea.ui.widgets.chip import Chip

KEY_ROLE = Qt.ItemDataRole.UserRole


class DraftsList(QListWidget):
    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme = theme
        self.setObjectName("DraftsList")
        self.setAccessibleName(strings.DRAFTS_LIST)
        self.setMinimumWidth(theme.size("drafts_list_min"))
        self.setMaximumWidth(theme.size("drafts_list"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(self.theme.size("drafts_list"), super().sizeHint().height())


class ElidedLabel(QLabel):
    """One line, cut with an ellipsis to fit; the full text is the tooltip."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.full_text = text
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(
            self.full_text, Qt.TextElideMode.ElideRight, rect.width()
        )
        p.drawText(rect, int(self.alignment()), text)
        p.end()


class DraftRow(QWidget):
    def __init__(self, theme: Theme, entry: Entry) -> None:
        super().__init__()
        self.setObjectName("DraftRow")
        col = QVBoxLayout(self)
        pad = theme.space(2)
        col.setContentsMargins(pad, pad, pad, pad)
        col.setSpacing(theme.space(0))
        self.title = ElidedLabel(entry.title)
        self.title.setProperty("role", "strong")
        col.addWidget(self.title)
        line = QHBoxLayout()
        line.setSpacing(theme.space(1))
        when = ElidedLabel(entry.when)
        when.setProperty("role", "caption")
        line.addWidget(when, 1)
        self.chip = Chip(theme, entry.chip_text, entry.chip_state)
        line.addWidget(self.chip)
        col.addLayout(line)
        self.setAccessibleName(f"{entry.title}, {entry.chip_text}, {entry.when}")


class WaitingPane(QWidget):
    """A hand-off still waiting for Claude's reply, with a way back into its dialog."""

    open_requested = Signal(int)

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.handoff_id = 0
        frame, layout = panel(theme)
        layout.setSpacing(theme.space(2))
        head = QHBoxLayout()
        head.setSpacing(theme.space(2))
        head.addWidget(Chip(theme, strings.CHIP_PROMPT_READY, "prompt"))
        self.title_label = QLabel()
        self.title_label.setProperty("role", "title")
        self.title_label.setWordWrap(True)
        head.addWidget(self.title_label, 1)
        layout.addLayout(head)
        layout.addWidget(muted(strings.WAITING_FOR_REPLY))
        self.since_label = muted("", "caption")
        layout.addWidget(self.since_label)
        row = QHBoxLayout()
        self.open_button = QPushButton(strings.OPEN_HANDOFF_PANE)
        self.open_button.setProperty("variant", "primary")
        self.open_button.clicked.connect(lambda: self.open_requested.emit(self.handoff_id))
        row.addWidget(self.open_button)
        row.addStretch(1)
        layout.addLayout(row)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        outer.addStretch(1)

    def show_entry(self, entry: Entry) -> None:
        self.handoff_id = entry.id
        self.title_label.setText(entry.title)
        self.since_label.setText(strings.WAITING_SINCE.format(when=entry.when))


class DraftsScreen(QWidget):
    selected = Signal(str, int)  # entry kind, id

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme = theme
        outer = QVBoxLayout(self)
        m = theme.space(5)
        outer.setContentsMargins(m, m, m, m)
        outer.setSpacing(theme.space(4))
        heading = QLabel(strings.TITLE_DRAFTS)
        heading.setProperty("role", "title")
        heading.setAccessibleName(strings.TITLE_DRAFTS)
        outer.addWidget(heading)

        self.stack = QStackedWidget()
        empty = QWidget()
        col = QVBoxLayout(empty)
        col.setContentsMargins(0, 0, 0, 0)
        frame, layout = panel(theme)
        self.empty_label = muted(strings.EMPTY_DRAFTS)
        layout.addWidget(self.empty_label)
        col.addWidget(frame)
        col.addStretch(1)
        self.stack.addWidget(empty)

        split = QWidget()
        row = QHBoxLayout(split)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.space(4))
        self.list = DraftsList(theme)
        self.list.currentItemChanged.connect(self._current_changed)
        row.addWidget(self.list)
        self.panes = QStackedWidget()
        self.blank = QWidget()
        self.panes.addWidget(self.blank)
        self.waiting = WaitingPane(theme)
        self.panes.addWidget(self.waiting)
        row.addWidget(self.panes, 1)
        self.stack.addWidget(split)
        outer.addWidget(self.stack, 1)
        self.draft_view: QWidget | None = None
        self._entries: dict[tuple[str, int], Entry] = {}

    def set_draft_view(self, view: QWidget) -> None:
        self.draft_view = view
        self.panes.addWidget(view)

    def is_empty(self) -> bool:
        return self.stack.currentIndex() == 0

    def set_groups(self, groups: list[Group]) -> None:
        current = self.current_key()
        self.list.blockSignals(True)
        self.list.clear()
        self._entries = {}
        for group in groups:
            head = QListWidgetItem()
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            label = QLabel(group.name)
            label.setObjectName("GroupHeading")
            head.setSizeHint(label.sizeHint())
            self.list.addItem(head)
            self.list.setItemWidget(head, label)
            for entry in group.entries:
                item = QListWidgetItem()
                item.setData(KEY_ROLE, entry.key)
                row = DraftRow(self.theme, entry)
                # A narrow hint: in list mode each row spans the list's full width anyway.
                item.setSizeHint(QSize(self.theme.space(6), row.sizeHint().height()))
                item.setData(Qt.ItemDataRole.AccessibleTextRole, row.accessibleName())
                self.list.addItem(item)
                self.list.setItemWidget(item, row)
                self._entries[entry.key] = entry
        self.list.blockSignals(False)
        self.stack.setCurrentIndex(1 if self._entries else 0)
        if current in self._entries:
            self.select(*current)
        elif self._entries:
            self.select(*next(iter(self._entries)))
        else:
            self.panes.setCurrentWidget(self.blank)

    def group_names(self) -> list[str]:
        names = []
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if isinstance(w, QLabel) and w.objectName() == "GroupHeading":
                names.append(w.text())
        return names

    def keys(self) -> list[tuple[str, int]]:
        return list(self._entries)

    def current_key(self) -> tuple[str, int] | None:
        item = self.list.currentItem()
        key = item.data(KEY_ROLE) if item is not None else None
        return tuple(key) if key else None  # type: ignore[return-value]

    def select(self, kind: str, entry_id: int) -> bool:
        for i in range(self.list.count()):
            item = self.list.item(i)
            key = item.data(KEY_ROLE)
            if key and tuple(key) == (kind, entry_id):
                if self.list.currentItem() is item:
                    self._current_changed(item, None)
                else:
                    self.list.setCurrentItem(item)
                return True
        return False

    def show_waiting(self, entry: Entry) -> None:
        self.waiting.show_entry(entry)
        self.panes.setCurrentWidget(self.waiting)

    def show_draft(self) -> None:
        if self.draft_view is not None:
            self.panes.setCurrentWidget(self.draft_view)

    def _current_changed(self, item: QListWidgetItem | None, _prev: object) -> None:
        key = item.data(KEY_ROLE) if item is not None else None
        if not key:
            return
        kind, entry_id = key
        entry = self._entries.get((kind, entry_id))
        if entry is None:
            return
        if kind == "handoff":
            self.show_waiting(entry)
        self.selected.emit(kind, entry_id)
