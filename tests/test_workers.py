"""workers: QThreadPool jobs with progress, cancellation and errors, delivered by signal."""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QThread, QTimer
from pytestqt.qtbot import QtBot

from tea import workers
from tea.domain import attachments

MB = 1024 * 1024


def _work(x: int, *, progress: Callable[[int, int], None], cancelled: Callable[[], bool]) -> int:
    progress(1, 2)
    progress(2, 2)
    return x * 2


def test_result_arrives_on_gui_thread(qtbot: QtBot) -> None:
    results: list[tuple[int, bool]] = []
    progress: list[tuple[int, int]] = []
    gui = QThread.currentThread()
    job = workers.run(
        _work, 21,
        on_done=lambda r: results.append((r, QThread.currentThread() is gui)),
        on_progress=lambda d, t: progress.append((d, t)),
    )  # fmt: skip
    qtbot.waitUntil(lambda: bool(results), timeout=5000)
    assert results == [(42, True)]
    assert progress == [(1, 2), (2, 2)]
    assert job.finished


def _boom(*, progress: Callable[[int, int], None], cancelled: Callable[[], bool]) -> None:
    raise ValueError("nope")


def test_errors_reach_on_error(qtbot: QtBot) -> None:
    errors: list[BaseException] = []
    workers.run(_boom, on_error=errors.append)
    qtbot.waitUntil(lambda: bool(errors), timeout=5000)
    assert isinstance(errors[0], ValueError)


def test_cancel_is_seen_by_the_job(qtbot: QtBot) -> None:
    started = threading.Event()
    errors: list[BaseException] = []

    def wait(*, progress: Callable[[int, int], None], cancelled: Callable[[], bool]) -> None:
        started.set()
        while not cancelled():
            threading.Event().wait(0.01)
        raise workers.Cancelled()

    job = workers.run(wait, on_error=errors.append)
    assert started.wait(5)
    job.cancel()
    qtbot.waitUntil(lambda: bool(errors), timeout=5000)
    assert isinstance(errors[0], workers.Cancelled)


def test_50_mb_copy_does_not_freeze_the_event_loop(qtbot: QtBot, tmp_path: Path) -> None:
    src = tmp_path / "big.bin"
    src.write_bytes(b"\0" * (50 * MB))
    target = attachments.reserve(1, "big.bin")
    ticks = {"n": 0}
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(lambda: ticks.__setitem__("n", ticks["n"] + 1))
    timer.start()
    done: list[int] = []
    progress: list[int] = []
    workers.run(
        attachments.copy_file, src, target,
        on_done=done.append, on_progress=lambda d, t: progress.append(d),
    )  # fmt: skip
    qtbot.waitUntil(lambda: bool(done), timeout=20000)
    timer.stop()
    assert done == [50 * MB]
    assert target.final.stat().st_size == 50 * MB
    assert len(progress) >= 10
    assert ticks["n"] >= 1  # the GUI loop kept running while the copy happened


def test_jobs_are_kept_alive_until_finished(qtbot: QtBot) -> None:
    done: list[int] = []
    workers.run(_work, 1, on_done=done.append)
    qtbot.waitUntil(lambda: bool(done), timeout=5000)
    qtbot.waitUntil(lambda: not workers.active_jobs(), timeout=5000)


@pytest.fixture(autouse=True)
def _drain() -> None:
    yield
    workers.pool().waitForDone(5000)


def test_cancelled_job_without_on_error_is_not_logged(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[str] = []
    monkeypatch.setattr(workers, "log_event", lambda event, **_: logged.append(event))
    started = threading.Event()

    def wait(*, progress: Callable[[int, int], None], cancelled: Callable[[], bool]) -> None:
        started.set()
        while not cancelled():
            threading.Event().wait(0.01)
        raise RuntimeError("stopped")  # a job's own cancel exception

    job = workers.run(wait)
    assert started.wait(5)
    job.cancel()
    qtbot.waitUntil(lambda: job.finished, timeout=5000)
    assert logged == []
    workers.run(_boom)
    qtbot.waitUntil(lambda: logged == ["worker_failed"], timeout=5000)
