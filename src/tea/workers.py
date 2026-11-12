"""QRunnable wrapper, signals and cancellation for slow work (ARCHITECTURE 3).

`run(fn, *args, on_done=, on_error=, on_progress=)` calls `fn(*args, progress=, cancelled=)` on
the shared `QThreadPool`. `progress(done, total)` and the result or exception reach the GUI
thread by queued signal. A job that touches SQLite opens its own connection.
"""

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from tea.logging_setup import log_event

Progress = Callable[[int, int], None]


class Cancelled(Exception):
    """Raised by a job that saw `cancelled()` turn true."""


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)
    progress = Signal(int, int)  # bytes fit Qt's int: files are capped at 50 MB


class Job(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple[Any, ...]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _Signals()  # created on the GUI thread, so slots run there
        self._fn = fn
        self._args = args
        self._cancel = threading.Event()
        self.finished = False

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        try:
            result = self._fn(
                *self._args, progress=self.signals.progress.emit, cancelled=self.is_cancelled
            )
        except BaseException as exc:  # noqa: BLE001 (every failure goes back to the caller)
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


_ACTIVE: set[Job] = set()


def pool() -> QThreadPool:
    return QThreadPool.globalInstance()


def active_jobs() -> list[Job]:
    return list(_ACTIVE)


def run(
    fn: Callable[..., Any],
    *args: Any,
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    on_progress: Progress | None = None,
) -> Job:
    job = Job(fn, args)
    _ACTIVE.add(job)

    def finish() -> None:
        job.finished = True
        _ACTIVE.discard(job)

    def done(result: object) -> None:
        finish()
        if on_done is not None:
            on_done(result)

    def failed(exc: object) -> None:
        finish()
        assert isinstance(exc, BaseException)
        if not (isinstance(exc, Cancelled) or job.is_cancelled()) and on_error is None:
            log_event("worker_failed", error=type(exc).__name__)
        if on_error is not None:
            on_error(exc)

    job.signals.done.connect(done)
    job.signals.failed.connect(failed)
    if on_progress is not None:
        job.signals.progress.connect(on_progress)
    pool().start(job)
    return job
