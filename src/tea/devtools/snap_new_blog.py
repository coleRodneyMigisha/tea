"""Snapshot states for the New blog screen (UI_DESIGN 3.2), drawn in the main window.

Qt is imported inside the builders, so `snap` can set QT_QPA_PLATFORM before Qt loads.
"""

from collections.abc import Callable
from typing import Any

from tea.clock import Clock
from tea.db.repos import Repos
from tea.devtools import snap_drafts
from tea.devtools.snap_dropzone import FILES, _stored
from tea.settings import Settings

TOPIC = "How to read an academic paper in 20 minutes"
Setup = Callable[[Repos, Clock], None]
Fill = Callable[[Any], None]


def _started(repos: Repos, clock: Clock, *, answered: int, finish: bool = False) -> None:
    from tea.domain import manual
    from tea.domain import questions as qs

    blog = manual.form_blog(repos)
    manual.start(
        repos, blog.id, topic="Green tea at work", scope_notes="", audience="",
        allowed_sources=["own_documents"], length="standard",
    )  # fmt: skip
    for q in manual.resume(repos, blog.id).questions[:answered]:
        qs.record_answer(repos, q, manual.CONTEXT, "A short answer.", blog_id=blog.id)
    if finish:
        manual.finish(repos, Settings(), clock, blog.id)


def _in_progress(repos: Repos, clock: Clock) -> None:
    _started(repos, clock, answered=3)


def _waiting(repos: Repos, clock: Clock) -> None:
    _started(repos, clock, answered=9, finish=True)


def _typed(screen: Any) -> None:
    screen.topic_edit.setText(TOPIC)
    screen.cover_edit.setPlainText(
        "A method for a first read: title, abstract, figures, then conclusions."
    )
    screen.audience_edit.setText("Graduate students")
    screen.source_boxes["academic"].setChecked(True)
    screen.length_buttons["short"].setChecked(True)


def _with_files(screen: Any) -> None:
    import shutil

    from tea.domain import attachments

    dz = screen.dropzone
    shutil.rmtree(attachments.blog_dir(dz.blog_id), ignore_errors=True)
    attachments.notice_shown(dz.repos)
    for name, size in FILES[:2]:
        _stored(dz.repos, dz.blog_id, name, size)
    dz.refresh()
    dz.notice.setVisible(True)  # the first-file notice, as after the first add
    _typed(screen)


def _build(setup: Setup | None = None, fill: Fill | None = None) -> Callable[..., Any]:
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.ui.handoff_flow import HandoffFlow
        from tea.ui.main_window import MainWindow
        from tea.ui.new_blog_flow import NewBlogFlow

        if setup is not None:
            setup(repos, clock)
        window = MainWindow(
            theme, Settings(), save_settings=lambda _s: None, remember_geometry=False
        )
        handoffs = HandoffFlow(theme, repos, clock, Settings, debug=False, parent=window)
        flow = NewBlogFlow(
            theme, repos, clock, Settings, window.new_blog_screen, handoffs, reduce_motion=True
        )
        snap_drafts.KEEP.append((handoffs, flow))  # alive until the snapshot is taken
        if fill is not None:
            fill(window.new_blog_screen)
        window.show_screen("new_blog")
        return window

    return build


def register_all(register: Callable[[str, str, Any], None], state: Callable[..., Any]) -> None:
    name = "new_blog"
    register(name, "empty", state(name, build=_build()))  # replaces the M3 title-only state
    register(name, "typed", state(name, build=_build(fill=_typed)))
    register(name, "files", state(name, build=_build(fill=_with_files)))
    register(name, "in_progress", state(name, build=_build(_in_progress)))
    register(name, "waiting", state(name, build=_build(_waiting)))
