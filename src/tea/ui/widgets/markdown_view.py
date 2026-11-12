"""Read-only Markdown view: the reading pane (SPEC 7, UI_DESIGN 3.3).

The reading face at the reading size with a 1.65 line height, in a column at most 680 wide that
stays centred in the pane. Raw HTML in a draft is shown as text, never rendered.
"""

from markdown_it import MarkdownIt
from PySide6.QtGui import (
    QFont,
    QResizeEvent,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QTextBrowser, QTextEdit

from tea.ui.theme import Theme

HEADING_SIZES = {1: "reading_h1", 2: "reading_h2", 3: "reading_h3"}
PERCENT = 100


def apply_reading_format(theme: Theme, document: QTextDocument) -> None:
    """Heading sizes, line height and paragraph spacing; body text uses the default font.

    Call after `setHtml` on a document whose default font is the reading body font.
    """
    line = round(theme.line_height("reading") * PERCENT)
    gap = theme.space(3)
    block = document.begin()
    while block.isValid():
        cursor = QTextCursor(block)
        fmt = block.blockFormat()
        level = fmt.headingLevel()
        if level:
            heading = theme.font("reading", HEADING_SIZES.get(level, HEADING_SIZES[3]))
            chars = QTextCharFormat()
            chars.setProperty(QTextFormat.Property.FontPixelSize, heading.pixelSize())
            chars.setFontWeight(QFont.Weight.DemiBold)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            cursor.mergeCharFormat(chars)
            fmt.setTopMargin(gap if block != document.begin() else 0)
        else:
            fmt.setLineHeight(line, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        fmt.setBottomMargin(gap)
        cursor.setBlockFormat(fmt)
        block = block.next()


def markdown_html(markdown: str) -> str:
    return MarkdownIt("commonmark", {"html": False}).enable("table").render(markdown or "")


class MarkdownView(QTextBrowser):
    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme = theme
        self.setProperty("reading", "true")
        self.setOpenLinks(False)  # links in a draft are text to check, not to follow
        self.setReadOnly(True)
        self.markdown = ""

    def set_markdown(self, markdown: str) -> None:
        self.markdown = markdown
        self.setExtraSelections([])
        self.document().setDefaultFont(self.theme.font("reading", "reading_body"))
        self.document().setHtml(markdown_html(markdown))
        apply_reading_format(self.theme, self.document())
        self.moveCursor(QTextCursor.MoveOperation.Start)
        self.verticalScrollBar().setValue(0)
        self._centre()

    def highlight(self, claim: str) -> bool:
        """Scroll to the claim and highlight it. Tries the whole claim, then its start."""
        words = claim.split()
        tries = [" ".join(words)] + [" ".join(words[:n]) for n in (8, 5) if len(words) > n]
        for text in tries:
            found = self.document().find(text)
            if not found.isNull():
                sel = QTextEdit.ExtraSelection()
                sel.cursor = found  # type: ignore[attr-defined]
                sel.format.setBackground(self.theme.color("primary_soft"))  # type: ignore[attr-defined]
                self.setExtraSelections([sel])
                self.setTextCursor(found)
                self.ensureCursorVisible()
                return True
        return False

    def _centre(self) -> None:
        side = max(0, (self.width() - self.theme.reading_measure()) // 2)
        self.setViewportMargins(side, 0, side, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        self._centre()
        super().resizeEvent(event)
