"""Freakyyy Desktop main window - a voice-first HUD. Typing and clicking are optional fallbacks."""
from __future__ import annotations

import time

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRect, QSequentialAnimationGroup,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget, QGridLayout)

from ..config import APP_VERSION, settings
from . import theme as T
from .widgets import Dot, Glass, Meter, Orb, paint_background


class ActivityItem(QWidget):
    def __init__(self, entry: dict):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        color = T.OUTCOME_COLORS.get(entry.get("outcome"), T.ICE)
        dot = Dot(color, 7)
        lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        cmd = QLabel(entry.get("command", ""))
        cmd.setFont(T.font(9.5, T.QFont.Weight.DemiBold))
        cmd.setWordWrap(True)
        tm = QLabel(time.strftime("%H:%M", time.localtime(entry.get("t", time.time()))))
        tm.setStyleSheet(f"color:{T.MUTED.name()}; font-size:8pt;")
        top.addWidget(cmd, 1)
        top.addWidget(tm, 0, Qt.AlignmentFlag.AlignTop)
        col.addLayout(top)
        msg = QLabel(entry.get("message", ""))
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color:{T.rgba(T.WHITE, .7)}; font-size:8.5pt;")
        col.addWidget(msg)
        lab = QLabel(T.OUTCOME_LABELS.get(entry.get("outcome"), entry.get("outcome", "")))
        lab.setStyleSheet(f"color:{color.name()}; font-size:7.5pt; letter-spacing:1.5px; font-weight:700;")
        col.addWidget(lab)
        lay.addLayout(col, 1)


class Chip(QWidget):
    """Status chip in the title bar: dot + text."""

    def __init__(self, text: str, color: QColor):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(6)
        self.dot = Dot(color, 7)
        self.label = QLabel(text)
        self.label.setFont(T.font(8, T.QFont.Weight.DemiBold, 1.4))
        self.label.setStyleSheet(f"color:{T.ICE.name()};")
        lay.addWidget(self.dot)
        lay.addWidget(self.label)

    def set(self, text: str, color: QColor, pulse: bool = False):
        self.label.setText(text)
        self.dot.set(color, pulse)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(255, 255, 255, 40))
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), self.height() / 2, self.height() / 2)


class MainWindow(QWidget):
    command = Signal(str)            # typed fallback
    mic_pressed = Signal()
    open_settings = Signal(str)
    pair_requested = Signal()
    hide_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Freakyyy")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(1360, 860)
        self.setMinimumSize(1100, 720)
        self._drag: QPoint | None = None
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 14, 22, 18)
        root.setSpacing(14)

        # Title bar
        bar = QHBoxLayout()
        from .emblem import Emblem
        bar.addWidget(Emblem(40))
        bar.addSpacing(6)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        title = QLabel("FREAKYYY")
        title.setFont(T.font(19, T.QFont.Weight.Bold, 7))
        sub = QLabel("PERSONAL AI SYSTEM")
        sub.setFont(T.font(7.5, T.QFont.Weight.Medium, 3.2))
        sub.setStyleSheet(f"color:{T.rgba(T.ICE, .6)};")
        brand.addWidget(title)
        brand.addWidget(sub)
        bar.addLayout(brand)
        bar.addSpacing(24)
        self.chip_wake = Chip("WAKE WORD", T.SUCCESS)
        self.chip_mic = Chip("MIC", T.MUTED)
        self.chip_link = Chip("PHONE", T.MUTED)
        self.chip_ai = Chip("AI", T.MUTED)
        self.chip_voice = Chip("VOICE", T.WARNING)
        for c in (self.chip_wake, self.chip_mic, self.chip_voice, self.chip_link, self.chip_ai):
            bar.addWidget(c)
        bar.addStretch(1)
        for text, slot, name, tip in (("⚙", lambda: self.open_settings.emit(""), "chrome", "Settings"),
                                      ("—", self.hide_requested.emit, "chrome", "Minimise to tray"),
                                      ("✕", self.hide_requested.emit, "close", "Hide (Freakyyy keeps listening)")):
            b = QPushButton(text)
            b.setObjectName("chrome" if name == "chrome" else "close")
            if name == "close":
                b.setStyleSheet("QPushButton{background:transparent;border:none;font-size:12pt;padding:4px 10px;}")
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        # ---------- Left column
        self.left = QVBoxLayout()
        self.left.setSpacing(14)
        sysc = Glass("System")
        self.m_cpu, self.m_mem, self.m_bat, self.m_disk = (Meter("CPU"), Meter("Memory"), Meter("Battery", higher_is_better=True), Meter("Disk"))
        for m in (self.m_cpu, self.m_mem, self.m_bat, self.m_disk):
            sysc.lay.addWidget(m)
        devc = Glass("Devices")
        self.dev_laptop = QLabel("💻  This laptop  ·  online")
        self.dev_laptop.setStyleSheet(f"color:{T.WHITE.name()};")
        self.dev_phone = QLabel("📱  No phone paired")
        self.dev_phone.setWordWrap(True)
        self.dev_phone.setStyleSheet(f"color:{T.rgba(T.WHITE, .75)};")
        pair = QPushButton("Add device")
        pair.clicked.connect(self.pair_requested.emit)
        devc.lay.addWidget(self.dev_laptop)
        devc.lay.addWidget(self.dev_phone)
        devc.lay.addWidget(pair)
        quick = Glass("Quick actions")
        grid = QGridLayout()
        grid.setSpacing(8)
        for n, (label, cmd) in enumerate((("Work mode", "start work mode"), ("Study mode", "start study mode on both devices"),
                                           ("Screenshot", "take a screenshot"), ("Git status", "check git status"),
                                           ("Phone status", "show my phone status"), ("Lock", "lock my laptop"))):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, c=cmd: self.command.emit(c))
            grid.addWidget(b, n // 2, n % 2)
        quick.lay.addLayout(grid)
        for w in (sysc, devc, quick):
            self.left.addWidget(w)
        self.left.addStretch(1)
        lw = QWidget()
        lw.setLayout(self.left)
        lw.setFixedWidth(300)
        body.addWidget(lw)

        # ---------- Center
        center = QVBoxLayout()
        center.setSpacing(6)
        self.orb = Orb()
        self.orb.clicked.connect(self.mic_pressed.emit)
        self.orb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center.addWidget(self.orb, 5)
        self.state_label = QLabel("STANDING BY")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setFont(T.font(11, T.QFont.Weight.DemiBold, 5))
        self.state_label.setStyleSheet(f"color:{T.CYAN.name()};")
        center.addWidget(self.state_label)
        self.hint = QLabel("Say “Hey Freaky”")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setFont(T.font(10))
        self.hint.setStyleSheet(f"color:{T.rgba(T.ICE, .55)};")
        center.addWidget(self.hint)
        center.addSpacing(8)
        self.transcript = QLabel("")
        self.transcript.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.transcript.setWordWrap(True)
        self.transcript.setFont(T.font(17, T.QFont.Weight.Light))
        self.transcript.setStyleSheet(f"color:{T.WHITE.name()};")
        center.addWidget(self.transcript)
        self.reply = QLabel("")
        self.reply.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reply.setWordWrap(True)
        self.reply.setFont(T.font(12.5))
        self.reply.setStyleSheet(f"color:{T.rgba(T.ICE, .9)};")
        center.addWidget(self.reply)
        self.action = QLabel("")
        self.action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action.setFont(T.font(8.5, mono=True))
        self.action.setStyleSheet(f"color:{T.rgba(T.CYAN, .65)};")
        center.addWidget(self.action)
        self.routine_label = QLabel("")
        self.routine_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.routine_label.setStyleSheet(f"color:{T.WARNING.name()};")
        center.addWidget(self.routine_label)
        center.addStretch(1)

        # Fallback input
        inp = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Optional: type a command and press Enter")
        self.input.returnPressed.connect(self._send_typed)
        self.input.setMinimumHeight(44)
        self.mic = QPushButton("🎙  Talk")
        self.mic.setObjectName("primary")
        self.mic.setMinimumHeight(44)
        self.mic.setToolTip(f"Push to talk ({settings.get('push_to_talk_hotkey').upper()})")
        self.mic.clicked.connect(self.mic_pressed.emit)
        inp.addWidget(self.input, 1)
        inp.addWidget(self.mic)
        center.addLayout(inp)
        cw = QWidget()
        cw.setLayout(center)
        body.addWidget(cw, 1)

        # ---------- Right column
        right = QVBoxLayout()
        right.setSpacing(14)
        act = Glass("Activity")
        self.activity = QListWidget()
        self.activity.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.activity.setSpacing(2)
        act.lay.addWidget(self.activity)
        right.addWidget(act, 3)
        self.results = Glass("Results")
        self.results_title = QLabel("")
        self.results_title.setStyleSheet(f"color:{T.WHITE.name()}; font-weight:600;")
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._open_result)
        self.results.lay.addWidget(self.results_title)
        self.results.lay.addWidget(self.results_list)
        self.results.hide()
        right.addWidget(self.results, 2)
        self.transfer = QLabel("")
        self.transfer.setWordWrap(True)
        self.transfer.setStyleSheet(f"color:{T.CYAN.name()};")
        right.addWidget(self.transfer)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(340)
        body.addWidget(rw)

        footer = QLabel(f"Freakyyy {APP_VERSION} · offline voice · audio never leaves this laptop")
        footer.setStyleSheet(f"color:{T.rgba(T.MUTED, .7)}; font-size:8pt;")
        root.addWidget(footer)

        self._panels = [lw, cw, rw]

    # ------------------------------------------------------------------ entrance animation
    def play_entrance(self):
        group = QParallelAnimationGroup(self)
        for n, panel in enumerate(self._panels):
            eff = QGraphicsOpacityEffect(panel)
            panel.setGraphicsEffect(eff)
            eff.setOpacity(0)
            fade = QPropertyAnimation(eff, b"opacity", self)
            fade.setDuration(700)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            seq = QSequentialAnimationGroup(self)
            seq.addPause(120 * n + (0 if n == 1 else 200))
            seq.addAnimation(fade)
            group.addAnimation(seq)
        orb = QPropertyAnimation(self.orb, b"intro", self)
        orb.setDuration(1100)
        orb.setStartValue(0.0)
        orb.setEndValue(1.0)
        orb.setEasingCurve(QEasingCurve.Type.OutBack)
        group.addAnimation(orb)
        group.finished.connect(lambda: [p.setGraphicsEffect(None) for p in self._panels])
        group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)

    # ------------------------------------------------------------------ updates
    def set_state(self, state: str):
        self.orb.set_state(state)
        self.state_label.setText(T.STATE_LABELS.get(state, state))
        self.state_label.setStyleSheet(f"color:{T.STATE_COLORS.get(state, T.CYAN).name()};")
        hints = {"IDLE": "Say “Hey Freaky”", "LISTENING": "Go ahead, I'm listening…", "WAKE_DETECTED": "Yes?",
                 "RECOGNIZING": "Understanding…", "WAITING_FOR_CONFIRMATION": "Say yes or no",
                 "OFFLINE": "Listening is off · press Talk or the hotkey"}
        if state in hints:
            self.hint.setText(hints[state])

    def set_transcript(self, text: str):
        self.transcript.setText(f"“{text}”" if text else "")
        self.reply.setText("")

    def set_reply(self, text: str, outcome: str):
        color = T.OUTCOME_COLORS.get(outcome, T.ICE)
        self.reply.setText(text)
        self.reply.setStyleSheet(f"color:{color.name() if outcome in ('FAILED', 'NOT_SUPPORTED') else T.rgba(T.ICE, .92)};")

    def add_activity(self, entry: dict):
        item = QListWidgetItem()
        w = ActivityItem(entry)
        item.setSizeHint(QSize(300, w.sizeHint().height() + 6))
        self.activity.insertItem(0, item)
        self.activity.setItemWidget(item, w)
        while self.activity.count() > 80:
            self.activity.takeItem(self.activity.count() - 1)

    def show_results(self, title: str, items: list[str]):
        self.results_title.setText(title)
        self.results_list.clear()
        for it in items[:40]:
            self.results_list.addItem(it)
        self.results.setVisible(bool(items))

    def _open_result(self, item):
        import os
        from pathlib import Path
        p = Path(item.text())
        if p.exists():
            os.startfile(p)

    def update_system(self, s: dict):
        self.m_cpu.set(s["cpu"] / 100, f"{s['cpu']:.0f}%")
        self.m_mem.set(s["mem"] / 100, f"{s['mem']:.0f}%")
        if s.get("battery") is not None:
            self.m_bat.set(s["battery"] / 100, f"{s['battery']}%{' ⚡' if s.get('charging') else ''}")
        else:
            self.m_bat.set(1, "AC power")
        self.m_disk.set(s["disk_percent"] / 100, f"{s['disk_free_gb']:.0f} GB free")

    def update_phone(self, d: dict | None):
        if not d:
            self.dev_phone.setText("📱  No phone paired")
            self.chip_link.set("PHONE · NOT PAIRED", T.MUTED)
            return
        st = d.get("status") or {}
        if d.get("online"):
            bat = f" · {st.get('battery')}%{' ⚡' if st.get('charging') else ''}" if st.get("battery") is not None else ""
            self.dev_phone.setText(f"📱  {d['name']}  ·  online{bat}")
            self.chip_link.set(f"PHONE · {d['name'].upper()[:18]}", T.SUCCESS)
        else:
            ago = int((time.time() - d.get("last_seen", 0)) / 60) if d.get("last_seen") else None
            self.dev_phone.setText(f"📱  {d['name']}  ·  offline" + (f" (seen {ago} min ago)" if ago is not None and ago < 600 else ""))
            self.chip_link.set("PHONE · OFFLINE", T.WARNING)

    def _send_typed(self):
        t = self.input.text().strip()
        if t:
            self.command.emit(t)
            self.input.clear()

    # ------------------------------------------------------------------ frameless window behaviour
    def paintEvent(self, e):
        p = QPainter(self)
        paint_background(p, self.rect())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < 60:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        if e.position().y() < 60:
            self.showNormal() if self.isMaximized() else self.showMaximized()

    def closeEvent(self, e):
        # Closing the window hides it; Freakyyy keeps running in the tray.
        e.ignore()
        self.hide_requested.emit()
