"""tea has no network code. Fail if any network module is imported under src/."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
FORBIDDEN = ["anthropic", "requests", "httpx", "urllib.request", "socket", "http.client"]


def _pattern(module: str) -> re.Pattern[str]:
    escaped = re.escape(module)
    parent, _, child = module.rpartition(".")
    alternatives = [
        rf"^\s*import\s+[^#\n]*\b{escaped}\b",
        rf"^\s*from\s+{escaped}(\.|\s)",
    ]
    if parent:
        alternatives.append(
            rf"^\s*from\s+{re.escape(parent)}\s+import\s+[^#\n]*\b{re.escape(child)}\b"
        )
    return re.compile("|".join(alternatives), re.MULTILINE)


def test_src_exists() -> None:
    assert any(SRC.rglob("*.py"))


def test_no_network_imports() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for module in FORBIDDEN:
            if _pattern(module).search(text):
                offenders.append(f"{path.relative_to(SRC)}: {module}")
    assert offenders == [], offenders
