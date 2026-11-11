# Reply format and parser

The prompts ask Claude to answer with the sections below. The parser (`handoff/parse.py`) must be **lenient**, because the reply comes from a chat window and may have preamble, code fences, different capitalization, or missing sections.

## Sections

```
<topic>The chosen topic</topic>                      (pick mode only)

<topic_candidates>                                   (pick mode only)
1 | topic | angle | why it is trending | url; url; url
2 | ...
</topic_candidates>

<draft>
# Title
...Markdown...
</draft>

<verification>
supported | claim text | S1 p.12 or https://url | short note
weak | claim text | R2 | short note
unsupported | claim text | none | short note
</verification>

<sources>
- Title | Publisher or filename | url or "p. N"
</sources>

<flags>
- Short note for the author
</flags>

<changes>                                            (improve only)
- What was changed and why
</changes>
```

## Parsing rules

1. Tags are matched case-insensitively and may be surrounded by whitespace or a Markdown code fence (` ``` `). Strip a leading line such as "Here is your draft:" before the first tag.
2. `<draft>` content is Markdown. Its first `# ` heading is the title. If there is no `<draft>` tag, use the whole reply (minus recognizable other sections) and add the parse warning `no_draft_tag`.
3. `<verification>` lines are `status | claim | source | note`, split on the first three ` | ` separators (a claim may contain a pipe: take the last two separators from the right instead). Normalize status: `supported`, `weak`, `unsupported`; map "verified", "ok" to supported, "partial", "partially" to weak, "unverified", "not supported" to unsupported. Unknown status becomes `weak` with a note. Missing section: warning `no_verification`.
4. `<topic_candidates>` lines are `n | topic | angle | why | urls`. A line with fewer fields is kept with the missing parts empty.
5. Truncation: an opening tag with no closing tag at the end of the reply means a truncated reply. Keep what is there and add the warning `truncated:<tag>`.
6. Keep the **raw reply** exactly as pasted in `drafts.raw_reply`.
7. Warnings are stored as a JSON list in `drafts.parse_warnings` and shown in the import summary and the Check before posting drawer, in plain words (see `UI_DESIGN.md` section 8).
8. The parser never raises on bad input. It returns a `ParsedReply` with whatever it found.

## ParsedReply

```python
@dataclass
class ParsedReply:
    title: str | None
    draft_markdown: str | None
    topic: str | None
    candidates: list[TopicCandidate]       # n, topic, angle, why, urls
    claims: list[Claim]                    # status, claim, source, note
    sources: list[SourceRef]               # title, publisher, location
    flags: list[str]
    changes: list[str]
    warnings: list[str]                    # no_draft_tag, no_verification, truncated:<tag>, unknown_status
    raw: str
```
