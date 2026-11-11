"""handoff/provider: ManualProvider satisfies the Provider protocol and hands the packet on."""

from tea.handoff.packets import Packet
from tea.handoff.provider import ManualProvider, Provider


def test_manual_provider_passes_packet_to_show() -> None:
    seen: list[Packet] = []
    provider: Provider = ManualProvider(seen.append)
    packet = Packet("text", 1, "weekly", {"packet_draft": 1})
    provider.deliver(packet)
    assert seen == [packet]


def test_manual_provider_without_show_does_nothing() -> None:
    ManualProvider().deliver(Packet("text", 1, "weekly", {}))
