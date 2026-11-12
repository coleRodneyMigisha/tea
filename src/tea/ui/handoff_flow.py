"""Opens hand-off dialogs and remembers what the owner did in them (UI_DESIGN 3.5).

One dialog per hand-off. Closing a dialog drops the widget but keeps its pasted text and
whether Claude was opened, for as long as tea runs (owner approved, M7), so reopening it
from Drafts, the ring, the tray or a notification picks up where the owner left off.
"""

import logging
import os
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Handoff
from tea.domain import drafts
from tea.handoff import packets
from tea.handoff.packets import Packet
from tea.logging_setup import log_event
from tea.settings import Settings
from tea.ui.theme import Theme
from tea.ui.widgets.handoff_dialog import HandoffDialog

Starter = Callable[[Repos, Settings, Clock, int], tuple[Handoff, int | None]]


class HandoffFlow(QObject):
    imported = Signal(int)  # blog id
    open_draft = Signal(int)  # blog id
    created = Signal(int, int)  # new hand-off id, the one it superseded (0 for none)
    changed = Signal()  # a hand-off was copied, imported or replaced

    def __init__(
        self,
        theme: Theme,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        *,
        debug: bool | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__()
        self.theme, self.repos, self.clock, self._settings = theme, repos, clock, settings
        self.debug = os.environ.get("TEA_DEBUG") == "1" if debug is None else debug
        self.parent_widget = parent
        self.dialogs: dict[int, HandoffDialog] = {}
        self._pasted: dict[int, str] = {}
        self._opened: set[int] = set()

    # Opening

    def open(self, handoff_id: int) -> HandoffDialog | None:
        h = self.repos.handoffs.get(handoff_id)
        if h is None:
            log_event("handoff_missing", logging.WARNING, handoff=handoff_id)
            return None
        if h.status == "superseded" and h.blog_id is not None:
            newer = self.repos.handoffs.list(open_only=True, blog_id=h.blog_id)
            if newer:
                h = newer[-1]
        dialog = self.dialogs.get(h.id)
        if dialog is None:
            dialog = self._make(h.id)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def open_latest(self) -> HandoffDialog | None:
        waiting = self.repos.handoffs.list(open_only=True)
        return self.open(waiting[-1].id) if waiting else None

    def open_for_packet(self, packet: Packet) -> None:
        """`ManualProvider.deliver`: show the dialog of the hand-off holding this packet."""
        found = [
            h
            for h in self.repos.handoffs.list(open_only=True, blog_id=packet.blog_id)
            if h.kind == packet.kind
        ]
        if found:
            self.open(found[-1].id)

    def is_open(self) -> bool:
        return any(d.isVisible() for d in self.dialogs.values())

    def pasted(self, handoff_id: int) -> str:
        return self._pasted.get(handoff_id, "")

    def close_all(self) -> None:
        for dialog in list(self.dialogs.values()):
            dialog.close()

    # New hand-offs started by the owner

    def regenerate(self, blog_id: int) -> HandoffDialog | None:
        return self._start(drafts.regenerate, blog_id)

    def second_pass(self, blog_id: int) -> HandoffDialog | None:
        return self._start(drafts.second_pass, blog_id)

    def _start(self, make: Starter, blog_id: int) -> HandoffDialog | None:
        try:
            new, old = make(self.repos, self._settings(), self.clock, blog_id)
        except (packets.PacketError, LookupError) as exc:
            log_event("handoff_start_failed", logging.WARNING, error=type(exc).__name__)
            return None
        new_id = new.id
        if old is not None and old in self.dialogs:
            self.dialogs[old].close()
        self.created.emit(new_id, old or 0)
        self.changed.emit()
        return self.open(new_id)

    # Dialog plumbing

    def _make(self, handoff_id: int) -> HandoffDialog:
        dialog = HandoffDialog(
            self.theme, self.repos, self.clock, self._settings, handoff_id,
            pasted=self._pasted.get(handoff_id, ""),
            claude_opened=handoff_id in self._opened,
            debug=self.debug, parent=self.parent_widget,
        )  # fmt: skip
        dialog.pasted_changed.connect(lambda text: self._pasted.__setitem__(handoff_id, text))
        dialog.claude_opened.connect(lambda: self._opened.add(handoff_id))
        dialog.imported.connect(self._on_imported)
        dialog.open_draft_requested.connect(self.open_draft)
        dialog.switch_requested.connect(lambda new: self._switch(handoff_id, new))
        dialog.copy_button.clicked.connect(self.changed)
        dialog.finished.connect(lambda _r: self._closed(handoff_id))
        self.dialogs[handoff_id] = dialog
        log_event("handoff_dialog_shown", handoff=handoff_id)
        return dialog

    def _on_imported(self, blog_id: int) -> None:
        self.imported.emit(blog_id)
        self.changed.emit()

    def _switch(self, old: int, new: int) -> None:
        self.changed.emit()
        dialog = self.dialogs.get(old)
        replacement = self.open(new)
        if dialog is not None and replacement is not None and dialog is not replacement:
            replacement.move(dialog.pos())
            dialog.close()

    def _closed(self, handoff_id: int) -> None:
        dialog = self.dialogs.pop(handoff_id, None)
        if dialog is not None:
            dialog.deleteLater()
        self.changed.emit()
