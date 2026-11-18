"""Manual mode in the UI (SPEC 5): the New blog form, its scope session and the hand-off.

Start questions saves the form, creates the scope questions and opens the popup, which
takes focus (the owner started it). Every answer is saved at once; Later closes the popup
and the banner and tray offer Resume. After the last question the `manual` hand-off is
prepared and its dialog opens.
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Question
from tea.domain import manual
from tea.domain import questions as qs
from tea.handoff import packets
from tea.logging_setup import log_event
from tea.settings import Settings
from tea.ui import strings
from tea.ui.handoff_flow import HandoffFlow
from tea.ui.screens.new_blog import NewBlogScreen
from tea.ui.theme import Theme
from tea.ui.widgets.dropzone import Dropzone
from tea.ui.widgets.question_popup import DONE, QuestionPopup


class NewBlogFlow(QObject):
    changed = Signal()  # a session started, paused or finished (tray and banners refresh)
    needs_window = Signal()  # a message on the screen the owner may not be looking at

    def __init__(
        self,
        theme: Theme,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        screen: NewBlogScreen,
        handoffs: HandoffFlow,
        *,
        reduce_motion: bool | None = None,
    ) -> None:
        super().__init__()
        self.theme, self.repos, self.clock, self._settings = theme, repos, clock, settings
        self.screen = screen
        self.handoffs = handoffs
        self._reduce_motion = reduce_motion
        self.popup: QuestionPopup | None = None
        self.blog_id: int | None = None  # the blog whose scope session is open
        self._asked: set[int] = set()  # questions already counted as asked
        screen.start_requested.connect(self.start)
        screen.cancel_requested.connect(self.cancel)
        screen.resume_requested.connect(self.resume)
        screen.open_handoff_requested.connect(self.open_waiting)
        self._new_form()
        self.refresh()

    # The form

    def _new_form(self, *, keep_values: bool = False) -> None:
        blog = manual.form_blog(self.repos)
        self.screen.set_dropzone(Dropzone(self.theme, self.repos, blog.id))
        if not keep_values:
            self.screen.reset(self._settings().default_length)

    def _form_id(self) -> int | None:
        dz = self.screen.dropzone
        return dz.blog_id if dz is not None else None

    def refresh(self) -> None:
        self.screen.set_banners(self.in_progress_topic(), bool(manual.waiting(self.repos)))

    def in_progress_topic(self) -> str | None:
        blogs = manual.in_progress(self.repos)
        return blogs[-1].topic if blogs else None

    def cancel(self) -> None:
        dz, form = self.screen.dropzone, self._form_id()
        if dz is not None and dz.copying():
            return  # a copy finishing later would record a file for a deleted blog
        if form is not None:
            manual.discard_form(self.repos, form)
        log_event("new_blog_cancelled")
        self._new_form()

    def start(self) -> None:
        if self.popup is not None:  # one session at a time; the filled form stays
            self.screen.show_error(strings.FINISH_OPEN_QUESTIONS)
            self._raise()
            return
        dz, form = self.screen.dropzone, self._form_id()
        if form is None or (dz is not None and dz.copying()):
            return
        try:
            chosen = manual.start(self.repos, form, **self.screen.values())  # type: ignore[arg-type]
        except (ValueError, LookupError) as exc:
            log_event("new_blog_start_failed", logging.WARNING, error=type(exc).__name__)
            self._new_form(keep_values=True)  # the row was gone: a fresh one, same answers
            self.screen.show_error(strings.START_FAILED)
            return
        log_event("new_blog_started", blog_id=form, count=len(chosen))
        self._new_form()
        self._open(form)

    # The scope session

    def resume(self, blog_id: int | None = None) -> None:
        if self.popup is not None:
            self._raise()
            return
        if blog_id is None:
            blogs = manual.in_progress(self.repos)
            if not blogs:
                return
            blog_id = blogs[-1].id
        self._open(blog_id)

    def _open(self, blog_id: int) -> None:
        r = manual.resume(self.repos, blog_id)
        if r.start >= len(r.questions):
            self._finish(blog_id)  # everything answered: the prompt was never prepared
            return
        reduce = self._reduce_motion
        if reduce is None:
            reduce = self._settings().reduce_motion
        popup = QuestionPopup(
            self.theme, r.questions, self._record, login=False,
            reduce_motion=reduce, start=r.start, answered=r.answered,
        )  # fmt: skip
        popup.finished.connect(self._on_finished)
        self.popup, self.blog_id = popup, blog_id
        self._asked = set(r.answered)
        self.screen.show_error("")
        log_event("scope_questions_shown", blog_id=blog_id, count=len(r.questions))
        popup.show()
        self.refresh()
        self.changed.emit()

    def _raise(self) -> None:
        if self.popup is not None:
            self.popup.show()
            self.popup.raise_()
            self.popup.activateWindow()

    def _record(self, q: Question, text: str, skipped: bool) -> None:
        qs.record_answer(
            self.repos, q, manual.CONTEXT, text, skipped=skipped,
            blog_id=self.blog_id, count_ask=q.id not in self._asked,
        )  # fmt: skip
        self._asked.add(q.id)

    def _on_finished(self, reason: str) -> None:
        popup, self.popup = self.popup, None
        blog_id, self.blog_id = self.blog_id, None
        log_event("scope_questions_closed", reason=reason)
        if popup is not None:
            popup.deleteLater()
        if reason == DONE and blog_id is not None:
            self._finish(blog_id)
            return
        self.refresh()
        self.changed.emit()

    def _finish(self, blog_id: int) -> None:
        try:
            h = manual.finish(self.repos, self._settings(), self.clock, blog_id)
        except packets.PacketError as exc:
            log_event("manual_packet_failed", logging.WARNING, error=type(exc).__name__)
            self.screen.show_error(strings.PACKET_FAILED)
            self.refresh()
            self.changed.emit()
            self.needs_window.emit()  # the session may have been resumed from the tray
            return
        log_event("manual_prompt_ready", handoff=h.id)
        self.refresh()
        self.changed.emit()
        self.handoffs.changed.emit()
        self.handoffs.open(h.id)

    def open_waiting(self) -> None:
        waiting = manual.waiting(self.repos)
        if waiting:
            self.handoffs.open(waiting[-1].id)
