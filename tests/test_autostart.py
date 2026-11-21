"""tea install-autostart and uninstall-autostart (M10, UBUNTU_NOTES 5, ARCHITECTURE 11)."""

import subprocess
import sys
from pathlib import Path

import pytest

from tea import autostart


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return h


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_install_writes_entries_with_the_absolute_path(home: Path) -> None:
    written = autostart.install(tea_bin="/opt/bin/tea")
    auto = home / ".config/autostart/tea-autostart.desktop"
    launcher = home / ".local/share/applications/tea.desktop"
    icon = home / ".local/share/icons/hicolor/scalable/apps/tea.svg"
    assert {auto, launcher, icon} <= set(written)
    assert "Exec=/opt/bin/tea --background" in auto.read_text()
    assert "X-GNOME-Autostart-Delay=8" in auto.read_text()
    assert "Exec=/opt/bin/tea\n" in launcher.read_text()
    for path in written:
        assert "__TEA_BIN__" not in path.read_text()
    assert icon.read_text().lstrip().startswith("<svg") or "<svg" in icon.read_text()


def test_install_then_uninstall_leaves_the_file_system_as_it_was(home: Path) -> None:
    before = _tree(home)
    autostart.install(tea_bin="/opt/bin/tea")
    assert _tree(home) != before
    removed = autostart.uninstall()
    assert removed
    assert _tree(home) == before


def test_uninstall_keeps_other_files_and_the_folders_that_hold_them(home: Path) -> None:
    other = home / ".config/autostart/other.desktop"
    other.parent.mkdir(parents=True)
    other.write_text("[Desktop Entry]\n")
    (home / ".local/share/applications").mkdir(parents=True)
    (home / ".local/share/applications/mine.desktop").write_text("[Desktop Entry]\n")
    before = _tree(home)
    autostart.install(tea_bin="/opt/bin/tea")
    autostart.uninstall()
    assert other.read_text() == "[Desktop Entry]\n"
    assert _tree(home) == before


def test_install_twice_is_the_same_as_once(home: Path) -> None:
    autostart.install(tea_bin="/opt/bin/tea")
    once = {p: p.read_text() for p in home.rglob("*") if p.is_file()}
    autostart.install(tea_bin="/opt/bin/tea")
    assert {p: p.read_text() for p in home.rglob("*") if p.is_file()} == once


def test_uninstall_without_install_does_nothing(home: Path) -> None:
    assert autostart.uninstall() == []
    assert _tree(home) == []


def test_paths_with_spaces_are_quoted(home: Path) -> None:
    autostart.install(tea_bin="/opt/my tools/tea")
    text = (home / ".config/autostart/tea-autostart.desktop").read_text()
    assert 'Exec="/opt/my tools/tea" --background' in text


def test_xdg_folders_are_respected(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    autostart.install(tea_bin="/opt/bin/tea")
    assert (home / "cfg/autostart/tea-autostart.desktop").is_file()
    assert (home / "data/applications/tea.desktop").is_file()


def test_find_bin_uses_path_then_the_running_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: "/usr/bin/tea")
    assert autostart.find_bin() == "/usr/bin/tea"
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: None)
    fake = tmp_path / "venv" / "bin"
    fake.mkdir(parents=True)
    (fake / "tea").write_text("#!/bin/sh\n")
    monkeypatch.setattr(autostart.sys, "executable", str(fake / "python"))
    assert autostart.find_bin() == str(fake / "tea")
    (fake / "tea").unlink()
    assert autostart.find_bin() is None


def test_install_without_a_tea_command_says_what_to_do(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(autostart, "find_bin", lambda: None)
    assert autostart.run_install() == 1
    assert "pipx" in capsys.readouterr().err
    assert _tree(home) == []


def test_commands_run_from_the_cli(home: Path, tmp_path: Path) -> None:
    import os

    fake = tmp_path / "bin"
    fake.mkdir()
    exe = fake / "tea"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": f"{fake}:{os.environ['PATH']}"}
    env.pop("XDG_CONFIG_HOME", None)
    env.pop("XDG_DATA_HOME", None)
    run = lambda *a: subprocess.run(  # noqa: E731
        [sys.executable, "-m", "tea", *a], capture_output=True, text=True, timeout=60, env=env
    )
    before = _tree(home)
    r = run("install-autostart")
    assert r.returncode == 0, r.stderr
    assert (home / ".config/autostart/tea-autostart.desktop").is_file()
    r = run("uninstall-autostart")
    assert r.returncode == 0, r.stderr
    assert _tree(home) == before
