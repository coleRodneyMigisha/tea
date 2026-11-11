"""New blog screen. M3: title only; the form arrives in M6 and M8."""

from tea.ui import strings
from tea.ui.screens import Page
from tea.ui.theme import Theme


class NewBlogScreen(Page):
    def __init__(self, theme: Theme) -> None:
        super().__init__(theme, strings.TITLE_NEW)
