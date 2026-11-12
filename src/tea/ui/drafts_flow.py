"""Drafts controller: fills the Drafts screen and routes its actions (UI_DESIGN 3.3)."""

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from tea.clock import Clock
from tea.db.repos import Repos
from tea.settings import Settings
from tea.ui import drafts_state
from tea.ui.handoff_flow import HandoffFlow
from tea.ui.screens.drafts import DraftsScreen
from tea.ui.theme import Theme
from tea.ui.widgets.draft_view import DraftView


class DraftsFlow(QObject):
    changed = Signal()  # a draft's status, copy or edit changed (This week, tray refresh)

    def __init__(
        self,
        theme: Theme,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        screen: DraftsScreen,
        handoffs: HandoffFlow,
    ) -> None:
        super().__init__()
        self.repos, self.clock, self.screen, self.handoffs = repos, clock, screen, handoffs
        self.view = DraftView(theme, repos, clock, settings)
        screen.set_draft_view(self.view)
        screen.selected.connect(self._selected)
        screen.waiting.open_requested.connect(handoffs.open)
        self.view.regenerate_requested.connect(handoffs.regenerate)
        self.view.second_pass_requested.connect(handoffs.second_pass)
        self.view.changed.connect(self._view_changed)
        handoffs.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.screen.set_groups(drafts_state.groups(self.repos, self.clock.now()))

    def select_blog(self, blog_id: int) -> bool:
        self.refresh()
        return self.screen.select(drafts_state.BLOG, blog_id)

    def _selected(self, kind: str, entry_id: int) -> None:
        if kind == drafts_state.BLOG:
            self.view.load(entry_id)
            self.screen.show_draft()

    def _view_changed(self) -> None:
        self.refresh()
        self.changed.emit()
