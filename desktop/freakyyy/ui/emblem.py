"""Animated Freakyyy emblem - the brand mark (F + AI core + orbital ring) drawn
live with QPainter so it can express state cheaply:

    idle       breathing glow (12 fps)
    hover      slightly brighter
    wake       quick flare of the ring
    listening  core reacts to the microphone level
    thinking   ring rotates slowly
    executing  an energy pulse travels around the ring
    speaking   core pulses with the voice level
    success    brief bright sweep
    error      subtle red, same identity
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

BLACK, NAVY = QColor("#080B12"), QColor("#0B1424")
BLUE, CYAN, WHITE = QColor("#168BFF"), QColor("#42D9FF"), QColor("#F5F8FF")
RED = QColor("#FF5A6E")

STATE_MAP = {
    "IDLE": "idle", "OFFLINE": "idle", "WAKE_DETECTED": "wake", "LISTENING": "listening", "RECOGNIZING": "thinking",
    "THINKING": "thinking", "EXECUTING": "executing", "WAITING_FOR_CONFIRMATION": "thinking", "SPEAKING": "speaking",
    "ERROR": "error", "SUCCESS": "success", "HOVER": "hover",
}

# Geometry in the 512-unit design space (same as brand/make_brand.py).
RING_R, GAP_START, GAP_SPAN = 168.0, 66.5, 329.0      # arc start/span in degrees (Qt: 0 = 3 o'clock, CCW)
CORE = QPointF(300, 250)


def _d_path() -> QPainterPath:
    """The F: stem + top arm, and a middle arm that runs into the AI core."""
    p = QPainterPath(QPointF(330, 152))
    p.lineTo(196, 152)
    p.lineTo(196, 360)
    p.moveTo(196, 250)
    p.lineTo(258, 250)
    return p


D_PATH = _d_path()


class Emblem(QWidget):
    def __init__(self, size: int, parent=None, simple: bool | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.simple = size < 48 if simple is None else simple
        self.mode = "idle"
        self.level = 0.0
        self._lvl = 0.0
        self._angle = 0.0
        self._pulse = 0.0
        self._t0 = time.monotonic()
        self._flash_until = 0.0
        self._timer = QTimer(self, timeout=self._tick)
        self._timer.start(83)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_state(self, state: str):
        mode = STATE_MAP.get(state, "idle")
        if mode in ("success", "wake"):
            self._flash_until = time.monotonic() + (0.9 if mode == "success" else 0.6)
        self.mode = mode
        busy = mode not in ("idle", "hover", "error")
        self._timer.setInterval(16 if busy else 83)        # 60 fps active, 12 fps breathing
        self.update()

    def set_level(self, v: float):
        self.level = max(0.0, min(1.0, v))

    def showEvent(self, e):
        self._timer.start()

    def hideEvent(self, e):
        self._timer.stop()                                  # no CPU while hidden

    def _tick(self):
        dt = 0.016 if self._timer.interval() < 30 else 0.083
        speed = {"thinking": 40.0, "executing": 70.0}.get(self.mode, 0.0)
        self._angle = (self._angle + speed * dt) % 360
        self._pulse = (self._pulse + dt * (0.9 if self.mode == "executing" else 0.0)) % 1.0
        self._lvl += (self.level - self._lvl) * 0.35
        if self.mode in ("success", "wake") and time.monotonic() > self._flash_until:
            self.mode = "idle"
            self._timer.setInterval(83)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.width() / 512.0
        p.scale(s, s)
        t = time.monotonic() - self._t0
        err = self.mode == "error"
        ring_col = RED if err else BLUE
        accent = RED if err else CYAN
        flash = max(0.0, self._flash_until - time.monotonic())
        breathe = 0.5 + 0.5 * math.sin(t * 1.6)

        ring_w = 22 if self.simple else 14
        d_w = 30 if self.simple else 26
        rect = QRectF(256 - RING_R, 256 - RING_R, 2 * RING_R, 2 * RING_R)

        # Glow under the ring (cheap: a wide translucent stroke)
        glow = QColor(accent)
        glow.setAlpha(int(40 + 50 * breathe + 120 * min(1.0, flash * 2) + (60 if self.mode == "hover" else 0)))
        gp = QPen(glow, ring_w * 2.6)
        gp.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.save()
        p.translate(256, 256)
        p.rotate(-self._angle)
        p.translate(-256, -256)
        p.setPen(gp)
        p.drawArc(rect, int(GAP_START * 16), int(GAP_SPAN * 16))
        # Ring
        rp = QPen(ring_col if not flash else accent, ring_w)
        rp.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(rp)
        p.drawArc(rect, int(GAP_START * 16), int(GAP_SPAN * 16))
        # Orbiting node at the start of the gap
        a = math.radians(GAP_START + GAP_SPAN)
        node = QPointF(256 + RING_R * math.cos(a), 256 - RING_R * math.sin(a))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawEllipse(node, 18 if self.simple else 13, 18 if self.simple else 13)
        p.restore()

        # Executing: an energy pulse travelling around the ring
        if self.mode == "executing":
            ang = GAP_START + GAP_SPAN * self._pulse
            for k in range(6):
                aa = math.radians(ang - k * 7)
                c = QColor(WHITE if k == 0 else CYAN)
                c.setAlpha(255 - k * 40)
                p.setBrush(c)
                p.drawEllipse(QPointF(256 + RING_R * math.cos(aa), 256 - RING_R * math.sin(aa)),
                              (14 - k * 1.6), (14 - k * 1.6))

        # The F
        dp = QPen(WHITE, d_w)
        dp.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        dp.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(dp)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(D_PATH)

        # The AI core
        react = self._lvl if self.mode in ("listening", "speaking") else 0.0
        r = (46 if self.simple else 40) * (1 + 0.35 * react + 0.04 * breathe)
        halo = QRadialGradient(CORE, r * 2.2)
        hc = QColor(accent)
        hc.setAlpha(int(70 + 120 * react + 40 * breathe))
        halo.setColorAt(0, hc)
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(CORE, r * 2.2, r * 2.2)
        core = QRadialGradient(QPointF(CORE.x() - r * 0.3, CORE.y() - r * 0.35), r * 1.4)
        core.setColorAt(0, WHITE)
        core.setColorAt(0.35, accent)
        core.setColorAt(1, RED.darker(140) if err else BLUE)
        p.setBrush(core)
        p.drawEllipse(CORE, r, r)
        if not self.simple:
            pen = QPen(BLACK, 7)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(CORE, 15, 15)
