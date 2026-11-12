"""Hand-off dialog (UI_DESIGN 3.5, TESTING 4): steps, import, summary, notes and recovery."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from handoff_world import TITLE, WEEK, imported, pick_handoff, weekly_handoff
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.domain import attachments, drafts
from tea.settings import Settings
from tea.ui import clipboard, strings
from tea.ui.theme import Theme
from tea.ui.widgets.handoff_dialog import HandoffDialog

Make = Callable[..., HandoffDialog]


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


@pytest.fixture
def make(qtbot: QtBot, theme: Theme, repos: Repos, clock: FakeClock) -> Iterator[Make]:
    made: list[HandoffDialog] = []

    def build(handoff_id: int, **kw: object) -> HandoffDialog:
        settings = kw.pop("settings", Settings())
        d = HandoffDialog(theme, repos, clock, lambda: settings, handoff_id, **kw)  # type: ignore[arg-type]
        qtbot.addWidget(d)
        made.append(d)
        return d

    yield build
    for d in made:
        d.close()


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[QUrl]:
    urls: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda u: urls.append(u)))
    return urls


# Step 1: Copy prompt


def test_title_and_subtitle(make: Make, repos: Repos, clock: FakeClock) -> None:
    d = make(weekly_handoff(repos, clock).id)
    assert d.title_label.text() == "Write this week's draft"
    assert "Why small teams" in d.subtitle_label.text()


def test_copy_prompt_puts_packet_on_clipboard_and_marks_copied(
    make: Make, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    d = make(h.id)
    assert not d.step_done(1)
    d.copy_button.click()
    assert clipboard.text() == h.packet_text
    got = repos.handoffs.get(h.id)
    assert got is not None and got.status == "copied"
    assert d.step_done(1)
    assert d.toast.text() == strings.PROMPT_COPIED and d.toast.isVisibleTo(d)


def test_word_count_shown(make: Make, repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    d = make(h.id)
    assert d.words_label.text() == f"{h.packet_words:,} words"


def test_view_prompt_shows_the_packet_read_only(make: Make, repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    d = make(h.id)
    d.view_prompt_button.click()
    viewer = d.prompt_viewer
    assert viewer is not None and viewer.isVisible()
    assert viewer.text_view.toPlainText() == h.packet_text
    assert viewer.text_view.isReadOnly()


def test_attached_files_listed_with_show_in_folder(
    make: Make, repos: Repos, clock: FakeClock, tmp_path: Path, opened: list[QUrl]
) -> None:
    h = weekly_handoff(repos, clock)
    assert h.blog_id is not None
    src = tmp_path / "report-2025.pdf"
    src.write_bytes(b"pdf")
    attachments.add(repos, h.blog_id, src)
    left = tmp_path / "left-out.docx"
    left.write_bytes(b"doc")
    a = attachments.add(repos, h.blog_id, left)
    attachments.set_included(repos, a.id, False)
    d = make(h.id)
    assert d.attach_label.text() == strings.ATTACH_FILES
    assert d.file_names() == ["report-2025.pdf"]
    d.folder_buttons[0].click()
    assert opened and opened[0].toLocalFile() == str(attachments.blog_dir(h.blog_id))


def test_no_files_no_attach_line(make: Make, repos: Repos, clock: FakeClock) -> None:
    d = make(weekly_handoff(repos, clock).id)
    assert d.file_names() == [] and not d.attach_label.isVisibleTo(d)


# Step 2: Open Claude


def test_open_claude_opens_the_configured_link(
    make: Make, repos: Repos, clock: FakeClock, opened: list[QUrl]
) -> None:
    settings = Settings(claude_url="https://claude.ai/project/abc")
    d = make(weekly_handoff(repos, clock).id, settings=settings)
    assert d.hint_label.text() == strings.WEB_SEARCH_HINT
    d.open_claude_button.click()
    assert [u.toString() for u in opened] == ["https://claude.ai/project/abc"]
    assert d.step_done(2)


# Step 3: paste and import


def test_import_disabled_with_empty_box(make: Make, repos: Repos, clock: FakeClock) -> None:
    d = make(weekly_handoff(repos, clock).id)
    assert not d.import_button.isEnabled()
    d.paste_box.setPlainText("   \n ")
    assert not d.import_button.isEnabled()
    d.paste_box.setPlainText("x")
    assert d.import_button.isEnabled()


def test_paste_from_clipboard(make: Make, repos: Repos, clock: FakeClock) -> None:
    d = make(weekly_handoff(repos, clock).id)
    QGuiApplication.clipboard().setText("<draft># Hi</draft>")
    d.paste_clipboard_button.click()
    assert d.paste_box.toPlainText() == "<draft># Hi</draft>"


def test_importing_the_sample_reply_shows_the_summary(
    make: Make, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    d = make(h.id)
    d.paste_box.setPlainText(sample_replies.WEEKLY)
    with_signal: list[int] = []
    d.imported.connect(with_signal.append)
    d.import_button.click()
    assert d.summary.isVisibleTo(d) and not d.paste_box.isVisibleTo(d)
    words = f"{len(drafts.current_text(_latest(repos, h.blog_id)).split()):,}"
    assert d.summary_label.text() == f"Imported {TITLE}: {words} words, 1 claim to check."
    assert d.note_lines() == []
    assert d.recoveries() == []
    assert d.step_done(3)
    assert with_signal == [h.blog_id]
    got = repos.handoffs.get(h.id)
    assert got is not None and got.status == "imported"


def _latest(repos: Repos, blog_id: int | None) -> drafts.Draft:
    assert blog_id is not None
    d = repos.drafts.latest_for_blog(blog_id)
    assert d is not None
    return d


def test_open_draft_button(make: Make, repos: Repos, clock: FakeClock) -> None:
    h = imported(repos, clock)
    d = make(h.id)
    asked: list[int] = []
    d.open_draft_requested.connect(asked.append)
    assert d.open_draft_button.property("variant") == "primary"
    d.open_draft_button.click()
    assert asked == [h.blog_id]


def test_paste_a_different_reply_reimports_as_new_version(
    make: Make, repos: Repos, clock: FakeClock
) -> None:
    h = imported(repos, clock)
    d = make(h.id)
    assert d.summary.isVisibleTo(d)
    d.paste_different_button.click()
    assert d.paste_box.isVisibleTo(d) and not d.summary.isVisibleTo(d)
    d.paste_box.setPlainText(sample_replies.WEEKLY)
    d.import_button.click()
    assert h.blog_id is not None
    assert [x.version for x in repos.drafts.list_for_blog(h.blog_id)] == [1, 2]


# Malformed replies: notes and recovery buttons (SPEC 3.3, acceptance 2)

EXPECTED: dict[str, tuple[list[str], list[str]]] = {
    "no_tags": ([strings.PARSE_NO_DRAFT, strings.PARSE_NO_VERIFICATION], ["audit"]),
    "no_draft_tag": ([strings.PARSE_NO_DRAFT], []),
    "no_verification": ([strings.PARSE_NO_VERIFICATION], ["audit"]),
    "truncated": ([strings.PARSE_TRUNCATED], ["continue"]),
    "pipes_in_claims": ([], []),
    "unknown_statuses": ([strings.PARSE_UNKNOWN_STATUS], []),
    "only_draft": ([strings.PARSE_NO_DRAFT, strings.PARSE_NO_VERIFICATION], ["audit"]),
}


def test_every_malformed_fixture_is_covered() -> None:
    assert set(EXPECTED) == set(sample_replies.MALFORMED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_malformed_reply_shows_notes_and_recovery(
    name: str, make: Make, repos: Repos, clock: FakeClock
) -> None:
    d = make(weekly_handoff(repos, clock).id)
    d.paste_box.setPlainText(sample_replies.MALFORMED[name])
    d.import_button.click()
    lines, recoveries = EXPECTED[name]
    assert d.note_lines() == lines
    assert d.recoveries() == recoveries
    assert d.summary.isVisibleTo(d)


def test_audit_recovery_copies_an_audit_prompt(make: Make, repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    d = make(h.id)
    d.paste_box.setPlainText(sample_replies.MALFORMED["no_verification"])
    d.import_button.click()
    switched: list[int] = []
    d.switch_requested.connect(switched.append)
    d.audit_button.click()
    audits = repos.handoffs.list(kind="audit", blog_id=h.blog_id)
    assert len(audits) == 1 and audits[0].status == "copied"
    assert clipboard.text() == audits[0].packet_text
    assert switched == [audits[0].id]


def test_continue_recovery_copies_the_continue_prompt(
    make: Make, repos: Repos, clock: FakeClock
) -> None:
    d = make(weekly_handoff(repos, clock).id)
    d.paste_box.setPlainText(sample_replies.MALFORMED["truncated"])
    d.import_button.click()
    d.continue_button.click()
    assert clipboard.text() == drafts.continue_prompt()
    assert d.toast.text() == strings.PROMPT_COPIED
    # Ready for the full reply: the paste box is back, emptied for the new paste.
    assert d.paste_box.isVisibleTo(d) and d.paste_box.toPlainText() == ""


def test_pick_mode_shows_the_chosen_topic(make: Make, repos: Repos, clock: FakeClock) -> None:
    d = make(pick_handoff(repos, clock).id)
    d.paste_box.setPlainText(sample_replies.WEEKLY_PICK)
    d.import_button.click()
    assert d.picked_label.text() == "Claude picked: Right-to-repair rules for phones"
    assert d.picked_label.isVisibleTo(d)


def test_pick_mode_without_topic_asks_for_it(make: Make, repos: Repos, clock: FakeClock) -> None:
    h = pick_handoff(repos, clock)
    d = make(h.id)
    d.paste_box.setPlainText(
        "<draft>\n# A title\n\nText.\n</draft>\n<verification>\n</verification>"
    )
    d.import_button.click()
    assert "topic" in d.recoveries()
    assert strings.PICK_NO_TOPIC in d.note_lines()
    assert not d.topic_save_button.isEnabled()
    d.topic_edit.setText("Phone repair rules")
    d.topic_save_button.click()
    w = repos.weeks.get(WEEK)
    assert w is not None and w.focus_text == "Phone repair rules"
    assert d.picked_label.text() == "Claude picked: Phone repair rules"
    assert not d.topic_edit.isVisibleTo(d)


# Debug aid


def test_sample_button_only_in_debug(make: Make, repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    assert make(h.id).sample_button is None
    d = make(h.id, debug=True)
    assert d.sample_button is not None
    d.sample_button.click()
    assert d.paste_box.toPlainText() == sample_replies.WEEKLY


def test_sample_button_uses_the_kind(make: Make, repos: Repos, clock: FakeClock) -> None:
    d = make(pick_handoff(repos, clock).id, debug=True)
    assert d.sample_button is not None
    d.sample_button.click()
    assert d.paste_box.toPlainText() == sample_replies.WEEKLY_PICK


# Keeping state


def test_pasted_text_and_claude_opened_are_restored(
    make: Make, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    d = make(h.id, pasted="half a reply", claude_opened=True)
    assert d.paste_box.toPlainText() == "half a reply"
    assert d.step_done(2)


def test_non_modal_and_width(make: Make, repos: Repos, clock: FakeClock, theme: Theme) -> None:
    d = make(weekly_handoff(repos, clock).id)
    assert not d.isModal()
    assert d.width() == theme.size("handoff_dialog_width")
