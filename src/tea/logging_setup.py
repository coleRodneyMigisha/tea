"""Rotating file log in ~/.local/state/tea/. No content is logged.

Use `log_event` for app events: it accepts numbers, booleans and a few short keyword
strings (kind, status, error class), and refuses anything that could be owner text.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tea import config

LOGGER_NAME = "tea"
_SAFE_STR_KEYS = frozenset({"kind", "status", "error", "week_start", "origin", "context"})
_MAX_SAFE_STR = 40


def setup_logging(level: int = logging.INFO) -> Path:
    path = config.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, "_tea", False):
            logger.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(
        path, maxBytes=config.LOG_MAX_BYTES, backupCount=config.LOG_BACKUPS, encoding="utf-8"
    )
    handler._tea = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return path


def _is_safe(key: str, value: object) -> bool:
    if value is None or isinstance(value, bool | int | float):
        return True
    return isinstance(value, str) and key in _SAFE_STR_KEYS and len(value) <= _MAX_SAFE_STR


def log_event(event: str, level: int = logging.INFO, **fields: object) -> None:
    """Log `event key=value ...`. Raises TypeError on values that could carry owner content."""
    parts = [event]
    for key, value in fields.items():
        if not _is_safe(key, value):
            raise TypeError(f"log field {key!r} is not allowed (no owner content in logs)")
        parts.append(f"{key}={value}")
    logging.getLogger(LOGGER_NAME).log(level, " ".join(parts))
