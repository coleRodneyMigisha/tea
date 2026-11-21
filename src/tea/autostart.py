"""`tea install-autostart` and `uninstall-autostart` (ARCHITECTURE 11, UBUNTU_NOTES 5).

Renders `desktop/*.desktop` with the absolute path to the `tea` command and installs the icons.
Everything written is listed in `_entries`, so uninstalling removes exactly that and any folder
it leaves empty.
"""

import os
import shutil
import sys
from pathlib import Path

from tea import config
from tea.ui import strings

PLACEHOLDER = "__TEA_BIN__"
AUTOSTART_NAME = "tea-autostart.desktop"
LAUNCHER_NAME = "tea.desktop"
ICON_NAMES = ("tea.svg", "tea-attention.svg")


class AutostartError(RuntimeError):
    """The entries could not be written."""


def _base(env: str, fallback: str) -> Path:
    value = os.environ.get(env)
    return Path(value) if value else Path.home() / fallback


def config_home() -> Path:
    return _base("XDG_CONFIG_HOME", ".config")


def data_home() -> Path:
    return _base("XDG_DATA_HOME", ".local/share")


def autostart_path() -> Path:
    return config_home() / "autostart" / AUTOSTART_NAME


def launcher_path() -> Path:
    return data_home() / "applications" / LAUNCHER_NAME


def icon_dir() -> Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps"


def _entries() -> list[Path]:
    return [autostart_path(), launcher_path(), *(icon_dir() / name for name in ICON_NAMES)]


def is_installed() -> bool:
    return autostart_path().is_file() and launcher_path().is_file()


def find_bin() -> str | None:
    """The absolute path of the `tea` command: on PATH, else next to the running Python."""
    found = shutil.which("tea")
    if found:
        return str(Path(found).absolute())
    beside = Path(sys.executable).parent / "tea"
    return str(beside) if beside.is_file() else None


def _exec_path(tea_bin: str) -> str:
    """Desktop Entry spec: quote a command that has spaces."""
    if any(ch in tea_bin for ch in " \t\"'\\$`"):
        escaped = tea_bin.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return tea_bin


def _write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    if isinstance(text, bytes):
        tmp.write_bytes(text)
    else:
        tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def install(tea_bin: str | None = None) -> list[Path]:
    """Write the entries and icons. Safe to repeat. Returns the files written."""
    tea_bin = tea_bin or find_bin()
    if tea_bin is None:
        raise AutostartError(strings.AUTOSTART_NO_BIN)
    desktop = config.resource_dir("desktop")
    icons = config.resource_dir("assets")
    jobs: list[tuple[Path, str | bytes]] = []
    try:
        for target, name in ((autostart_path(), AUTOSTART_NAME), (launcher_path(), LAUNCHER_NAME)):
            text = (desktop / name).read_text(encoding="utf-8")
            jobs.append((target, text.replace(PLACEHOLDER, _exec_path(tea_bin))))
        for name in ICON_NAMES:
            jobs.append((icon_dir() / name, (icons / name).read_bytes()))
        for path, content in jobs:
            _write(path, content)
    except OSError as exc:
        raise AutostartError(strings.AUTOSTART_FAILED.format(error=exc.strerror or exc)) from exc
    return [path for path, _ in jobs]


def _prune(folder: Path, stop: Path) -> None:
    """Remove `folder` and its parents while they are empty (rmdir refuses a folder with files).

    Never removes `stop` or anything above it.
    """
    while folder != stop and stop in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def uninstall() -> list[Path]:
    """Remove what `install` wrote, and the folders that leaves empty. Returns the files removed."""
    removed: list[Path] = []
    for path in _entries():
        if not path.is_file():
            continue
        path.unlink()
        removed.append(path)
        _prune(path.parent, Path.home())
    return removed


def run_install() -> int:
    try:
        written = install()
    except AutostartError as exc:
        print(f"tea: {exc}", file=sys.stderr)
        return 1
    print(strings.AUTOSTART_INSTALLED.format(count=len(written)))
    return 0


def run_uninstall() -> int:
    removed = uninstall()
    print(strings.AUTOSTART_REMOVED.format(count=len(removed)))
    return 0
