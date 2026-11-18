"""New blog screen and flow (pytest-qt): form, validation, scope session, resume, hand-off."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.connection import open_db
from tea.db.repos import Repos
from tea.devtools import sample_replies
from tea.domain import manual
from tea.settings import Settings
from tea.ui import strings
from tea.ui.handoff_flow import HandoffFlow
from tea.ui.new_blog_flow import NewBlogFlow
from tea.ui.screens.new_blog import NewBlogScreen
from tea.ui.theme import Theme
from tea.ui.widgets.question_popup import QuestionPopup


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


class World:
    def __init__(self, qtbot: QtBot, theme: Theme, repos: Repos, clock: FakeClock) -> None:
        self.repos = repos
        self.screen = NewBlogScreen(theme)
        qtbot.addWidget(self.screen)
        self.handoffs = HandoffFlow(theme, repos, clock, Settings)
        self.flow = NewBlogFlow(
            theme, repos, clock, Settings, self.screen, self.handoffs, reduce_motion=True
        )
        self.screen.show()

    def fill(self, topic: str = "Green tea at work") -> None:
        self.screen.topic_edit.setText(topic)

    @property
    def popup(self) -> QuestionPopup:
        assert self.flow.popup is not None
        return self.flow.popup

    def answer(self, n: int) -> None:
        for i in range(n):
            p = self.popup
            q = p.current
            if q.kind == "text":
                p.text_edit.setPlainText(f"answer {i}")
            elif q.kind == "choice":
                p.choice_buttons[0].click()
            else:
                p.scale_buttons[2].click()
            p.next_button.click()

    def close(self) -> None:
        if self.flow.popup is not None:
            self.flow.popup.close()
        self.handoffs.close_all()


@pytest.fixture
def world(qtbot: QtBot, theme: Theme, repos: Repos, clock: FakeClock) -> Iterator[World]:
    w = World(qtbot, theme, repos, clock)
    yield w
    w.close()


# The form


def test_form_has_every_field_from_the_design(world: World) -> None:
    s = world.screen
    assert s.cover_edit.isVisible() and s.audience_edit.isVisible()
    assert list(s.source_boxes) == ["own_documents", "web", "academic"]
    assert [b.text() for b in s.source_boxes.values()] == ["My documents", "Web", "Academic papers"]
    assert s.source_boxes["own_documents"].isChecked()
    assert not s.source_boxes["web"].isChecked()
    assert [b.text() for b in s.length_buttons.values()] == ["Short", "Standard", "Long"]
    assert s.length_buttons["standard"].isChecked()
    assert s.dropzone is not None and s.dropzone.isVisible()
    assert s.start_button.text() == strings.START_QUESTIONS
    assert s.panel.maximumWidth() == world.screen.theme.size("form_max_width")


def test_start_is_disabled_until_topic_has_text(world: World) -> None:
    s = world.screen
    assert not s.start_button.isEnabled()
    world.fill("   ")
    assert not s.start_button.isEnabled()
    world.fill("Tea")
    assert s.start_button.isEnabled()
    world.fill("")
    assert not s.start_button.isEnabled()


def test_start_waits_for_file_copies(world: World, tmp_path: Path, qtbot: QtBot) -> None:
    world.fill()
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 1024)
    dz = world.screen.dropzone
    assert dz is not None
    dz.add_paths([big])
    assert dz.copying()  # the worker reports back through the event loop
    assert not world.screen.start_button.isEnabled()
    world.screen.start_requested.emit()
    assert world.flow.popup is None
    qtbot.waitUntil(lambda: not dz.copying(), timeout=10_000)
    assert world.screen.start_button.isEnabled()


def test_files_land_on_the_form_blog(world: World, tmp_path: Path, qtbot: QtBot) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("notes")
    dz = world.screen.dropzone
    assert dz is not None
    dz.add_paths([src])
    qtbot.waitUntil(lambda: not dz.copying())
    assert dz.blog_id == manual.form_blog(world.repos).id
    assert len(world.repos.attachments.list_for_blog(dz.blog_id)) == 1


def test_cancel_clears_the_form_and_its_files(world: World, tmp_path: Path, qtbot: QtBot) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("notes")
    dz = world.screen.dropzone
    assert dz is not None
    old = dz.blog_id
    dz.add_paths([src])
    qtbot.waitUntil(lambda: not dz.copying())
    world.fill()
    world.screen.source_boxes["web"].setChecked(True)
    stored = Path(world.repos.attachments.list_for_blog(old)[0].stored_path)
    world.screen.cancel_button.click()
    assert not stored.exists()
    s = world.screen
    assert s.topic_edit.text() == "" and not s.source_boxes["web"].isChecked()
    assert s.dropzone is not None and s.dropzone is not dz
    assert s.dropzone.rows == []
    assert world.repos.attachments.list_for_blog(s.dropzone.blog_id) == []
    assert len(world.repos.blogs.list(origin="manual")) == 1


# Starting the scope session


def test_start_saves_the_form_and_opens_a_focused_popup(world: World, qtbot: QtBot) -> None:
    s = world.screen
    world.fill("Green tea at work")
    s.cover_edit.setPlainText("Why it helps focus")
    s.audience_edit.setText("Office staff")
    s.source_boxes["web"].setChecked(True)
    s.length_buttons["long"].click()
    s.start_button.click()
    blogs = manual.in_progress(world.repos)
    assert len(blogs) == 1
    b = blogs[0]
    assert (b.topic, b.scope_notes, b.audience, b.length) == (
        "Green tea at work", "Why it helps focus", "Office staff", "long",
    )  # fmt: skip
    assert b.allowed_sources == ["own_documents", "web"]
    popup = world.popup
    assert not popup.login
    n = len(popup.questions)
    assert 5 <= n <= 15
    assert popup.progress_text() == f"Question 1 of {n}"
    qtbot.waitUntil(lambda: QApplication.activeWindow() is popup)
    # The form is ready for another blog.
    assert s.topic_edit.text() == ""
    assert s.dropzone is not None and s.dropzone.blog_id != b.id


def test_double_click_makes_one_blog_one_popup(world: World) -> None:
    world.fill()
    world.screen.start_button.click()
    first = world.flow.popup
    world.screen.start_button.click()
    world.screen.start_requested.emit()
    assert world.flow.popup is first
    assert len(manual.in_progress(world.repos)) == 1
    assert len(world.repos.blogs.list(origin="manual")) == 2  # the one started + a fresh form


def test_answers_are_saved_on_every_answer(world: World) -> None:
    world.fill()
    world.screen.start_button.click()
    world.answer(2)
    bid = manual.in_progress(world.repos)[0].id
    answers = world.repos.answers.list(blog_id=bid)
    assert [a.context for a in answers] == [manual.CONTEXT] * 2
    assert manual.resume(world.repos, bid).start == 2


def test_later_keeps_progress_and_shows_the_banner(world: World) -> None:
    world.fill("Green tea at work")
    world.screen.start_button.click()
    world.answer(3)
    world.popup.later_button.click()
    assert world.flow.popup is None
    s = world.screen
    assert s.progress_banner.isVisibleTo(s)
    assert s.progress_label.text() == strings.IN_PROGRESS.format(topic="Green tea at work")
    assert world.flow.in_progress_topic() == "Green tea at work"
    s.resume_button.click()
    assert world.popup.index == 3
    n = len(world.popup.questions)
    assert world.popup.progress_text() == f"Question 4 of {n}"


def test_resume_raises_an_open_popup(world: World) -> None:
    world.fill()
    world.screen.start_button.click()
    first = world.popup
    world.flow.resume()
    assert world.flow.popup is first


# Finishing


def test_done_opens_the_manual_handoff_dialog(world: World) -> None:
    world.fill()
    world.screen.start_button.click()
    bid = manual.in_progress(world.repos)[0].id
    world.answer(len(world.popup.questions))
    assert world.flow.popup is None
    blog = world.repos.blogs.get(bid)
    assert blog is not None and blog.status == "prompt_ready"
    (h,) = world.repos.handoffs.list(blog_id=bid)
    assert h.kind == "manual"
    assert h.id in world.handoffs.dialogs
    assert world.handoffs.dialogs[h.id].isVisible()
    s = world.screen
    assert not s.progress_banner.isVisibleTo(s)
    assert s.waiting_banner.isVisibleTo(s)
    assert s.waiting_label.text() == strings.PROMPT_WAITING


def test_open_handoff_banner_opens_the_dialog(world: World) -> None:
    world.fill()
    world.screen.start_button.click()
    world.answer(len(world.popup.questions))
    world.handoffs.close_all()
    world.screen.open_handoff_button.click()
    assert world.handoffs.is_open()


def test_full_flow_imports_the_sample_reply(world: World, tmp_path: Path, qtbot: QtBot) -> None:
    src = tmp_path / "keshav.pdf"
    src.write_bytes(b"%PDF")
    dz = world.screen.dropzone
    assert dz is not None
    dz.add_paths([src])
    qtbot.waitUntil(lambda: not dz.copying())
    world.fill("How to read an academic paper in 20 minutes")
    world.screen.start_button.click()
    keys = {q.template_key for q in world.popup.questions}
    assert "s-files-parts" in keys  # the attached file shaped the questions
    world.answer(len(world.popup.questions))
    dialog = next(iter(world.handoffs.dialogs.values()))
    h = world.repos.handoffs.get(dialog.handoff_id)
    assert h is not None and "keshav.pdf" in h.packet_text
    dialog.copy_button.click()
    dialog.paste_box.setPlainText(sample_replies.MANUAL)
    dialog.import_button.click()
    blog = world.repos.blogs.get(dz.blog_id)
    assert blog is not None and blog.status == "ready"
    assert world.repos.drafts.latest_for_blog(blog.id) is not None
    world.flow.refresh()
    assert not world.screen.waiting_banner.isVisibleTo(world.screen)


def test_closing_mid_session_resumes_after_restart(
    qtbot: QtBot, theme: Theme, db_path: Path, clock: FakeClock
) -> None:
    conn = open_db(db_path)
    w = World(qtbot, theme, Repos(conn, clock), clock)
    w.fill()
    w.screen.start_button.click()
    w.answer(4)
    w.popup.skip_button.click()
    w.popup.close()  # the app quits with the popup open
    w.close()
    conn.close()

    conn = open_db(db_path)
    again = World(qtbot, theme, Repos(conn, clock), clock)
    try:
        assert again.flow.in_progress_topic() == "Green tea at work"
        assert again.screen.progress_banner.isVisibleTo(again.screen)
        again.screen.resume_button.click()
        p = again.popup
        assert p.index == 5
        assert p.progress_text() == f"Question 6 of {len(p.questions)}"
        p.back_button.click()
        p.back_button.click()
        assert p.text_edit.toPlainText() == "answer 3"  # index 3 is a text question
    finally:
        again.close()
        conn.close()


# Review fixes (M8)


def test_cancel_waits_for_file_copies(world: World, tmp_path: Path, qtbot: QtBot) -> None:
    src = tmp_path / "notes.txt"
    src.write_bytes(b"x" * 1024)
    dz = world.screen.dropzone
    assert dz is not None
    dz.add_paths([src])
    assert dz.copying()
    assert not world.screen.cancel_button.isEnabled()
    world.screen.cancel_requested.emit()  # ignored while a copy runs
    assert world.screen.dropzone is dz
    qtbot.waitUntil(lambda: not dz.copying())
    assert world.screen.cancel_button.isEnabled()
    assert len(world.repos.attachments.list_for_blog(dz.blog_id)) == 1


def test_packet_failure_shows_a_message_and_asks_for_the_window(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tea.handoff import packets

    def fail(*_a: object, **_k: object) -> None:
        raise packets.PacketError("boom")

    monkeypatch.setattr(manual, "finish", fail)
    shown: list[bool] = []
    world.flow.needs_window.connect(lambda: shown.append(True))
    world.fill()
    world.screen.start_button.click()
    world.answer(len(world.popup.questions))
    assert world.screen.error.text() == strings.PACKET_FAILED
    assert shown == [True]
    assert world.screen.progress_banner.isVisibleTo(world.screen)  # Resume tries again


def test_resume_with_every_question_answered_prepares_the_prompt(world: World) -> None:
    world.fill()
    world.screen.start_button.click()
    bid = manual.in_progress(world.repos)[0].id
    n = len(world.popup.questions)
    world.answer(n - 1)
    from tea.domain import questions as qs

    last = world.popup.current
    world.popup.close()  # the app quit before the last answer reached the flow
    qs.record_answer(world.repos, last, manual.CONTEXT, "late", blog_id=bid)
    world.flow.popup = None
    world.flow.resume()
    assert world.flow.popup is None
    (h,) = world.repos.handoffs.list(blog_id=bid)
    assert h.id in world.handoffs.dialogs


def test_start_while_another_session_is_open_explains_why(world: World) -> None:
    world.fill("First")
    world.screen.start_button.click()
    first = world.flow.popup
    world.fill("Second")
    world.screen.start_button.click()
    assert world.flow.popup is first
    assert world.screen.error.text() == strings.FINISH_OPEN_QUESTIONS
    assert world.screen.topic_edit.text() == "Second"  # the new form is kept
    assert len(manual.in_progress(world.repos)) == 1


def test_start_on_a_vanished_form_row_keeps_the_typed_form(world: World) -> None:
    world.fill("Kept topic")
    dz = world.screen.dropzone
    assert dz is not None
    world.repos.blogs.delete(dz.blog_id)
    world.screen.start_button.click()
    assert world.screen.error.text() == strings.START_FAILED
    assert world.screen.topic_edit.text() == "Kept topic"
    new = world.screen.dropzone
    assert new is not None and world.repos.blogs.get(new.blog_id) is not None
    world.screen.start_button.click()  # works with the new row
    assert world.flow.popup is not None
