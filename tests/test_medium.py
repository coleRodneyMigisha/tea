"""domain/medium: Medium-safe HTML, plain text and formatting warnings (TESTING 3)."""

from pathlib import Path

import pytest

from tea.devtools import sample_replies
from tea.domain import medium
from tea.handoff.parse import parse

GOLDEN = Path(__file__).resolve().parent / "golden" / "medium"


def test_title_paragraph_and_subheadings() -> None:
    out = medium.render("# Title\n\nA *short* **post**.\n\n## Part one\n\n### Detail\n")
    assert out.html == (
        "<h1>Title</h1>\n<p>A <em>short</em> <strong>post</strong>.</p>\n"
        "<h2>Part one</h2>\n<h3>Detail</h3>"
    )
    assert out.plain == "Title\n\nA short post.\n\nPart one\n\nDetail\n"
    assert out.warnings == []


def test_deep_headings_are_capped_at_h3_with_a_warning() -> None:
    out = medium.render("# T\n\n#### Four\n\n###### Six\n")
    assert "<h4>" not in out.html and "<h6>" not in out.html
    assert out.html.count("<h3>") == 2
    assert out.warnings == ["deep_heading"]


def test_only_one_h1_later_ones_become_h2() -> None:
    out = medium.render("# Title\n\nText.\n\n# Another top heading\n")
    assert out.html.count("<h1>") == 1
    assert "<h2>Another top heading</h2>" in out.html
    assert out.warnings == ["extra_h1"]


def test_tables_are_never_emitted() -> None:
    md = "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter.\n"
    out = medium.render(md)
    assert "<table" not in out.html and "<td" not in out.html
    assert "<p>a | b</p>" in out.html and "<p>1 | 2</p>" in out.html
    assert "table" in out.warnings


def test_nested_lists_are_flattened_with_a_warning() -> None:
    md = "# T\n\n- one\n  - one a\n  - one b\n- two\n"
    out = medium.render(md)
    assert out.html.count("<ul>") == 1
    assert "<li>one</li>\n<li>one a</li>\n<li>one b</li>\n<li>two</li>" in out.html
    assert out.warnings == ["nested_list"]
    assert "- one\n- one a\n- one b\n- two" in out.plain


def test_ordered_list_and_plain_numbers() -> None:
    out = medium.render("1. first\n2. second\n")
    assert out.html == "<ol>\n<li>first</li>\n<li>second</li>\n</ol>"
    assert out.plain == "1. first\n2. second\n"


def test_images_are_left_out_with_a_warning() -> None:
    out = medium.render("Look ![a cat](cat.png) here.\n")
    assert "<img" not in out.html and "cat.png" not in out.plain
    assert out.warnings == ["image"]


def test_raw_html_is_left_out_with_a_warning() -> None:
    out = medium.render("<div>boxed</div>\n\nText with <span>inline</span> html.\n")
    assert "<div>" not in out.html and "<span>" not in out.html
    assert "raw_html" in out.warnings


def test_links_quotes_and_code() -> None:
    md = (
        "See [the study](https://example.org/s?a=1&b=2).\n\n"
        "> A quoted line.\n\n```\ncode <here>\n```\n\nUse `x < y` inline.\n"
    )
    out = medium.render(md)
    assert '<a href="https://example.org/s?a=1&amp;b=2">the study</a>' in out.html
    assert "<blockquote>\n<p>A quoted line.</p>\n</blockquote>" in out.html
    assert "<pre><code>code &lt;here&gt;\n</code></pre>" in out.html
    assert "<code>x &lt; y</code>" in out.html
    assert "See the study (https://example.org/s?a=1&b=2)." in out.plain
    assert "code <here>" in out.plain
    assert out.warnings == []


def test_text_is_escaped() -> None:
    out = medium.render("Fish & chips <b>bold</b>\n")
    assert "Fish &amp; chips" in out.html
    assert "<b>" not in out.html


def test_empty_and_whitespace_never_raise() -> None:
    for md in ("", "   \n\n", "#", "-", "```"):
        out = medium.render(md)
        assert isinstance(out.html, str) and isinstance(out.plain, str)


def test_warnings_listed_once_in_document_order() -> None:
    md = "#### a\n\n![i](x.png)\n\n##### b\n\n![j](y.png)\n"
    assert medium.render(md).warnings == ["deep_heading", "image"]


@pytest.mark.parametrize("name", ["sample_draft"])
def test_golden(name: str) -> None:
    """The sample weekly draft, rendered exactly as the checked-in golden files."""
    md = parse(sample_replies.WEEKLY).draft_markdown or ""
    out = medium.render(md)
    assert out.html == (GOLDEN / f"{name}.html").read_text().rstrip("\n")
    assert out.plain == (GOLDEN / f"{name}.txt").read_text()
    assert out.warnings == []


def test_no_disclosure_line_is_ever_inserted() -> None:
    """Owner dropped the AI disclosure (DEVIATIONS M1)."""
    out = medium.render("# T\n\nOne.\n\nTwo.\n")
    assert out.html == "<h1>T</h1>\n<p>One.</p>\n<p>Two.</p>"
