"""Store attachment copies, enforce limits (20 files, 50 MB), list for prompts.

tea never opens, reads or uploads the owner's files (DECISIONS D4). It copies the bytes into
`<data>/uploads/<blog_id>/`, records name, extension and size, and keeps the list. Copies are
written to `<name>.part` first and renamed at the end, so a cancelled or failed copy leaves
nothing behind. A name already taken gets " (2)", " (3)" and so on; nothing is overwritten.
"""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tea import config
from tea.db.repos import Repos
from tea.db.rows import Attachment
from tea.ui import strings

CHUNK_BYTES = 1024 * 1024
NAME_MAX_BYTES = 255  # ext4 and most Linux file systems
PART = ".part"
NOTICE_KEY = "attachments_notice_shown"


class AttachmentLimitError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CopyCancelled(Exception):
    """The owner cancelled a copy; the part file is gone."""


@dataclass(frozen=True)
class Target:
    """A reserved destination: the final path and the `.part` file that holds the name."""

    final: Path
    part: Path


def blog_dir(blog_id: int) -> Path:
    return config.uploads_dir() / str(blog_id)


def kind_of(name: str) -> str:
    return Path(name).suffix.lstrip(".").lower()


def check(repos: Repos, blog_id: int, path: Path, pending: int = 0) -> str | None:
    """The message to show if `path` cannot be added, else None. `pending` counts copies
    still running for this blog. Left-out files count: they are still stored."""
    count = repos.attachments.count_for_blog(blog_id) + pending
    if count >= config.MAX_ATTACHMENTS_PER_BLOG:
        return strings.TOO_MANY_FILES
    if path.stat().st_size > config.MAX_ATTACHMENT_BYTES:
        return strings.FILE_TOO_LARGE.format(name=path.name)
    return None


def _fit(stem: str, tail: str) -> str:
    """`stem + tail`, with the stem cut so the name plus ".part" fits NAME_MAX_BYTES."""
    room = NAME_MAX_BYTES - len(PART) - len(tail.encode())
    if room < 1:  # an absurd extension: cut the whole name instead
        stem, tail = stem + tail, ""
        room = NAME_MAX_BYTES - len(PART)
    return stem.encode()[:room].decode(errors="ignore") + tail


def _candidates(name: str) -> Iterator[str]:
    stem, suffix = Path(name).stem, Path(name).suffix
    yield _fit(stem, suffix)
    n = 2
    while True:
        yield _fit(stem, f" ({n}){suffix}")
        n += 1


def reserve(blog_id: int, name: str) -> Target:
    """Claim a free name in the blog's folder by creating its `.part` file."""
    folder = blog_dir(blog_id)
    folder.mkdir(parents=True, exist_ok=True)
    for candidate in _candidates(name):
        final = folder / candidate
        part = folder / f"{candidate}{PART}"
        if final.exists():
            continue
        try:
            fd = os.open(part, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        return Target(final, part)
    raise AssertionError("unreachable")


def release(target: Target) -> None:
    target.part.unlink(missing_ok=True)


def sweep_parts() -> int:
    """Delete `.part` files left by a copy that never finished (tea was killed). Run at app
    start, before any copy can begin. Returns how many were removed."""
    root = config.uploads_dir()
    if not root.is_dir():
        return 0
    removed = 0
    for part in root.glob(f"*/*{PART}"):
        try:
            part.unlink(missing_ok=True)
        except OSError:
            continue  # a folder the owner locked; harmless, the name just stays taken
        removed += 1
    return removed


def copy_file(
    src: Path,
    target: Target,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> int:
    """Copy the bytes of `src` to `target` in chunks. Returns the size. Safe in a worker."""
    try:
        total = src.stat().st_size
        done = 0
        with src.open("rb") as fin, target.part.open("wb") as fout:
            while True:
                if cancelled is not None and cancelled():
                    raise CopyCancelled()
                chunk = fin.read(CHUNK_BYTES)
                if not chunk:
                    break
                fout.write(chunk)
                done += len(chunk)
                if done > config.MAX_ATTACHMENT_BYTES:  # the file grew after `check`
                    raise AttachmentLimitError(strings.FILE_TOO_LARGE.format(name=src.name))
                if progress is not None:
                    progress(done, total)
        if progress is not None and total == 0:
            progress(0, 0)
        os.replace(target.part, target.final)
        return done
    except BaseException:
        release(target)
        raise


def record(repos: Repos, blog_id: int, target: Target, size: int) -> Attachment:
    name = target.final.name
    return repos.attachments.add(blog_id, name, str(target.final), kind_of(name), size)


def add(repos: Repos, blog_id: int, path: Path) -> Attachment:
    """Check, copy and record in one call (no worker). Raises AttachmentLimitError."""
    message = check(repos, blog_id, path)
    if message is not None:
        raise AttachmentLimitError(message)
    target = reserve(blog_id, path.name)
    size = copy_file(path, target)
    return record(repos, blog_id, target, size)


def set_included(repos: Repos, attachment_id: int, included: bool) -> None:
    repos.attachments.set_included(attachment_id, included)


def remove(repos: Repos, attachment_id: int) -> None:
    """Delete the row and tea's stored copy. The owner's original is never touched."""
    att = repos.attachments.get(attachment_id)
    if att is None:
        return
    repos.attachments.delete(attachment_id)
    stored = Path(att.stored_path)
    if stored.parent == blog_dir(att.blog_id):
        stored.unlink(missing_ok=True)


def notice_due(repos: Repos) -> bool:
    return repos.meta.get(NOTICE_KEY) is None


def notice_shown(repos: Repos) -> None:
    repos.meta.set(NOTICE_KEY, "1")


def sweep_orphans(repos: Repos) -> int:
    """Remove empty `uploads/<id>` folders whose blog no longer exists. Never deletes a file.

    Returns how many folders were removed. Run at app start, after `sweep_parts`.
    """
    root = config.uploads_dir()
    if not root.is_dir():
        return 0
    removed = 0
    for folder in root.iterdir():
        if not (folder.is_dir() and folder.name.isdigit()):
            continue
        if repos.blogs.get(int(folder.name)) is not None:
            continue
        try:
            folder.rmdir()  # fails, and is skipped, when anything is inside
        except OSError:
            continue
        removed += 1
    return removed
