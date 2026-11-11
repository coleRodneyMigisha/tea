"""Settings screen. M3: title only; the panels arrive in M10."""

from tea.ui import strings
from tea.ui.screens import Page
from tea.ui.theme import Theme


class SettingsScreen(Page):
    def __init__(self, theme: Theme) -> None:
        super().__init__(theme, strings.TITLE_SETTINGS)
