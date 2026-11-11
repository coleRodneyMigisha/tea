"""Load prompts/*.md and prompts/blocks/*.md, check variables, render.

Each file starts with a header (see prompts/README.md):

    ---
    name: <file name without .md>
    version: <integer>
    variables: comma-separated list of every {{variable}} used
    ---
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tea import config

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class PromptError(ValueError):
    """A prompt file is missing or malformed, or rendering got the wrong variables."""


@dataclass(frozen=True)
class Template:
    name: str
    version: int
    variables: frozenset[str]
    body: str


@dataclass(frozen=True)
class Rendered:
    text: str
    name: str
    version: int


def prompts_dir() -> Path:
    return config.resource_dir("prompts")


def placeholders(body: str) -> frozenset[str]:
    return frozenset(PLACEHOLDER.findall(body))


def _parse(path: Path, text: str) -> Template:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise PromptError(f"{path.name}: missing '---' header")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise PromptError(f"{path.name}: header is not closed with '---'")
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    missing = {"name", "version", "variables"} - set(fields)
    if missing:
        raise PromptError(f"{path.name}: header lacks {sorted(missing)}")
    if fields["name"] != path.stem:
        raise PromptError(f"{path.name}: header name {fields['name']!r} differs from file name")
    try:
        version = int(fields["version"])
    except ValueError:
        raise PromptError(f"{path.name}: version must be an integer") from None
    declared = frozenset(v.strip() for v in fields["variables"].split(",") if v.strip())
    body = text[end + len("\n---\n") :]
    used = placeholders(body)
    if declared != used:
        raise PromptError(
            f"{path.name}: header variables differ from placeholders; "
            f"undeclared {sorted(used - declared)}, unused {sorted(declared - used)}"
        )
    return Template(fields["name"], version, declared, body)


def load(name: str, folder: Path | None = None) -> Template:
    """Load `name` (for example "packet_draft" or "blocks/pick_topic")."""
    path = (folder or prompts_dir()) / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PromptError(f"{path.name} could not be read: {exc.__class__.__name__}") from exc
    return _parse(path, text)


def all_templates(folder: Path | None = None) -> list[Template]:
    root = folder or prompts_dir()
    paths = sorted(root.glob("*.md")) + sorted((root / "blocks").glob("*.md"))
    names = [str(p.relative_to(root).with_suffix("")) for p in paths if p.name != "README.md"]
    return [load(n, root) for n in names]


def render(name: str, values: Mapping[str, str], folder: Path | None = None) -> Rendered:
    """Fill every placeholder. Raise on an unfilled or unexpected variable."""
    template = load(name, folder)
    unexpected = set(values) - template.variables
    if unexpected:
        raise PromptError(f"{template.name}: unexpected variables {sorted(unexpected)}")
    unfilled = template.variables - set(values)
    if unfilled:
        raise PromptError(f"{template.name}: unfilled variables {sorted(unfilled)}")
    # One pass, so braces inside a value are never expanded again.
    text = PLACEHOLDER.sub(lambda m: values[m.group(1)], template.body)
    return Rendered(text, template.name, template.version)
