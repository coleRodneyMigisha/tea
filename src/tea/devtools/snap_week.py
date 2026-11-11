"""Snapshot states for the This week screen (every ring state) and the focus dialog.

Each state moves the FakeClock to its moment in the week of Monday 9 November 2026, seeds
what that state needs, and shows the main window on This week. Qt loads inside builders.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from tea.clock import Clock, FakeClock
from tea.db.repos import Repos
from tea.settings import Settings

WEEK = date(2026, 11, 9)
FOCUS = "Why small teams ship faster than big ones"
Setup = Callable[[Repos, Clock, Settings], None]


def _at(clock: Clock, day: int, hour: int, minute: int = 0) -> None:
    assert isinstance(clock, FakeClock)
    when = datetime.combine(WEEK + timedelta(days=day), datetime.min.time(), clock.tz())
    clock.set(when.replace(hour=hour, minute=minute))


def _focus(repos: Repos, clock: Clock, settings: Settings) -> None:
    from tea.domain import weekly

    weekly.save_focus(repos, settings, clock, WEEK, FOCUS)


def _pick(repos: Repos, clock: Clock, settings: Settings) -> None:
    from tea.domain import weekly

    weekly.enter_pick_mode(repos, settings, WEEK)


def _prompt(copied: bool = False, imported: bool = False) -> Setup:
    def setup(repos: Repos, clock: Clock, settings: Settings) -> None:
        from tea.devtools import sample_replies
        from tea.domain import weekly
        from tea.handoff.importer import import_reply

        now = clock.now()
        _at(clock, 0, 9, 5)
        _focus(repos, clock, settings)
        assert isinstance(clock, FakeClock)
        clock.set(now)
        h = weekly.prepare_packet(repos, settings, clock, "weekly", WEEK)
        if copied:
            repos.handoffs.mark_copied(h.id)
        if imported:
            import_reply(repos, h.id, sample_replies.WEEKLY)

    return setup


def _week(
    day: int, hour: int, minute: int = 0, setup: Setup | None = None, **settings: Any
) -> Callable[[Any, Repos, Clock], Any]:
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.domain import questions as qs
        from tea.ui.main_window import MainWindow
        from tea.ui.week_state import week_view

        s = Settings.model_validate(settings)
        qs.seed_bank(repos)
        _at(clock, day, hour, minute)
        if setup is not None:
            setup(repos, clock, s)
        window = MainWindow(theme, s, save_settings=lambda _s: None, remember_geometry=False)
        window.week_screen.ring.reduce_motion = True
        window.week_screen.set_view(week_view(repos, s, clock.now()))
        window.show_screen("this_week")
        return window

    return build


def _dialog(text: str = "", carried: bool = False) -> Callable[[Any, Repos, Clock], Any]:
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.ui.widgets.focus_dialog import FocusDialog

        dialog = FocusDialog(theme, current=text, carried=carried)
        return dialog

    return build


def _focused_set_focus(theme: Any, repos: Repos, clock: Clock) -> Any:
    window = _week(2, 10)(theme, repos, clock)
    window.activateWindow()
    window.week_screen.action_button.setFocus()
    return window


def register_all(register: Callable[[str, str, Any], None], state: Callable[..., Any]) -> None:
    week = "this_week"
    for name, build in {
        "empty": _week(2, 10),
        "no_focus": _week(2, 10),
        "no_focus_thursday": _week(3, 7, 30),
        "steeping_start": _week(0, 0, 0, _focus),
        "steeping": _week(2, 10, 30, _focus),
        "steeping_late": _week(4, 16, 50, _focus),
        "pick": _week(3, 11, 0, _pick),
        "prompt_ready": _week(4, 18, 5, _prompt()),
        "prompt_copied": _week(4, 19, 0, _prompt(copied=True)),
        "ready": _week(5, 10, 0, _prompt(imported=True)),
        "paused": _week(2, 10, 0, None, pause_automation=True),
    }.items():
        register(week, name, state(week, build=build))
    dialog = "focus_dialog"
    register(dialog, "empty", state(dialog, build=_dialog()))
    register(dialog, "typed", state(dialog, build=_dialog(FOCUS)))
    register(dialog, "carried", state(dialog, build=_dialog(carried=True)))
    register(dialog, "typed_focused", state(dialog, build=_dialog(FOCUS), keep_focus=True))
    register(week, "no_focus_focused", state(week, build=_focused_set_focus, keep_focus=True))
