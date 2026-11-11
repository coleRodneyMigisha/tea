"""Notifications: copy, replace-by-id, coalescing within 5 minutes, tray fallback, actions."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtWidgets import QApplication
from sched_world import FakeBackend

from tea.clock import FakeClock
from tea.notify import Notifier, gvariant_string, parse_notify_reply
from tea.ui import strings

TZ = ZoneInfo("Africa/Kampala")
WEEK = date(2026, 11, 9)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 13, 18, 0, tzinfo=TZ))


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def notifier(qapp: QApplication, clock: FakeClock, backend: FakeBackend) -> Notifier:
    return Notifier(clock, backend)


def test_prompt_ready_copy(notifier: Notifier, backend: FakeBackend) -> None:
    notifier.prompts_ready([(1, "weekly", "Small teams")])
    [s] = backend.sent
    assert (s.title, s.body, s.action) == (
        strings.NOTIFY_PROMPT_READY,
        "Small teams",
        strings.NOTIFY_OPEN_HANDOFF,
    )


def test_improve_copy(notifier: Notifier, backend: FakeBackend) -> None:
    notifier.prompts_ready([(2, "improve", "Old post")])
    assert backend.sent[0].title == strings.NOTIFY_IMPROVE_READY


def test_untitled_pick_prompt_says_claude_picks(notifier: Notifier, backend: FakeBackend) -> None:
    notifier.prompts_ready([(3, "weekly_pick", "")])
    assert backend.sent[0].body == strings.CHIP_PICK


def test_two_in_one_pass_send_one(notifier: Notifier, backend: FakeBackend) -> None:
    notifier.prompts_ready([(1, "weekly", "A"), (2, "improve", "B")])
    [s] = backend.sent
    assert s.title == strings.NOTIFY_TWO_READY and "A" in s.body and "B" in s.body


def test_second_within_five_minutes_replaces(
    notifier: Notifier, backend: FakeBackend, clock: FakeClock
) -> None:
    notifier.prompts_ready([(1, "weekly", "A")])
    clock.advance(minutes=4, seconds=59)
    notifier.prompts_ready([(2, "improve", "B")])
    first, second = backend.sent
    assert second.title == strings.NOTIFY_TWO_READY and second.replaces_id == first.id


def test_second_after_five_minutes_is_separate(
    notifier: Notifier, backend: FakeBackend, clock: FakeClock
) -> None:
    notifier.prompts_ready([(1, "weekly", "A")])
    clock.advance(minutes=5, seconds=1)
    notifier.prompts_ready([(2, "improve", "B")])
    first, second = backend.sent
    assert second.title == strings.NOTIFY_IMPROVE_READY and second.replaces_id == 0


def test_reminder_replaces_the_handoff_notification(
    notifier: Notifier, backend: FakeBackend, clock: FakeClock
) -> None:
    notifier.prompts_ready([(1, "weekly", "A")])
    clock.advance(hours=3)
    notifier.reminder(1, "A")
    clock.advance(hours=3)
    notifier.reminder(1, "A")
    first, r1, r2 = backend.sent
    assert r1.title == strings.NOTIFY_REMINDER and r1.body == "A"
    assert r1.replaces_id == first.id and r2.replaces_id == first.id


def test_other_notification_copy(notifier: Notifier, backend: FakeBackend) -> None:
    notifier.focus_prompt(WEEK)
    notifier.pick_mode(WEEK)
    notifier.no_focus(WEEK)
    got = [(s.title, s.body, s.action) for s in backend.sent]
    assert got == [
        (strings.NOTIFY_FOCUS, strings.NOTIFY_FOCUS_BODY, strings.NOTIFY_SET_FOCUS),
        (strings.NOTIFY_PICK, strings.NOTIFY_PICK_BODY, strings.NOTIFY_SET_OWN_TOPIC),
        (strings.NOTIFY_NO_FOCUS, strings.NOTIFY_NO_FOCUS_BODY, strings.NOTIFY_SET_FOCUS),
    ]


def test_action_maps_server_id_to_target(notifier: Notifier, backend: FakeBackend) -> None:
    got: list[str] = []
    notifier.action_invoked.connect(got.append)
    notifier.prompts_ready([(7, "weekly", "A")])
    notifier.focus_prompt(WEEK)
    notifier.on_server_action(backend.sent[0].id, "default")
    notifier.on_server_action(backend.sent[1].id, "default")
    notifier.on_server_action(9999, "default")  # someone else's notification
    assert got == ["handoff:7", f"focus:{WEEK.isoformat()}"]


def test_fallback_to_tray_when_dbus_fails(qapp: QApplication, clock: FakeClock) -> None:
    shown: list[tuple[str, str]] = []
    n = Notifier(clock, FakeBackend(fail=True), fallback=lambda t, b: shown.append((t, b)))
    got: list[str] = []
    n.action_invoked.connect(got.append)
    n.prompts_ready([(4, "weekly", "A")])
    assert shown == [(strings.NOTIFY_PROMPT_READY, "A")]
    n.on_fallback_clicked()
    assert got == ["handoff:4"]


def test_fallback_without_backend(qapp: QApplication, clock: FakeClock) -> None:
    shown: list[tuple[str, str]] = []
    n = Notifier(clock, None, fallback=lambda t, b: shown.append((t, b)))
    n.no_focus(WEEK)
    assert shown == [(strings.NOTIFY_NO_FOCUS, strings.NOTIFY_NO_FOCUS_BODY)]


def test_no_backend_no_tray_does_not_raise(qapp: QApplication, clock: FakeClock) -> None:
    Notifier(clock, None).prompts_ready([(1, "weekly", "A")])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain", '"plain"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ("two\nlines", '"two\\nlines"'),
        ("tab\tbell\a", '"tab\\tbell\\u0007"'),
        ("café ☕", '"café ☕"'),
    ],
)
def test_gvariant_string(text: str, expected: str) -> None:
    assert gvariant_string(text) == expected


@pytest.mark.parametrize(
    ("out", "expected"),
    [("(uint32 23,)\n", 23), ("", None), ("garbage", None), ("(uint32 0,)", None)],
)
def test_parse_notify_reply(out: str, expected: int | None) -> None:
    assert parse_notify_reply(out) == expected
