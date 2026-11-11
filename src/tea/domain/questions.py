"""Question seeding, template instantiation, weighted selection, session mix, cooldown.

Pools (SPEC 6): the seed bank, focus questions for the week, improvement questions for a
carried-over draft, and manual-mode scope questions for a blog. A question counts as asked
when the owner answers or skips it; closing the popup does not count.
"""

import json
import random
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Any

from tea import config
from tea.db.repos import Repos
from tea.db.rows import Answer, Blog, Question

Template = dict[str, Any]

FRESH_DAYS = 14  # no re-asking within this many days unless the pool is exhausted
WEIGHT_DAYS_CAP = 60  # a never-asked question counts as this many days since last asked
SCOPE_MIN, SCOPE_MAX = 5, 15
LOGIN_JOB = "login_questions"
_PLACEHOLDER = re.compile(r"\{([^{}\s]*)\}")


class TemplateError(ValueError):
    """A template uses a placeholder that was not supplied."""


@cache
def _load(name: str) -> str:
    return (config.resource_dir("data") / name).read_text(encoding="utf-8")


def load_templates(name: str) -> list[Template]:
    """`templates` from a data file (`questions` for the bank)."""
    data = json.loads(_load(name))
    return list(data.get("templates", data.get("questions", [])))


# Seeding and templates


def seed_bank(repos: Repos) -> int:
    """Insert bank questions whose `bank_key` is missing. Returns how many were added."""
    added = 0
    with repos.transaction():
        for t in load_templates("question_bank.json"):
            key = t["bank_key"]
            if repos.questions.get_by_bank_key(key) is not None:
                continue
            repos.questions.create(
                t["text"], t["kind"], t["category"], "bank",
                options=t.get("options", []), template_key=key, bank_key=key,
            )  # fmt: skip
            added += 1
    return added


def fill(text: str, values: Mapping[str, str]) -> str:
    """Replace `{name}` placeholders in one pass; raise on any placeholder not in `values`."""
    unknown = sorted({m for m in _PLACEHOLDER.findall(text) if m not in values})
    if unknown:
        raise TemplateError(f"unknown placeholders: {unknown}")
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def instantiate(
    repos: Repos,
    templates: Sequence[Template],
    values: Mapping[str, str],
    *,
    origin: str,
    week_start: date | None = None,
    blog_id: int | None = None,
) -> list[Question]:
    """Rows for `templates`, one per template key for this week or blog, in template order.

    Idempotent: an active row with the same key and text is reused. If the text changed
    (a new focus or title), the old row is deactivated, keeping its answers, and a new one made.
    """
    texts = [fill(t["text"], values) for t in templates]  # validate everything first
    existing = [
        q
        for q in repos.questions.list(origin=origin, week_start=week_start, blog_id=blog_id)
        if (week_start is None or q.week_start == week_start)
        and (blog_id is None or q.blog_id == blog_id)
    ]
    by_key = {q.template_key: q for q in existing}
    made: list[Question] = []
    with repos.transaction():
        for t, text in zip(templates, texts, strict=True):
            current = by_key.get(t["key"])
            if current is not None and current.text == text:
                made.append(current)
                continue
            if current is not None:
                repos.questions.set_active(current.id, False)
            made.append(
                repos.questions.create(
                    text,
                    t["kind"],
                    t["category"],
                    origin,
                    options=t.get("options", []),
                    week_start=week_start,
                    blog_id=blog_id,
                    template_key=t["key"],
                )  # fmt: skip
            )
    return made


def instantiate_focus(repos: Repos, week: date, focus: str) -> list[Question]:
    templates = load_templates("focus_question_templates.json")
    repos.weeks.ensure(week)
    return instantiate(repos, templates, {"focus": focus}, origin="week", week_start=week)


def instantiate_improve(repos: Repos, blog: Blog, title: str) -> list[Question]:
    templates = load_templates("improve_questions.json")
    return instantiate(repos, templates, {"title": title}, origin="improve", blog_id=blog.id)


# Scope questions (manual mode)


def scope_conditions(
    *,
    has_files: bool,
    allowed_sources: Sequence[str],
    length: str,
    scope_notes: str,
    audience: str,
) -> set[str]:
    """Which `applies` values hold for a blog's options."""
    held = {"always"}
    if has_files:
        held.add("has_files")
    held.update(s for s in ("web", "academic") if s in allowed_sources)
    if length in ("long", "short"):
        held.add(length)
    if not scope_notes.strip():
        held.add("scope_empty")
    if not audience.strip():
        held.add("audience_empty")
    return held


def select_scope_templates(templates: Sequence[Template], conditions: set[str]) -> list[Template]:
    """All templates whose condition holds, by `order`, up to 15; topped up to 5 with `always`."""
    ordered = sorted(templates, key=lambda t: t["order"])
    chosen = [t for t in ordered if t["applies"] in conditions][:SCOPE_MAX]
    for t in ordered:
        if len(chosen) >= SCOPE_MIN:
            break
        if t["applies"] == "always" and t not in chosen:
            chosen.append(t)
    return sorted(chosen, key=lambda t: t["order"])


def _blog_conditions(blog: Blog, has_files: bool) -> set[str]:
    return scope_conditions(
        has_files=has_files, allowed_sources=blog.allowed_sources, length=blog.length,
        scope_notes=blog.scope_notes, audience=blog.audience,
    )  # fmt: skip


def instantiate_scope(repos: Repos, blog: Blog, *, has_files: bool) -> list[Question]:
    templates = select_scope_templates(
        load_templates("scope_question_templates.json"), _blog_conditions(blog, has_files)
    )
    return instantiate(repos, templates, {"topic": blog.topic}, origin="blog", blog_id=blog.id)


def pending_scope(repos: Repos, blog: Blog, *, has_files: bool) -> list[Question]:
    """Scope questions not yet answered or skipped, so Later resumes where the owner stopped."""
    done = {a.question_id for a in repos.answers.list(blog_id=blog.id)}
    return [q for q in instantiate_scope(repos, blog, has_files=has_files) if q.id not in done]


# Weighted selection and the login mix


def _days_since(q: Question, now: datetime) -> float | None:
    if q.last_asked_at is None:
        return None
    last = datetime.fromisoformat(q.last_asked_at).astimezone(UTC)
    return (now.astimezone(UTC) - last) / timedelta(days=1)


def weight(q: Question, now: datetime) -> float:
    """Rises with days since last asked (capped), falls with how often it was asked."""
    days = _days_since(q, now)
    capped = WEIGHT_DAYS_CAP if days is None else min(max(days, 0.0), WEIGHT_DAYS_CAP)
    return (1 + capped) / (1 + q.asked_count)


def weighted_pick(candidates: Sequence[Question], now: datetime, rng: random.Random) -> Question:
    return rng.choices(list(candidates), weights=[weight(q, now) for q in candidates])[0]


def _is_fresh(q: Question, now: datetime) -> bool:
    days = _days_since(q, now)
    return days is None or days >= FRESH_DAYS


def login_pools(repos: Repos, week: date) -> dict[str, list[Question]]:
    return {
        "improve": repos.questions.list(origin="improve"),
        "week": [q for q in repos.questions.list(origin="week") if q.week_start == week],
        "bank": repos.questions.list(origin="bank"),
    }


def select_login(
    repos: Repos, now: datetime, rng: random.Random, count: int, week: date
) -> list[Question]:
    """One improvement, one focus, the rest from the bank; empty slots filled from other pools.

    Questions asked in the last 14 days are used only when fresh ones run out.
    """
    pools = login_pools(repos, week)
    chosen: list[Question] = []

    def take(pool: str, limit: int, fresh_only: bool) -> None:
        while len(chosen) < limit:
            ids = {q.id for q in chosen}
            left = [
                q for q in pools[pool] if q.id not in ids and (not fresh_only or _is_fresh(q, now))
            ]
            if not left:
                return
            chosen.append(weighted_pick(left, now, rng))

    for fresh_only in (True, False):
        for pool in ("improve", "week"):
            if not any(q.origin == pool for q in chosen):
                take(pool, min(count, len(chosen) + 1), fresh_only)
        for pool in ("bank", "improve", "week"):
            take(pool, count, fresh_only)
    order = {"improve": 0, "week": 1, "bank": 2}
    return sorted(chosen, key=lambda q: order[q.origin])


# Recording and the cooldown


def record_answer(
    repos: Repos,
    question: Question,
    context: str,
    text: str,
    *,
    skipped: bool = False,
    week_start: date | None = None,
    blog_id: int | None = None,
    count_ask: bool = True,
) -> Answer:
    """Store an answer (or a skip, with no text) and count the question as asked.

    Pass `count_ask=False` when the owner changes an answer in the same sitting (Back).
    """
    with repos.transaction():
        answer = repos.answers.add(
            question.id, context, "" if skipped else text, skipped=skipped,
            week_start=week_start, blog_id=blog_id,
        )  # fmt: skip
        if count_ask:
            repos.questions.mark_asked(question.id)
    return answer


def login_allowed(repos: Repos, now: datetime) -> bool:
    job = repos.jobs.get(LOGIN_JOB)
    if job is None or job.snoozed_until is None:
        return True
    return now.astimezone(UTC) >= datetime.fromisoformat(job.snoozed_until).astimezone(UTC)


def note_dismissed(repos: Repos, now: datetime, *, minutes: int) -> None:
    with repos.transaction():
        repos.jobs.record_attempt(LOGIN_JOB)
        repos.jobs.snooze(LOGIN_JOB, now + timedelta(minutes=minutes))


def note_completed(repos: Repos, now: datetime) -> None:
    del now  # the attempt time comes from the repo's clock
    with repos.transaction():
        repos.jobs.record_attempt(LOGIN_JOB)
        repos.jobs.snooze(LOGIN_JOB, None)
