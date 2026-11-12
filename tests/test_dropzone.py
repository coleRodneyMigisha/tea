"""Dropzone (UI_DESIGN 3.2): drop or choose files, limits, leave out, remove, progress."""

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog
from pytestqt.qtbot import QtBot

from tea import workers
from tea.db.repos import Repos
from tea.domain import attachments
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.dropzone import Dropzone

MB = 1024 * 1024
# PySide marks the QPoint QDragEnterEvent constructor deprecated; Qt 6 has no other one.
pytestmark = pytest.mark.filterwarnings("ignore:Function.*QDragEnterEvent:DeprecationWarning")


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


@pytest.fixture
def blog(repos: Repos) -> int:
    return repos.blogs.create("Green tea", "Green tea", "manual").id


@pytest.fixture(autouse=True)
def _drain() -> None:
    yield
    workers.pool().waitForDone(10000)


def make(qtbot: QtBot, theme: Theme, repos: Repos, blog: int) -> Dropzone:
    dz = Dropzone(theme, repos, blog)
    qtbot.addWidget(dz)
    dz.show()
    return dz


def _file(tmp_path: Path, name: str, size: int = 10, sparse: bool = False) -> Path:
    folder = tmp_path / "src"
    folder.mkdir(exist_ok=True)
    path = folder / name
    if sparse:
        with path.open("wb") as f:
            f.truncate(size)
    else:
        path.write_bytes(b"x" * size)
    return path


def _settle(qtbot: QtBot, dz: Dropzone) -> None:
    qtbot.waitUntil(lambda: not dz.copying(), timeout=20000)


def _mime(*paths: Path) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def test_empty_state_copy(qtbot: QtBot, theme: Theme, repos: Repos, blog: int) -> None:
    dz = make(qtbot, theme, repos, blog)
    assert dz.choose_button.text() == strings.DROP_CHOOSE
    assert dz.hint.text() == strings.DROP_HINT
    assert dz.rows == []
    assert not dz.notice.isVisible() and not dz.error.isVisible()
    assert not dz.show_folder_button.isVisible()
    assert dz.acceptDrops()


def test_choose_files_adds_them(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    a, b = _file(tmp_path, "a.pdf"), _file(tmp_path, "b.docx", 2 * MB)
    paths = [str(a), str(b)]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *x, **k: (paths, "")))
    dz = make(qtbot, theme, repos, blog)
    changed: list[bool] = []
    dz.changed.connect(lambda: changed.append(True))
    dz.choose_button.click()
    _settle(qtbot, dz)
    assert [r.name.text() for r in dz.rows] == ["a.pdf", "b.docx"]
    assert dz.rows[1].size.text() == "2 MB"
    assert len(repos.attachments.list_for_blog(blog)) == 2
    assert changed
    assert dz.show_folder_button.isVisible()


def test_drop_adds_files_and_drag_over_highlights(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    path = _file(tmp_path, "notes.txt")
    mime = _mime(path)
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)  # fmt: skip
    dz.dragEnterEvent(enter)
    assert enter.isAccepted() and dz.drag_over
    drop = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)  # fmt: skip
    dz.dropEvent(drop)
    assert not dz.drag_over
    _settle(qtbot, dz)
    assert [r.name.text() for r in dz.rows] == ["notes.txt"]


def test_drag_without_files_is_refused(qtbot: QtBot, theme: Theme, repos: Repos, blog: int) -> None:
    dz = make(qtbot, theme, repos, blog)
    mime = QMimeData()
    mime.setText("hello")
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)  # fmt: skip
    enter.ignore()
    dz.dragEnterEvent(enter)
    assert not enter.isAccepted() and not dz.drag_over


def test_rejects_51_mb_file_with_message(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    big = _file(tmp_path, "report.pdf", 51 * MB, sparse=True)
    dz.add_paths([big])
    assert dz.error.isVisible()
    assert dz.error.text() == "report.pdf is over 50 MB. Choose a smaller file or split it."
    assert not dz.copying() and dz.rows == []
    assert repos.attachments.count_for_blog(blog) == 0


def test_rejects_21st_file_with_message(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, f"f{i}.txt") for i in range(21)])
    _settle(qtbot, dz)
    assert dz.error.text() == "A blog can have up to 20 files. Remove one to add another."
    assert dz.error.isVisible()
    assert len(dz.rows) == 20 and repos.attachments.count_for_blog(blog) == 20
    dz.rows[0].remove_button.click()
    dz.add_paths([_file(tmp_path, "another.txt")])
    _settle(qtbot, dz)
    assert not dz.error.isVisible()
    assert repos.attachments.count_for_blog(blog) == 20


def test_leave_out_shows_not_listed_chip_and_include_undoes_it(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    _settle(qtbot, dz)
    row = dz.rows[0]
    assert row.leave_button.text() == strings.LEAVE_OUT and not row.chip.isVisible()
    row.leave_button.click()
    row = dz.rows[0]
    assert row.chip.isVisible() and row.chip.text() == strings.NOT_LISTED
    assert row.leave_button.text() == strings.INCLUDE_FILE
    assert repos.attachments.list_for_blog(blog, included_only=True) == []
    row.leave_button.click()
    assert not dz.rows[0].chip.isVisible()
    assert len(repos.attachments.list_for_blog(blog, included_only=True)) == 1


def test_remove_deletes_the_file(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    _settle(qtbot, dz)
    stored = Path(repos.attachments.list_for_blog(blog)[0].stored_path)
    dz.rows[0].remove_button.click()
    assert dz.rows == [] and not stored.exists()
    assert not dz.show_folder_button.isVisible()


def test_first_file_notice_shows_once(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    _settle(qtbot, dz)
    assert dz.notice.isVisible() and dz.notice.text() == strings.FIRST_FILE_ADDED
    again = make(qtbot, theme, repos, blog)
    again.add_paths([_file(tmp_path, "b.pdf")])
    _settle(qtbot, again)
    assert not again.notice.isVisible()


def test_show_in_folder_opens_the_blog_folder(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda u: opened.append(u)))
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    _settle(qtbot, dz)
    dz.show_folder_button.click()
    assert [u.toLocalFile() for u in opened] == [str(attachments.blog_dir(blog))]


def test_large_copy_shows_progress_and_can_be_cancelled(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    big = _file(tmp_path, "big.bin", 40 * MB)
    gate = __import__("threading").Event()
    real = attachments.copy_file

    def slow(*args: object, **kw: object) -> int:
        assert gate.wait(10)
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(attachments, "copy_file", slow)
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([big])
    assert dz.copying()
    progress = dz.copy_rows[0]
    assert progress.name.text() == "big.bin" and progress.bar.isVisible()
    progress.cancel_button.click()
    gate.set()
    _settle(qtbot, dz)
    assert dz.rows == [] and repos.attachments.count_for_blog(blog) == 0
    assert not any(attachments.blog_dir(blog).glob("*"))
    assert not dz.error.isVisible()


def test_copy_failure_shows_a_message(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    def broken(*args: object, **kw: object) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(attachments, "copy_file", broken)
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    _settle(qtbot, dz)
    assert dz.error.isVisible() and dz.error.text() == strings.COPY_FAILED.format(name="a.pdf")
    assert dz.rows == []


def test_folders_are_skipped(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([tmp_path])
    assert not dz.copying() and dz.rows == [] and not dz.error.isVisible()


def test_existing_files_are_listed(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    att = attachments.add(repos, blog, _file(tmp_path, "a.pdf"))
    attachments.set_included(repos, att.id, False)
    dz = make(qtbot, theme, repos, blog)
    assert [r.name.text() for r in dz.rows] == ["a.pdf"]
    assert dz.rows[0].chip.isVisible()
    assert not dz.notice.isVisible()


def test_tab_order_follows_the_screen(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    for name in ("a.pdf", "b.pdf"):
        attachments.add(repos, blog, _file(tmp_path, name))
    dz = make(qtbot, theme, repos, blog)
    order = [dz.choose_button]
    widget = dz.choose_button
    for _ in range(5):
        widget = widget.nextInFocusChain()
        while widget.focusPolicy() == Qt.FocusPolicy.NoFocus or not widget.isVisible():
            widget = widget.nextInFocusChain()
        order.append(widget)
    rows = dz.rows
    assert order == [
        dz.choose_button, rows[0].leave_button, rows[0].remove_button,
        rows[1].leave_button, rows[1].remove_button, dz.show_folder_button,
    ]  # fmt: skip


def test_keyboard_focus_survives_leave_out_and_remove(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        attachments.add(repos, blog, _file(tmp_path, name))
    dz = make(qtbot, theme, repos, blog)
    dz.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is dz, timeout=3000)
    dz.rows[0].leave_button.setFocus()
    dz.rows[0].leave_button.click()  # builds a "Not listed" row
    qtbot.wait(50)  # let any stray window show and steal activation
    assert QApplication.activeWindow() is dz and dz.rows[0].leave_button.hasFocus()
    dz.rows[0].remove_button.click()
    qtbot.wait(50)
    assert dz.rows[0].remove_button.hasFocus() and dz.rows[0].name.text() == "b.pdf"
    dz.rows[1].leave_button.click()
    dz.rows[0].remove_button.click()
    dz.rows[0].remove_button.click()
    qtbot.wait(50)
    assert dz.choose_button.hasFocus()


def test_drag_over_switches_text_to_ink(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.area.set_drag_over(True)
    ink = theme.color("ink").name()
    assert dz.hint.palette().color(dz.hint.foregroundRole()).name() == ink
    dz.area.set_drag_over(False)
    assert dz.hint.palette().color(dz.hint.foregroundRole()).name() != ink


def test_drop_area_keeps_its_height_when_a_message_shows(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.setFixedWidth(theme.size("form_max_width"))
    dz.adjustSize()
    before = dz.area.height()
    dz.add_paths([_file(tmp_path, "report.pdf", 51 * MB, sparse=True)])
    dz.adjustSize()
    assert dz.area.height() == before
    assert dz.error_icon.isVisible()


def test_several_rejections_are_all_shown(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    a = _file(tmp_path, "a.pdf", 51 * MB, sparse=True)
    b = _file(tmp_path, "b.pdf", 51 * MB, sparse=True)
    dz.add_paths([a, b])
    assert dz.error.text() == "\n".join(
        strings.FILE_TOO_LARGE.format(name=n) for n in ("a.pdf", "b.pdf")
    )


def test_file_system_errors_show_copy_failed(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    def broken(blog_id: int, name: str) -> object:
        raise OSError(36, "File name too long")

    monkeypatch.setattr(attachments, "reserve", broken)
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    assert dz.error.text() == strings.COPY_FAILED.format(name="a.pdf")
    assert not dz.copying()


def test_long_file_name_is_added(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = make(qtbot, theme, repos, blog)
    dz.add_paths([_file(tmp_path, "n" * 252 + ".a")])
    _settle(qtbot, dz)
    assert len(dz.rows) == 1 and not dz.error.isVisible()


def test_closing_mid_copy_cancels_and_leaves_nothing(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    import threading

    gate = threading.Event()
    real = attachments.copy_file

    def slow(*args: object, **kw: object) -> int:
        assert gate.wait(10)
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(attachments, "copy_file", slow)
    dz = Dropzone(theme, repos, blog)
    dz.show()
    dz.add_paths([_file(tmp_path, "big.bin", 10 * MB)])
    job = dz.copy_rows[0].job
    assert job is not None
    dz.deleteLater()
    qtbot.waitUntil(lambda: job.is_cancelled(), timeout=5000)
    gate.set()
    qtbot.waitUntil(lambda: job.finished, timeout=10000)
    assert not any(attachments.blog_dir(blog).iterdir())
    assert repos.attachments.count_for_blog(blog) == 0


def test_copy_finishing_after_close_is_still_recorded(
    qtbot: QtBot, theme: Theme, repos: Repos, blog: int, tmp_path: Path
) -> None:
    dz = Dropzone(theme, repos, blog)
    dz.add_paths([_file(tmp_path, "a.pdf")])
    job = dz.copy_rows[0].job
    assert job is not None
    workers.pool().waitForDone(5000)  # the copy ends before the widget goes away
    dz.deleteLater()
    qtbot.waitUntil(lambda: job.finished, timeout=5000)
    assert repos.attachments.count_for_blog(blog) == 1
