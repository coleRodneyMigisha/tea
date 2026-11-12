"""Snapshot states for the hand-off dialog and the Drafts screen (M7).

Every state starts on Friday 13 November 2026 at 18:05, with this week's prompt ready.
Qt is imported inside the builders, so `snap` can set QT_QPA_PLATFORM first.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from tea.clock import Clock, FakeClock
from tea.db.repos import Repos
from tea.settings import Settings

WEEK = date(2026, 11, 9)
FOCUS = "Why small teams ship faster than big ones"
Build = Callable[[Any, Repos, Clock], Any]
KEEP: list[tuple[Any, Any]] = []


def _friday(clock: Clock) -> None:
    assert isinstance(clock, FakeClock)
    clock.set(datetime(2026, 11, 13, 18, 5, tzinfo=clock.tz()))


def _handoff(repos: Repos, clock: Clock, kind: str = "weekly", files: bool = False) -> int:
    from tea.domain import attachments, weekly

    _friday(clock)
    s = Settings()
    if kind == "weekly_pick":
        weekly.enter_pick_mode(repos, s, WEEK)
    else:
        weekly.save_focus(repos, s, clock, WEEK, FOCUS)
    if files:
        blog = weekly.week_blog(repos, WEEK)
        assert blog is not None
        folder = attachments.blog_dir(blog.id).parent / "snap-sources"
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("report-2025.pdf", "notes.docx"):
            path = folder / name
            path.write_bytes(b"sample")
            attachments.add(repos, blog.id, path)
    open_ = repos.handoffs.list(open_only=True, week_start=WEEK)
    if open_:
        return open_[-1].id
    return weekly.prepare_packet(repos, s, clock, kind, WEEK).id


def _dialog(
    kind: str = "weekly",
    *,
    copied: bool = False,
    opened: bool = False,
    files: bool = False,
    paste: str | None = None,
    reply: str | None = None,
) -> Build:
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.domain import drafts
        from tea.ui.widgets.handoff_dialog import HandoffDialog

        hid = _handoff(repos, clock, kind, files)
        if copied:
            drafts.copy_prompt(repos, hid)
        dialog = HandoffDialog(
            theme, repos, clock, Settings, hid, claude_opened=opened, pasted=paste or ""
        )
        if reply is not None:
            dialog.paste_box.setPlainText(reply)
            dialog.import_button.click()
        return dialog

    return build


def _sample(name: str) -> str:
    from tea.devtools import sample_replies

    return sample_replies.WELL_FORMED.get(name) or sample_replies.MALFORMED[name]


def _drafts(setup: Callable[[Repos, Clock], int | None], then: str = "") -> Build:
    """The main window on Drafts, with `setup` returning the blog to select (or None)."""

    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.ui.drafts_flow import DraftsFlow
        from tea.ui.handoff_flow import HandoffFlow
        from tea.ui.main_window import MainWindow

        blog_id = setup(repos, clock)
        window = MainWindow(
            theme, Settings(), save_settings=lambda _s: None, remember_geometry=False
        )
        handoffs = HandoffFlow(theme, repos, clock, Settings, debug=False, parent=window)
        flow = DraftsFlow(theme, repos, clock, Settings, window.drafts_screen, handoffs)
        KEEP.append((handoffs, flow))  # alive until the snapshot is taken
        window.show_screen("drafts")
        if blog_id is not None:
            flow.select_blog(blog_id)
        if then == "edit":
            flow.view.toggle_edit()
        return window

    return build


def _ready(copied: bool = False, versions: bool = False) -> Callable[[Repos, Clock], int | None]:
    def setup(repos: Repos, clock: Clock) -> int | None:
        from tea.devtools import sample_replies
        from tea.handoff.importer import import_reply

        hid = _handoff(repos, clock)
        result = import_reply(repos, hid, sample_replies.WEEKLY)
        if versions:
            import_reply(repos, hid, sample_replies.WEEKLY)
        if copied:
            repos.drafts.mark_copied(result.draft.id)
        return result.draft.blog_id

    return setup


def _waiting(repos: Repos, clock: Clock) -> int | None:
    _handoff(repos, clock)  # the only entry, so the list selects it
    return None


def register_all(register: Callable[[str, str, Any], None], state: Callable[..., Any]) -> None:
    d = "handoff_dialog"
    register(d, "fresh", state(d, build=_dialog()))
    register(d, "copied", state(d, build=_dialog(copied=True)))
    register(d, "opened", state(d, build=_dialog(copied=True, opened=True)))
    register(d, "files", state(d, build=_dialog(files=True)))
    register(
        d, "pasted", state(d, build=_dialog(copied=True, opened=True, paste=_sample("weekly")))
    )
    register(
        d, "summary", state(d, build=_dialog(copied=True, opened=True, reply=_sample("weekly")))
    )
    register(d, "truncated", state(d, build=_dialog(copied=True, reply=_sample("truncated"))))
    register(d, "no_verification", state(d, build=_dialog(reply=_sample("no_verification"))))
    register(d, "pick", state(d, build=_dialog("weekly_pick", reply=_sample("weekly_pick"))))
    no_topic = "<draft>\n# What the new phone repair rules mean\n\nText.\n</draft>"
    register(d, "pick_no_topic", state(d, build=_dialog("weekly_pick", reply=no_topic)))
    s = "drafts"
    register(s, "ready", state(s, build=_drafts(_ready(copied=True))))
    register(s, "drawer_open", state(s, build=_drafts(_ready())))
    register(s, "editing", state(s, build=_drafts(_ready(copied=True), "edit")))
    register(s, "versions", state(s, build=_drafts(_ready(copied=True, versions=True))))
    register(s, "waiting", state(s, build=_drafts(_waiting)))
