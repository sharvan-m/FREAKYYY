"""Freakyyy Notch - a MacBook-style notch fused to the top edge of the screen
(flat top, curved shoulders, rounded bottom) that grows downward into four layouts:

    PILL   emblem · FREAKYYY · mic dot · laptop/phone dots         (no focus, never in the way)
    HOVER  "How can I help?" · voice · text field · devices · history · quick actions · expand
    VOICE  live session: transcript · waveform · target · action · status · result · stop/cancel
    PANEL  full control panel: emblem + waveform, input + mic + target switch, conversation /
           activity / history / applications views, device cards, quick actions, settings

It only displays state and submits text - the app's own parser, executor,
listener and Kokoro voice do the work, exactly as for voice input.
"""
from __future__ import annotations

import ctypes
import math
import random
import time
from collections import deque

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from ..config import settings
from . import theme as T
from .emblem import Emblem

PILL, HOVER, VOICE, PANEL = 0, 1, 2, 3
SIZES = {PILL: (264, 34), HOVER: (600, 200), VOICE: (620, 228), PANEL: (840, 640)}
GLOW = 12          # room for the state glow at the sides and bottom
EAR = 10           # the notch's curved shoulders where it meets the top edge
SIDE = GLOW + EAR
SESSION = {"WAKE_DETECTED", "LISTENING", "RECOGNIZING", "THINKING", "EXECUTING", "WAITING_FOR_CONFIRMATION", "SPEAKING"}
CAPTURE = {"WAKE_DETECTED", "LISTENING", "RECOGNIZING"}


class Waveform(QWidget):
    def __init__(self, bars: int = 64, parent=None):
        super().__init__(parent)
        self.levels: deque[float] = deque([0.0] * bars, maxlen=bars)
        self.setMinimumHeight(34)

    def push(self, v: float):
        self.levels.append(v)
        if self.isVisible():
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n, w, h = len(self.levels), self.width(), self.height()
        step = w / n
        p.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(self.levels):
            amp = max(2.0, min(1.0, v * 1.4) * (h - 4))
            c = QColor(T.CYAN)
            c.setAlpha(int(70 + 180 * i / n))
            p.setBrush(c)
            p.drawRoundedRect(QRectF(i * step + step * 0.22, (h - amp) / 2, step * 0.56, amp), 1.5, 1.5)


class Dot(QLabel):
    def __init__(self, tip: str = ""):
        super().__init__("●")
        self.setToolTip(tip)
        self.set(T.MUTED)

    def set(self, color: QColor, big: bool = False, tip: str | None = None):
        self.setStyleSheet(f"color:{color.name()}; font-size:{'11pt' if big else '8.5pt'}; background:transparent;")
        if tip:
            self.setToolTip(tip)


class DeviceCard(QFrame):
    def __init__(self, icon: str, title: str):
        super().__init__()
        self.setStyleSheet(f"QFrame{{background:{T.rgba(T.WHITE, .05)}; border:1px solid {T.rgba(T.ICE, .14)}; border-radius:14px;}}"
                           "QLabel{border:none; background:transparent;}")
        lay = QGridLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setHorizontalSpacing(8)
        self.icon = QLabel(icon)
        self.icon.setStyleSheet("font-size:16pt;")
        self.title = QLabel(title)
        self.title.setFont(T.font(9.5, T.QFont.Weight.DemiBold))
        self.dot = Dot()
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color:{T.MUTED.name()}; font-size:8.5pt;")
        lay.addWidget(self.icon, 0, 0, 2, 1)
        lay.addWidget(self.title, 0, 1)
        lay.addWidget(self.dot, 0, 2)
        lay.addWidget(self.detail, 1, 1, 1, 2)
        lay.setColumnStretch(1, 1)

    def set(self, title: str, online: bool | None, detail: str):
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(title, Qt.TextElideMode.ElideRight, 170))
        self.title.setToolTip(title)
        self.dot.set(T.SUCCESS if online else T.WARNING if online is False else T.MUTED)
        self.detail.setText(detail)


class DynamicIsland(QWidget):
    command = Signal(str)
    push_to_talk = Signal()
    cancel_voice = Signal()
    mute_toggled = Signal(bool)
    open_settings = Signal(str)
    open_dashboard = Signal()
    pair_device = Signal()
    hide_requested = Signal()
    exit_requested = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Freakyyy Notch")
        self.mode = PILL
        self.state = "IDLE"
        self.muted = False
        self.result_until = 0.0
        self.phone: dict | None = None
        self.laptop: dict = {}
        self.get_apps = lambda: []           # set by the app
        self.get_history = lambda: []
        self._hovered = False
        self._press: QPoint | None = None
        self._dragging = False
        self._from = self._to = SIZES[PILL]
        self._particles = [[random.random(), random.random(), random.uniform(0.0004, 0.0014), random.uniform(1, 2.2)]
                           for _ in range(34)]
        self._anim = QVariantAnimation(self, duration=360, startValue=0.0, endValue=1.0)
        self._anim.valueChanged.connect(self._step)
        self._anim.finished.connect(self._settled)
        self._collapse = QTimer(self, singleShot=True, timeout=self._auto_collapse)
        # Open only while the pointer rests on it, you're typing in it, or Freakyyy is listening/speaking;
        # otherwise fold back into the notch (also immediately when you click anywhere else).
        self._hover_since: float | None = None
        # After Stop/Cancel the notch stays folded until the pointer leaves it or a new "Hey Freaky" starts.
        self._dismissed = False
        self._dismissed_at = 0.0
        self._idle_since: float | None = None
        self._watch = QTimer(self, interval=100, timeout=self._watchdog)
        self._watch.start()
        # While open, sample the mouse buttons every 20 ms so even a quick click elsewhere is caught
        # (cheap, and unlike a global mouse hook it can never slow the system's pointer down).
        self._click_pos: QPoint | None = None
        self._was_down = False
        self._clicks = QTimer(self, interval=20, timeout=self._sample_clicks)
        self._fx = QTimer(self, interval=40, timeout=self._fx_tick)

        self._build()
        self._place(SIZES[PILL])
        self._show_content(PILL, fade=False)
        QGuiApplication.instance().screenAdded.connect(lambda _: self._place(SIZES[self.mode]))
        QGuiApplication.instance().screenRemoved.connect(lambda _: self._place(SIZES[self.mode]))

    # ================================================================== building
    def _label(self, text="", size=9.5, weight=T.QFont.Weight.Normal, color=None, spacing=0.0, wrap=False, mono=False):
        l = QLabel(text)
        l.setFont(T.font(size, weight, spacing, mono=mono))
        if color is not None:
            l.setStyleSheet(f"color:{color};")
        l.setWordWrap(wrap)
        return l

    def _button(self, text, tip, slot, primary=False, small=False) -> QPushButton:
        b = QPushButton(text)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            b.setObjectName("primary")
        else:
            b.setStyleSheet(f"QPushButton{{padding:{'4px 9px' if small else '6px 12px'}; border-radius:11px; font-size:{'8.5pt' if small else '9pt'};}}")
        b.clicked.connect(slot)
        return b

    def _input(self, placeholder) -> QLineEdit:
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setMinimumHeight(34)
        e.returnPressed.connect(lambda: self._run(e))
        return e

    def _build(self):
        # ---------------- PILL
        self.pill = QWidget(self)
        pl = QHBoxLayout(self.pill)
        pl.setContentsMargins(12, 0, 14, 2)
        pl.setSpacing(7)
        self.pill_emblem = Emblem(24)
        self.pill_text = self._label("FREAKYYY", 8.5, T.QFont.Weight.DemiBold, T.WHITE.name(), 3)
        self.pill_mic = Dot("Microphone")
        self.pill_lap = self._label("💻", 9)
        self.pill_lap_dot = Dot("Laptop")
        self.pill_phone = self._label("📱", 9)
        self.pill_phone_dot = Dot("Phone")
        pl.addWidget(self.pill_emblem)
        pl.addWidget(self.pill_text, 1)
        self.pill_mic.setParent(self.pill)
        self.pill_mic.hide()                     # mic state shows on the emblem; the notch keeps two dots
        for w in (self.pill_lap, self.pill_lap_dot, self.pill_phone, self.pill_phone_dot):
            pl.addWidget(w)

        # ---------------- HOVER
        self.hover = QWidget(self)
        hl = QHBoxLayout(self.hover)
        hl.setContentsMargins(18, 14, 18, 14)
        hl.setSpacing(16)
        self.h_emblem = Emblem(104)
        hl.addWidget(self.h_emblem, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(6)
        top = QHBoxLayout()
        self.h_title = self._label("How can I help?", 13, T.QFont.Weight.DemiBold, T.WHITE.name())
        top.addWidget(self.h_title, 1)
        top.addWidget(self._button("History", "Recent commands", lambda: self._open_panel_view("history"), small=True))
        top.addWidget(self._button("⤢", "Open the full panel", lambda: self.set_mode(PANEL), small=True))
        col.addLayout(top)
        self.h_status = self._label("", 8.5, T.QFont.Weight.DemiBold, T.CYAN.name(), 1.6)
        col.addWidget(self.h_status)
        row = QHBoxLayout()
        self.h_input = self._input("Type a command — Enter to run")
        row.addWidget(self.h_input, 1)
        row.addWidget(self._button("🎙", "Talk (Ctrl+Alt+D)", self._talk, primary=True))
        col.addLayout(row)
        qa = QHBoxLayout()
        qa.setSpacing(5)
        for label, fn in (("Apps", lambda: self._open_panel_view("apps")), ("Status", lambda: self.command.emit("system status")),
                          ("Devices", self._devices_action), ("Routines", lambda: self.open_settings.emit("routines"))):
            qa.addWidget(self._button(label, label, fn, small=True))
        qa.addStretch(1)
        self.h_devices = self._label("", 8.5, color=T.MUTED.name())
        qa.addWidget(self.h_devices)
        col.addLayout(qa)
        hl.addLayout(col, 1)

        # ---------------- VOICE (live session / execution)
        self.voice = QWidget(self)
        vl = QHBoxLayout(self.voice)
        vl.setContentsMargins(18, 14, 18, 14)
        vl.setSpacing(16)
        self.v_emblem = Emblem(132)
        vl.addWidget(self.v_emblem, 0, Qt.AlignmentFlag.AlignVCenter)
        vc = QVBoxLayout()
        vc.setSpacing(4)
        vtop = QHBoxLayout()
        self.v_mic = Dot()
        self.v_state = self._label("", 9.5, T.QFont.Weight.DemiBold, None, 3)
        vtop.addWidget(self.v_mic)
        vtop.addWidget(self.v_state, 1)
        self.v_cancel = self._button("Cancel", "Cancel listening", lambda: self._stop_and_fold(cancel=True), small=True)
        vtop.addWidget(self.v_cancel)
        vtop.addWidget(self._button("Stop", "Stop speaking and any running task", self._stop_and_fold, small=True))
        vc.addLayout(vtop)
        self.v_transcript = self._label("", 13, T.QFont.Weight.Light, T.WHITE.name(), wrap=True)
        vc.addWidget(self.v_transcript)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        self.v_target = self._label("", 9, color=T.WHITE.name())
        self.v_action = self._label("", 9, color=T.WHITE.name())
        self.v_status = self._label("", 9, T.QFont.Weight.DemiBold)
        for r, (k, w) in enumerate((("Target", self.v_target), ("Action", self.v_action), ("Status", self.v_status))):
            grid.addWidget(self._label(k.upper(), 7.5, T.QFont.Weight.DemiBold, T.rgba(T.ICE, .55), 1.6), r, 0)
            grid.addWidget(w, r, 1)
        grid.setColumnStretch(1, 1)
        vc.addLayout(grid)
        self.v_result = self._label("", 9.5, color=T.rgba(T.ICE, .9), wrap=True)
        vc.addWidget(self.v_result)
        self.v_wave = Waveform(56)
        vc.addWidget(self.v_wave)
        vl.addLayout(vc, 1)

        # ---------------- PANEL
        self.panel = QWidget(self)
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(22, 14, 22, 16)
        pv.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(Emblem(28))
        head.addWidget(self._label("FREAKYYY", 11.5, T.QFont.Weight.Bold, T.WHITE.name(), 5))
        head.addSpacing(10)
        self.p_mic_dot = Dot()
        self.p_mic_label = self._label("", 8.5, color=T.ICE.name(), spacing=1)
        head.addWidget(self.p_mic_dot)
        head.addWidget(self.p_mic_label)
        head.addStretch(1)
        self.p_mute = self._button("Mute", "Turn the microphone off/on", self._toggle_mute, small=True)
        head.addWidget(self.p_mute)
        head.addWidget(self._button("Hide", "Hide the island (tray → Show island)", self.hide_requested.emit, small=True))
        head.addWidget(self._button("Exit", "Quit Freakyyy", self.exit_requested.emit, small=True))
        head.addWidget(self._button("✕", "Collapse (Esc)", lambda: self.set_mode(PILL), small=True))
        pv.addLayout(head)

        hero = QHBoxLayout()
        hero.setSpacing(18)
        self.p_emblem = Emblem(168)
        hero.addWidget(self.p_emblem)
        info = QVBoxLayout()
        info.setSpacing(4)
        self.p_state = self._label("", 10, T.QFont.Weight.DemiBold, None, 4)
        self.p_transcript = self._label("", 14, T.QFont.Weight.Light, T.WHITE.name(), wrap=True)
        self.p_detail = self._label("", 8.5, mono=True, color=T.rgba(T.CYAN, .75), wrap=True)
        self.p_result = self._label("", 10, color=T.rgba(T.ICE, .9), wrap=True)
        self.p_wave = Waveform(72)
        for w in (self.p_state, self.p_transcript, self.p_detail, self.p_result):
            info.addWidget(w)
        info.addStretch(1)
        info.addWidget(self.p_wave)
        hero.addLayout(info, 1)
        cards = QVBoxLayout()
        self.card_laptop = DeviceCard("💻", "This laptop")
        self.card_phone = DeviceCard("📱", "Phone")
        cards.addWidget(self.card_laptop)
        cards.addWidget(self.card_phone)
        cards.addStretch(1)
        cw = QWidget()
        cw.setLayout(cards)
        cw.setFixedWidth(262)
        hero.addWidget(cw)
        pv.addLayout(hero)

        ctl = QHBoxLayout()
        ctl.addWidget(self._label("SEND TO", 7.5, T.QFont.Weight.DemiBold, T.rgba(T.ICE, .55), 1.6))
        self.target = QButtonGroup(self)
        seg = (f"QPushButton{{padding:5px 11px; border-radius:11px; font-weight:600; font-size:8.5pt;}}"
               f"QPushButton:checked{{background:{T.rgba(T.BLUE, .55)}; border-color:{T.CYAN.name()};}}")
        for n, label in enumerate(("Auto", "Laptop", "Phone", "Both")):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(n == 0)
            b.setStyleSheet(seg)
            b.setToolTip("Where typed commands run. Auto follows your words (\"…on my phone\").")
            self.target.addButton(b, n)
            ctl.addWidget(b)
        self.p_input = self._input("Type a command — Enter runs it, Esc closes")
        self.p_input.textChanged.connect(lambda _: self.view == "apps" and self._refresh_view())
        ctl.addWidget(self.p_input, 1)
        ctl.addWidget(self._button("🎙 Talk", "Switch to voice", self._talk, primary=True))
        pv.addLayout(ctl)

        views = QHBoxLayout()
        self.view_group = QButtonGroup(self)
        for n, (key, label) in enumerate((("conversation", "Conversation"), ("activity", "Recent activity"),
                                          ("history", "History"), ("apps", "Applications"))):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(n == 0)
            b.setStyleSheet(seg)
            b.clicked.connect(lambda _=False, k=key: self._show_view(k))
            self.view_group.addButton(b, n)
            views.addWidget(b)
        views.addStretch(1)
        pv.addLayout(views)
        self.p_list = QListWidget()
        self.p_list.setWordWrap(True)
        self.p_list.setStyleSheet(f"QListWidget{{background:{T.rgba(T.WHITE, .04)}; border:1px solid {T.rgba(T.ICE, .1)}; border-radius:12px; padding:4px;}}"
                                  f"QListWidget::item{{padding:4px 6px;}}")
        self.p_list.itemDoubleClicked.connect(self._list_activated)
        pv.addWidget(self.p_list, 1)
        self.view = "conversation"
        self.convo: list[tuple[str, QColor]] = []
        self.activity: list[tuple[str, QColor]] = []

        quick = QHBoxLayout()
        quick.setSpacing(6)
        for label, fn in (("Applications", lambda: self._show_view("apps")),
                          ("System status", lambda: self.command.emit("system status")),
                          ("Device connection", self._devices_action),
                          ("Recent activity", lambda: self._show_view("activity")),
                          ("Routines", lambda: self.open_settings.emit("routines")),
                          ("History", lambda: self._show_view("history")),
                          ("Settings", lambda: self.open_settings.emit("")),
                          ("Full dashboard", self.open_dashboard.emit)):
            quick.addWidget(self._button(label, label, fn, small=True))
        pv.addLayout(quick)

        for w in (self.pill, self.hover, self.voice, self.panel):
            w.hide()

    # ================================================================== placement
    def _screen(self):
        name = settings.get("island_screen")
        for s in QGuiApplication.screens():
            if s.name() == name:
                return s
        return QGuiApplication.primaryScreen()

    def _rect_for(self, size) -> QRect:
        """The notch hangs from the very top of the screen; only its horizontal position can change."""
        geo = self._screen().availableGeometry()
        w, h = min(size[0], geo.width() - 2 * SIDE - 20), min(size[1], geo.height() - 40)
        cx = geo.center().x() + int(settings.get("island_dx") or 0)
        cx = max(geo.left() + w // 2 + SIDE, min(geo.right() - w // 2 - SIDE, cx))
        return QRect(cx - w // 2 - SIDE, geo.top(), w + 2 * SIDE, h + GLOW)

    def _body(self) -> tuple[int, int]:
        return self.width() - 2 * SIDE, self.height() - GLOW

    def _place(self, size):
        self.setGeometry(self._rect_for(size))

    def _no_activate(self, on: bool):
        """WS_EX_NOACTIVATE while collapsed: clicks on the pill never steal keyboard focus."""
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_NOACTIVATE) if on else (ex & ~WS_EX_NOACTIVATE))
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)
        self._no_activate(self.mode == PILL)

    # ================================================================== morphing
    def set_mode(self, mode: int):
        if mode == self.mode and self._anim.state() != QVariantAnimation.State.Running:
            return
        self._from = self._body()
        self._to = SIZES[mode]
        growing = self._to[0] * self._to[1] > self._from[0] * self._from[1]
        self._anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutBack) if growing else QEasingCurve(QEasingCurve.Type.OutCubic))
        self._anim.setDuration(420 if growing else 260)
        self.mode = mode
        for w in (self.pill, self.hover, self.voice, self.panel):
            w.hide()
        self._no_activate(mode == PILL)
        self._anim.stop()
        self._anim.start()
        self._fx.start() if mode in (PANEL, VOICE) else self._fx.stop()
        if mode == PANEL:
            self._refresh_view()

    def _step(self, t):
        fw, fh = self._from
        tw, th = self._to
        self._place((round(fw + (tw - fw) * t), round(fh + (th - fh) * t)))
        self.update()

    def _settled(self):
        self._place(SIZES[self.mode])
        self._show_content(self.mode)
        if self.mode == PANEL:
            self.raise_()
            self.activateWindow()
            self.p_input.setFocus()

    def _show_content(self, mode, fade=True):
        w = {PILL: self.pill, HOVER: self.hover, VOICE: self.voice, PANEL: self.panel}[mode]
        bw, bh = self._body()
        w.setGeometry(SIDE, 0, bw, bh)
        if not fade:
            w.show()
            return
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(0.0)
        w.setGraphicsEffect(eff)
        w.show()
        a = QVariantAnimation(self, duration=170, startValue=0.0, endValue=1.0)
        a.valueChanged.connect(eff.setOpacity)
        a.finished.connect(lambda: w.setGraphicsEffect(None))
        a.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _busy(self) -> bool:
        return self.state in SESSION or time.time() < self.result_until

    def _schedule_collapse(self, extra_ms: int = 0):
        """Collapsing is decided by _watchdog; kept for callers."""

    def _auto_collapse(self):
        pass

    # ------------------------------------------------------------------ open / close rules
    HOVER_DWELL = 0.35        # s the pointer must rest on the notch before it opens (ignores fly-overs)
    IDLE_GRACE = 0.6          # s before folding back once nothing keeps it open

    def _pointer_inside(self) -> bool:
        if not self.isVisible():
            return False
        pos = QCursor.pos()
        if self.mode == PILL:                   # only the black notch itself, not the glow margin
            bw, bh = self._body()
            return QRect(self.x() + SIDE, self.y(), bw, bh + 2).contains(pos)
        return self.geometry().contains(pos)

    def _typing(self) -> bool:
        field = self.p_input if self.mode == PANEL else self.h_input
        return self.isActiveWindow() and field.hasFocus() and bool(field.text())

    def _speaking(self) -> bool:
        return self.state in SESSION or time.time() < self.result_until

    @staticmethod
    def _mouse_down() -> bool:
        try:
            gaks = ctypes.windll.user32.GetAsyncKeyState
            return bool(gaks(0x01) & 0x8000 or gaks(0x02) & 0x8000)      # left / right button
        except Exception:
            return False

    def _sample_clicks(self):
        down = self._mouse_down()
        if down and not self._was_down:
            self._click_pos = QCursor.pos()          # where a new click started
        self._was_down = down

    def _stop_and_fold(self, cancel: bool = False):
        """Stop / Cancel: end what Freakyyy is doing and go straight back to the notch."""
        if cancel:
            self.cancel_voice.emit()
        else:
            self.command.emit("stop")
        self._dismissed = True
        self._dismissed_at = time.monotonic()
        self.result_until = 0.0
        self._idle_since = None
        self._hover_since = None
        self.set_mode(PILL)

    def keep_open_reason(self) -> str:
        """Why the notch is open right now ('' = nothing keeps it open). Used by the watchdog and tests."""
        if self._dragging or self._press is not None:
            return "dragging"
        if self._speaking():
            return "speaking"
        if self._typing():
            return "typing"
        if self._pointer_inside():
            return "hover"
        return ""

    def _watchdog(self):
        now = time.monotonic()
        if self.mode == PILL:
            if self._clicks.isActive():
                self._clicks.stop()
                self._click_pos = None
            if self._dismissed:
                # Stay folded for 3 s (the "Stopped." reply lands meanwhile) and until the pointer is off it.
                if not self._pointer_inside() and now - self._dismissed_at > 3.0:
                    self._dismissed = False
                return
            if self._pointer_inside() and not self._mouse_down():
                if self._hover_since is None:
                    self._hover_since = now
                elif now - self._hover_since >= self.HOVER_DWELL:
                    self._hover_since = None
                    self.pill_emblem.set_state("HOVER" if self.state == "IDLE" else self.state)
                    self.set_mode(VOICE if self._busy() else HOVER)
            else:
                self._hover_since = None
            return
        if not self._clicks.isActive():
            self._was_down = self._mouse_down()
            self._clicks.start()
        if self._anim.state() == QVariantAnimation.State.Running:
            return
        click, self._click_pos = self._click_pos, None
        clicked_elsewhere = click is not None and not self.geometry().contains(click)
        # Clicking elsewhere means "I'm done here" - it ends typing too, but never interrupts a voice session.
        if clicked_elsewhere and not self._speaking() and not self._dragging:
            self._idle_since = None
            self.set_mode(PILL)
            return
        reason = self.keep_open_reason()
        if reason:
            self._idle_since = None
            return
        if self._idle_since is not None and now - self._idle_since >= self.IDLE_GRACE:
            self._idle_since = None
            self.set_mode(PILL)
        elif self._idle_since is None:
            self._idle_since = now

    # ================================================================== painting
    def _fx_tick(self):
        for pt in self._particles:
            pt[1] -= pt[2]
            if pt[1] < 0:
                pt[0], pt[1] = random.random(), 1.0
        self.update()

    @staticmethod
    def _outline(r: QRectF) -> QPainterPath:
        """Open outline: left shoulder -> left side -> bottom -> right side -> right shoulder (no top edge)."""
        rb = min(r.height() - EAR, 13 if r.height() < 60 else 26)
        path = QPainterPath(QPointF(r.left() - EAR, r.top()))
        path.cubicTo(r.left() - EAR * 0.35, r.top(), r.left(), r.top() + EAR * 0.4, r.left(), r.top() + EAR)
        path.lineTo(r.left(), r.bottom() - rb)
        path.arcTo(QRectF(r.left(), r.bottom() - 2 * rb, 2 * rb, 2 * rb), 180, 90)
        path.lineTo(r.right() - rb, r.bottom())
        path.arcTo(QRectF(r.right() - 2 * rb, r.bottom() - 2 * rb, 2 * rb, 2 * rb), 270, 90)
        path.lineTo(r.right(), r.top() + EAR)
        path.cubicTo(r.right(), r.top() + EAR * 0.4, r.right() + EAR * 0.35, r.top(), r.right() + EAR, r.top())
        return path

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bw, bh = self._body()
        r = QRectF(SIDE, 0, bw, bh)
        outline = self._outline(r)
        path = QPainterPath(outline)
        path.closeSubpath()                                   # the flat top runs along the screen edge
        accent = QColor(T.STATE_COLORS.get(self.state, T.BLUE))
        live = self.state in SESSION
        # Soft state glow below and beside the notch (none in idle, like a real notch).
        if live or self.mode != PILL:
            for i in range(GLOW, 0, -2):
                c = QColor(accent)
                c.setAlpha(int((18 if live else 7) * (GLOW - i + 2) / GLOW))
                p.setPen(QPen(c, i * 1.7))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(outline)
        # Pure black, so the collapsed notch reads as part of the screen bezel.
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(0, 0, 0, 255))
        g.setColorAt(0.7, QColor(2, 4, 9, 255))
        g.setColorAt(1, QColor(6, 10, 18, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(path)
        if r.height() > 100:
            p.save()
            p.setClipPath(path)
            for cx, cy, rad, col in ((0.16, 0.18, 0.5, T.BLUE), (0.9, 0.95, 0.45, T.CYAN)):
                rg = QRadialGradient(QPointF(r.left() + r.width() * cx, r.top() + r.height() * cy), r.width() * rad)
                cc = QColor(col)
                cc.setAlpha(30)
                rg.setColorAt(0, cc)
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(r, rg)
            if self._fx.isActive():
                for x, y, _, s in self._particles:
                    p.setBrush(QColor(66, 217, 255, int(70 * math.sin(math.pi * y))))
                    p.drawEllipse(QPointF(r.left() + x * r.width(), r.top() + y * r.height()), s, s)
            p.restore()
        # Hairline rim on the sides and bottom only, fading in from the top edge.
        edge = QLinearGradient(r.topLeft(), r.bottomLeft())
        edge.setColorAt(0, QColor(0, 0, 0, 0))
        ec = QColor(accent)
        ec.setAlpha(110 if live else 55)
        edge.setColorAt(0.55, ec)
        edge.setColorAt(1, QColor(ec.red(), ec.green(), ec.blue(), 150 if live else 70))
        p.setPen(QPen(QBrush(edge), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(outline)

    # ================================================================== mouse / keyboard
    def enterEvent(self, e):
        self._hovered = True                     # opening waits for the hover dwell (see _watchdog)

    def leaveEvent(self, e):
        self._hovered = False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._dragging = False

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        delta = e.globalPosition().toPoint() - self._press
        if not self._dragging and delta.manhattanLength() > 6:
            self._dragging = True
        if self._dragging:
            self.move(self.x() + delta.x(), self.y())          # a notch slides along the top edge only
            self._press = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        if self._dragging:
            # Remember the spot relative to the screen it was dropped on (multi-monitor, any DPI).
            centre = self.geometry().center()
            screen = QGuiApplication.screenAt(centre) or QGuiApplication.primaryScreen()
            geo = screen.availableGeometry()
            settings.set("island_screen", screen.name())
            settings.set("island_dx", centre.x() - geo.center().x())
            self._place(SIZES[self.mode])
        elif self.mode != PANEL:
            self.set_mode(PANEL)
        self._press = None
        self._dragging = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            field = self.p_input if self.mode == PANEL else self.h_input
            if field.text():
                field.clear()
            elif self.state in CAPTURE:
                self._stop_and_fold(cancel=True)
            else:
                self.set_mode(PILL)
            return
        super().keyPressEvent(e)

    def changeEvent(self, e):
        # Clicking outside closes the panel - but never mid-session or with text typed.
        if e.type() == QEvent.Type.ActivationChange and not self.isActiveWindow() and self.mode == PANEL:
            if not self._busy() and not self.p_input.text():
                QTimer.singleShot(120, lambda: (not self.isActiveWindow() and self.mode == PANEL and not self._busy())
                                  and self.set_mode(PILL))
        super().changeEvent(e)

    # ================================================================== actions
    def _run(self, field: QLineEdit):
        text = field.text().strip()
        if not text:
            return
        if field is self.p_input and self.view == "apps":
            matches = [n for n in self.get_apps() if text.lower() in n.lower()]
            field.clear()
            if matches:
                self.command.emit("open " + matches[0])
            return
        field.clear()
        target = self.target.checkedId() if field is self.p_input else 0
        suffix = {1: " on my laptop", 2: " on my phone", 3: " on both devices"}.get(target, "")
        self.command.emit(text + suffix)

    def _talk(self):
        self.push_to_talk.emit()

    def _toggle_mute(self):
        self.mute_toggled.emit(not self.muted)

    def _devices_action(self):
        if not self.phone:
            self.pair_device.emit()
        else:
            self.command.emit("show my phone status")

    def _open_panel_view(self, view: str):
        self.view = view
        self.set_mode(PANEL)

    def _show_view(self, view: str):
        self.view = view
        if self.mode != PANEL:
            self.set_mode(PANEL)
        else:
            self._refresh_view()

    def _refresh_view(self):
        ids = {"conversation": 0, "activity": 1, "history": 2, "apps": 3}
        b = self.view_group.button(ids.get(self.view, 0))
        if b:
            b.setChecked(True)
        self.p_list.clear()
        rows: list[tuple[str, QColor]]
        if self.view == "conversation":
            rows = self.convo or [("Say “Hey Freaky”, or type below.", T.MUTED)]
        elif self.view == "activity":
            rows = self.activity or [("No activity yet.", T.MUTED)]
        elif self.view == "history":
            rows = [(f"{time.strftime('%H:%M', time.localtime(h.get('t', 0)))}  {h.get('command', '')} — {h.get('message', '')[:80]}",
                     T.OUTCOME_COLORS.get(h.get("outcome"), T.ICE)) for h in self.get_history()[:80]] or [("No history yet.", T.MUTED)]
        else:
            q = self.p_input.text().strip().lower()
            names = [n for n in self.get_apps() if q in n.lower()]
            rows = [(f"▸  {n}", T.WHITE) for n in names[:300]] or [("No apps match.", T.MUTED)]
            if not q:
                self.p_input.setPlaceholderText("Filter apps — double-click one to open it")
        for text, color in rows:
            it = QListWidgetItem(text)
            it.setForeground(color)
            self.p_list.addItem(it)
        if self.view == "conversation":
            self.p_list.scrollToBottom()

    def _list_activated(self, item: QListWidgetItem):
        if self.view == "apps" and item.text().startswith("▸"):
            self.command.emit("open " + item.text()[3:].strip())
        elif self.view == "history":
            cmd = item.text()[7:].split(" — ")[0].strip()
            if cmd and not cmd.startswith("["):
                self.p_input.setText(cmd)
                self.p_input.setFocus()

    # ================================================================== state from the app
    def state_was_idle(self) -> bool:
        return self._prev_state in ("IDLE", "OFFLINE", "ERROR", "SUCCESS")

    def set_state(self, state: str):
        self._prev_state = getattr(self, "state", "IDLE")
        self.state = state
        color = T.STATE_COLORS.get(state, T.CYAN)
        label = T.STATE_LABELS.get(state, state)
        for em in (self.pill_emblem, self.h_emblem, self.v_emblem, self.p_emblem):
            em.set_state(state)
        idle = state in ("IDLE", "OFFLINE")
        self.pill_text.setText("FREAKYYY" if idle else label)
        self.pill_text.setStyleSheet(f"color:{T.WHITE.name() if idle else color.name()};")
        self.h_status.setText(label)
        self.h_status.setStyleSheet(f"color:{color.name()};")
        self.v_state.setText(label)
        self.v_state.setStyleSheet(f"color:{color.name()};")
        self.p_state.setText(label)
        self.p_state.setStyleSheet(f"color:{color.name()};")
        self.v_cancel.setVisible(state in CAPTURE)
        if state in SESSION:
            self._collapse.stop()
            if state in CAPTURE:
                self.v_status.setText("Listening" if state != "RECOGNIZING" else "Recognizing")
            elif state in ("THINKING", "EXECUTING"):
                self.v_status.setText("Executing" if state == "EXECUTING" else "Thinking")
                self.v_status.setStyleSheet(f"color:{color.name()};")
            if state in ("WAKE_DETECTED", "LISTENING"):
                self.v_transcript.setText("…")
                self.v_target.setText("")
                self.v_action.setText("")
                self.v_result.setText("")
            if state in ("WAKE_DETECTED", "LISTENING") and self.state_was_idle():
                self._dismissed = False           # a new "Hey Freaky" always opens it
            if settings.get("island_enabled") and self.isVisible() and self.mode in (PILL, HOVER) and not self._dismissed:
                self.set_mode(VOICE)
        else:
            self._schedule_collapse(int(max(0.0, self.result_until - time.time()) * 1000))
        self.update()

    def set_level(self, v: float):
        for em in (self.pill_emblem, self.h_emblem, self.v_emblem, self.p_emblem):
            em.set_level(v)
        if self.mode == VOICE:
            self.v_wave.push(v)
        elif self.mode == PANEL:
            self.p_wave.push(v)

    def set_partial(self, text: str):
        if text:
            self.v_transcript.setText(f"“{text}…”")
            self.p_transcript.setText(f"“{text}…”")

    def set_transcript(self, text: str, source: str = ""):
        if not text:
            return
        shown = f"“{text}”" + ("  · from phone" if source.startswith("phone") else "")
        self.v_transcript.setText(shown)
        self.p_transcript.setText(shown)
        self.p_result.setText("")
        self.v_result.setText("")
        self.convo.append((f"You: {text}", T.WHITE))
        self._trim_and_refresh("conversation")

    def set_action(self, data: dict):
        device = data.get("device", "")
        target = {"laptop": "Windows laptop", "phone": "Android phone", "both": "Laptop + phone"}.get(device, device)
        self.v_target.setText(target)
        self.v_action.setText(data.get("description", ""))
        self.v_status.setText("Executing")
        self.v_status.setStyleSheet(f"color:{T.STATE_COLORS['EXECUTING'].name()};")
        self.p_detail.setText(f"Target: {target}   ·   Action: {data.get('description', '')}")
        self.p_detail.setToolTip(data.get("label", ""))

    def set_reply(self, text: str, outcome: str):
        if not text:
            return
        color = T.OUTCOME_COLORS.get(outcome, T.ICE)
        status = {"COMPLETED": "Succeeded", "OPENED": "Opened · your turn", "INFO": "Done", "FAILED": "Failed",
                  "NOT_SUPPORTED": "Not allowed", "DEVICE_OFFLINE": "Device offline", "NEEDS_PERMISSION": "Needs permission",
                  "NEEDS_CONFIRMATION": "Waiting for yes/no", "CLARIFY": "Needs a detail",
                  "UNKNOWN": "Didn't understand"}.get(outcome, outcome.title())
        self.v_status.setText(status)
        self.v_status.setStyleSheet(f"color:{color.name()};")
        self.v_result.setText(text)
        self.p_result.setText(text)
        self.p_result.setStyleSheet(f"color:{color.name() if outcome in ('FAILED', 'NOT_SUPPORTED') else T.rgba(T.ICE, .92)};")
        flash = "SUCCESS" if outcome == "COMPLETED" else "ERROR" if outcome in ("FAILED", "NOT_SUPPORTED") else None
        if flash:
            for em in (self.pill_emblem, self.v_emblem, self.p_emblem):
                em.set_state(flash)
            if flash == "ERROR":
                QTimer.singleShot(2500, lambda: [em.set_state(self.state) for em in (self.pill_emblem, self.v_emblem, self.p_emblem)])
        self.convo.append((f"Freakyyy: {text}", color))
        self._trim_and_refresh("conversation")
        if self._dismissed:
            return                                # e.g. "Stopped." after the Stop button: stay folded
        self.result_until = time.time() + min(6.0, 2.5 + len(text) / 20)
        if settings.get("island_enabled") and self.isVisible() and self.mode in (PILL, HOVER):
            self.set_mode(VOICE)
        self._schedule_collapse(int((self.result_until - time.time()) * 1000))

    def add_activity(self, entry: dict):
        mark = {"COMPLETED": "✓", "FAILED": "✕", "NOT_SUPPORTED": "✕", "OPENED": "↗", "DEVICE_OFFLINE": "⚠",
                "NEEDS_PERMISSION": "⚠", "NEEDS_CONFIRMATION": "?"}.get(entry.get("outcome"), "•")
        self.activity.insert(0, (f"{mark}  {entry.get('command', '')} — {entry.get('message', '')[:100]}",
                                 T.OUTCOME_COLORS.get(entry.get("outcome"), T.ICE)))
        del self.activity[60:]
        if self.mode == PANEL and self.view == "activity":
            self._refresh_view()

    def _trim_and_refresh(self, view):
        del self.convo[:-80]
        if self.mode == PANEL and self.view == view:
            self._refresh_view()

    def set_mic(self, live: bool, capturing: bool, muted: bool):
        self.muted = muted
        color = T.DANGER if capturing else (T.MUTED if muted or not live else T.SUCCESS)
        tip = "Microphone live — listening to you" if capturing else "Muted" if muted else "Listening for “Hey Freaky”"
        self.pill_mic.set(color, capturing, tip)
        self.v_mic.set(color, capturing, tip)
        self.p_mic_dot.set(color, capturing, tip)
        self.p_mic_label.setText("MIC LIVE" if capturing else "MUTED" if muted else "WAKE WORD ON" if live else "MIC OFF")
        self.p_mute.setText("Unmute" if muted else "Mute")

    def set_devices(self, phone: dict | None, laptop: dict | None = None):
        self.phone = phone
        self.laptop = laptop or self.laptop
        lap = self.laptop
        lap_detail = f"CPU {lap.get('cpu', 0):.0f}% · RAM {lap.get('mem', 0):.0f}%"
        if lap.get("battery") is not None:
            lap_detail = f"{lap['battery']}%{' ⚡' if lap.get('charging') else ''} · " + lap_detail
        self.card_laptop.set("This laptop", True, lap_detail)
        self.pill_lap_dot.set(T.SUCCESS, tip="Laptop: online")
        if not phone:
            self.card_phone.set("No phone paired", None, "Use Device connection to pair")
            self.pill_phone_dot.set(T.DANGER, tip="Phone: not connected (no phone paired)")
            ph = "📱 not paired"
        else:
            st = phone.get("status") or {}
            online = bool(phone.get("online"))
            detail = "online" if online else "offline"
            if online and st.get("battery") is not None:
                detail += f" · {st['battery']}%{' ⚡' if st.get('charging') else ''}"
            self.card_phone.set(phone.get("name", "Phone")[:24], online, detail)
            self.pill_phone_dot.set(T.SUCCESS if online else T.DANGER,
                                    tip=f"{phone.get('name')}: {'connected' if online else 'not connected'}")
            ph = f"📱 {detail}"
        self.h_devices.setText(f"💻 online   {ph}")
