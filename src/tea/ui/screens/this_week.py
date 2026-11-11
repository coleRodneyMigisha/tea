"""This week screen. M3: empty state only; the steep ring arrives in M5."""

from tea.ui import strings
from tea.ui.screens import Page, muted, panel
from tea.ui.theme import Theme


class ThisWeekScreen(Page):
    def __init__(self, theme: Theme) -> None:
        super().__init__(theme, strings.TITLE_WEEK)
        frame, layout = panel(theme)
        layout.addWidget(muted(strings.FOCUS_LABEL, "caption"))
        self.focus_text = muted(strings.EMPTY_FOCUS, "display")
        self.focus_text.setProperty("muted", True)
        layout.addWidget(self.focus_text)
        self.body.addWidget(frame)
