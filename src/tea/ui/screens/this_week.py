"""This week screen (UI_DESIGN 3.1): the steep ring, the focus and the questions card.

The screen only shows a `WeekView` and emits what the owner asked for; `ui/week_flow.py`
does the work. The Carried over card and "Picked by tea" arrive in M9.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from tea.ui import strings
from tea.ui.screens import Page, muted, panel
from tea.ui.theme import Theme
from tea.ui.week_state import WeekView, caption_text, centre_caption, centre_text, ring_sentence
from tea.ui.widgets.chip import Chip
from tea.ui.widgets.steep_ring import SteepRing


def _button(text: str, variant: str | None = None) -> QPushButton:
    button = QPushButton(text)
    if variant:
        button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ThisWeekScreen(Page):
    set_focus_requested = Signal()
    open_handoff_requested = Signal(int)
    open_draft_requested = Signal(int)
    answer_requested = Signal()
    preview_requested = Signal()

    def __init__(self, theme: Theme, *, reduce_motion: bool = False) -> None:
        super().__init__(theme, strings.TITLE_WEEK)
        self.view: WeekView | None = None
        top = QHBoxLayout()
        top.setSpacing(theme.space(5))

        ring_col = QVBoxLayout()
        ring_col.setSpacing(theme.space(2))
        self.ring = SteepRing(theme, reduce_motion=reduce_motion)
        ring_col.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignHCenter)
        self.pick_chip = Chip(strings.CHIP_PICK, "pick")
        ring_col.addWidget(self.pick_chip, 0, Qt.AlignmentFlag.AlignHCenter)
        self.action_button = _button("", "primary")
        self.action_button.clicked.connect(self._on_action)
        ring_col.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.caption = muted("", "caption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ring_col.addWidget(self.caption)
        ring_col.addStretch(1)
        ring_box = QWidget()  # as wide as the ring, so a long caption wraps instead of shifting
        ring_box.setLayout(ring_col)
        ring_col.setContentsMargins(0, 0, 0, 0)
        ring_box.setFixedWidth(theme.size("ring"))
        top.addWidget(ring_box)

        focus_col = QVBoxLayout()
        focus_col.setSpacing(theme.space(1))
        focus_col.addWidget(muted(strings.FOCUS_LABEL, "caption"))
        self.focus_text = muted(strings.EMPTY_FOCUS, "display")
        self.focus_text.setProperty("muted", True)
        self.focus_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        focus_col.addWidget(self.focus_text)
        self.edit_focus_button = _button(strings.EDIT_FOCUS)
        self.edit_focus_button.clicked.connect(self.set_focus_requested)
        focus_col.addWidget(self.edit_focus_button, 0, Qt.AlignmentFlag.AlignLeft)
        focus_col.addStretch(1)
        top.addLayout(focus_col, 1)
        self.body.addLayout(top)

        card, card_layout = panel(theme)
        head = QHBoxLayout()
        title = QLabel(strings.QUESTIONS_THIS_WEEK)
        title.setProperty("role", "strong")
        head.addWidget(title)
        head.addStretch(1)
        self.answered_label = muted(strings.ANSWERED.format(n=0), "caption")
        head.addWidget(self.answered_label)
        card_layout.addLayout(head)
        buttons = QHBoxLayout()
        buttons.setSpacing(theme.space(1))
        self.answer_button = _button(strings.ANSWER_FEW)
        self.answer_button.clicked.connect(self.answer_requested)
        buttons.addWidget(self.answer_button)
        self.preview_button = _button(strings.WHAT_CLAUDE_TOLD, "quiet")
        self.preview_button.clicked.connect(self.preview_requested)
        buttons.addWidget(self.preview_button)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)
        self.body.addWidget(card)

        self.pick_chip.hide()
        self.action_button.hide()
        self.caption.hide()
        self.edit_focus_button.hide()

    def set_view(self, v: WeekView) -> None:
        self.view = v
        self.ring.set_state(
            v.state, v.progress, centre_text(v), centre_caption(v), ring_sentence(v)
        )
        self.pick_chip.setVisible(v.state == "pick")
        action = {
            "no_focus": strings.SET_FOCUS,
            "prompt_ready": strings.OPEN_HANDOFF,
            "ready": strings.OPEN_DRAFT,
        }.get(v.state)
        self.action_button.setVisible(action is not None)
        if action:
            self.action_button.setText(action)
            self.action_button.setAccessibleName(action)
        caption = caption_text(v)
        self.caption.setText(caption)
        self.caption.setVisible(bool(caption))

        has_focus = bool(v.focus)
        self.focus_text.setText(v.focus if has_focus else strings.EMPTY_FOCUS)  # type: ignore[arg-type]
        self.focus_text.setProperty("muted", not has_focus)
        _repolish(self.focus_text)
        if has_focus:
            label = strings.EDIT_FOCUS
        else:
            label = strings.SET_OWN_TOPIC if v.pick_mode else strings.SET_FOCUS
        self.edit_focus_button.setText(label)
        self.edit_focus_button.setVisible(v.state != "no_focus")
        self.answered_label.setText(strings.ANSWERED.format(n=v.answered))

    def _on_action(self) -> None:
        v = self.view
        if v is None:
            return
        if v.state == "no_focus":
            self.set_focus_requested.emit()
        elif v.state == "prompt_ready" and v.handoff_id is not None:
            self.open_handoff_requested.emit(v.handoff_id)
        elif v.state == "ready" and v.blog_id is not None:
            self.open_draft_requested.emit(v.blog_id)
