"""Clipboard writes: rich text for Medium (HTML plus plain text) and plain text (ARCHITECTURE 7)."""

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

HTML = "text/html"
PLAIN = "text/plain"


def set_rich(html: str, plain: str) -> None:
    """Both formats in one `QMimeData`: Medium's editor reads the HTML, others the text."""
    mime = QMimeData()
    mime.setHtml(html)
    mime.setText(plain)
    QGuiApplication.clipboard().setMimeData(mime)


def set_plain(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def text() -> str:
    return QGuiApplication.clipboard().text()
