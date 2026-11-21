"""Login questions (SPEC 6, ARCHITECTURE 4 `login_questions`).

At most one login session per app start, none during the pause after a dismissal, and a
Later or a 90-second timeout counts as dismissed. "Answer questions now" (tray or
`tea login-questions`) ignores both rules, takes focus and never times out.
"""

import random
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from tea.clock import Clock
from tea.db.repos import Repos
from tea.db.rows import Question
from tea.domain import questions as qs
from tea.domain.weeks import week_start
from tea.logging_setup import log_event
from tea.settings import Settings
from tea.ui.theme import Theme
from tea.ui.widgets.question_popup import DONE, LOGIN_TIMEOUT_MS, QuestionPopup

# The manual session still asks this many when the owner set questions per login to 0.
MANUAL_FALLBACK_COUNT = 3


class LoginFlow(QObject):
    # "Answer questions now" found nothing to ask; the app shows strings.NO_QUESTIONS_LEFT.
    nothing_to_ask = Signal()

    def __init__(
        self,
        theme: Theme,
        repos: Repos,
        clock: Clock,
        settings: Callable[[], Settings],
        *,
        rng: random.Random | None = None,
        timeout_ms: int = LOGIN_TIMEOUT_MS,
        reduce_motion: bool | None = None,
    ) -> None:
        super().__init__()
        self.theme = theme
        self.repos = repos
        self.clock = clock
        self._settings = settings
        self._rng = rng or random.Random()
        self._timeout_ms = timeout_ms
        self._reduce_motion = reduce_motion
        self._started = False
        self.popup: QuestionPopup | None = None
        self._asked: set[int] = set()  # question ids already counted in this sitting

    def on_app_start(self) -> bool:
        """Show the login session if the rules allow. Returns whether a popup opened."""
        if self._started:
            return False
        self._started = True
        if self.popup is not None:  # `tea login-questions` already opened the manual session
            return False
        settings = self._settings()
        now = self.clock.now()
        if settings.questions_per_login <= 0 or not qs.login_allowed(self.repos, now):
            log_event("login_questions_skipped")
            return False
        return self._open(settings.questions_per_login, login=True)

    def on_unlock(self) -> bool:
        """The screen unlocked (optional setting): a login session under the same rules."""
        settings = self._settings()
        if not settings.questions_on_unlock or settings.pause_automation or self.popup is not None:
            return False
        if settings.questions_per_login <= 0 or not qs.login_allowed(self.repos, self.clock.now()):
            log_event("login_questions_skipped", kind="unlock")
            return False
        return self._open(settings.questions_per_login, login=True)

    def ask_now(self) -> bool:
        """The owner asked for questions: no cooldown, takes focus, no auto-close."""
        if self.popup is not None:
            self.popup.make_manual()
            self.popup.show()
            self.popup.raise_()
            self.popup.activateWindow()
            return True
        count = self._settings().questions_per_login or MANUAL_FALLBACK_COUNT
        if self._open(count, login=False):
            return True
        self.nothing_to_ask.emit()
        return False

    def _open(self, count: int, *, login: bool) -> bool:
        now = self.clock.now()
        chosen = qs.select_login(self.repos, now, self._rng, count, week_start(now))
        if not chosen:
            log_event("login_questions_empty")
            return False
        reduce = self._reduce_motion
        if reduce is None:
            reduce = self._settings().reduce_motion
        popup = QuestionPopup(
            self.theme,
            chosen,
            self._record,
            login=login,
            reduce_motion=reduce,
            timeout_ms=self._timeout_ms,
        )
        popup.finished.connect(self._on_finished)
        self.popup = popup
        self._asked = set()
        log_event("login_questions_shown", count=len(chosen), manual=not login)
        popup.show()
        return True

    def _record(self, q: Question, text: str, skipped: bool) -> None:
        qs.record_answer(
            self.repos, q, "login", text, skipped=skipped,
            week_start=week_start(self.clock.now()), blog_id=q.blog_id,
            count_ask=q.id not in self._asked,
        )  # fmt: skip
        self._asked.add(q.id)

    def _on_finished(self, reason: str) -> None:
        popup, self.popup = self.popup, None
        login = popup is not None and popup.login
        now = self.clock.now()
        # Only a login popup touches the pause; the manual session is the owner's own.
        if login and reason == DONE:
            qs.note_completed(self.repos, now)
        elif login:
            qs.note_dismissed(self.repos, now, minutes=self._settings().dismiss_pause_minutes)
        log_event("login_questions_closed", reason=reason, manual=not login)
        if popup is not None:
            popup.deleteLater()
