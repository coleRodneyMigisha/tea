"""Floating question popup (UI_DESIGN section 4): text, choice and scale questions.

Answers are handed to `save(question, text, skipped)` one at a time, on Next and Skip, so
Later or a crash keeps everything answered so far. `finished` says how the popup closed.
"""

import math
from collections.abc import Callable, Sequence

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tea.db.rows import Question
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.answer_inputs import ChoiceInput, ScaleInput

DONE, LATER, TIMEOUT = "done", "later", "timeout"
LOGIN_TIMEOUT_MS = 90_000
TEXT_MIN_ROWS, TEXT_MAX_ROWS = 3, 6
SaveFn = Callable[[Question, str, bool], None]
_ACTIVITY = {QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel}


def _button(text: str, variant: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class _Header(QWidget):
    """The top row. Dragging it moves the popup; the compositor does the move on Wayland."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PopupHeader")
        self._grab: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        handle = self.window().windowHandle()
        if handle is not None and handle.startSystemMove():
            return
        self._grab = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._grab is not None:
            self.window().move(event.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._grab = None


class QuestionPopup(QWidget):
    finished = Signal(str)

    def __init__(
        self,
        theme: Theme,
        questions: Sequence[Question],
        save: SaveFn,
        *,
        login: bool,
        reduce_motion: bool = False,
        timeout_ms: int = LOGIN_TIMEOUT_MS,
    ) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        self.theme = theme
        self.questions = list(questions)
        self.login = login
        self.index = 0
        self._save = save
        self._drafts: dict[int, str] = {}
        self._saved: dict[int, tuple[str, bool]] = {}
        self._ended = False
        self._placed = False
        self.rise = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, login)
        self._build()
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(timeout_ms)
        self._idle.timeout.connect(lambda: self._finish(TIMEOUT))
        self.entry: QVariantAnimation | None = None
        if not reduce_motion:
            self.entry = QVariantAnimation(self)
            self.entry.setDuration(theme.motion_ms("popup_in"))
            self.entry.setStartValue(0.0)
            self.entry.setEndValue(1.0)
            self.entry.valueChanged.connect(self._animate)
            self.entry.finished.connect(self._end_fade)
        self._load()

    # Layout

    def _build(self) -> None:
        t = self.theme
        shadow_room = t.size("popup_shadow_blur")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(shadow_room, shadow_room, shadow_room, shadow_room)
        self.card = QWidget()
        self.card.setObjectName("PopupCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.card.setFixedWidth(t.size("width"))
        self.card.setMinimumHeight(t.size("popup_min_height"))
        self.card.setMaximumHeight(t.size("popup_max_height"))
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(shadow_room)
        shadow.setOffset(QPointF(0, t.size("popup_shadow_y")))
        shadow.setColor(t.color("shadow"))
        self.card.setGraphicsEffect(shadow)
        # The fade runs on this wrapper; the card itself carries the shadow effect.
        self._fade = QWidget()
        wrap = QVBoxLayout(self._fade)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(self.card)
        outer.addWidget(self._fade)

        body = QVBoxLayout(self.card)
        pad = t.space(4)
        body.setContentsMargins(pad, t.space(3), pad, pad)
        body.setSpacing(t.space(3))

        header = _Header()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        self.progress = QLabel()
        self.progress.setObjectName("PopupProgress")
        self.later_button = _button(strings.POPUP_LATER, "quiet")
        self.later_button.setToolTip(strings.POPUP_LATER_TOOLTIP)
        self.later_button.clicked.connect(lambda: self._finish(LATER))
        row.addWidget(self.progress)
        row.addStretch(1)
        row.addWidget(self.later_button)
        body.addWidget(header)

        self.question_label = QLabel()
        self.question_label.setObjectName("PopupQuestion")
        self.question_label.setWordWrap(True)
        body.addWidget(self.question_label)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setTabChangesFocus(True)
        self.text_edit.textChanged.connect(self._on_text)
        body.addWidget(self.text_edit)

        self.choice = ChoiceInput(t)
        self.choice.changed.connect(self._on_toggle)
        body.addWidget(self.choice)
        self.scale = ScaleInput(t)
        self.scale.changed.connect(self._on_toggle)
        body.addWidget(self.scale)
        body.addStretch(1)

        buttons = QHBoxLayout()
        self.skip_button = _button(strings.POPUP_SKIP, "quiet")
        self.skip_button.clicked.connect(self._skip)
        self.back_button = _button(strings.POPUP_BACK, "quiet")
        self.back_button.clicked.connect(self._back)
        self.next_button = _button(strings.POPUP_NEXT, "primary")
        self.next_button.clicked.connect(self._next)
        buttons.addWidget(self.skip_button)
        buttons.addWidget(self.back_button)
        buttons.addStretch(1)
        buttons.addWidget(self.next_button)
        body.addLayout(buttons)

        self._watch(self)

    def _watch(self, root: QWidget) -> None:
        root.installEventFilter(self)
        for child in root.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Ctrl+Return is Next and Esc is Later, wherever focus is inside the popup.

        Handled here rather than with QShortcut so the keys work even while the compositor
        has not made this tool window the active one.
        """
        if event.type() in _ACTIVITY:
            self._touch()
        if isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
            ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            if ctrl and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._next()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._finish(LATER)
                return True
        return False

    def _touch(self) -> None:
        if self._idle.isActive():
            self._idle.start()

    # The current question

    @property
    def current(self) -> Question:
        return self.questions[self.index]

    @property
    def scale_labels(self) -> tuple[str, str]:
        return self.scale.low.text(), self.scale.high.text()

    @property
    def choice_buttons(self) -> list[QAbstractButton]:
        return self.choice.buttons

    @property
    def scale_buttons(self) -> list[QAbstractButton]:
        return self.scale.buttons

    def progress_text(self) -> str:
        return self.progress.text()

    def rows_height(self, rows: int) -> int:
        edit = self.text_edit
        margins = edit.contentsMargins()
        doc = int(math.ceil(edit.document().documentMargin() * 2))
        return edit.fontMetrics().lineSpacing() * rows + doc + margins.top() + margins.bottom()

    def _load(self) -> None:
        q = self.current
        total = len(self.questions)
        self.progress.setText(strings.POPUP_PROGRESS.format(n=self.index + 1, m=total))
        self.question_label.setText(q.text)
        self.next_button.setText(
            strings.POPUP_DONE if self.index == total - 1 else strings.POPUP_NEXT
        )
        self.back_button.setHidden(self.index == 0)
        value = self._drafts.get(self.index, "")
        self.text_edit.setVisible(q.kind == "text")
        self.choice.setVisible(q.kind == "choice")
        self.scale.setVisible(q.kind == "scale")
        if q.kind == "choice":
            self.choice.set_question(q, value)
            self._watch(self.choice)
        elif q.kind == "scale":
            self.scale.set_question(q, value)
        else:
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(value)
            self.text_edit.blockSignals(False)
            self.text_edit.setAccessibleName(q.text)
            self._fit_text()
        self._update_next()
        self._input_widget().setFocus(Qt.FocusReason.OtherFocusReason)
        self.adjustSize()

    def _input_widget(self) -> QWidget:
        kind = self.current.kind
        if kind == "text":
            return self.text_edit
        target = (self.choice if kind == "choice" else self.scale).focus_target()
        return target or self.next_button

    def value(self) -> str:
        kind = self.current.kind
        if kind == "text":
            return self.text_edit.toPlainText()
        return (self.choice if kind == "choice" else self.scale).value()

    def _update_next(self) -> None:
        self.next_button.setEnabled(bool(self.value().strip()))

    def _on_text(self) -> None:
        self._fit_text()
        self._update_next()
        self._touch()

    def _on_toggle(self) -> None:
        self._update_next()
        self._touch()

    def _fit_text(self) -> None:
        lines = math.ceil(self.text_edit.document().size().height())
        rows = min(max(lines, TEXT_MIN_ROWS), TEXT_MAX_ROWS)
        self.text_edit.setFixedHeight(self.rows_height(rows))

    # Actions

    def _next(self) -> None:
        if self._ended or not self.next_button.isEnabled():
            return
        value = self.value()
        self._drafts[self.index] = value
        if self._saved.get(self.index) != (value, False):
            self._save(self.current, value, False)
            self._saved[self.index] = (value, False)
        self._advance()

    def _skip(self) -> None:
        if self._ended:
            return
        self._drafts[self.index] = ""
        if self._saved.get(self.index) != ("", True):
            self._save(self.current, "", True)
            self._saved[self.index] = ("", True)
        self._advance()

    def _back(self) -> None:
        if self.index == 0:
            return
        self._drafts[self.index] = self.value()
        self.index -= 1
        self._load()

    def _advance(self) -> None:
        if self.index >= len(self.questions) - 1:
            self._finish(DONE)
            return
        self.index += 1
        self._load()

    def _finish(self, reason: str) -> None:
        if self._ended:
            return
        self._ended = True
        self._idle.stop()
        self.close()
        self.finished.emit(reason)

    # Showing

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._placed:
            self._placed = True
            self._place()
            if self.entry is not None:
                self.entry.start()
        if self.login:
            self._idle.start()
        else:
            self.raise_()
            self.activateWindow()

    def _place(self) -> None:
        """Bottom-right of the primary screen. On Wayland the compositor decides instead."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.adjustSize()
        area = screen.availableGeometry()
        gap = self.theme.size("margin") - self.theme.size("popup_shadow_blur")
        self.move(area.right() - self.width() - gap, area.bottom() - self.height() - gap)

    def _animate(self, value: object) -> None:
        progress = float(value)  # type: ignore[arg-type]
        self.rise = round(self.theme.space(1) * (1 - progress))
        room = self.theme.size("popup_shadow_blur")
        layout = self.layout()
        assert layout is not None
        layout.setContentsMargins(room, room + self.rise, room, room - self.rise)
        effect = self._fade.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self._fade)
            self._fade.setGraphicsEffect(effect)
        effect.setOpacity(progress)

    def _end_fade(self) -> None:
        effect = self._fade.graphicsEffect()
        if effect is not None:
            effect.setEnabled(False)  # draw the card directly once it is fully shown
