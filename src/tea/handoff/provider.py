"""Provider protocol and ManualProvider, the only provider in v1 (ARCHITECTURE 5).

Keep this interface so an automated provider could be added later. Do not implement one.
"""

from collections.abc import Callable
from typing import Protocol

from tea.handoff.packets import Packet


class Provider(Protocol):
    def deliver(self, packet: Packet) -> None:
        """Get the packet to Claude. The reply comes back through importer.import_reply."""
        ...


class ManualProvider:
    """The owner copies the prompt, pastes it into Claude and pastes the reply back.

    The hand-off dialog arrives in M7; until then `show` is whatever the caller passes.
    """

    def __init__(self, show: Callable[[Packet], None] | None = None) -> None:
        self._show = show

    def deliver(self, packet: Packet) -> None:
        if self._show is not None:
            self._show(packet)
