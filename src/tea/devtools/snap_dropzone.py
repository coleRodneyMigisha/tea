"""Snapshot states for the attachment dropzone (UI_DESIGN 3.2), drawn inside a form panel.

Qt is imported inside the builders, so `snap` can set QT_QPA_PLATFORM before Qt loads.
"""

from collections.abc import Callable
from typing import Any

from tea import config
from tea.clock import Clock
from tea.db.repos import Repos

MB = 1024 * 1024
FILES = (("report-2025.pdf", 42 * MB), ("notes.docx", 180 * 1024), ("interview.m4a", 9 * MB))


def _source(name: str, size: int) -> Any:
    folder = config.data_dir() / "snap-sources"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    with path.open("wb") as f:
        f.truncate(size)  # sparse: the snapshot never writes real megabytes
    return path


def _stored(repos: Repos, blog: int, name: str, size: int) -> Any:
    """A listed file without copying megabytes: the dropzone only shows name and size."""
    from tea.domain import attachments

    target = attachments.reserve(blog, name)
    target.part.rename(target.final)
    return repos.attachments.add(blog, name, str(target.final), attachments.kind_of(name), size)


def _panel(theme: Any, repos: Repos, setup: Callable[[Any, int], None] | None) -> Any:
    from PySide6.QtWidgets import QFrame, QVBoxLayout

    from tea.ui.widgets.dropzone import Dropzone

    blog = repos.blogs.create("Green tea at work", "Green tea at work", "manual").id
    panel = QFrame()
    panel.setObjectName("Panel")
    panel.setFixedWidth(theme.size("form_max_width"))
    layout = QVBoxLayout(panel)
    pad = theme.size("panel_padding")
    layout.setContentsMargins(pad, pad, pad, pad)
    dropzone = Dropzone(theme, repos, blog)
    layout.addWidget(dropzone)
    if setup is not None:
        setup(dropzone, blog)
    panel.adjustSize()
    return panel


def _state(setup: Callable[[Any, int], None] | None = None) -> Callable[[Any, Repos, Clock], Any]:
    def build(theme: Any, repos: Repos, clock: Clock) -> Any:
        return _panel(theme, repos, setup)

    return build


def _with_files(first_time: bool) -> Callable[[Any, int], None]:
    def setup(dz: Any, blog: int) -> None:
        from tea.domain import attachments

        if not first_time:
            attachments.notice_shown(dz.repos)
        for name, size in FILES:
            att = _stored(dz.repos, blog, name, size)
            if name == "interview.m4a":
                attachments.set_included(dz.repos, att.id, False)
        if first_time:
            attachments.notice_shown(dz.repos)
            dz.notice.setVisible(True)
        dz.refresh()

    return setup


def _drag_over(dz: Any, blog: int) -> None:
    dz.area.set_drag_over(True)


def _copying(dz: Any, blog: int) -> None:
    from tea.domain import attachments

    attachments.notice_shown(dz.repos)
    _stored(dz.repos, blog, "notes.docx", 180 * 1024)
    dz.refresh()
    entry = dz.copy_row("report-2025.pdf", 42 * MB)
    entry.bar.setValue(entry.bar.maximum() * 2 // 5)


def _too_large(dz: Any, blog: int) -> None:
    dz.add_paths([_source("report.pdf", 51 * MB)])


def _too_many(dz: Any, blog: int) -> None:
    from tea.domain import attachments

    attachments.notice_shown(dz.repos)
    for i in range(20):
        _stored(dz.repos, blog, f"source-{i + 1:02d}.pdf", 64 * 1024)
    dz.refresh()
    dz.add_paths([_source("one-more.pdf", 1024)])


def register_all(register: Callable[[str, str, Any], None], state: Callable[..., Any]) -> None:
    name = "dropzone"
    register(name, "empty", state(name, build=_state()))
    register(name, "drag_over", state(name, build=_state(_drag_over)))
    register(name, "files", state(name, build=_state(_with_files(False))))
    register(name, "first_file", state(name, build=_state(_with_files(True))))
    register(name, "copying", state(name, build=_state(_copying)))
    register(name, "too_large", state(name, build=_state(_too_large)))
    register(name, "too_many", state(name, build=_state(_too_many)))
