"""Check before posting drawer (UI_DESIGN 3.3): checklist, claims, sources, notes, warnings.

The AI disclosure toggle and its checklist item are left out: the owner dropped the
disclosure (DEVIATIONS M1). Checklist ticks are not enforced and last while tea runs.
"""

import html

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tea.db.rows import Draft
from tea.ui import import_notes, strings
from tea.ui.screens import clear_layout, muted
from tea.ui.theme import Theme

VERDICT_ICONS = {"supported": "check", "weak": "weak", "unsupported": "cross"}
VERDICT_ROLES = {"supported": "primary", "weak": "amber", "unsupported": "attention"}
VERDICT_ORDER = ("unsupported", "weak", "supported")
MAX_CLAIM_ROWS = 200  # a row is a widget; 2,000 of them take seconds to build


class WrapCheck(QWidget):
    """A checkbox whose label wraps (QCheckBox text never wraps in a narrow drawer)."""

    def __init__(self, theme: Theme, text: str) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.space(1))
        self.box = QCheckBox()
        self.box.setAccessibleName(text)
        row.addWidget(self.box, 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setBuddy(self.box)
        row.addWidget(self.label, 1)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        self.box.toggle()
        super().mousePressEvent(event)


class ClaimRow(QFrame):
    """Icon, verdict word and claim. Click or Enter finds the claim in the draft."""

    clicked = Signal(str)

    def __init__(self, theme: Theme, status: str, claim: str) -> None:
        super().__init__()
        self.claim = claim
        self.status = status
        self.setObjectName("ClaimRow")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        verdict = strings.VERDICTS.get(status, strings.VERDICTS["weak"])
        self.setAccessibleName(strings.CLAIM_ACCESSIBLE.format(verdict=verdict, claim=claim))
        col = QVBoxLayout(self)
        pad = theme.space(1)
        col.setContentsMargins(pad, pad, pad, pad)
        col.setSpacing(theme.space(0))
        row = QHBoxLayout()
        row.setSpacing(theme.space(1))
        col.addLayout(row)
        icon = QLabel()
        side = theme.type_px("body")
        icon.setPixmap(
            theme.icon(
                VERDICT_ICONS.get(status, "weak"), VERDICT_ROLES.get(status, "amber")
            ).pixmap(side, side)
        )
        row.addWidget(icon)
        word = QLabel(verdict)
        word.setProperty("verdict", status)
        row.addWidget(word)
        row.addStretch(1)
        # The claim on its own line, full width, so every claim starts at the same x.
        text = QLabel(claim)
        text.setWordWrap(True)
        col.addWidget(text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        self.clicked.emit(self.claim)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.claim)
            return
        super().keyPressEvent(event)


def _source_text(source: dict[str, str]) -> str:
    """ "Title, Publisher" then the location: a link for a URL, else "p. 12" or a filename."""
    title = html.escape(source.get("title", "").strip())
    publisher = html.escape(source.get("publisher", "").strip())
    location = source.get("location", "").strip()
    head = ", ".join(p for p in (title, publisher) if p)
    if location.startswith(("http://", "https://")):
        link = html.escape(location, quote=True)
        tail = f'<a href="{link}">{html.escape(location)}</a>'
    else:
        tail = html.escape(location)
    return "<br>".join(p for p in (head, tail) if p)


class CheckDrawer(QScrollArea):
    claim_clicked = Signal(str)

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme = theme
        self.setObjectName("CheckDrawer")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(theme.size("drawer_width"))
        self.setAccessibleName(strings.DRAWER_TOGGLE)
        self._ticks: dict[int, tuple[bool, bool]] = {}
        self._draft_id: int | None = None
        self.sections: dict[str, list[str]] = {}
        self.claim_rows: list[ClaimRow] = []
        self.checks: list[QCheckBox] = []
        self._body = QWidget()
        self._body.setObjectName("DrawerBody")
        self.setWidget(self._body)
        self._layout = QVBoxLayout(self._body)
        pad = theme.space(4)
        self._layout.setContentsMargins(pad, pad, pad, pad)
        self._layout.setSpacing(theme.space(2))

    # Content

    def set_draft(self, draft: Draft, medium_warnings: list[str]) -> None:
        self._remember_ticks()
        self._draft_id = draft.id
        self._clear()
        if draft.kind == "improved" and draft.changes:
            self._list(strings.DRAWER_CHANGES, [str(c) for c in draft.changes])
        self._checklist(draft.id)
        self._claims(draft.verification)
        self._sources(draft.sources)
        self._list(strings.DRAWER_FLAGS, [str(f) for f in draft.flags])
        notes = import_notes.notes(draft.parse_warnings, draft.flags).lines
        self._list(strings.DRAWER_IMPORT_NOTES, notes)
        lines = import_notes.medium_lines(medium_warnings) or [strings.MEDIUM_OK]
        self._list(strings.DRAWER_MEDIUM, lines)
        self._layout.addStretch(1)

    def set_medium_warnings(self, codes: list[str]) -> None:
        """Refresh only the Medium formatting section (the owner is editing)."""
        lines = import_notes.medium_lines(codes) or [strings.MEDIUM_OK]
        box = self._body.findChild(QWidget, "Section-medium")
        if box is None:
            return
        layout = box.layout()
        assert layout is not None
        clear_layout(layout, keep=1)
        for line in lines:
            layout.addWidget(muted(line, "body"))
        self.sections[strings.DRAWER_MEDIUM] = lines

    def ticks(self) -> tuple[bool, bool]:
        return (
            (self.checks[0].isChecked(), self.checks[1].isChecked())
            if self.checks
            else (False, False)
        )

    # Building

    def _clear(self) -> None:
        self.sections, self.claim_rows, self.checks = {}, [], []
        clear_layout(self._layout)

    def _section(self, title: str, name: str = "") -> QVBoxLayout:
        box = QWidget()
        if name:
            box.setObjectName(f"Section-{name}")
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, self.theme.space(2))
        col.setSpacing(self.theme.space(1))
        heading = QLabel(title)
        heading.setProperty("role", "strong")
        col.addWidget(heading)
        self._layout.addWidget(box)
        return col

    def _list(self, title: str, lines: list[str]) -> None:
        if not lines:
            return
        name = "medium" if title == strings.DRAWER_MEDIUM else ""
        col = self._section(title, name)
        for line in lines:
            col.addWidget(muted(line, "body"))
        self.sections[title] = lines

    def _checklist(self, draft_id: int) -> None:
        col = self._section(strings.DRAWER_CHECKLIST)
        ticks = self._ticks.get(draft_id, (False, False))
        for text, ticked in zip(
            (strings.CHECK_OWN_WORDS, strings.CHECK_CLAIMS), ticks, strict=True
        ):
            check = WrapCheck(self.theme, text)
            check.box.setChecked(ticked)
            col.addWidget(check)
            self.checks.append(check.box)
        self.sections[strings.DRAWER_CHECKLIST] = [strings.CHECK_OWN_WORDS, strings.CHECK_CLAIMS]

    def _claims(self, claims: list[dict[str, str]]) -> None:
        if not claims:
            return
        col = self._section(strings.DRAWER_CLAIMS)
        lines = []
        for status in VERDICT_ORDER:
            for c in claims:
                if len(self.claim_rows) >= MAX_CLAIM_ROWS:
                    break
                if c.get("status", "weak") == status or (
                    status == "weak" and c.get("status") not in VERDICT_ICONS
                ):
                    row = ClaimRow(self.theme, status, c.get("claim", ""))
                    row.clicked.connect(self.claim_clicked)
                    col.addWidget(row)
                    self.claim_rows.append(row)
                    lines.append(f"{status}: {row.claim}")
        if len(claims) > len(self.claim_rows):
            note = strings.CLAIMS_CAPPED.format(shown=len(self.claim_rows), total=len(claims))
            col.addWidget(muted(note, "caption"))
            lines.append(note)
        self.sections[strings.DRAWER_CLAIMS] = lines

    def _sources(self, sources: list[dict[str, str]]) -> None:
        if not sources:
            return
        col = self._section(strings.DRAWER_SOURCES)
        lines = []
        for s in sources:
            label = QLabel(_source_text(s))
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setOpenExternalLinks(False)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.LinksAccessibleByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
            )
            label.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
            col.addWidget(label)
            lines.append(label.text())
        self.sections[strings.DRAWER_SOURCES] = lines

    def _remember_ticks(self) -> None:
        if self._draft_id is not None and self.checks:
            self._ticks[self._draft_id] = self.ticks()
