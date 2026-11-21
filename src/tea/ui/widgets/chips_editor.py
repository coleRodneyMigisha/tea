"""Interests editor (UI_DESIGN 3.4): removable chips and an entry line.

Enter adds what is typed. A click on a chip removes it. The editor never saves: it emits
`changed` with the new list and the screen decides.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.flow_layout import FlowLayout

MAX_LENGTH = 60


class ChipsEditor(QWidget):
    changed = Signal(list)

    def __init__(self, theme: Theme, items: list[str] | None = None) -> None:
        super().__init__()
        self.theme = theme
        self._items: list[str] = []
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.space(1))
        self._chips = QWidget()
        self._flow = FlowLayout(self._chips, theme.space(1))
        column.addWidget(self._chips)
        self.message = QLabel("")
        self.message.setProperty("role", "error")
        self.message.setWordWrap(True)
        self.message.hide()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText(strings.SETTINGS_ADD_INTEREST)
        self.entry.setAccessibleName(strings.SETTINGS_ADD_INTEREST)
        self.entry.returnPressed.connect(self._add)
        self.entry.textEdited.connect(lambda _t: self.message.hide())
        column.addWidget(self.entry)
        column.addWidget(self.message)
        self.set_items(items or [])

    def items(self) -> list[str]:
        return list(self._items)

    def chip_buttons(self) -> list[QPushButton]:
        found = (self._flow.itemAt(i) for i in range(self._flow.count()))
        return [w for it in found if it is not None and isinstance(w := it.widget(), QPushButton)]

    def set_items(self, items: list[str]) -> None:
        """Show `items` without emitting."""
        self._items = list(items)
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for name in self._items:
            self._flow.addWidget(self._chip(name))
        self._chips.setVisible(bool(self._items))
        self._chips.updateGeometry()

    def _chip(self, name: str) -> QPushButton:
        chip = QPushButton(name, self._chips)
        chip.setProperty("pill", True)
        chip.setIcon(self.theme.icon("cross", "muted"))
        chip.setIconSize(self.theme.icon_size())
        chip.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # the cross after the text
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(strings.SETTINGS_REMOVE_INTEREST.format(name=name))
        chip.setAccessibleName(strings.SETTINGS_REMOVE_INTEREST.format(name=name))
        chip.clicked.connect(lambda _=False, n=name: self._remove(n))
        chip.show()
        return chip

    def _problem(self, text: str) -> str | None:
        if len(text) > MAX_LENGTH:
            return strings.SETTINGS_INTEREST_LONG
        if text.casefold() in (i.casefold() for i in self._items):
            return strings.SETTINGS_INTEREST_DUPLICATE
        return None

    def _add(self) -> None:
        text = " ".join(self.entry.text().split())
        if not text:
            return
        problem = self._problem(text)
        if problem is not None:
            self.message.setText(problem)
            self.message.show()
            return
        self.message.hide()
        self.entry.clear()
        self.set_items([*self._items, text])
        self.changed.emit(self.items())

    def _remove(self, name: str) -> None:
        self.set_items([i for i in self._items if i != name])
        self.changed.emit(self.items())
