"""Optional trigger: the screen was unlocked (GNOME `org.gnome.ScreenSaver` `ActiveChanged`).

Listens on the session bus only while the owner has the setting on. Nothing is sent and nothing
leaves the machine; a missing service just means the signal never arrives.
"""

import logging

from PySide6.QtCore import SLOT, QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection

from tea.logging_setup import log_event

SERVICE = "org.gnome.ScreenSaver"
PATH = "/org/gnome/ScreenSaver"
INTERFACE = "org.gnome.ScreenSaver"


class UnlockWatcher(QObject):
    unlocked = Signal()

    def __init__(self, *, listen: bool = True, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listen = listen
        self.enabled = False

    def set_enabled(self, on: bool) -> None:
        if on == self.enabled:
            return
        self.enabled = on
        if not self._listen:
            return
        bus = QDBusConnection.sessionBus()
        # The stubs ask for bytes, but PySide6 accepts only the str that SLOT() returns.
        args = (SERVICE, PATH, INTERFACE, "ActiveChanged", self, SLOT("on_active_changed(bool)"))
        if on:
            if not bus.connect(*args):  # type: ignore[call-overload]
                log_event("unlock_signal_unavailable", logging.WARNING)
        else:
            bus.disconnect(*args)  # type: ignore[call-overload]

    @Slot(bool)
    def on_active_changed(self, active: bool) -> None:
        """`active` is True when the screen locks, False when it unlocks."""
        if not active:
            self.unlocked.emit()
