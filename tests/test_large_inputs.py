"""Very large replies and answer histories: fast, and the caps hold (M11)."""

import time
from collections.abc import Iterator

import pytest
from handoff_world import weekly_handoff
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tea.clock import FakeClock
from tea.db.repos import Repos
from tea.handoff import packets
from tea.settings import Settings
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.check_drawer import MAX_CLAIM_ROWS, CheckDrawer
from tea.ui.widgets.handoff_dialog import HandoffDialog
from tea.ui.widgets.markdown_view import MarkdownView

SLOW = 5.0  # seconds: a stall the owner would call a freeze, far above what these take


@pytest.fixture
def theme(qapp: QApplication) -> Iterator[Theme]:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    yield t


def _big_reply(paragraphs: int, claims: int) -> str:
    body = "# Big draft\n\n" + (
        "A paragraph with **bold** and a [link](https://x.y). " * 4 + "\n\n"
    ) * (paragraphs)
    rows = "".join(f"supported | claim number {i} | src | note\n" for i in range(claims))
    return f"<draft>\n{body}</draft>\n<verification>\n{rows}</verification>\n"


def test_200_kb_reply_imports_through_the_dialog_without_a_stall(
    qtbot: QtBot, theme: Theme, repos: Repos, clock: FakeClock
) -> None:
    reply = _big_reply(paragraphs=1000, claims=100)
    assert len(reply.encode()) > 200 * 1024
    h = weekly_handoff(repos, clock)
    dialog = HandoffDialog(theme, repos, clock, Settings, h.id)
    qtbot.addWidget(dialog)
    start = time.perf_counter()
    dialog.paste_box.setPlainText(reply)
    dialog.import_button.click()
    assert time.perf_counter() - start < SLOW
    draft = repos.drafts.latest_for_blog(h.blog_id or 0)
    assert draft is not None and draft.title == "Big draft" and len(draft.verification) == 100
    dialog.close()


def test_200_kb_draft_renders_in_the_reading_pane_quickly(qtbot: QtBot, theme: Theme) -> None:
    view = MarkdownView(theme)
    qtbot.addWidget(view)
    view.resize(800, 600)
    body = (
        "# Big draft\n\n"
        + ("A paragraph with **bold** and a [link](https://x.y). " * 4 + "\n\n") * 1000
    )
    assert len(body.encode()) > 200 * 1024
    start = time.perf_counter()
    view.set_markdown(body)
    assert time.perf_counter() - start < SLOW


def test_drawer_caps_the_claim_rows_and_says_so(qtbot: QtBot, theme: Theme, repos: Repos) -> None:
    from tea.domain import medium
    from tea.handoff.parse import parse

    parsed = parse(_big_reply(paragraphs=2, claims=2000))
    assert len(parsed.claims) == 2000  # the parser keeps them all
    blog = repos.blogs.create("T", "T", "weekly")
    draft = repos.drafts.add(
        blog_id=blog.id,
        title="T",
        body_markdown=parsed.draft_markdown or "",
        raw_reply="raw",
        prompt_versions={"packet_draft": 1},
        verification=[{"claim": c.claim, "status": c.status} for c in parsed.claims],
    )
    drawer = CheckDrawer(theme)
    qtbot.addWidget(drawer)
    start = time.perf_counter()
    drawer.set_draft(draft, medium.warnings(parsed.draft_markdown or ""))
    assert time.perf_counter() - start < SLOW
    assert len(drawer.claim_rows) == MAX_CLAIM_ROWS
    assert (
        strings.CLAIMS_CAPPED.format(shown=MAX_CLAIM_ROWS, total=2000)
        in drawer.sections[strings.DRAWER_CLAIMS]
    )


def test_drawer_shows_worst_claims_first_when_capped(qtbot: QtBot, theme: Theme) -> None:
    drawer = CheckDrawer(theme)
    qtbot.addWidget(drawer)
    claims = [{"claim": f"ok {i}", "status": "supported"} for i in range(MAX_CLAIM_ROWS + 5)]
    claims.append({"claim": "bad one", "status": "unsupported"})
    drawer._claims(claims)  # noqa: SLF001
    assert drawer.claim_rows[0].claim == "bad one"


def test_huge_answers_history_keeps_the_cap_and_every_boundary(
    repos: Repos, clock: FakeClock
) -> None:
    weekly_handoff(repos, clock)
    for i in range(3000):
        q = repos.questions.create(f"Question {i}?", "text", "voice", "bank", bank_key=f"q{i}")
        repos.answers.add(q.id, "login", f"Answer number {i} with some more words in it.")
    boundary = repos.questions.create("Off limits?", "text", "boundaries", "bank", bank_key="b")
    repos.answers.add(boundary.id, "login", "Never write about my employer.")
    settings = Settings(max_answer_words=1500)
    start = time.perf_counter()
    packet = packets.build("weekly", repos, settings, clock, week=repos.weeks.list()[0].week_start)
    assert time.perf_counter() - start < SLOW
    section = packet.text.split("<my_answers>")[1].split("</my_answers>")[0]
    assert len(section.split()) <= settings.max_answer_words + 200
    assert "Never write about my employer." in section
    assert "Answer number 2999" in section  # the newest survive, the oldest are dropped
    assert "Answer number 0 " not in section
