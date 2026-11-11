"""Choice and scale inputs for the question popup (UI_DESIGN section 4).

Both are exclusive button groups: arrow keys move inside them and Tab leaves them, the usual
radio-group behaviour. `value()` is the stored answer text ("" when nothing is picked).
"""

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from tea.db.rows import Question
from tea.handoff.answers import SCALE_POINTS
from tea.ui import strings
from tea.ui.theme import Theme


class _GroupInput(QWidget):
    changed = Signal()

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.group = QButtonGroup(self)
        self.group.buttonToggled.connect(lambda *_: self.changed.emit())
        self.buttons: list[QAbstractButton] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(theme.space(0))

    def _values(self) -> Sequence[str]:
        raise NotImplementedError

    def value(self) -> str:
        i = self.group.checkedId()
        return self._values()[i] if i >= 0 else ""

    def _check(self, value: str) -> None:
        self.group.setExclusive(False)  # an exclusive group cannot be cleared
        for button, v in zip(self.buttons, self._values(), strict=True):
            button.setChecked(v == value)
        self.group.setExclusive(True)

    def focus_target(self) -> QAbstractButton | None:
        checked = self.group.checkedButton()
        return checked or (self.buttons[0] if self.buttons else None)


class ChoiceInput(_GroupInput):
    """A vertical radio list; each option is a full-width row."""

    def __init__(self, theme: Theme) -> None:
        super().__init__(theme)
        self._options: list[str] = []

    def _values(self) -> Sequence[str]:
        return self._options

    def set_question(self, q: Question, value: str) -> None:
        for old in self.buttons:
            self.group.removeButton(old)
            old.deleteLater()
        self.buttons, self._options = [], [str(o) for o in q.options]
        for i, option in enumerate(self._options):
            radio = QRadioButton(option.replace("&", "&&"))
            radio.setProperty("row", "true")
            self.group.addButton(radio, i)
            self._layout.addWidget(radio)
            radio.show()  # layouts show new children on a queued call; focus needs it now
            self.buttons.append(radio)
        self._check(value)
        self.setAccessibleName(q.text)


class ScaleInput(_GroupInput):
    """Five segmented buttons with the low and high labels under the ends."""

    def __init__(self, theme: Theme) -> None:
        super().__init__(theme)
        segs = QHBoxLayout()
        segs.setSpacing(0)
        last = len(SCALE_POINTS) - 1
        for i, point in enumerate(SCALE_POINTS):
            seg = QPushButton(point)
            seg.setCheckable(True)
            seg.setProperty("seg", "first" if i == 0 else "last" if i == last else "true")
            self.group.addButton(seg, i)
            self.buttons.append(seg)
            segs.addWidget(seg, 1)
        self._layout.addLayout(segs)
        ends = QHBoxLayout()
        self.low = QLabel()
        self.high = QLabel()
        for label in (self.low, self.high):
            label.setProperty("role", "caption")
        ends.addWidget(self.low)
        ends.addStretch(1)
        ends.addWidget(self.high)
        self._layout.addLayout(ends)

    def _values(self) -> Sequence[str]:
        return SCALE_POINTS

    def set_question(self, q: Question, value: str) -> None:
        low, high = ([str(o) for o in q.options] + ["", ""])[:2]
        self.low.setText(low)
        self.high.setText(high)
        ends = {0: low, len(SCALE_POINTS) - 1: high}
        for i, seg in enumerate(self.buttons):
            n = SCALE_POINTS[i]
            name = strings.POPUP_SCALE_POINT.format(n=n)
            if i in ends:
                name = strings.POPUP_SCALE_END.format(n=n, label=ends[i])
            seg.setAccessibleName(name)
        self._check(value)
        self.setAccessibleName(q.text)
