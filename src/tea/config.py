"""Paths (platformdirs), constants and defaults.

Each folder can be overridden with TEA_DATA_DIR, TEA_CONFIG_DIR, TEA_STATE_DIR or TEA_RUNTIME_DIR
(tests, dev).
"""

import os
from datetime import timedelta
from pathlib import Path

import platformdirs

APP_NAME = "tea"

# Attachments (DECISIONS D4)
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_ATTACHMENTS_PER_BLOG = 20

# Scheduling (SPEC 4, 4.3)
REMINDER_PAUSE = timedelta(hours=2)
CATCH_UP_WINDOW = timedelta(days=7)

# Threading (ARCHITECTURE 3)
PARSE_IN_WORKER_BYTES = 200 * 1024

# Logging (ARCHITECTURE 10)
LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUPS = 3

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent


def _dir(env: str, default: Path) -> Path:
    override = os.environ.get(env)
    return Path(override) if override else default


def data_dir() -> Path:
    return _dir("TEA_DATA_DIR", platformdirs.user_data_path(APP_NAME))


def config_dir() -> Path:
    return _dir("TEA_CONFIG_DIR", platformdirs.user_config_path(APP_NAME))


def state_dir() -> Path:
    return _dir("TEA_STATE_DIR", platformdirs.user_state_path(APP_NAME))


def runtime_dir() -> Path:
    """Lock file and local socket for single instance (ARCHITECTURE 1)."""
    return _dir("TEA_RUNTIME_DIR", platformdirs.user_runtime_path(APP_NAME))


def icon_cache_dir() -> Path:
    """Recolored icon copies written by the theme."""
    return state_dir() / "icons"


def window_state_path() -> Path:
    return state_dir() / "window.ini"


def uploads_dir() -> Path:
    return data_dir() / "uploads"


def db_path() -> Path:
    return data_dir() / "tea.db"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def log_path() -> Path:
    return state_dir() / "tea.log"


def resource_dir(name: str) -> Path:
    """A bundled folder such as `data` or `prompts`.

    Installed wheels carry them inside the package; a source checkout keeps them at the repo root.
    """
    bundled = _PACKAGE_DIR / name
    return bundled if bundled.is_dir() else _REPO_ROOT / name
