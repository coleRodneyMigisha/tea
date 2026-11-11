"""Single instance: QLockFile plus a local socket (ARCHITECTURE section 1)."""

from pathlib import Path

from pytestqt.qtbot import QtBot

from tea.single_instance import SingleInstance


def test_first_instance_acquires(tmp_path: Path) -> None:
    first = SingleInstance(tmp_path)
    try:
        assert first.acquire()
    finally:
        first.release()


def test_second_instance_is_refused_and_focuses_first(tmp_path: Path, qtbot: QtBot) -> None:
    first = SingleInstance(tmp_path)
    second = SingleInstance(tmp_path)
    try:
        assert first.acquire()
        assert not second.acquire()
        with qtbot.waitSignal(first.message, timeout=3000) as blocker:
            assert second.notify_running("show")
        assert blocker.args == ["show"]
    finally:
        second.release()
        first.release()


def test_lock_is_free_after_release(tmp_path: Path) -> None:
    first = SingleInstance(tmp_path)
    assert first.acquire()
    first.release()
    again = SingleInstance(tmp_path)
    try:
        assert again.acquire()
    finally:
        again.release()


def test_notify_without_a_running_instance_fails_quietly(tmp_path: Path) -> None:
    lonely = SingleInstance(tmp_path)
    assert lonely.notify_running("show", timeout_ms=200) is False


def test_stale_socket_file_does_not_block_listening(tmp_path: Path) -> None:
    (tmp_path / "tea-ipc").write_text("")  # left over from a crash
    first = SingleInstance(tmp_path)
    try:
        assert first.acquire()
    finally:
        first.release()
