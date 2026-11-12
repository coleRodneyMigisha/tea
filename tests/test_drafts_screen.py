"""Drafts screen and draft view (UI_DESIGN 3.3, TESTING 4)."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from handoff_world import TITLE, imported, weekly_handoff
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.domain import drafts
from tea.handoff.importer import import_reply
from tea.settings import Settings
from tea.ui import clipboard, drafts_state, strings
from tea.ui.drafts_flow import DraftsFlow
from tea.ui.handoff_flow import HandoffFlow
from tea.ui.screens.drafts import DraftsScreen
from tea.ui.theme import Theme
from tea.ui.widgets.draft_view import DraftView


@dataclass
class World:
    screen: DraftsScreen
    flow: DraftsFlow
    handoffs: HandoffFlow

    @property
    def view(self) -> DraftView:
        return self.flow.view


@pytest.fixture
def world(qtbot: QtBot, qapp: QApplication, repos: Repos, clock: FakeClock) -> Iterator[World]:
    theme = Theme(qapp, appearance="light", scale=1.0)
    theme.apply()
    handoffs = HandoffFlow(theme, repos, clock, Settings, debug=False)
    screen = DraftsScreen(theme)
    qtbot.addWidget(screen)
    flow = DraftsFlow(theme, repos, clock, Settings, screen, handoffs)
    screen.resize(theme.size("default_width"), theme.size("default_height"))
    screen.show()
    yield World(screen, flow, handoffs)
    handoffs.close_all()


def _ready(world: World, repos: Repos, clock: FakeClock) -> int:
    h = imported(repos, clock)
    assert h.blog_id is not None
    assert world.flow.select_blog(h.blog_id)
    return h.blog_id


def _draft(repos: Repos, blog_id: int) -> drafts.Draft:
    d = repos.drafts.latest_for_blog(blog_id)
    assert d is not None
    return d


def test_empty_state(world: World) -> None:
    assert world.screen.is_empty()
    assert world.screen.empty_label.text() == strings.EMPTY_DRAFTS


def test_groups_and_selection(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    drafts.regenerate(repos, Settings(), clock, blog_id)
    world.flow.refresh()
    assert world.screen.group_names() == [strings.GROUP_WAITING, strings.GROUP_READY]
    assert world.screen.current_key() == (drafts_state.BLOG, blog_id)
    v = world.view
    assert v.title_label.text() == TITLE
    assert v.chip is not None and v.chip.text() == strings.CHIP_READY
    assert " words - " in v.meta_label.text() and v.meta_label.text().endswith("min read")


def test_waiting_item_opens_the_handoff_dialog(
    world: World, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    world.flow.refresh()
    assert world.screen.select(drafts_state.HANDOFF, h.id)
    assert world.screen.panes.currentWidget() is world.screen.waiting
    world.screen.waiting.open_button.click()
    assert h.id in world.handoffs.dialogs


def test_copy_for_medium_sets_both_formats_and_copied_at(
    world: World, repos: Repos, clock: FakeClock
) -> None:
    blog_id = _ready(world, repos, clock)
    world.view.copy_medium_button.click()
    mime = QGuiApplication.clipboard().mimeData()
    assert mime.hasHtml() and mime.hasText()
    assert set(mime.formats()) >= {clipboard.HTML, clipboard.PLAIN}
    assert mime.html().startswith(f"<h1>{TITLE}</h1>") or f"<h1>{TITLE}</h1>" in mime.html()
    assert mime.text().startswith(TITLE + "\n\n")
    assert _draft(repos, blog_id).copied_at is not None
    assert world.view.after_copy_label.isVisibleTo(world.view)
    assert world.view.after_copy_label.text() == strings.AFTER_COPY
    assert world.view.toast.text() == strings.COPIED_FOR_MEDIUM


def test_copy_markdown(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    world.view.copy_md_button.click()
    assert clipboard.text() == _draft(repos, blog_id).body_markdown
    assert _draft(repos, blog_id).copied_at is None  # only Copy for Medium counts as used


def test_edit_autosaves_and_keeps_the_import(
    qtbot: QtBot, world: World, repos: Repos, clock: FakeClock
) -> None:
    blog_id = _ready(world, repos, clock)
    before = _draft(repos, blog_id)
    v = world.view
    v.edit_button.click()
    assert v.editing() and v.edit_button.text() == strings.PREVIEW
    assert v.editor.toPlainText() == before.body_markdown
    v.editor.setPlainText("# My title\n\nMy own words.\n")
    assert v.editor.timer.isActive() and v.editor.timer.interval() == 2000
    qtbot.waitUntil(lambda: _draft(repos, blog_id).edited_markdown is not None, timeout=4000)
    after = _draft(repos, blog_id)
    assert after.edited_markdown == "# My title\n\nMy own words.\n"
    assert after.body_markdown == before.body_markdown
    assert v.edited_note.isVisibleTo(v) and v.edited_note.text() == strings.EDITED_NOTE
    v.edit_button.click()  # Preview
    assert not v.editing()
    assert "My own words." in v.reader.toPlainText()


def test_preview_saves_pending_edits_at_once(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    v = world.view
    v.edit_button.click()
    v.editor.setPlainText("quick change")
    v.edit_button.click()
    assert _draft(repos, blog_id).edited_markdown == "quick change"


def test_version_picker(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    v = world.view
    assert not v.version_row.isVisibleTo(v)
    h = repos.handoffs.latest(blog_id=blog_id)
    assert h is not None
    import_reply(repos, h.id, sample_replies.WEEKLY.replace("Most small teams", "Every small team"))
    first = repos.drafts.list_for_blog(blog_id)[0]
    drafts.save_edit(repos, first.id, "edited v1")
    world.flow.select_blog(blog_id)
    assert v.version_row.isVisibleTo(v)
    assert v.version_entries() == ["Version 1 (New, edited)", "Version 2 (Regenerated)"]
    assert v.version_chip is not None and v.version_chip.text() == "Regenerated"
    assert "Every small team" in v.reader.toPlainText()
    v.version_combo.activated.emit(0)
    assert v.draft is not None and v.draft.version == 1
    assert v.reader.toPlainText().strip() == "edited v1"
    assert v.edited_marker.isVisibleTo(v)


def test_drawer_contents(world: World, repos: Repos, clock: FakeClock) -> None:
    _ready(world, repos, clock)
    v = world.view
    assert v.drawer_button.isChecked() and v.drawer.isVisibleTo(v)  # open for a new draft
    s = v.drawer.sections
    assert s[strings.DRAWER_CHECKLIST] == [strings.CHECK_OWN_WORDS, strings.CHECK_CLAIMS]
    assert [r.status for r in v.drawer.claim_rows] == ["weak", "supported"]
    assert "Nielsen Norman Group" in s[strings.DRAWER_SOURCES][0]
    assert 'href="https://www.nngroup.com/' in s[strings.DRAWER_SOURCES][0]
    assert s[strings.DRAWER_FLAGS] == [
        "No first-hand story about a document that went unread was given."
    ]
    assert strings.DRAWER_IMPORT_NOTES not in s
    assert s[strings.DRAWER_MEDIUM] == [strings.MEDIUM_OK]
    assert strings.DRAWER_CHANGES not in s
    v.drawer_button.click()
    assert not v.drawer.isVisibleTo(v)


def test_drawer_closed_once_copied(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    repos.drafts.mark_copied(_draft(repos, blog_id).id)
    world.view.draft = None
    world.flow.select_blog(blog_id)
    assert not world.view.drawer_button.isChecked()


def test_drawer_import_notes_and_medium_warnings(
    world: World, repos: Repos, clock: FakeClock
) -> None:
    h = weekly_handoff(repos, clock)
    reply = "<draft>\n# T\n\n#### Deep\n\n| a | b |\n|---|---|\n| 1 | 2 |\n</draft>"
    import_reply(repos, h.id, reply)
    assert h.blog_id is not None
    world.flow.select_blog(h.blog_id)
    s = world.view.drawer.sections
    assert s[strings.DRAWER_IMPORT_NOTES] == [strings.PARSE_NO_VERIFICATION]
    assert s[strings.DRAWER_MEDIUM] == [
        strings.MEDIUM_WARNINGS["deep_heading"],
        strings.MEDIUM_WARNINGS["table"],
    ]


def test_improved_version_shows_what_changed(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    improve = repos.handoffs.create("improve", "p", 1, {"packet_improve": 1}, blog_id=blog_id)
    import_reply(repos, improve.id, sample_replies.IMPROVE)
    world.flow.select_blog(blog_id)
    lines = world.view.drawer.sections[strings.DRAWER_CHANGES]
    assert lines[0].startswith("Added the story about the onboarding wiki")


def test_clicking_a_claim_highlights_it(world: World, repos: Repos, clock: FakeClock) -> None:
    h = weekly_handoff(repos, clock)
    reply = sample_replies.WEEKLY.replace(
        "weak | Teams of five rarely need written specs",
        "weak | Teams of five rarely have that moment",
    )
    import_reply(repos, h.id, reply)
    assert h.blog_id is not None
    world.flow.select_blog(h.blog_id)
    v = world.view
    row = v.drawer.claim_rows[0]
    row.clicked.emit(row.claim)
    sel = v.reader.extraSelections()
    assert len(sel) == 1 and sel[0].cursor.selectedText() == "Teams of five rarely have that moment"


def test_source_link_opens_in_browser(
    world: World, repos: Repos, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(world, repos, clock)
    urls: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda u: urls.append(u)))
    from PySide6.QtWidgets import QLabel

    labels = [
        w
        for w in world.view.drawer.findChildren(QLabel)
        if "nngroup" in w.text() and "<a" in w.text()
    ]
    labels[0].linkActivated.emit("https://www.nngroup.com/x")
    assert [u.toString() for u in urls] == ["https://www.nngroup.com/x"]


def test_regenerate_and_second_pass_open_new_handoffs(
    world: World, repos: Repos, clock: FakeClock
) -> None:
    blog_id = _ready(world, repos, clock)
    world.view.regenerate_button.click()
    weekly_open = repos.handoffs.list(open_only=True, blog_id=blog_id)
    assert [h.kind for h in weekly_open] == ["weekly"]
    assert weekly_open[0].id in world.handoffs.dialogs
    world.view.second_pass_action.trigger()
    kinds = [h.kind for h in repos.handoffs.list(open_only=True, blog_id=blog_id)]
    assert kinds == ["weekly", "audit"]
    assert world.screen.group_names()[0] == strings.GROUP_WAITING


def test_mark_posted_shelve_revive(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    v = world.view
    assert v.shelve_action.isVisible() and not v.revive_action.isVisible()
    v.shelve_action.trigger()
    assert world.screen.group_names() == [strings.GROUP_SHELVED]
    assert v.revive_action.isVisible() and not v.shelve_action.isVisible()
    v.revive_action.trigger()
    assert world.screen.group_names() == [strings.GROUP_CARRIED]
    v.posted_action.trigger()
    assert world.screen.group_names() == [strings.GROUP_POSTED]
    assert _draft(repos, blog_id).posted_at is not None
    assert v.chip is not None and v.chip.text() == strings.CHIP_POSTED
    assert not v.posted_action.isVisible()


def test_delete_asks_first(world: World, repos: Repos, clock: FakeClock) -> None:
    blog_id = _ready(world, repos, clock)
    v = world.view
    asked: list[str] = []
    v.confirm_delete = lambda text: asked.append(text) or False  # type: ignore[method-assign]
    v.delete_action.trigger()
    assert repos.drafts.list_for_blog(blog_id) and asked
    v.confirm_delete = lambda text: True  # type: ignore[method-assign]
    v.delete_action.trigger()
    assert repos.drafts.list_for_blog(blog_id) == []
    assert world.screen.is_empty()


def test_export_writes_the_current_text(
    world: World, repos: Repos, clock: FakeClock, tmp_path: Path
) -> None:
    blog_id = _ready(world, repos, clock)
    drafts.save_edit(repos, _draft(repos, blog_id).id, "# Mine\n")
    world.flow.select_blog(blog_id)
    target = tmp_path / "out.md"
    world.view.export_path = lambda suggested: target  # type: ignore[method-assign]
    world.view.export_action.trigger()
    assert target.read_text() == "# Mine\n"


def test_reading_pane_uses_reading_font_and_line_height(
    world: World, repos: Repos, clock: FakeClock
) -> None:
    _ready(world, repos, clock)
    doc = world.view.reader.document()
    theme = world.view.theme
    assert doc.defaultFont().families()[0] == theme.font("reading", "reading_body").families()[0]
    block = doc.begin().next()  # first paragraph after the title
    assert block.blockFormat().lineHeight() == 165
    assert doc.begin().blockFormat().headingLevel() == 1
