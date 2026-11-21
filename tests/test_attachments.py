"""domain/attachments: limits with exact messages, copies, leave out, remove, duplicates."""

from pathlib import Path

import pytest

from tea import config
from tea.db.repos import Repos
from tea.domain import attachments
from tea.domain.attachments import AttachmentLimitError, CopyCancelled
from tea.ui import strings

MB = 1024 * 1024


def _blog(repos: Repos) -> int:
    return repos.blogs.create("Green tea", "Green tea", "manual").id


def _file(folder: Path, name: str, size: int = 10, sparse: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if sparse:
        with path.open("wb") as f:
            f.truncate(size)
    else:
        path.write_bytes(b"x" * size)
    return path


def test_limit_messages_are_the_docs_text() -> None:
    assert strings.FILE_TOO_LARGE.format(name="report.pdf") == (
        "report.pdf is over 50 MB. Choose a smaller file or split it."
    )
    assert strings.TOO_MANY_FILES == "A blog can have up to 20 files. Remove one to add another."
    assert config.MAX_ATTACHMENT_BYTES == 50 * MB
    assert config.MAX_ATTACHMENTS_PER_BLOG == 20


def test_51_mb_file_is_rejected_with_exact_message(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    big = _file(tmp_path / "src", "report.pdf", 51 * MB, sparse=True)
    expected = "report.pdf is over 50 MB. Choose a smaller file or split it."
    assert attachments.check(repos, blog, big) == expected
    with pytest.raises(AttachmentLimitError) as err:
        attachments.add(repos, blog, big)
    assert err.value.message == expected
    assert repos.attachments.list_for_blog(blog) == []
    assert not attachments.blog_dir(blog).exists() or not any(attachments.blog_dir(blog).iterdir())


def test_exactly_50_mb_is_allowed(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    edge = _file(tmp_path / "src", "edge.bin", 50 * MB, sparse=True)
    assert attachments.check(repos, blog, edge) is None
    one_more = _file(tmp_path / "src", "over.bin", 50 * MB + 1, sparse=True)
    assert attachments.check(repos, blog, one_more) is not None


def test_21st_file_is_rejected_with_exact_message(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    for i in range(20):
        attachments.add(repos, blog, _file(tmp_path / "src", f"f{i}.txt"))
    extra = _file(tmp_path / "src", "f20.txt")
    expected = "A blog can have up to 20 files. Remove one to add another."
    assert attachments.check(repos, blog, extra) == expected
    with pytest.raises(AttachmentLimitError) as err:
        attachments.add(repos, blog, extra)
    assert err.value.message == expected
    assert repos.attachments.count_for_blog(blog) == 20


def test_left_out_files_still_count_and_pending_copies_count(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    for i in range(18):
        att = attachments.add(repos, blog, _file(tmp_path / "src", f"f{i}.txt"))
        attachments.set_included(repos, att.id, False)
    extra = _file(tmp_path / "src", "x.txt")
    assert attachments.check(repos, blog, extra) is None
    assert attachments.check(repos, blog, extra, pending=1) is None
    assert attachments.check(repos, blog, extra, pending=2) == strings.TOO_MANY_FILES


def test_limit_is_per_blog(repos: Repos, tmp_path: Path) -> None:
    a, b = _blog(repos), _blog(repos)
    for i in range(20):
        attachments.add(repos, a, _file(tmp_path / "src", f"f{i}.txt"))
    assert attachments.check(repos, b, _file(tmp_path / "src", "x.txt")) is None


def test_copy_goes_to_uploads_blog_folder(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    src = _file(tmp_path / "src", "Notes.DOCX", 1234)
    att = attachments.add(repos, blog, src)
    stored = Path(att.stored_path)
    assert stored == config.data_dir() / "uploads" / str(blog) / "Notes.DOCX"
    assert stored.read_bytes() == src.read_bytes()
    assert src.exists()  # the original is never moved
    assert (att.filename, att.kind, att.size_bytes, att.include_in_list) == (
        "Notes.DOCX", "docx", 1234, True,
    )  # fmt: skip
    assert not list(stored.parent.glob("*.part"))


def test_file_without_extension(repos: Repos, tmp_path: Path) -> None:
    att = attachments.add(repos, _blog(repos), _file(tmp_path / "src", "README"))
    assert att.kind == ""


def test_duplicate_names_get_a_suffix_and_never_overwrite(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    first = attachments.add(repos, blog, _file(tmp_path / "a", "notes.docx", 10))
    second = attachments.add(repos, blog, _file(tmp_path / "b", "notes.docx", 20))
    third = attachments.add(repos, blog, _file(tmp_path / "c", "notes.docx", 30))
    assert [first.filename, second.filename, third.filename] == [
        "notes.docx", "notes (2).docx", "notes (3).docx",
    ]  # fmt: skip
    assert [Path(a.stored_path).stat().st_size for a in (first, second, third)] == [10, 20, 30]
    assert third.kind == "docx"


def test_reserve_skips_names_being_copied(repos: Repos) -> None:
    blog = _blog(repos)
    one = attachments.reserve(blog, "a.pdf")
    two = attachments.reserve(blog, "a.pdf")
    assert one.final.name == "a.pdf" and two.final.name == "a (2).pdf"
    assert one.part.exists() and two.part.exists()


def test_leave_out_keeps_the_file_and_include_brings_it_back(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    att = attachments.add(repos, blog, _file(tmp_path / "src", "a.pdf"))
    attachments.set_included(repos, att.id, False)
    assert repos.attachments.list_for_blog(blog, included_only=True) == []
    assert Path(att.stored_path).exists()
    assert repos.attachments.count_for_blog(blog) == 1
    attachments.set_included(repos, att.id, True)
    assert [a.id for a in repos.attachments.list_for_blog(blog, included_only=True)] == [att.id]


def test_remove_deletes_row_and_stored_copy(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    src = _file(tmp_path / "src", "a.pdf")
    att = attachments.add(repos, blog, src)
    attachments.remove(repos, att.id)
    assert repos.attachments.get(att.id) is None
    assert not Path(att.stored_path).exists()
    assert src.exists()
    attachments.remove(repos, att.id)  # a second remove is harmless


def test_remove_tolerates_a_missing_copy(repos: Repos, tmp_path: Path) -> None:
    att = attachments.add(repos, _blog(repos), _file(tmp_path / "src", "a.pdf"))
    Path(att.stored_path).unlink()
    attachments.remove(repos, att.id)
    assert repos.attachments.get(att.id) is None


def test_copy_reports_progress(tmp_path: Path) -> None:
    src = _file(tmp_path / "src", "big.bin", 3 * MB + 5)
    target = attachments.reserve(1, "big.bin")
    seen: list[tuple[int, int]] = []
    size = attachments.copy_file(src, target, progress=lambda d, t: seen.append((d, t)))
    assert size == 3 * MB + 5
    assert target.final.read_bytes() == src.read_bytes()
    assert not target.part.exists()
    assert seen[-1] == (3 * MB + 5, 3 * MB + 5)
    assert len(seen) >= 3 and all(t == 3 * MB + 5 for _, t in seen)


def test_cancelled_copy_leaves_nothing(tmp_path: Path) -> None:
    src = _file(tmp_path / "src", "big.bin", 3 * MB)
    target = attachments.reserve(1, "big.bin")
    calls = {"n": 0}

    def cancelled() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(CopyCancelled):
        attachments.copy_file(src, target, cancelled=cancelled)
    assert not target.part.exists() and not target.final.exists()


def test_failed_copy_leaves_nothing(tmp_path: Path) -> None:
    target = attachments.reserve(1, "gone.bin")
    with pytest.raises(OSError):
        attachments.copy_file(tmp_path / "missing.bin", target)
    assert not target.part.exists() and not target.final.exists()


def test_first_notice_shows_once(repos: Repos) -> None:
    assert attachments.notice_due(repos)
    attachments.notice_shown(repos)
    assert not attachments.notice_due(repos)


def test_module_never_opens_files_for_reading_content() -> None:
    source = Path(attachments.__file__).read_text()
    for banned in ("import zipfile", "import mimetypes", "PdfReader", "docx", ".read_text("):
        assert banned not in source


def test_long_names_fit_the_file_system(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    stem = "é" * 140  # 280 bytes in UTF-8
    target = attachments.reserve(blog, stem + ".pdf")
    assert len(target.part.name.encode()) <= 255
    assert target.final.name.endswith(".pdf")
    target.part.rename(target.final)
    again = attachments.reserve(blog, stem + ".pdf")
    assert again.final.name.endswith(" (2).pdf") and len(again.part.name.encode()) <= 255
    odd = attachments.reserve(blog, "a." + "x" * 300)
    assert len(odd.part.name.encode()) <= 255


def test_long_name_can_be_added(repos: Repos, tmp_path: Path) -> None:
    name = "n" * 251  # fits on disk, but not with ".part" added
    src = tmp_path / "src"
    src.mkdir()
    (src / name).write_bytes(b"x")
    att = attachments.add(repos, _blog(repos), src / name)
    assert Path(att.stored_path).exists() and len(att.filename.encode()) <= 250


def test_copy_stops_when_a_file_grows_past_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "MAX_ATTACHMENT_BYTES", 2 * MB)
    src = _file(tmp_path / "src", "grew.bin", 3 * MB)
    target = attachments.reserve(1, "grew.bin")
    with pytest.raises(AttachmentLimitError) as err:
        attachments.copy_file(src, target)
    assert err.value.message == strings.FILE_TOO_LARGE.format(name="grew.bin")
    assert not target.part.exists() and not target.final.exists()


def test_sweep_removes_stale_part_files(repos: Repos, tmp_path: Path) -> None:
    blog = _blog(repos)
    stale = attachments.reserve(blog, "a.pdf")
    kept = attachments.add(repos, blog, _file(tmp_path / "src", "b.pdf"))
    assert attachments.sweep_parts() == 1
    assert not stale.part.exists() and Path(kept.stored_path).exists()
    assert attachments.reserve(blog, "a.pdf").final.name == "a.pdf"


def test_sweep_without_uploads_folder() -> None:
    assert attachments.sweep_parts() == 0


def test_sweep_removes_empty_folders_of_deleted_blogs_only(repos: Repos, tmp_path: Path) -> None:
    kept = repos.blogs.create("Kept", "Kept", "manual")
    src = tmp_path / "a.txt"
    src.write_text("x")
    attachments.add(repos, kept.id, src)
    empty_orphan = config.uploads_dir() / "9999"
    empty_orphan.mkdir(parents=True)
    full_orphan = config.uploads_dir() / "9998"
    full_orphan.mkdir()
    (full_orphan / "precious.pdf").write_text("x")
    other = config.uploads_dir() / "not-a-blog"
    other.mkdir()
    assert attachments.sweep_orphans(repos) == 1
    assert not empty_orphan.exists()
    assert full_orphan.exists() and other.exists()  # never deletes files, nor odd folders
    assert attachments.blog_dir(kept.id).exists()
