"""Settings screen (UI_DESIGN 3.4): one scrolling column of panels with plain headings.

Every control saves as soon as it changes (text boxes when the owner leaves them, the style
notes a moment after typing). A value the model rejects is not saved; its message sits under
the control. The screen emits `changed(Settings)` and the app saves and applies it.
"""

from datetime import time
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Qt, QTime, QTimer, Signal
from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from tea import __version__
from tea.clock import Clock
from tea.settings import Settings
from tea.ui import strings
from tea.ui.screens import Page, button, muted, panel
from tea.ui.screens.settings_actions import SettingsActions
from tea.ui.theme import Theme
from tea.ui.widgets.chips_editor import ChipsEditor
from tea.ui.widgets.report_dialog import ReportDialog

NOTES_DELAY_MS = 700
NOTE_ROWS = 6
APPEARANCES = ("light", "dark", "system")
LENGTHS = ("short", "standard", "long")


def _qtime(value: time) -> QTime:
    return QTime(value.hour, value.minute)


def _time(value: QTime) -> time:
    return time(value.hour(), value.minute())


class SettingsScreen(Page):
    changed = Signal(object)

    def __init__(self, theme: Theme, settings: Settings, clock: Clock) -> None:
        super().__init__(theme, strings.TITLE_SETTINGS)
        self._settings = settings
        self._syncing = False
        self._titles: list[str] = []
        self.tasks = SettingsActions(theme, clock, self)
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(NOTES_DELAY_MS)
        self._notes_timer.timeout.connect(self.flush)

        scroll = QScrollArea()
        scroll.setObjectName("FormScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("Content")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, theme.space(5))
        column.setSpacing(theme.space(3))
        self._column = column
        self._width = theme.size("form_max_width")

        banner = QFrame()
        banner.setObjectName("Banner")
        banner.setMaximumWidth(self._width)
        line = QHBoxLayout(banner)
        pad = theme.size("panel_padding")
        line.setContentsMargins(pad, theme.space(1), pad, theme.space(1))
        self.load_error = muted("", "strong")
        line.addWidget(self.load_error)
        self._load_banner = banner
        banner.hide()
        column.addWidget(banner)

        self._schedule()
        self._topic()
        self._questions()
        self._carry()
        self._reminders()
        self._handoff()
        self._writing()
        self._appearance()
        self._data()
        self._automation()
        self._about()
        column.addStretch(1)
        scroll.setWidget(content)
        self.body.addWidget(scroll, 1)
        outer = self.layout()
        assert isinstance(outer, QVBoxLayout)
        outer.takeAt(outer.count() - 1)  # Page's trailing stretch: the scroll area fills instead
        outer.setStretch(outer.count() - 1, 1)
        margins = outer.contentsMargins()
        margins.setBottom(0)
        outer.setContentsMargins(margins)
        scroll.setMaximumWidth(self._width + theme.space(4))
        self.set_settings(settings)

    # Building blocks

    def _section(self, key: str) -> tuple[QVBoxLayout, QGridLayout]:
        frame, box = panel(self.theme)
        frame.setMaximumWidth(self._width)
        title = strings.SETTINGS_SECTIONS[key]
        heading = QLabel(title)
        heading.setProperty("role", "heading")
        heading.setAccessibleName(title)
        box.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(self.theme.space(3))
        grid.setVerticalSpacing(self.theme.space(2))
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        self._titles.append(title)
        self._column.addWidget(frame)
        return box, grid

    def _row(self, grid: QGridLayout, text: str, field: QWidget | QHBoxLayout) -> None:
        row = grid.rowCount()
        label = QLabel(text)
        if isinstance(field, QWidget):
            label.setBuddy(field)
        tall = isinstance(field, ChipsEditor | QPlainTextEdit)
        align = Qt.AlignmentFlag.AlignTop if tall else Qt.AlignmentFlag.AlignVCenter
        grid.addWidget(label, row, 0, align)
        if isinstance(field, QComboBox | QSpinBox | QTimeEdit):
            grid.addWidget(field, row, 1, Qt.AlignmentFlag.AlignLeft)  # short controls keep size
        elif isinstance(field, QWidget):
            grid.addWidget(field, row, 1)
        else:
            grid.addLayout(field, row, 1)

    def _span(self, grid: QGridLayout, widget: QWidget) -> None:
        grid.addWidget(widget, grid.rowCount(), 0, 1, 2)

    def _day(self, field: str) -> QComboBox:
        box = QComboBox()
        for index, name in enumerate(strings.WEEKDAY_LONG):
            box.addItem(name, index)
        box.currentIndexChanged.connect(lambda i: self._commit(**{field: i}))
        return box

    def _clock(self, field: str) -> QTimeEdit:
        edit = QTimeEdit()
        edit.setDisplayFormat("HH:mm")
        edit.timeChanged.connect(lambda t: self._commit(**{field: _time(t)}))
        return edit

    def _when(self, grid: QGridLayout, text: str, day: QComboBox, at: QTimeEdit) -> None:
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(1))
        line.addWidget(day)
        line.addWidget(at)
        line.addStretch(1)
        day.setAccessibleName(f"{text}, day")
        at.setAccessibleName(f"{text}, time")
        self._row(grid, text, line)

    def _switch(self, text: str, field: str) -> QCheckBox:
        box = QCheckBox(text)
        box.toggled.connect(lambda on: self._commit(**{field: on}))
        return box

    def _spin(self, low: int, high: int, field: str, step: int = 1, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(lambda v: self._commit(**{field: v}))
        return spin

    def _combo(self, keys: tuple[str, ...], labels: dict[str, str], field: str) -> QComboBox:
        box = QComboBox()
        for key in keys:
            box.addItem(labels[key], key)
        box.currentIndexChanged.connect(lambda i: self._commit(**{field: box.itemData(i)}))
        return box

    # Panels

    def _schedule(self) -> None:
        _box, grid = self._section("schedule")
        self.focus_day, self.focus_time = self._day("focus_day"), self._clock("focus_time")
        self.pick_day, self.pick_time = self._day("pick_day"), self._clock("pick_time")
        self.prompt_day, self.prompt_time = self._day("prompt_day"), self._clock("prompt_time")
        self._when(grid, strings.SETTINGS_FOCUS, self.focus_day, self.focus_time)
        self._when(grid, strings.SETTINGS_PICK, self.pick_day, self.pick_time)
        self._when(grid, strings.SETTINGS_PROMPT, self.prompt_day, self.prompt_time)

    def _topic(self) -> None:
        _box, grid = self._section("topic")
        self.pick_enabled = self._switch(strings.SETTINGS_PICK_SWITCH, "pick_enabled")
        self._span(grid, self.pick_enabled)
        self.interests = ChipsEditor(self.theme)
        self.interests.changed.connect(lambda items: self._commit(interests=items))
        self._row(grid, strings.SETTINGS_INTERESTS, self.interests)
        hint = muted(strings.SETTINGS_INTERESTS_HINT, "caption")
        grid.addWidget(hint, grid.rowCount(), 1)
        self.region = QLineEdit()
        self.region.setAccessibleName(strings.SETTINGS_REGION)
        self.region.editingFinished.connect(lambda: self._commit(region=self.region.text().strip()))
        self._row(grid, strings.SETTINGS_REGION, self.region)

    def _questions(self) -> None:
        _box, grid = self._section("questions")
        self.per_login = self._spin(0, 5, "questions_per_login")
        self.dismiss_pause = self._spin(
            0, 24 * 60, "dismiss_pause_minutes", 15, strings.SETTINGS_MINUTES
        )
        self._row(grid, strings.SETTINGS_PER_LOGIN, self.per_login)
        self._row(grid, strings.SETTINGS_PAUSE_AFTER, self.dismiss_pause)

    def _carry(self) -> None:
        _box, grid = self._section("carry")
        self.carry_weeks = self._spin(0, 3, "carry_over_weeks")
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(1))
        lead = QLabel(strings.SETTINGS_KEEP_PREFIX)
        lead.setBuddy(self.carry_weeks)
        line.addWidget(lead)
        line.addWidget(self.carry_weeks)
        line.addWidget(QLabel(strings.SETTINGS_KEEP_SUFFIX))
        line.addStretch(1)
        grid.addLayout(line, grid.rowCount(), 0, 1, 2)

    def _reminders(self) -> None:
        _box, grid = self._section("reminders")
        self.reminders = self._switch(strings.SETTINGS_REMINDERS, "reminders_enabled")
        self._span(grid, self.reminders)

    def _handoff(self) -> None:
        _box, grid = self._section("handoff")
        self.claude_url = QLineEdit()
        self.claude_url.setAccessibleName(strings.SETTINGS_CLAUDE_LINK)
        self.claude_url.editingFinished.connect(self._commit_url)
        self._row(grid, strings.SETTINGS_CLAUDE_LINK, self.claude_url)
        self.claude_url_error = muted("", "error")
        self.claude_url_error.hide()
        grid.addWidget(self.claude_url_error, grid.rowCount(), 1)
        self.include_notes = self._switch(strings.SETTINGS_INCLUDE_NOTES, "include_style_notes")
        self._span(grid, self.include_notes)
        self.style_notes = QPlainTextEdit()
        self.style_notes.setAccessibleName(strings.SETTINGS_STYLE_NOTES)
        self.style_notes.setPlaceholderText(strings.SETTINGS_STYLE_HINT)
        self.style_notes.setTabChangesFocus(True)
        self.style_notes.setMinimumHeight(self.style_notes.fontMetrics().lineSpacing() * NOTE_ROWS)
        self.style_notes.textChanged.connect(self._notes_changed)
        self._row(grid, strings.SETTINGS_STYLE_NOTES, self.style_notes)
        self.max_words = self._spin(200, 5000, "max_answer_words", 100, strings.SETTINGS_WORDS)
        self._row(grid, strings.SETTINGS_MAX_ANSWERS, self.max_words)

    def _writing(self) -> None:
        _box, grid = self._section("writing")
        self.length = self._combo(LENGTHS, strings.LENGTH_LABELS, "default_length")
        self._row(grid, strings.SETTINGS_LENGTH, self.length)

    def _appearance(self) -> None:
        _box, grid = self._section("appearance")
        self.appearance = self._combo(APPEARANCES, strings.APPEARANCE_LABELS, "appearance")
        self._row(grid, strings.SETTINGS_APPEARANCE, self.appearance)
        self.reduce_motion = self._switch(strings.SETTINGS_REDUCE_MOTION, "reduce_motion")
        self._span(grid, self.reduce_motion)

    def _data(self) -> None:
        box, grid = self._section("data")
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(1))
        self.open_data_button = button(strings.SETTINGS_OPEN_DATA)
        self.open_logs_button = button(strings.SETTINGS_OPEN_LOGS)
        self.export_button = button(strings.SETTINGS_EXPORT)
        for b in (self.open_data_button, self.open_logs_button, self.export_button):
            line.addWidget(b)
        line.addStretch(1)
        grid.addLayout(line, grid.rowCount(), 0, 1, 2)
        self.data_status = muted("", "caption")
        self.data_status.setAccessibleName(strings.SETTINGS_SECTIONS["data"])
        box.addWidget(self.data_status)
        self.open_data_button.clicked.connect(self.tasks.open_data)
        self.open_logs_button.clicked.connect(self.tasks.open_logs)
        self.export_button.clicked.connect(self.tasks.export)
        self.data_status.hide()
        self.tasks.status.connect(self._show_status)
        self.tasks.busy.connect(lambda busy: self.export_button.setEnabled(not busy))

    def _show_status(self, text: str) -> None:
        self.data_status.setText(text)
        self.data_status.setVisible(bool(text))

    def _automation(self) -> None:
        _box, grid = self._section("automation")
        self.pause = self._switch(strings.SETTINGS_PAUSE_SWITCH, "pause_automation")
        self._span(grid, self.pause)

    def _about(self) -> None:
        _box, grid = self._section("about")
        line = QHBoxLayout()
        line.setSpacing(self.theme.space(3))
        self.version_label = QLabel(strings.SETTINGS_VERSION.format(version=__version__))
        line.addWidget(self.version_label)
        self.checks_button = button(strings.SETTINGS_RUN_CHECKS)
        self.checks_button.clicked.connect(self.tasks.run_checks)
        line.addWidget(self.checks_button)
        line.addStretch(1)
        grid.addLayout(line, grid.rowCount(), 0, 1, 2)

    # State

    @property
    def checks_dialog(self) -> ReportDialog | None:
        return self.tasks.checks_dialog

    def section_titles(self) -> list[str]:
        return list(self._titles)

    def set_notice(self, text: str | None) -> None:
        """A message above the panels, such as "settings.json could not be read" (None hides)."""
        if text:
            self.load_error.setText(text)
        self._load_banner.setVisible(bool(text))

    def set_settings(self, s: Settings) -> None:
        """Show `s` in every control without emitting `changed`."""
        self._settings = s
        self._syncing = True
        try:
            for combo, value in (
                (self.focus_day, s.focus_day),
                (self.pick_day, s.pick_day),
                (self.prompt_day, s.prompt_day),
            ):
                combo.setCurrentIndex(value)
            self.focus_time.setTime(_qtime(s.focus_time))
            self.pick_time.setTime(_qtime(s.pick_time))
            self.prompt_time.setTime(_qtime(s.prompt_time))
            self.pick_enabled.setChecked(s.pick_enabled)
            self.interests.set_items(s.interests)
            self.region.setText(s.region)
            self.per_login.setValue(s.questions_per_login)
            self.dismiss_pause.setValue(s.dismiss_pause_minutes)
            self.carry_weeks.setValue(s.carry_over_weeks)
            self.reminders.setChecked(s.reminders_enabled)
            self.claude_url.setText(s.claude_url)
            self.claude_url_error.hide()
            self.include_notes.setChecked(s.include_style_notes)
            if self.style_notes.toPlainText() != s.style_notes:
                self.style_notes.setPlainText(s.style_notes)
            self.max_words.setValue(s.max_answer_words)
            self.length.setCurrentIndex(self.length.findData(s.default_length))
            self.appearance.setCurrentIndex(self.appearance.findData(s.appearance))
            self.reduce_motion.setChecked(s.reduce_motion)
            self.pause.setChecked(s.pause_automation)
        finally:
            self._syncing = False
        self._notes_timer.stop()
        self._sync_pick()

    def _sync_pick(self) -> None:
        on = self.pick_enabled.isChecked()
        self.pick_day.setEnabled(on)
        self.pick_time.setEnabled(on)

    def _commit(self, **changes: Any) -> bool:
        if self._syncing:
            return False
        try:
            new = Settings.model_validate({**self._settings.model_dump(), **changes})
        except ValidationError:
            return False
        self._sync_pick()
        if new != self._settings:
            self._settings = new
            self.changed.emit(new)
        return True

    def _commit_url(self) -> None:
        text = self.claude_url.text().strip()
        problem = None
        if not text:
            problem = strings.SETTINGS_URL_EMPTY
        elif not text.startswith("https://"):
            problem = strings.SETTINGS_URL_HTTPS
        elif not self._commit(claude_url=text):
            problem = strings.SETTINGS_URL_NO_SITE
        self.claude_url_error.setText(problem or "")
        self.claude_url_error.setVisible(problem is not None)
        if problem is None:
            self.claude_url.setText(text)

    def _notes_changed(self) -> None:
        if not self._syncing:
            self._notes_timer.start()

    def flush(self) -> None:
        """Save style notes typed in the last moment (also on leaving the screen and quitting)."""
        self._notes_timer.stop()
        self._commit(style_notes=self.style_notes.toPlainText())

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 (Qt override)
        self.flush()
        super().hideEvent(event)
