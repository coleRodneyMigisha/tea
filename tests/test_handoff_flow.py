"""HandoffFlow: one dialog per hand-off, state kept across closing (TESTING 4)."""

from collections.abc import Iterator

import pytest
from handoff_world import imported, weekly_handoff
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.handoff import packets
from tea.handoff.provider import ManualProvider
from tea.settings import Settings
from tea.ui.handoff_flow import HandoffFlow
from tea.ui.theme import Theme


@pytest.fixture
def flow(qapp: QApplication, repos: Repos, clock: FakeClock) -> Iterator[HandoffFlow]:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    f = HandoffFlow(theme, repos, clock, Settings, debug=False)
    yield f
    f.close_all()
    qapp.processEvents()


def test_open_twice_gives_one_dialog(flow: HandoffFlow, repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    first = flow.open(h.id)
    assert first is not None and first.isVisible()
    assert flow.open(h.id) is first
    assert flow.is_open()


def test_closing_and_reopening_keeps_pasted_text(
    qtbot: QtBot, flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    d = flow.open(h.id)
    assert d is not None
    d.paste_box.setPlainText("first half of the reply")
    d.claude_opened.emit()
    d.close()
    qtbot.waitUntil(lambda: h.id not in flow.dialogs)
    assert not flow.is_open()
    again = flow.open(h.id)
    assert again is not None and again is not d
    assert again.paste_box.toPlainText() == "first half of the reply"
    assert again.step_done(2)
    # The hand-off is still waiting (it stays in Drafts under Waiting).
    assert [x.id for x in repos.handoffs.list(open_only=True)] == [h.id]


def test_superseded_handoff_opens_its_replacement(
    flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    first = flow.regenerate(h.blog_id)
    assert first is not None
    second = flow.regenerate(h.blog_id)
    assert second is not None and second.handoff_id != first.handoff_id
    reopened = flow.open(first.handoff_id)
    assert reopened is not None and reopened.handoff_id == second.handoff_id


def test_regenerate_emits_created_with_the_superseded_one(
    flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    seen: list[tuple[int, int]] = []
    flow.created.connect(lambda new, old: seen.append((new, old)))
    one = flow.regenerate(h.blog_id)
    two = flow.regenerate(h.blog_id)
    assert one is not None and two is not None
    assert seen == [(one.handoff_id, 0), (two.handoff_id, one.handoff_id)]
    assert one.handoff_id not in flow.dialogs or not flow.dialogs[one.handoff_id].isVisible()
    assert two.title_label.text() == "Write this week's draft"


def test_second_pass_opens_check_this_draft(
    flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = imported(repos, clock)
    assert h.blog_id is not None
    d = flow.second_pass(h.blog_id)
    assert d is not None and d.title_label.text() == "Check this draft"


def test_manual_provider_deliver_opens_the_dialog(
    flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    provider = ManualProvider(flow.open_for_packet)
    packet = packets.build("weekly", repos, Settings(), clock, blog_id=h.blog_id)
    provider.deliver(packet)
    assert h.id in flow.dialogs and flow.dialogs[h.id].isVisible()


def test_open_latest(flow: HandoffFlow, repos: Repos, clock: FakeClock) -> None:
    assert flow.open_latest() is None
    h = weekly_handoff(repos, clock)
    d = flow.open_latest()
    assert d is not None and d.handoff_id == h.id


def test_import_and_open_draft_signals(
    qtbot: QtBot, flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    d = flow.open(h.id)
    assert d is not None
    got: list[int] = []
    wanted: list[int] = []
    flow.imported.connect(got.append)
    flow.open_draft.connect(wanted.append)
    d.paste_box.setPlainText(sample_replies.WEEKLY)
    d.import_button.click()
    d.open_draft_button.click()
    assert got == [h.blog_id] and wanted == [h.blog_id]
    qtbot.waitUntil(lambda: not flow.is_open())


def test_audit_recovery_switches_dialogs(
    qtbot: QtBot, flow: HandoffFlow, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    d = flow.open(h.id)
    assert d is not None
    d.paste_box.setPlainText(sample_replies.MALFORMED["no_verification"])
    d.import_button.click()
    d.audit_button.click()
    audit = repos.handoffs.list(kind="audit")[-1]
    qtbot.waitUntil(lambda: h.id not in flow.dialogs)
    assert audit.id in flow.dialogs and flow.dialogs[audit.id].isVisible()
    assert flow.dialogs[audit.id].step_done(1)


def test_missing_handoff_opens_nothing(flow: HandoffFlow) -> None:
    assert flow.open(12345) is None


def test_debug_follows_tea_debug(
    qapp: QApplication, repos: Repos, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    theme = Theme(qapp, appearance="light", scale=1.0)
    monkeypatch.setenv("TEA_DEBUG", "1")
    flow = HandoffFlow(theme, repos, clock, Settings)
    d = flow.open(weekly_handoff(repos, clock).id)
    assert flow.debug and d is not None and d.sample_button is not None
    flow.close_all()
    monkeypatch.delenv("TEA_DEBUG")
    assert not HandoffFlow(theme, repos, clock, Settings).debug
