"""Steep ring progress widget (UI_DESIGN 3.1), painted with QPainter.

The arc runs clockwise from 12 o'clock, coloured by a conical gradient through the steep
stops, so it darkens from jade to oolong as the week steeps. Full states use a solid stop:
Prompt ready is oolong (stop 2), Ready is pu-erh (stop 3). Changing to either of them
settles the arc to full over `motion_ms.ring_settle`, unless reduce motion is on.
"""

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from tea.ui.theme import Theme

STATES = ("no_focus", "steeping", "pick", "prompt_ready", "ready", "paused")
FULL_STATES = ("prompt_ready", "ready")
_SOLID_STOP = {"prompt_ready": 2, "ready": 3}
_ARC_STATES = ("steeping", "pick", "prompt_ready", "ready")


class SteepRing(QWidget):
    def __init__(self, theme: Theme, *, reduce_motion: bool = False) -> None:
        super().__init__()
        self.theme = theme
        self.reduce_motion = reduce_motion
        side = theme.size("ring")
        self.stroke = theme.size("ring_stroke")
        self.setFixedSize(side, side)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.state = ""
        self.progress = 0.0
        self.displayed = 0.0
        self.centre = ""
        self.caption = ""
        self.animation: QVariantAnimation | None = None
        theme.changed.connect(self.update)

    @property
    def dashed(self) -> bool:
        return self.state == "no_focus"

    def set_state(
        self, state: str, progress: float, centre: str, caption: str, sentence: str = ""
    ) -> None:
        if state not in STATES:
            raise ValueError(f"unknown ring state {state!r}")
        previous = self.state
        self.state = state
        self.progress = min(1.0, max(0.0, progress))
        self.centre, self.caption = centre, caption
        self.setAccessibleName(sentence or centre)
        settle = (
            state in FULL_STATES
            and previous not in ("", *FULL_STATES)
            and not self.reduce_motion
            and self.displayed < self.progress
        )
        self._stop_animation()
        if settle:
            anim = QVariantAnimation(self)
            anim.setStartValue(self.displayed)
            anim.setEndValue(self.progress)
            anim.setDuration(self.theme.motion_ms("ring_settle"))
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(self._on_frame)
            anim.finished.connect(self._stop_animation)
            self.animation = anim
            anim.start()
        else:
            self.displayed = self.progress
        self.update()

    def _on_frame(self, value: object) -> None:
        self.displayed = float(value)  # type: ignore[arg-type]
        self.update()

    def _stop_animation(self) -> None:
        if self.animation is not None:
            self.animation.stop()
            self.animation.deleteLater()
            self.animation = None
            self.displayed = self.progress

    # Painting

    def _arc_brush(self, rect: QRectF) -> QBrush:
        stops = self.theme.steep_stops()
        if self.state in _SOLID_STOP:
            return QBrush(stops[_SOLID_STOP[self.state]][1])
        # Qt's conical gradient runs counter-clockwise from its start angle. Start it just
        # before 12 o'clock, by the width of the round cap, so the cap is jade rather than the
        # pu-erh end of the gradient; then clockwise progress `at` is position 1 - cap - at.
        cap = math.degrees((self.stroke / 2) / (rect.width() / 2)) / 360
        gradient = QConicalGradient(rect.center(), 90 + cap * 360)
        gradient.setColorAt(1.0, stops[0][1])
        for at, color in stops:
            gradient.setColorAt(max(0.0, 1.0 - cap - at), color)
        return QBrush(gradient)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        del event
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = self.stroke / 2
        rect = QRectF(half, half, self.width() - self.stroke, self.height() - self.stroke)

        track = QPen(t.color("line"), self.stroke)  # paused: this track and no arc
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        if self.dashed:
            track.setStyle(Qt.PenStyle.CustomDashLine)
            track.setDashPattern([1.2, 1.2])
        p.setPen(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        if self.state in _ARC_STATES and self.displayed > 0:
            pen = QPen(self._arc_brush(rect), self.stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            span = -round(self.displayed * 360 * 16)  # negative: clockwise
            if self.displayed >= 1.0:
                p.drawEllipse(rect)
            else:
                p.drawArc(rect, 90 * 16, span)

        self._paint_text(p)
        p.end()

    def _paint_text(self, p: QPainter) -> None:
        t = self.theme
        centre_font = t.font("reading", "ring_centre")
        caption_font = t.font("ui", "caption")
        inner = self.width() - 2 * self.stroke - 2 * t.space(2)
        x = (self.width() - inner) / 2
        mid = self.height() / 2
        p.setFont(centre_font)
        p.setPen(QColor(t.color("muted" if self.state == "paused" else "ink")))
        line_h = p.fontMetrics().height()
        gap = t.space(0)
        cap_h = 0
        if self.caption:
            p.save()
            p.setFont(caption_font)
            cap_h = p.fontMetrics().height()
            p.restore()
        flags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
        rows = p.fontMetrics().boundingRect(0, 0, round(inner), 0, int(flags), self.centre).height()
        rows = max(rows, line_h)
        top = mid - (rows + (gap + cap_h if cap_h else 0)) / 2
        p.drawText(QRectF(x, top, inner, rows), int(flags), self.centre)
        if self.caption:
            p.setFont(caption_font)
            p.setPen(t.color("muted"))
            p.drawText(QRectF(x, top + rows + gap, inner, cap_h), int(flags), self.caption)

    def centre_point(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)
