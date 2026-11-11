"""The "What Claude will be told about you" preview dialog."""

from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_data
from tea.domain.weeks import week_start
from tea.handoff import answers
from tea.settings import Settings
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.answers_preview import AnswersPreview, preview_text


def _theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


def test_preview_text_is_the_answers_section(repos: Repos, clock: FakeClock) -> None:
    sample_data.seed(repos, clock)
    text = preview_text(repos, clock, Settings())
    expected = answers.answers_section(
        repos, blog=None, week=week_start(clock.now()), max_words=Settings().max_answer_words
    )
    assert text == expected and text
    labels = [answers.LABELS[c] for c in answers.CATEGORY_ORDER[:6]]
    positions = [text.index(label + "\n") for label in labels]
    assert positions == sorted(positions)
    assert "Never name my employer" in text
    assert "What have you worked on recently" not in text  # skipped answers are left out


def test_dialog_is_read_only_and_shows_the_text(
    qapp: QApplication, qtbot: QtBot, repos: Repos, clock: FakeClock
) -> None:
    sample_data.seed(repos, clock)
    dialog = AnswersPreview(_theme(qapp), preview_text(repos, clock, Settings()))
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == strings.PREVIEW_TITLE
    assert dialog.view.isReadOnly()
    assert dialog.view.toPlainText() == preview_text(repos, clock, Settings())
    assert dialog.empty_label.isHidden()


def test_dialog_empty_state(qapp: QApplication, qtbot: QtBot) -> None:
    dialog = AnswersPreview(_theme(qapp), "")
    qtbot.addWidget(dialog)
    assert dialog.view.isHidden()
    assert dialog.empty_label.text() == strings.PREVIEW_EMPTY
