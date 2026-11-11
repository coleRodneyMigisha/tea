"""Snapshot states for standalone widgets: the question popup and the answers preview.

Qt is imported inside the builders, so `snap` can set QT_QPA_PLATFORM before Qt loads.
"""

from collections.abc import Callable
from typing import Any

from tea.clock import Clock
from tea.db.repos import Repos

LOGIN_KEYS = ("aud-who", "voice-humor", "voice-formality")  # text, choice, scale


def _login_popup(step: int, pick: int | None = None) -> Callable[[Any, Repos, Clock], Any]:
    """A login session of three, advanced to question `step` (0-based)."""

    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.domain import questions as qs
        from tea.ui.widgets.question_popup import QuestionPopup

        qs.seed_bank(repos)
        chosen = [repos.questions.get_by_bank_key(k) for k in LOGIN_KEYS]
        popup = QuestionPopup(
            theme, [q for q in chosen if q is not None], lambda *_: None,
            login=True, reduce_motion=True,
        )  # fmt: skip
        if step >= 1:
            popup.text_edit.setPlainText("A team lead at a small company, short on time.")
            popup.next_button.click()
        if step >= 2:
            popup.choice_buttons[1].click()
            popup.next_button.click()
        if pick is not None:
            buttons = popup.choice_buttons if step == 1 else popup.scale_buttons
            buttons[pick].click()
        return popup

    return build


def _scope_popup(theme: Any, repos: Repos, clock: Clock) -> Any:
    from tea.domain import questions as qs
    from tea.ui.widgets.question_popup import QuestionPopup

    blog = repos.blogs.create(
        "Green tea at work", "Green tea at work", "manual",
        allowed_sources=["web"], audience="", scope_notes="Why it helps focus",
    )  # fmt: skip
    chosen = qs.instantiate_scope(repos, blog, has_files=False)
    return QuestionPopup(theme, chosen, lambda *_: None, login=False, reduce_motion=True)


def _preview(sample: bool) -> Callable[[Any, Repos, Clock], Any]:
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        from tea.devtools import sample_data
        from tea.settings import Settings
        from tea.ui.widgets.answers_preview import AnswersPreview, preview_text

        if sample:
            sample_data.seed(repos, clock)
        return AnswersPreview(theme, preview_text(repos, clock, Settings()))

    return build


def register_all(register: Callable[[str, str, Any], None], state: Callable[..., Any]) -> None:
    popup = "question_popup"
    register(popup, "text", state(popup, build=_login_popup(0)))
    register(popup, "choice", state(popup, build=_login_popup(1)))
    register(popup, "choice_picked", state(popup, build=_login_popup(1, pick=2)))
    register(popup, "scale", state(popup, build=_login_popup(2)))
    register(popup, "scale_picked", state(popup, build=_login_popup(2, pick=1)))
    register(popup, "scope", state(popup, build=_scope_popup))
    register("answers_preview", "sample", state("answers_preview", build=_preview(True)))
    register("answers_preview", "empty", state("answers_preview", build=_preview(False)))


def grab_on_background(widget: Any, theme: Any) -> Any:
    """The widget as an image; a translucent window is drawn over the window background."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap

    shot = widget.grab()
    if not widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
        return shot
    canvas = QPixmap(shot.size())
    canvas.setDevicePixelRatio(shot.devicePixelRatio())
    canvas.fill(theme.color("bg"))
    painter = QPainter(canvas)
    painter.drawPixmap(0, 0, shot)
    painter.end()
    return canvas
