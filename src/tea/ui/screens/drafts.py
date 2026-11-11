"""Drafts screen. M3: empty state only; the list and draft view arrive in M7."""

from tea.ui import strings
from tea.ui.screens import Page, muted, panel
from tea.ui.theme import Theme


class DraftsScreen(Page):
    def __init__(self, theme: Theme) -> None:
        super().__init__(theme, strings.TITLE_DRAFTS)
        frame, layout = panel(theme)
        layout.addWidget(muted(strings.EMPTY_DRAFTS))
        self.body.addWidget(frame)
