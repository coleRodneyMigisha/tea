"""CLI surface tests (ARCHITECTURE section 12)."""

import subprocess
import sys

COMMANDS = [
    "packet",
    "import-reply",
    "login-questions",
    "install-autostart",
    "uninstall-autostart",
    "doctor",
]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tea", *args], capture_output=True, text=True, timeout=60
    )


def test_help_lists_every_command() -> None:
    result = _run("--help")
    assert result.returncode == 0
    for command in COMMANDS:
        assert command in result.stdout
    assert "--background" in result.stdout


def test_unknown_command_exits_nonzero() -> None:
    result = _run("no-such-command")
    assert result.returncode != 0


def test_packet_accepts_week_and_kind() -> None:
    # An empty database has no blog for that week: a clean error, not a usage error.
    result = _run("packet", "--week", "2026-11-09", "--kind", "weekly_pick")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_packet_rejects_bad_kind() -> None:
    result = _run("packet", "--kind", "nope")
    assert result.returncode != 0


def test_import_reply_requires_file() -> None:
    result = _run("import-reply")
    assert result.returncode != 0
