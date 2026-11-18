"""Why dialog: show the stored topic candidates and their sources."""


import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.why_dialog import WhyDialog

CANDIDATES: list[dict[str, object]] = [
    {
        "n": 1,
        "topic": "Right-to-repair rules for phones",
        "angle": "What the new rules change for buyers",
        "why": "Covered by two national outlets this week",
        "urls": ["https://example.org/a", "https://example.org/b"],
    },
    {
        "n": 2,
        "topic": "Four-day week trials",
        "angle": "What the trial data says",
        "why": "Reported by two business papers",
        "urls": ["https://example.org/c"],
    },
]


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    return theme


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[QUrl]:
    urls: list[QUrl] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        staticmethod(lambda url: urls.append(url)),
    )
    return urls


def make(qtbot: QtBot, theme: Theme) -> WhyDialog:
    dialog = WhyDialog(
        theme,
        topic="Right-to-repair rules for phones",
        candidates=CANDIDATES,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_shows_topic_and_candidate_details(
    qtbot: QtBot,
    theme: Theme,
) -> None:
    dialog = make(qtbot, theme)

    assert dialog.windowTitle() == strings.WHY_TITLE
    assert dialog.topic_label.text() == "Right-to-repair rules for phones"
    assert len(dialog.candidate_cards) == 2

    first = dialog.candidate_cards[0]
    assert "Right-to-repair rules for phones" in first.toPlainText()
    assert "What the new rules change for buyers" in first.toPlainText()
    assert "Covered by two national outlets this week" in first.toPlainText()


def test_source_links_open_in_the_browser(
    qtbot: QtBot,
    theme: Theme,
    opened: list[QUrl],
) -> None:
    dialog = make(qtbot, theme)

    assert len(dialog.link_buttons) == 3

    dialog.link_buttons[0].click()

    assert [url.toString() for url in opened] == ["https://example.org/a"]
