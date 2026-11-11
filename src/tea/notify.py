"""Desktop notifications with an action button, tray fallback and coalescing (ARCHITECTURE 8).

`Notifier` holds the rules: copy from UI_DESIGN 5, one notification id per hand-off so
reminders replace rather than stack, and "Two prompts are ready" when a second prompt is
ready within 5 minutes of the first. `DBusBackend` talks to org.freedesktop.Notifications.

PySide6 cannot marshal the `uint32` that `Notify` takes (see DEVIATIONS), so the call is
sent with `gdbus call` in a QProcess, which types the arguments from the server's
introspection. `ActionInvoked` comes back over QtDBus. The GUI thread never waits on it.
"""

import logging
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from PySide6.QtCore import SLOT, QObject, QProcess, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection

from tea.clock import Clock
from tea.domain.weekly import elapsed
from tea.logging_setup import log_event
from tea.ui import strings

COALESCE_WINDOW = timedelta(minutes=5)
SERVICE = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
INTERFACE = "org.freedesktop.Notifications"
SEND_TIMEOUT_MS = 5000

Done = Callable[[int | None], None]


class Backend(Protocol):
    def send(self, replaces_id: int, title: str, body: str, action: str, done: Done) -> None:
        """Show or replace a notification; call `done` with the server id, or None on failure."""
        ...


@dataclass
class _Slot:
    target: str  # what the action opens: "handoff:<id>" or "focus:<week>"
    server_id: int = 0
    pending: bool = False
    queued: tuple[str, str, str] | None = None


@dataclass
class _Group:
    """Prompts announced together (UI_DESIGN 5: "Two prompts are ready")."""

    at: datetime
    slot: str
    ids: list[int] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)


class Notifier(QObject):
    action_invoked = Signal(str)
    announced = Signal()  # a prompt is ready or still waiting: the tray shows attention

    def __init__(
        self,
        clock: Clock,
        backend: Backend | None,
        fallback: Callable[[str, str], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.clock = clock
        self.backend = backend
        self._fallback = fallback
        self._slots: dict[str, _Slot] = {}
        self._by_server: dict[int, str] = {}
        self._handoff_slot: dict[int, str] = {}
        self._group: _Group | None = None
        self._fallback_target: str | None = None

    # The notifications

    def prompts_ready(
        self, items: Sequence[tuple[int, str, str]], replacing: Mapping[int, int] | None = None
    ) -> None:
        """`items` are (handoff id, kind, title) prepared in one pass.

        `replacing` maps a new hand-off to the one it superseded (focus change, regenerate):
        the new one takes the old one's place, so it never counts as a second prompt.
        """
        now = self.clock.now()
        replacing = replacing or {}
        touched: dict[str, tuple[_Group, str, str, int]] = {}
        for hid, kind, title in items:
            title = title or strings.CHIP_PICK
            old = replacing.get(hid)
            g = self._group
            fresh = g is not None and elapsed(now, g.at) <= COALESCE_WINDOW
            if g is not None and fresh and old is not None and old in g.ids:
                i = g.ids.index(old)
                g.ids[i], g.titles[i] = hid, title
            elif g is not None and fresh and hid not in g.ids:
                g.ids.append(hid)
                g.titles.append(title)
            else:
                slot = self._handoff_slot.get(old, f"handoff:{hid}") if old else f"handoff:{hid}"
                g = self._group = _Group(now, slot, [hid], [title])
            self._handoff_slot[hid] = g.slot
            improve = kind == "improve"
            head = strings.NOTIFY_IMPROVE_READY if improve else strings.NOTIFY_PROMPT_READY
            touched[g.slot] = (g, head, title, hid)
        for slot, (g, head, title, hid) in touched.items():
            if len(g.ids) > 1:
                head, title, hid = strings.NOTIFY_TWO_READY, "\n".join(g.titles), g.ids[0]
            self._post(slot, f"handoff:{hid}", head, title, strings.NOTIFY_OPEN_HANDOFF)
        if touched:
            self.announced.emit()

    def reminders(self, items: Sequence[tuple[int, str]]) -> None:
        """Reminders from one pass: one notification, listing every waiting title."""
        if not items:
            return
        first = items[0][0]
        slot = self._handoff_slot.get(first, f"handoff:{first}")
        for hid, _ in items:
            self._handoff_slot.setdefault(hid, slot)
        body = "\n".join(t or strings.CHIP_PICK for _, t in items)
        self._post(slot, f"handoff:{first}", strings.NOTIFY_REMINDER, body,
                   strings.NOTIFY_OPEN_HANDOFF)  # fmt: skip
        self.announced.emit()

    def reminder(self, handoff_id: int, title: str) -> None:
        self.reminders([(handoff_id, title)])

    def focus_prompt(self, week: date) -> None:
        self._week_notice("focus", week, strings.NOTIFY_FOCUS, strings.NOTIFY_FOCUS_BODY,
                          strings.NOTIFY_SET_FOCUS)  # fmt: skip

    def pick_mode(self, week: date) -> None:
        self._week_notice("pick", week, strings.NOTIFY_PICK, strings.NOTIFY_PICK_BODY,
                          strings.NOTIFY_SET_OWN_TOPIC)  # fmt: skip

    def no_focus(self, week: date) -> None:
        self._week_notice("nofocus", week, strings.NOTIFY_NO_FOCUS, strings.NOTIFY_NO_FOCUS_BODY,
                          strings.NOTIFY_SET_FOCUS)  # fmt: skip

    def _week_notice(self, name: str, week: date, title: str, body: str, action: str) -> None:
        """Week notices all open the focus dialog for that week."""
        self._post(f"{name}:{week.isoformat()}", f"focus:{week.isoformat()}", title, body, action)

    # Actions

    @Slot(int, str)
    def on_server_action(self, server_id: int, action_key: str) -> None:
        key = self._by_server.get(int(server_id))
        if key is None:
            return  # another app's notification
        log_event("notification_action", kind=key.split(":", 1)[0])
        self.action_invoked.emit(self._slots[key].target)

    @Slot()
    def on_fallback_clicked(self) -> None:
        if self._fallback_target is not None:
            self.action_invoked.emit(self._fallback_target)

    # Sending

    def _post(self, key: str, target: str, title: str, body: str, action: str) -> None:
        slot = self._slots.setdefault(key, _Slot(target))
        slot.target = target
        if self.backend is None:
            self._show_fallback(title, body, target)
            return
        if slot.pending:  # the server has not told us the id yet; replace once it has
            slot.queued = (title, body, action)
            return
        slot.pending = True
        self.backend.send(
            slot.server_id, title, body, action,
            lambda nid: self._sent(key, nid, title, body),
        )  # fmt: skip

    def _sent(self, key: str, server_id: int | None, title: str, body: str) -> None:
        slot = self._slots[key]
        slot.pending = False
        if server_id is None:
            self._show_fallback(title, body, slot.target)
        else:
            if slot.server_id:
                self._by_server.pop(slot.server_id, None)
            slot.server_id = server_id
            self._by_server[server_id] = key
        if slot.queued is not None:
            queued, slot.queued = slot.queued, None
            self._post(key, slot.target, *queued)

    def _show_fallback(self, title: str, body: str, target: str) -> None:
        self._fallback_target = target
        if self._fallback is None:
            log_event("notification_dropped", logging.WARNING)
            return
        self._fallback(title, body)


# DBus


def gvariant_string(text: str) -> str:
    """`text` as a GVariant text-format string literal, for a `gdbus call` argument."""
    out = ['"']
    for ch in text:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


_REPLY = re.compile(r"^\(uint32 (\d+),\)\s*$")


def parse_notify_reply(stdout: str) -> int | None:
    match = _REPLY.match(stdout.strip())
    if match is None:
        return None
    value = int(match.group(1))
    return value or None


class DBusBackend(QObject):
    """org.freedesktop.Notifications on the session bus (GNOME Shell on Ubuntu)."""

    action = Signal(int, str)

    def __init__(self, gdbus: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._gdbus = gdbus
        # The stub asks for bytes, but PySide6 accepts only the str that SLOT() returns.
        self.listening = QDBusConnection.sessionBus().connect(  # type: ignore[call-overload]
            SERVICE, PATH, INTERFACE, "ActionInvoked", self, SLOT("_on_action(uint,QString)")
        )

    @classmethod
    def create(cls, parent: QObject | None = None) -> "DBusBackend | None":
        gdbus = shutil.which("gdbus")
        bus = QDBusConnection.sessionBus()
        if gdbus is None or not bus.isConnected():
            log_event("notifications_unavailable", logging.WARNING)
            return None
        return cls(gdbus, parent)

    def arguments(self, replaces_id: int, title: str, body: str, action: str) -> list[str]:
        label = gvariant_string(action)
        return [
            "call", "--session", "--dest", SERVICE, "--object-path", PATH,
            "--method", f"{INTERFACE}.Notify",
            gvariant_string("tea"), f"uint32 {replaces_id}", gvariant_string(""),
            gvariant_string(title), gvariant_string(body),
            # "default" is a click on the notification; "open" is the visible button.
            f'["default", {label}, "open", {label}]',
            '{"desktop-entry": <"tea">}',
            "int32 -1",
        ]  # fmt: skip

    def send(self, replaces_id: int, title: str, body: str, action: str, done: Done) -> None:
        proc = QProcess(self)
        timer = QTimer(proc)
        timer.setSingleShot(True)
        finished = False

        def finish(server_id: int | None) -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            timer.stop()
            if server_id is None:
                log_event("notification_failed", logging.WARNING)
            done(server_id)
            proc.deleteLater()

        def on_finished(code: int, _status: QProcess.ExitStatus) -> None:
            out = bytes(proc.readAllStandardOutput().data()).decode("utf-8", "replace")
            finish(parse_notify_reply(out) if code == 0 else None)

        proc.finished.connect(on_finished)
        proc.errorOccurred.connect(lambda _e: finish(None))

        def on_timeout() -> None:
            proc.kill()
            finish(None)

        timer.timeout.connect(on_timeout)
        timer.start(SEND_TIMEOUT_MS)
        proc.start(self._gdbus, self.arguments(replaces_id, title, body, action))

    @Slot("uint", "QString")
    def _on_action(self, server_id: int, action_key: str) -> None:
        self.action.emit(int(server_id), action_key)
