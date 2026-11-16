"""Custom painted widgets: the Freakyyy orb, glass panels, meters, background."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Property, Signal
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from . import theme as T


def paint_background(p: QPainter, rect) -> None:
    g = QLinearGradient(0, 0, 0, rect.height())
    g.setColorAt(0, QColor("#020611"))
    g.setColorAt(0.45, T.BLACK)
    g.setColorAt(0.8, QColor("#030D20"))
    g.setColorAt(1, QColor("#071D3D"))
    p.fillRect(rect, g)
    for cx, cy, r, c, a in ((0.12, 0.15, 0.55, T.BLUE, 40), (0.92, 0.95, 0.6, T.CYAN, 24), (0.5, 0.45, 0.35, T.ELECTRIC, 16)):
        rg = QRadialGradient(QPointF(rect.width() * cx, rect.height() * cy), rect.width() * r)
        col = QColor(c)
        col.setAlpha(a)
        rg.setColorAt(0, col)
        rg.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(rect, rg)
    # faint HUD grid
    pen = QPen(QColor(109, 220, 255, 9), 1)
    p.setPen(pen)
    step = 48
    for x in range(0, rect.width(), step):
        p.drawLine(x, 0, x, rect.height())
    for y in range(0, rect.height(), step):
        p.drawLine(0, y, rect.width(), y)


class Glass(QFrame):
    """Translucent glass card with a light top edge."""

    def __init__(self, title: str | None = None, parent=None, radius: int = 20, highlighted: bool = False):
        super().__init__(parent)
        self.radius = radius
        self.highlighted = highlighted
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)
        if title:
            t = QLabel(title.upper())
            t.setFont(T.font(8.5, T.QFont.Weight.DemiBold, 2.2))
            t.setStyleSheet(f"color: {T.rgba(T.ICE, .7)};")
            self.lay.addWidget(t)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill = QLinearGradient(0, 0, 0, r.height())
        fill.setColorAt(0, QColor(255, 255, 255, 22))
        fill.setColorAt(0.5, QColor(39, 139, 255, 16))
        fill.setColorAt(1, QColor(255, 255, 255, 8))
        edge = QLinearGradient(0, 0, 0, r.height())
        if self.highlighted:
            edge.setColorAt(0, T.CYAN)
            edge.setColorAt(1, QColor(35, 140, 255, 90))
        else:
            edge.setColorAt(0, QColor(255, 255, 255, 80))
            edge.setColorAt(0.6, QColor(35, 140, 255, 40))
            edge.setColorAt(1, QColor(189, 235, 255, 14))
        p.setPen(QPen(QBrush(edge), 1))
        p.setBrush(fill)
        p.drawRoundedRect(r, self.radius, self.radius)


class Meter(QWidget):
    """Label + value + thin gradient bar."""

    def __init__(self, label: str, parent=None, higher_is_better: bool = False):
        super().__init__(parent)
        self.label, self.value, self.text = label, 0.0, "—"
        self.higher_is_better = higher_is_better
        self.setMinimumHeight(38)

    def set(self, value: float | None, text: str):
        self.value = 0 if value is None else max(0.0, min(1.0, value))
        self.text = text
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setFont(T.font(9, T.QFont.Weight.Medium))
        p.setPen(T.MUTED)
        p.drawText(QRectF(0, 0, w / 2, 18), Qt.AlignmentFlag.AlignLeft, self.label)
        p.setPen(T.WHITE)
        p.setFont(T.font(9.5, T.QFont.Weight.DemiBold))
        p.drawText(QRectF(w / 2, 0, w / 2, 18), Qt.AlignmentFlag.AlignRight, self.text)
        track = QRectF(0, 26, w, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 25))
        p.drawRoundedRect(track, 2, 2)
        g = QLinearGradient(0, 0, w, 0)
        hot = self.value < 0.15 if self.higher_is_better else self.value > 0.85
        g.setColorAt(0, T.WARNING if hot else T.BLUE)
        g.setColorAt(1, T.DANGER if hot else T.CYAN)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 26, max(4.0, w * self.value), 4), 2, 2)


class Dot(QWidget):
    def __init__(self, color: QColor, size: int = 8, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(size + 6, size + 6)
        self.pulse = False
        self._t = 0.0
        self._timer = QTimer(self, interval=60, timeout=self._tick)

    def set(self, color: QColor, pulse: bool = False):
        self.color = color
        self.pulse = pulse
        (self._timer.start() if pulse else self._timer.stop())
        self.update()

    def _tick(self):
        self._t += 0.12
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = (self.width() - 6) / 2
        if self.pulse:
            halo = QColor(self.color)
            halo.setAlpha(int(70 + 60 * math.sin(self._t)))
            p.setBrush(halo)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, r + 3, r + 3)
        p.setBrush(self.color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c, r, r)


class Orb(QWidget):
    """Freakyyy's state visualiser. Idle: a slow, low-frame-rate breath.
    Active states: rotating arcs, pulse and a voice-reactive waveform ring."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "IDLE"
        self.level = 0.0
        self._level_s = 0.0
        self._angle = 0.0
        self._t = 0.0
        self._intro = 0.0          # 0..1 entrance animation
        self._bars = [random.random() for _ in range(96)]
        self._timer = QTimer(self, timeout=self._tick)
        self._timer.start(33)
        self.setMinimumSize(320, 320)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        self.clicked.emit()

    def set_state(self, state: str):
        self.state = state
        active = state not in ("IDLE", "OFFLINE")
        self._timer.setInterval(16 if active else 66)      # ~60 fps active, ~15 fps idle

    def set_level(self, v: float):
        self.level = max(0.0, min(1.0, v))

    def get_intro(self):
        return self._intro

    def set_intro(self, v):
        self._intro = v
        self.update()

    intro = Property(float, get_intro, set_intro)

    def _tick(self):
        active = self.state not in ("IDLE", "OFFLINE")
        speed = {"THINKING": 4.0, "EXECUTING": 3.0, "RECOGNIZING": 2.5}.get(self.state, 1.0 if active else 0.25)
        self._angle = (self._angle + speed) % 360
        self._t += 0.033 if not active else 0.016
        self._level_s += (self.level - self._level_s) * 0.25
        if active:
            for i in range(len(self._bars)):
                self._bars[i] += (random.random() - self._bars[i]) * 0.18
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        c = QPointF(w / 2, h / 2)
        R = min(w, h) / 2 * 0.9 * (0.6 + 0.4 * self._intro)
        accent = QColor(T.STATE_COLORS.get(self.state, T.BLUE))
        active = self.state not in ("IDLE", "OFFLINE")
        breath = 1 + 0.025 * math.sin(self._t * 2.2) + (0.08 * self._level_s if active else 0)
        p.setOpacity(self._intro)

        # Outer glow
        glow = QRadialGradient(c, R * 1.15)
        ga = QColor(accent)
        ga.setAlpha(70 if active else 45)
        glow.setColorAt(0, ga)
        glow.setColorAt(0.55, QColor(18, 107, 255, 22))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, R * 1.15, R * 1.15)

        # HUD tick ring
        p.save()
        p.translate(c)
        p.rotate(-self._angle * 0.3)
        tick_pen = QPen(QColor(189, 235, 255, 60), 1.2)
        for i in range(120):
            p.setPen(tick_pen if i % 10 else QPen(QColor(109, 220, 255, 150), 2))
            r1 = R * 0.98
            r2 = R * (0.94 if i % 10 else 0.9)
            a = math.radians(i * 3)
            p.drawLine(QPointF(math.cos(a) * r1, math.sin(a) * r1), QPointF(math.cos(a) * r2, math.sin(a) * r2))
        p.restore()

        # Sweep arcs
        p.save()
        p.translate(c)
        p.rotate(self._angle)
        cg = QConicalGradient(QPointF(0, 0), 0)
        cg.setColorAt(0, QColor(0, 0, 0, 0))
        cg.setColorAt(0.25, QColor("#248CFF"))
        cg.setColorAt(0.5, QColor("#C5F4FF"))
        cg.setColorAt(0.75, QColor("#356DFF"))
        cg.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(QPen(QBrush(cg), 3.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        rr = R * 0.84
        p.drawArc(QRectF(-rr, -rr, rr * 2, rr * 2), 25 * 16, 285 * 16)
        p.setPen(QPen(accent, 2))
        p.rotate(-self._angle * 2.2)
        rr2 = R * 0.77
        p.drawArc(QRectF(-rr2, -rr2, rr2 * 2, rr2 * 2), 190 * 16, 85 * 16)
        p.restore()

        # Voice waveform ring
        if active:
            p.save()
            p.translate(c)
            n = len(self._bars)
            base = R * 0.66
            for i, v in enumerate(self._bars):
                amp = (0.15 + v * 0.85) * (0.15 + self._level_s * 1.3) * R * 0.12
                a = math.radians(i * 360 / n + self._angle * 0.5)
                col = QColor(accent)
                col.setAlpha(200)
                pen = QPen(col, 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(math.cos(a) * base, math.sin(a) * base),
                           QPointF(math.cos(a) * (base + amp), math.sin(a) * (base + amp)))
            p.restore()

        # Core sphere
        core = R * 0.6 * breath
        cg2 = QRadialGradient(QPointF(c.x() - core * 0.25, c.y() - core * 0.3), core * 1.2)
        cg2.setColorAt(0, QColor("#2C6CC0"))
        cg2.setColorAt(0.35, QColor("#103C79"))
        cg2.setColorAt(0.75, QColor("#071B3C"))
        cg2.setColorAt(1, QColor("#030B1B"))
        p.setPen(QPen(QColor(189, 235, 255, 70), 1.2))
        p.setBrush(cg2)
        p.drawEllipse(c, core, core)

        # Liquid-glass lens
        p.save()
        p.translate(c)
        p.rotate(-self._angle * 0.65)
        lens = core * 0.78
        path = QPainterPath()
        path.addRoundedRect(QRectF(-lens, -lens, lens * 2, lens * 2), lens * 0.55, lens * 0.55)
        lg = QLinearGradient(-lens, -lens, lens, lens)
        lg.setColorAt(0, QColor(181, 237, 255, 80))
        lg.setColorAt(0.5, QColor(39, 140, 255, 20))
        lg.setColorAt(1, QColor(125, 141, 255, 70))
        edge = QLinearGradient(-lens, -lens, lens, lens)
        edge.setColorAt(0, T.ICE)
        edge.setColorAt(0.3, QColor(0, 0, 0, 0))
        edge.setColorAt(0.6, T.BLUE)
        edge.setColorAt(1, T.ICE)
        p.setPen(QPen(QBrush(edge), 1.5))
        p.setBrush(lg)
        p.drawPath(path)
        p.restore()

        # Inner light
        inner = QRadialGradient(c, core * 0.6)
        ia = QColor(accent)
        ia.setAlpha(150)
        inner.setColorAt(0, ia)
        inner.setColorAt(0.6, QColor(23, 109, 255, 40))
        inner.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(inner)
        p.drawEllipse(c, core * 0.6, core * 0.6)

        # Specular highlight
        spec = QRadialGradient(QPointF(c.x() - core * 0.35, c.y() - core * 0.45), core * 0.45)
        spec.setColorAt(0, QColor(255, 255, 255, 70))
        spec.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(spec)
        p.drawEllipse(QPointF(c.x() - core * 0.35, c.y() - core * 0.45), core * 0.45, core * 0.3)

        # Monogram
        p.setPen(QColor(248, 250, 255, 235))
        p.setFont(T.font(R * 0.17, T.QFont.Weight.ExtraLight))
        p.drawText(QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R), Qt.AlignmentFlag.AlignCenter, "F")
