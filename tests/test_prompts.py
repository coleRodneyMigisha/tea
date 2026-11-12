"""handoff/prompts: every template loads, headers match placeholders, rendering is strict."""

from pathlib import Path

import pytest

from tea.handoff import prompts
from tea.handoff.prompts import PromptError

NAMES = [
    "packet_draft",
    "packet_improve",
    "packet_audit",
    "continue",
    "blocks/attachments",
    "blocks/pick_topic",
    "blocks/research_on",
    "blocks/research_off",
]


def test_every_prompt_file_is_known() -> None:
    found = {t.name for t in prompts.all_templates()}
    assert found == {n.rsplit("/", 1)[-1] for n in NAMES}


@pytest.mark.parametrize("name", NAMES)
def test_header_variables_equal_placeholders(name: str) -> None:
    template = prompts.load(name)
    assert template.variables == prompts.placeholders(template.body)
    assert template.version >= 1
    assert template.name == name.rsplit("/", 1)[-1]


def test_research_off_has_no_variables() -> None:
    assert prompts.load("blocks/research_off").variables == frozenset()


def test_render_fills_every_variable() -> None:
    out = prompts.render("blocks/research_on", {"allowed_types": "web sources"})
    assert "web sources" in out.text
    assert "{{" not in out.text
    assert (out.name, out.version) == ("research_on", 1)


def test_render_raises_on_unfilled_variable() -> None:
    with pytest.raises(PromptError, match="allowed_types"):
        prompts.render("blocks/research_on", {})


def test_render_raises_on_unexpected_variable() -> None:
    with pytest.raises(PromptError, match="surprise"):
        prompts.render("blocks/research_on", {"allowed_types": "web", "surprise": "x"})


def test_render_does_not_expand_braces_inside_values() -> None:
    out = prompts.render("blocks/research_on", {"allowed_types": "{{allowed_types}}"})
    assert out.text.count("{{allowed_types}}") == 1


def test_empty_value_is_allowed() -> None:
    out = prompts.render("blocks/attachments", {"file_list": ""})
    assert "<attached_files>" in out.text


def _write(folder: Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(text, encoding="utf-8")


def test_header_missing_a_placeholder_raises(tmp_path: Path) -> None:
    _write(tmp_path, "bad", "---\nname: bad\nversion: 1\nvariables: a\n---\n{{a}} {{b}}\n")
    with pytest.raises(PromptError, match="b"):
        prompts.load("bad", folder=tmp_path)


def test_header_listing_an_unused_variable_raises(tmp_path: Path) -> None:
    _write(tmp_path, "bad", "---\nname: bad\nversion: 1\nvariables: a, c\n---\n{{a}}\n")
    with pytest.raises(PromptError, match="c"):
        prompts.load("bad", folder=tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        "no header at all {{a}}",
        "---\nname: bad\nvariables: a\n---\n{{a}}\n",  # no version
        "---\nname: bad\nversion: one\nvariables: a\n---\n{{a}}\n",
        "---\nname: other\nversion: 1\nvariables: a\n---\n{{a}}\n",  # name differs from file
        "---\nname: bad\nversion: 1\nvariables: a\n{{a}}\n",  # header never closed
    ],
)
def test_malformed_headers_raise(tmp_path: Path, text: str) -> None:
    _write(tmp_path, "bad", text)
    with pytest.raises(PromptError):
        prompts.load("bad", folder=tmp_path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PromptError):
        prompts.load("nope", folder=tmp_path)
