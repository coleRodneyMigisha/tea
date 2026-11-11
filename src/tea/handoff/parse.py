"""Lenient parser for pasted replies (docs/PASTE_FORMAT.md). Never raises."""

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

SECTIONS = ("topic_candidates", "topic", "draft", "verification", "sources", "flags", "changes")
_TAG = re.compile(r"<\s*(/?)\s*(" + "|".join(SECTIONS) + r")\s*>", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(```|~~~)[^\n]*$")
_H1 = re.compile(r"^#[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_TABLE_RULE = re.compile(r"^[\s|:-]+$")

STATUS = {
    "supported": "supported",
    "verified": "supported",
    "ok": "supported",
    "weak": "weak",
    "partial": "weak",
    "partially": "weak",
    "partially supported": "weak",
    "unsupported": "unsupported",
    "unverified": "unsupported",
    "not supported": "unsupported",
}


@dataclass(frozen=True)
class TopicCandidate:
    n: int
    topic: str
    angle: str
    why: str
    urls: list[str]


@dataclass(frozen=True)
class Claim:
    status: str
    claim: str
    source: str
    note: str


@dataclass(frozen=True)
class SourceRef:
    title: str
    publisher: str
    location: str


@dataclass
class ParsedReply:
    title: str | None = None
    draft_markdown: str | None = None
    topic: str | None = None
    candidates: list[TopicCandidate] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass(frozen=True)
class _Section:
    name: str
    start: int  # of the opening tag
    end: int  # after the closing tag, or where the content stops
    content: str
    closed: bool


def parse(raw: str) -> ParsedReply:
    """Parse whatever was pasted. Any unexpected failure still returns the raw text as the draft."""
    try:
        return _parse(raw if isinstance(raw, str) else str(raw or ""), raw)
    except Exception as exc:  # the parser must never raise
        log.warning("parse_failed error=%s", exc.__class__.__name__)
        text = raw if isinstance(raw, str) else ""
        return ParsedReply(
            draft_markdown=text.strip() or None,
            warnings=["no_draft_tag", "no_verification"],
            raw=text,
        )


def _parse(text: str, raw: object) -> ParsedReply:
    out = ParsedReply(raw=raw if isinstance(raw, str) else text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    sections = _sections(text)
    found = {s.name: s for s in sections}

    draft = found.get("draft")
    if draft is not None:
        out.draft_markdown = _unfence(draft.content) or None
    else:
        out.warnings.append("no_draft_tag")
        out.draft_markdown = _untagged_draft(text, sections) or None
    if out.draft_markdown:
        m = _H1.search(out.draft_markdown)
        out.title = m.group(1).strip() if m else None

    for s in sections:
        if not s.closed and s is sections[-1]:
            out.warnings.append(f"truncated:{s.name}")

    if "verification" in found:
        out.claims = _claims(found["verification"].content, out.warnings)
    else:
        out.warnings.append("no_verification")
    if "topic" in found:
        lines = _lines(found["topic"].content)
        out.topic = (lines[0].strip("*_\"'` ") or None) if lines else None
    if "topic_candidates" in found:
        out.candidates = _candidates(found["topic_candidates"].content)
    if "sources" in found:
        out.sources = _sources(found["sources"].content)
    if "flags" in found:
        out.flags = _bullets(found["flags"].content)
    if "changes" in found:
        out.changes = _bullets(found["changes"].content)
    # unknown_status is recorded where it is found; keep the documented order otherwise.
    if "unknown_status" in out.warnings:
        out.warnings.remove("unknown_status")
        out.warnings.append("unknown_status")
    return out


def _sections(text: str) -> list[_Section]:
    """The first occurrence of each known section, in reply order."""
    tags = list(_TAG.finditer(text))
    sections: list[_Section] = []
    seen: set[str] = set()
    i = 0
    while i < len(tags):
        m = tags[i]
        name = m.group(2).lower()
        if m.group(1) or name in seen:
            i += 1
            continue
        seen.add(name)
        close = next(
            (
                j
                for j in range(i + 1, len(tags))
                if tags[j].group(1) and tags[j].group(2).lower() == name
            ),
            None,
        )
        if close is not None:
            c = tags[close]
            sections.append(_Section(name, m.start(), c.end(), text[m.end() : c.start()], True))
            i = close + 1
            continue
        nxt = next((j for j in range(i + 1, len(tags)) if not tags[j].group(1)), None)
        stop = tags[nxt].start() if nxt is not None else len(text)
        sections.append(_Section(name, m.start(), stop, text[m.end() : stop], False))
        i = nxt if nxt is not None else len(tags)
    return sections


def _unfence(text: str) -> str:
    """Strip whitespace and a code fence wrapped around the whole text."""
    lines = text.strip().split("\n")
    if lines and _FENCE.match(lines[0]):
        lines = lines[1:]
        if lines and _FENCE.match(lines[-1]):
            lines = lines[:-1]
    elif lines and _FENCE.match(lines[-1]) and sum(bool(_FENCE.match(ln)) for ln in lines) % 2:
        lines = lines[:-1]  # the closing half of a fence opened outside this text
    return "\n".join(lines).strip()


def _untagged_draft(text: str, sections: list[_Section]) -> str:
    """The whole reply minus the recognised sections, any wrapping fence and a preamble line."""
    parts, pos = [], 0
    for s in sections:
        parts.append(text[pos : s.start])
        pos = s.end
    parts.append(text[pos:])
    rest = _TAG.sub("", "".join(parts)).strip()  # drop stray closing tags
    first, _, after = rest.partition("\n")
    if after.strip() and _is_preamble(first):
        rest = after
    return _unfence(rest)


def _is_preamble(line: str) -> bool:
    line = line.strip()
    return line.endswith(":") and not line.startswith("#") and len(line.split()) <= 20


def _lines(content: str) -> list[str]:
    return [ln.strip() for ln in _unfence(content).split("\n") if ln.strip()]


def _fields(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):  # Markdown table row
        line = line.strip("|")
    sep = " | " if " | " in line else "|"
    return [f.strip() for f in line.split(sep)]


def _claims(content: str, warnings: list[str]) -> list[Claim]:
    claims = []
    for line in _lines(content):
        if "|" not in line or _TABLE_RULE.match(line):
            continue
        parts = _fields(_BULLET.sub("", line))
        given = parts[0]
        if given.lower() == "status":  # table header
            continue
        if len(parts) > 4:
            claim, source, note = " | ".join(parts[1:-2]), parts[-2], parts[-1]
        else:
            parts += [""] * (4 - len(parts))
            claim, source, note = parts[1], parts[2], parts[3]
        status = STATUS.get(given.strip("*_` .:").lower())
        if status is None:
            status = "weak"
            note = f"Status given as {given!r}. {note}".strip()
            if "unknown_status" not in warnings:
                warnings.append("unknown_status")
        claims.append(Claim(status, claim, source, note))
    return claims


def _candidates(content: str) -> list[TopicCandidate]:
    out = []
    for index, line in enumerate(_lines(content), start=1):
        if _TABLE_RULE.match(line):
            continue
        parts = _fields(line) if "|" in line else [_BULLET.sub("", line)]
        if parts[0].lower() in ("n", "#"):
            continue
        digits = re.match(r"\d+", parts[0])
        if digits and len(parts) > 1:
            n, parts = int(digits.group()), parts[1:]
        else:
            n = index
        if len(parts) > 4:
            parts = [*parts[:3], " ".join(parts[3:])]
        parts += [""] * (4 - len(parts))
        urls = [u for u in re.split(r"[;,\s]+", parts[3]) if u]
        out.append(TopicCandidate(n, parts[0], parts[1], parts[2], urls))
    return out


def _sources(content: str) -> list[SourceRef]:
    out = []
    for line in _lines(content):
        parts = _fields(_BULLET.sub("", line))
        if _TABLE_RULE.match(line) or parts[0].lower() == "title":
            continue
        if len(parts) > 3:
            parts = [parts[0], parts[1], " | ".join(parts[2:])]
        parts += [""] * (3 - len(parts))
        out.append(SourceRef(parts[0], parts[1], parts[2]))
    return out


def _bullets(content: str) -> list[str]:
    return [_BULLET.sub("", ln).strip() for ln in _lines(content) if _BULLET.sub("", ln).strip()]
