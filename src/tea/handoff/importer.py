"""Turn a pasted reply into a new draft version and update statuses (ARCHITECTURE 5).

A bad reply never raises: it is stored with warnings. Only a missing hand-off or blog raises.
"""

import logging
import time
from dataclasses import asdict, dataclass
from datetime import date

from tea.db.repos import Repos
from tea.db.rows import Draft
from tea.handoff.parse import ParsedReply, parse
from tea.ui.strings import UNTITLED_DRAFT

log = logging.getLogger(__name__)

NO_TOPIC = "no_topic"  # pick mode, but the reply named no <topic>: the owner types it (SPEC 3.3)


@dataclass(frozen=True)
class ImportResult:
    handoff_id: int
    draft: Draft
    parsed: ParsedReply
    warnings: list[str]

    @property
    def needs_topic(self) -> bool:
        return NO_TOPIC in self.warnings


def _draft_kind(handoff_kind: str, has_drafts: bool) -> str:
    if handoff_kind == "improve":
        return "improved"
    if handoff_kind == "audit":
        return "checked"
    return "regenerated" if has_drafts else "new"


def _pick_applies(repos: Repos, status: str, week: date | None) -> bool:
    """Never overwrite a focus the owner set, nor apply a superseded pick hand-off (SPEC 4.1)."""
    if status == "superseded":
        return False
    w = repos.weeks.get(week) if week is not None else None
    return w is None or w.focus_text is None or w.topic_origin == "auto_trending"


def import_reply(repos: Repos, handoff_id: int, text: str) -> ImportResult:
    started = time.monotonic()
    handoff = repos.handoffs.get(handoff_id)
    if handoff is None:
        raise LookupError(f"no hand-off with id {handoff_id}")
    blog = repos.blogs.get(handoff.blog_id) if handoff.blog_id is not None else None
    if blog is None:
        raise LookupError(f"hand-off {handoff_id} has no blog")

    parsed = parse(text)
    warnings = list(parsed.warnings)
    pick = handoff.kind == "weekly_pick"
    if pick and not parsed.topic:
        warnings.append(NO_TOPIC)
    title = parsed.title or blog.title or UNTITLED_DRAFT

    with repos.transaction():
        kind = _draft_kind(handoff.kind, repos.drafts.latest_for_blog(blog.id) is not None)
        draft = repos.drafts.add(
            blog.id,
            title,
            parsed.draft_markdown or "",
            text,
            handoff.prompt_versions,
            kind=kind,
            sources=[asdict(s) for s in parsed.sources],
            verification=[asdict(c) for c in parsed.claims],
            flags=parsed.flags,
            changes=parsed.changes,
            parse_warnings=warnings,
        )
        fields: dict[str, str] = {"status": "ready"}
        if pick and _pick_applies(repos, handoff.status, handoff.week_start):
            if parsed.title:
                fields["title"] = parsed.title
            if parsed.topic:
                fields.update(topic=parsed.topic, topic_origin="auto_trending")
                if handoff.week_start is not None:
                    repos.weeks.set_focus(handoff.week_start, parsed.topic, "auto_trending")
            if parsed.candidates and handoff.week_start is not None:
                candidates = [asdict(c) for c in parsed.candidates]
                repos.weeks.set_trend_candidates(handoff.week_start, candidates)
        repos.blogs.update(blog.id, **fields)
        repos.handoffs.mark_imported(handoff.id, draft.id)

    log.info(
        "reply_imported handoff=%s draft=%s version=%s warnings=%s ms=%d",
        handoff.id,
        draft.id,
        draft.version,
        len(warnings),
        (time.monotonic() - started) * 1000,
    )
    return ImportResult(handoff.id, draft, parsed, warnings)
