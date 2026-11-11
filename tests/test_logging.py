import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler

import pytest

from tea import config
from tea.logging_setup import log_event, setup_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    root = logging.getLogger("tea")
    for handler in [h for h in root.handlers if isinstance(h, RotatingFileHandler)]:
        root.removeHandler(handler)
        handler.close()


def test_rotating_file_in_state_dir() -> None:
    path = setup_logging()
    assert path == config.log_path()
    handlers = [h for h in logging.getLogger("tea").handlers if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 1024 * 1024
    assert handlers[0].backupCount == 3
    assert logging.getLogger("tea").level == logging.INFO


def test_setup_twice_keeps_one_handler() -> None:
    setup_logging()
    setup_logging()
    files = [h for h in logging.getLogger("tea").handlers if isinstance(h, RotatingFileHandler)]
    assert len(files) == 1


def test_log_event_writes_names_and_ids() -> None:
    path = setup_logging()
    log_event("draft_imported", blog_id=4, draft_id=9, duration_ms=12.5, kind="weekly")
    for h in logging.getLogger("tea").handlers:
        h.flush()
    line = path.read_text().strip().splitlines()[-1]
    assert "draft_imported" in line
    assert "blog_id=4" in line and "draft_id=9" in line and "kind=weekly" in line


def test_log_event_refuses_free_text_in_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEA_DEBUG", "1")
    with pytest.raises(TypeError):
        log_event("answer_saved", answer="I like short sentences")
    with pytest.raises(TypeError):
        log_event("attachment_added", filename="secret.pdf")


def test_log_event_allows_error_class() -> None:
    log_event("import_failed", error="ValueError", handoff_id=1)


def test_log_event_drops_free_text_in_normal_use() -> None:
    path = setup_logging()
    log_event("answer_saved", answer="I like short sentences", question_id=3)
    for h in logging.getLogger("tea").handlers:
        h.flush()
    text = path.read_text()
    assert "short sentences" not in text
    assert "field_rejected=answer" in text and "question_id=3" in text
