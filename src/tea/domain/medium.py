"""Markdown to Medium-safe HTML and plain text, with formatting warnings (ARCHITECTURE 7).

Medium's editor has a title, two heading sizes, bold, italic, links, flat lists, block
quotes and code blocks (MEDIUM_NOTES 2). So tea emits one H1, then H2 and H3 only, and
never tables, deeper headings, nested lists, raw HTML or images. Each of those, when the
draft has it, adds one warning code. There is no disclosure line: the owner dropped it
(DEVIATIONS M1). Rendering never raises.
"""

import html
from collections.abc import Sequence
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.token import Token

# Warning codes, in the order they are first met. The UI words live in ui/import_notes.py.
TABLE = "table"
DEEP_HEADING = "deep_heading"
EXTRA_H1 = "extra_h1"
NESTED_LIST = "nested_list"
RAW_HTML = "raw_html"
IMAGE = "image"


@dataclass(frozen=True)
class MediumCopy:
    html: str
    plain: str
    warnings: list[str]


@dataclass
class _Block:
    kind: str  # h1, h2, h3, p, li, code, hr
    html: str
    plain: str
    group: int = 0  # list or quote this block belongs to (0 = none)
    ordered: bool = False
    quote: int = 0


@dataclass
class _Walker:
    blocks: list[_Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seen_h1: bool = False
    lists: list[bool] = field(default_factory=list)  # open lists, True if ordered
    list_id: int = 0
    quote_depth: int = 0
    quote_id: int = 0
    heading: str | None = None
    in_item: bool = False
    item: _Block | None = None
    row: list[str] = field(default_factory=list)
    in_row: bool = False

    def warn(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)

    def walk(self, tokens: Sequence[Token]) -> None:
        for tok in tokens:
            self.token(tok)

    def token(self, tok: Token) -> None:  # noqa: C901 (one branch per token type)
        t = tok.type
        if t == "heading_open":
            self.heading = self._heading_kind(int(tok.tag[1:]))
        elif t == "heading_close":
            self.heading = None
        elif t in ("bullet_list_open", "ordered_list_open"):
            if self.lists:
                self.warn(NESTED_LIST)
            else:
                self.list_id += 1
            self.lists.append(t == "ordered_list_open")
        elif t in ("bullet_list_close", "ordered_list_close"):
            self.lists.pop()
        elif t == "list_item_open":
            self.in_item, self.item = True, None
        elif t == "list_item_close":
            self.in_item, self.item = False, None
        elif t == "blockquote_open":
            if self.quote_depth == 0:
                self.quote_id += 1
            self.quote_depth += 1
        elif t == "blockquote_close":
            self.quote_depth -= 1
        elif t == "table_open":
            self.warn(TABLE)
        elif t == "tr_open":
            self.in_row, self.row = True, []
        elif t == "tr_close":
            self.in_row = False
            cells = [c for c in self.row if c]
            if cells:
                text = " | ".join(cells)
                self._add("p", html.escape(text, quote=False), text)
        elif t == "inline":
            self._inline(tok)
        elif t in ("fence", "code_block"):
            code = tok.content
            self._add("code", f"<pre><code>{html.escape(code, quote=False)}</code></pre>", code)
        elif t == "hr":
            self._add("hr", "<hr>", "")
        elif t == "html_block":
            self.warn(RAW_HTML)

    def _heading_kind(self, level: int) -> str:
        if level == 1:
            if not self.seen_h1:
                self.seen_h1 = True
                return "h1"
            self.warn(EXTRA_H1)
            return "h2"
        if level >= 4:
            self.warn(DEEP_HEADING)
            return "h3"
        return f"h{level}"

    def _inline(self, tok: Token) -> None:
        h, p = _render_inline(tok.children or [], self.warn)
        if self.in_row:
            self.row.append(p.strip())
            return
        if not p.strip() and not h.strip():
            return
        if self.heading is not None:
            self._add(self.heading, h, p)
        elif self.lists and self.in_item and self.item is not None:
            # A second paragraph in the same item joins it on a new line.
            self.item.html += f"<br>{h}"
            self.item.plain += f" {p}"
        elif self.lists:
            self.item = self._add("li", h, p)
        else:
            self._add("p", h, p)

    def _add(self, kind: str, h: str, p: str) -> _Block:
        block = _Block(kind, h, p)
        if self.lists and kind == "li":
            block.group, block.ordered = self.list_id, self.lists[0]
        if self.quote_depth:
            block.quote = self.quote_id
        self.blocks.append(block)
        return block


def _render_inline(children: Sequence[Token], warn: object) -> tuple[str, str]:
    """HTML and plain text for one inline run."""
    assert callable(warn)
    out_h: list[str] = []
    out_p: list[str] = []
    links: list[tuple[str, int]] = []  # href, length of plain text at the link start
    skip_image = 0
    for c in children:
        t = c.type
        if skip_image:
            skip_image -= 1
            continue
        if t == "text":
            out_h.append(html.escape(c.content, quote=False))
            out_p.append(c.content)
        elif t == "softbreak":
            out_h.append(" ")
            out_p.append(" ")
        elif t == "hardbreak":
            out_h.append("<br>")
            out_p.append("\n")
        elif t == "code_inline":
            out_h.append(f"<code>{html.escape(c.content, quote=False)}</code>")
            out_p.append(c.content)
        elif t in ("em_open", "em_close", "strong_open", "strong_close"):
            tag = "em" if t.startswith("em") else "strong"
            out_h.append(f"<{tag}>" if t.endswith("open") else f"</{tag}>")
        elif t == "link_open":
            href = str(c.attrs.get("href", ""))
            out_h.append(f'<a href="{html.escape(href)}">')
            links.append((href, len("".join(out_p))))
        elif t == "link_close":
            out_h.append("</a>")
            if links:
                href, start = links.pop()
                text = "".join(out_p)[start:]
                if href and href != text.strip():
                    out_p.append(f" ({href})")
        elif t == "image":
            warn(IMAGE)
        elif t == "html_inline":
            warn(RAW_HTML)
    return "".join(out_h).strip(), "".join(out_p).strip()


def _parser() -> MarkdownIt:
    # HTML is parsed (so it can be found and left out) but never rendered; tables are
    # parsed so they can be flattened and warned about.
    return MarkdownIt("commonmark", {"html": True}).enable("table")


def _html(blocks: list[_Block]) -> str:
    lines: list[str] = []
    open_list: tuple[int, bool] | None = None
    open_quote = 0
    for b in blocks:
        if open_list is not None and (b.kind != "li" or b.group != open_list[0]):
            lines.append("</ol>" if open_list[1] else "</ul>")
            open_list = None
        if open_quote and b.quote != open_quote:
            lines.append("</blockquote>")
            open_quote = 0
        if b.quote and not open_quote:
            lines.append("<blockquote>")
            open_quote = b.quote
        if b.kind == "li":
            if open_list is None:
                lines.append("<ol>" if b.ordered else "<ul>")
                open_list = (b.group, b.ordered)
            lines.append(f"<li>{b.html}</li>")
        elif b.kind in ("code", "hr"):
            lines.append(b.html)
        else:
            lines.append(f"<{b.kind}>{b.html}</{b.kind}>")
    if open_list is not None:
        lines.append("</ol>" if open_list[1] else "</ul>")
    if open_quote:
        lines.append("</blockquote>")
    return "\n".join(lines)


def _plain(blocks: list[_Block]) -> str:
    parts: list[str] = []
    number = 0
    prev: _Block | None = None
    for b in blocks:
        if b.kind == "hr":
            prev = b
            continue
        same_list = b.kind == "li" and prev is not None and prev.kind == "li"
        same_list = same_list and prev is not None and prev.group == b.group
        if b.kind == "li":
            number = number + 1 if same_list else 1
            text = f"{number}. {b.plain}" if b.ordered else f"- {b.plain}"
        else:
            text = b.plain.rstrip("\n")
        parts.append(("\n" if same_list else "\n\n") + text if parts else text)
        prev = b
    return "".join(parts) + "\n" if parts else ""


def render(markdown: str) -> MediumCopy:
    walker = _Walker()
    try:
        walker.walk(_parser().parse(markdown or ""))
    except Exception:  # markdown-it should never raise; if it does, paste the text as is
        text = markdown or ""
        return MediumCopy(f"<p>{html.escape(text, quote=False)}</p>", text, [])
    return MediumCopy(_html(walker.blocks), _plain(walker.blocks), walker.warnings)


def warnings(markdown: str) -> list[str]:
    return render(markdown).warnings
