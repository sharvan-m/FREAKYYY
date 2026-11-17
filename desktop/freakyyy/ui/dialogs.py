"""Boot splash, pairing dialog and settings."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QInputDialog, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..config import get_secret, set_secret, settings
from . import theme as T
from .widgets import Orb, paint_background


class Splash(QWidget):
    """Entrance: the orb assembles, the wordmark resolves and each boot line ticks
    off as the real subsystem finishes loading."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(560, 600)
        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.move(scr.center() - self.rect().center())
        self.t0 = time.time()
        self.lines: list[list] = [["Voice engine · Kokoro am_onyx", False], ["Speech recognition · offline", False],
                                  ["Wake word · Hey Freaky", False], ["Freakyyy Link · secure channel", False],
                                  ["Applications · indexing", False]]
        self.orb = Orb(self)
        self.orb.setGeometry(130, 40, 300, 300)
        self.orb.set_state("THINKING")
        self.orb.set_intro(0)
        anim = QPropertyAnimation(self.orb, b"intro", self)
        anim.setDuration(1300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        anim.start()
        self._anim = anim
        self._timer = QTimer(self, interval=16, timeout=self.update)
        self._timer.start()

    def mark(self, index: int):
        if 0 <= index < len(self.lines):
            self.lines[index][1] = True

    @property
    def all_done(self) -> bool:
        return all(done for _, done in self.lines)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(109, 220, 255, 70), 1))
        bg = QRadialGradient(r.center(), r.width() * 0.7)
        bg.setColorAt(0, QColor(7, 21, 44, 250))
        bg.setColorAt(1, QColor(2, 4, 10, 250))
        p.setBrush(bg)
        p.drawRoundedRect(r, 28, 28)
        el = time.time() - self.t0
        # Wordmark resolving letter by letter
        word = "FREAKYYY"
        p.setFont(T.font(30, T.QFont.Weight.Bold, 14))
        fm = p.fontMetrics()
        total = fm.horizontalAdvance(word) + 14 * (len(word) - 1)
        x = (self.width() - total) / 2
        for n, ch in enumerate(word):
            a = max(0.0, min(1.0, (el - 0.5 - n * 0.09) / 0.35))
            p.setPen(QColor(248, 250, 255, int(255 * a)))
            p.drawText(QPointF(x, 385 + (1 - a) * 12), ch)
            x += fm.horizontalAdvance(ch) + 14
        sub_a = max(0.0, min(1.0, (el - 1.2) / 0.5))
        p.setFont(T.font(8, T.QFont.Weight.Medium, 4))
        p.setPen(QColor(189, 235, 255, int(160 * sub_a)))
        p.drawText(QRectF(0, 398, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "PERSONAL AI SYSTEM")
        # Boot lines
        p.setFont(T.font(9, mono=True))
        for n, (label, done) in enumerate(self.lines):
            a = max(0.0, min(1.0, (el - 1.0 - n * 0.15) / 0.3))
            y = 440 + n * 24
            spin = "◐◓◑◒"[int(el * 8) % 4]
            mark = "✓" if done else spin
            p.setPen(QColor(101, 221, 170, int(255 * a)) if done else QColor(109, 220, 255, int(200 * a)))
            p.drawText(QPointF(150, y), mark)
            p.setPen(QColor(248, 250, 255, int((230 if done else 150) * a)))
            p.drawText(QPointF(175, y), label)
        # Progress arc under everything
        frac = sum(1 for _, d in self.lines if d) / len(self.lines)
        p.setPen(QPen(QColor(255, 255, 255, 25), 3))
        p.drawLine(QPointF(150, 568), QPointF(self.width() - 150, 568))
        pen = QPen(T.CYAN, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(150, 568), QPointF(150 + (self.width() - 300) * frac, 568))

    def fade_out(self, done):
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(450)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.finished.connect(lambda: (self.close(), done()))
        a.start()
        self._fade = a


class GlassDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)

    def paintEvent(self, e):
        p = QPainter(self)
        paint_background(p, self.rect())


class PairingDialog(GlassDialog):
    decided = Signal(bool)

    def __init__(self, uri: str, parent=None):
        super().__init__("Pair a phone", parent)
        self.resize(520, 700)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        h = QLabel("Add your phone")
        h.setFont(T.font(20, T.QFont.Weight.Bold))
        lay.addWidget(h)
        s = QLabel("On your phone, open Freakyyy → Devices → Scan code. Both devices must be on the same Wi-Fi. "
                   "The code works once and expires in 5 minutes.")
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{T.rgba(T.ICE, .75)};")
        lay.addWidget(s)
        qr = QLabel()
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr.setPixmap(self._qr(uri))
        lay.addWidget(qr)
        link = QLineEdit(uri)
        link.setReadOnly(True)
        copy = QPushButton("Copy pairing link")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(uri))
        lay.addWidget(QLabel("No camera? Paste this link in Freakyyy on the phone:"))
        lay.addWidget(link)
        lay.addWidget(copy)
        self.code = QLabel("")
        self.code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code.setFont(T.font(26, T.QFont.Weight.Bold, 8, mono=True))
        self.code.setStyleSheet(f"color:{T.CYAN.name()};")
        lay.addWidget(self.code)
        self.prompt = QLabel("Waiting for your phone…")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt.setWordWrap(True)
        lay.addWidget(self.prompt)
        row = QHBoxLayout()
        self.accept_btn = QPushButton("Pair")
        self.accept_btn.setObjectName("primary")
        self.reject_btn = QPushButton("Decline")
        self.accept_btn.setEnabled(False)
        self.reject_btn.setEnabled(False)
        self.accept_btn.clicked.connect(lambda: self._decide(True))
        self.reject_btn.clicked.connect(lambda: self._decide(False))
        row.addWidget(self.reject_btn)
        row.addWidget(self.accept_btn)
        lay.addLayout(row)

    def _qr(self, uri: str) -> QPixmap:
        import qrcode
        q = qrcode.QRCode(border=2, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(uri)
        q.make(fit=True)
        img = q.make_image(fill_color="#02040A", back_color="#F8FAFF").convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.size[0], img.size[1], img.size[0] * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(qimg).scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def show_request(self, name: str, code: str):
        self.code.setText(f"{code[:3]} {code[3:]}")
        self.prompt.setText(f"“{name}” wants to pair. Check that the phone shows the same code, then press Pair or say “yes”.")
        self.accept_btn.setEnabled(True)
        self.reject_btn.setEnabled(True)

    def finished_pairing(self, ok: bool, name: str | None):
        self.prompt.setText(f"Paired with {name}. You can close this window." if ok else "Pairing cancelled.")
        self.accept_btn.setEnabled(False)
        self.reject_btn.setEnabled(False)
        if ok:
            QTimer.singleShot(1800, self.close)

    def _decide(self, accept: bool):
        self.accept_btn.setEnabled(False)
        self.reject_btn.setEnabled(False)
        self.prompt.setText("Waiting for the phone to confirm…" if accept else "Declined.")
        self.decided.emit(accept)


class SettingsDialog(GlassDialog):
    changed = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__("Freakyyy settings", parent)
        self.ctx = ctx              # the App object
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        h = QLabel("Settings")
        h.setFont(T.font(20, T.QFont.Weight.Bold))
        lay.addWidget(h)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._listening(), "Listening")
        self.tabs.addTab(self._voice(), "Voice")
        self.tabs.addTab(self._ai(), "AI")
        self.tabs.addTab(self._memory(), "Memory")
        self.tabs.addTab(self._email(), "Email")
        self.tabs.addTab(self._devices(), "Devices")
        self.tabs.addTab(self._routines(), "Routines")
        self.tabs.addTab(self._general(), "General & privacy")

    def show_tab(self, name: str):
        names = {"listening": 0, "voice": 1, "ai": 2, "email": 3, "devices": 4, "routines": 5, "general": 6}
        if name in names:
            self.tabs.setCurrentIndex(names[name])

    def _page(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(8, 16, 8, 8)
        f.setSpacing(12)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        return w, f

    def _note(self, f: QFormLayout, text: str):
        n = QLabel(text)
        n.setWordWrap(True)
        n.setStyleSheet(f"color:{T.rgba(T.ICE, .6)}; font-size:9pt;")
        f.addRow(n)

    def _check(self, key: str, label: str, on_change=None) -> QCheckBox:
        c = QCheckBox(label)
        c.setChecked(bool(settings.get(key)))
        c.toggled.connect(lambda v: (settings.set(key, v), on_change and on_change(v), self.changed.emit(key)))
        return c

    # ---------------------------------------------------------------- tabs
    def _listening(self):
        w, f = self._page()
        f.addRow(self._check("wake_enabled", "Listen for “Hey Freaky” in the background",
                             lambda v: self.ctx.listener and self.ctx.listener.set_enabled(v)))
        sens = QComboBox()
        sens.addItems(["strict", "normal", "sensitive"])
        sens.setCurrentText(settings.get("wake_sensitivity"))
        sens.currentTextChanged.connect(lambda v: (settings.set("wake_sensitivity", v), self.ctx.listener.change_device()))
        f.addRow("Wake word sensitivity", sens)
        mic = QComboBox()
        mic.addItem("System default", None)
        from ..voice.listener import Listener
        for idx, name in Listener.input_devices():
            mic.addItem(name, idx)
            if settings.get("mic_device") == idx:
                mic.setCurrentIndex(mic.count() - 1)
        mic.currentIndexChanged.connect(lambda _: (settings.set("mic_device", mic.currentData()), self.ctx.listener.change_device()))
        f.addRow("Microphone", mic)
        timeout = QSpinBox()
        timeout.setRange(3, 20)
        timeout.setValue(int(settings.get("listen_timeout_seconds")))
        timeout.valueChanged.connect(lambda v: settings.set("listen_timeout_seconds", v))
        f.addRow("Listening timeout (s)", timeout)
        follow = QSpinBox()
        follow.setRange(3, 15)
        follow.setValue(int(settings.get("follow_up_seconds")))
        follow.valueChanged.connect(lambda v: settings.set("follow_up_seconds", v))
        f.addRow("Answer window after a question (s)", follow)
        f.addRow("Push-to-talk hotkey", QLabel(settings.get("push_to_talk_hotkey").upper()))
        f.addRow(self._check("activation_sound", "Play a soft chime when Freakyyy starts listening"))
        f.addRow(self._check("island_enabled", "Show the Freakyyy notch at the top of the screen",
                             lambda v: self.ctx.set_island(v)))
        delay = QSpinBox()
        delay.setRange(800, 15000)
        delay.setSingleStep(250)
        delay.setSuffix(" ms")
        delay.setValue(int(settings.get("island_collapse_ms")))
        delay.valueChanged.connect(lambda v: settings.set("island_collapse_ms", v))
        f.addRow("Notch collapses after", delay)
        reset = QPushButton("Re-centre the notch")
        reset.clicked.connect(self._reset_island)
        f.addRow(reset)
        self._note(f, "Wake-word detection and speech recognition run entirely on this laptop (Vosk + Whisper). "
                      "Audio is never recorded to disk or sent anywhere. Strict needs “Hey Freaky”; sensitive also "
                      "accepts “Freaky” alone and skips the second check.")
        return w

    def _reset_island(self):
        settings.update({"island_dx": 0, "island_dy": 4, "island_screen": None})
        isl = self.ctx.island
        isl._place(isl._body())

    def _voice(self):
        w, f = self._page()
        f.addRow(self._check("voice_enabled", "Speak replies"))
        f.addRow("Engine", QLabel(getattr(self.ctx.voice.engine, "name", "loading…") if self.ctx.voice else "—"))
        f.addRow("Voice", QLabel(settings.get("voice_id")))
        speed = QSlider(Qt.Orientation.Horizontal)
        speed.setRange(80, 130)
        speed.setValue(int(float(settings.get("voice_speed")) * 100))
        lab = QLabel(f"{settings.get('voice_speed'):.2f}×")
        speed.valueChanged.connect(lambda v: (settings.set("voice_speed", v / 100), lab.setText(f"{v / 100:.2f}×")))
        row = QHBoxLayout()
        row.addWidget(speed, 1)
        row.addWidget(lab)
        f.addRow("Speed", row)
        test = QPushButton("Test voice")
        test.clicked.connect(lambda: self.ctx.voice.speak("Good morning. Freakyyy is online, and all systems are ready."))
        f.addRow(test)
        self._note(f, "Sound profile: high-pass 80 Hz · EQ 180 Hz −2 dB · EQ 3 kHz +2 dB · compressor 0.08, 2:1, "
                      "15/120 ms, makeup 1.5 · −16 LUFS, −1.5 dBTP. Same chain as Freakyyy Mobile.")
        return w

    def _ai(self):
        w, f = self._page()
        f.addRow(self._check("ai_enabled", "Use AI for open-ended requests (email triage, research, summaries)"))
        provider = QComboBox()
        modes = [("auto", "Automatic — Claude if a key is saved, otherwise free local AI"),
                 ("local", "Free local AI (Ollama, runs offline on this laptop)"),
                 ("claude", "Claude (Anthropic API key)")]
        for k, label in modes:
            provider.addItem(label, k)
        provider.setCurrentIndex(max(0, [k for k, _ in modes].index(settings.get("ai_provider") or "auto")))
        provider.currentIndexChanged.connect(lambda _: (settings.set("ai_provider", provider.currentData()),
                                                        self.ctx.brain.reset(), self.changed.emit("ai")))
        f.addRow("AI provider", provider)

        local_model = QLineEdit(settings.get("local_model"))
        local_model.editingFinished.connect(lambda: (settings.set("local_model", local_model.text().strip()),
                                                     self.ctx.brain.reset()))
        f.addRow("Local model", local_model)
        local_status = QLabel("")

        def refresh_local():
            ok, why = self.ctx.brain.local.status(0)
            local_status.setText("Ready — free and offline" if ok else f"Not ready: {why}")
        refresh_local()
        check = QPushButton("Check local AI")
        check.clicked.connect(refresh_local)
        row0 = QHBoxLayout()
        row0.addWidget(local_status, 1)
        row0.addWidget(check)
        f.addRow("Local status", row0)

        key = QLineEdit()
        key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText("sk-ant-…  (stored in Windows Credential Manager)")
        if get_secret("anthropic_api_key"):
            key.setPlaceholderText("A key is saved. Paste a new one to replace it.")
        save = QPushButton("Save key")
        save.clicked.connect(lambda: (set_secret("anthropic_api_key", key.text().strip()), key.clear(),
                                      self.ctx.brain.reset(), self.changed.emit("ai")))
        row = QHBoxLayout()
        row.addWidget(key, 1)
        row.addWidget(save)
        f.addRow("Anthropic API key", row)
        model = QLineEdit(settings.get("ai_model"))
        model.editingFinished.connect(lambda: settings.set("ai_model", model.text().strip()))
        f.addRow("Model", model)
        effort = QComboBox()
        effort.addItems(["low", "medium", "high"])
        effort.setCurrentText(settings.get("ai_effort"))
        effort.currentTextChanged.connect(lambda v: settings.set("ai_effort", v))
        f.addRow("Thinking effort", effort)
        f.addRow(self._check("ui_control_enabled", "Let the AI read the screen and click and type for me"))
        self._note(f, "Screen control is how multi-step jobs inside apps and websites get done — opening a chat, "
                      "filling a form, changing a setting in a page. Freakyyy reads the controls of a window the way "
                      "a screen reader does. It never types into password fields, and it asks you first before any "
                      "click that sends, buys or deletes something.")
        self._note(f, "Device automation never needs AI and works offline. AI is used only for requests the "
                      "built-in engine doesn't recognise. The local AI keeps everything on this laptop; Claude "
                      "sends the request text and whatever its tools return (emails, page text, files you ask about) "
                      "to Anthropic.")
        return w

    def _memory(self):
        from ..ai import memory as memory_mod
        mem = memory_mod.get()
        w, f = self._page()
        self.m_list = QListWidget()
        self.m_list.setMinimumHeight(220)
        self.m_count = QLabel("")

        def refresh():
            self.m_list.clear()
            for fact in mem.facts():
                it = QListWidgetItem(f"{fact.text}   ·  {fact.when()}{'  ·  learned' if fact.source == 'ai' else ''}")
                it.setData(Qt.ItemDataRole.UserRole, fact.id)
                it.setData(Qt.ItemDataRole.UserRole + 1, fact.text)
                self.m_list.addItem(it)
            self.m_count.setText(f"{self.m_list.count()} saved facts · {mem.message_count()} conversation messages")
        self._refresh_memory = refresh
        f.addRow(self.m_list)
        f.addRow(self.m_count)

        new_fact = QLineEdit()
        new_fact.setPlaceholderText("Add something for Freakyyy to remember…")
        add = QPushButton("Add")

        def do_add():
            if new_fact.text().strip():
                mem.add(new_fact.text().strip())
                new_fact.clear()
                refresh()
        add.clicked.connect(do_add)
        new_fact.returnPressed.connect(do_add)
        row = QHBoxLayout()
        row.addWidget(new_fact, 1)
        row.addWidget(add)
        f.addRow(row)

        def do_edit(item=None):
            item = item or self.m_list.currentItem()
            if not item:
                return
            text, ok = QInputDialog.getText(self, "Edit memory", "Fact:", text=item.data(Qt.ItemDataRole.UserRole + 1))
            if ok and text.strip():
                mem.update(item.data(Qt.ItemDataRole.UserRole), text.strip())
                refresh()

        def do_delete():
            for item in self.m_list.selectedItems():
                mem.delete(item.data(Qt.ItemDataRole.UserRole))
            refresh()

        def do_clear_history():
            if QMessageBox.question(self, "Clear conversation history",
                                    "Delete the saved conversation history? Saved facts stay. This can't be undone.") \
                    == QMessageBox.StandardButton.Yes:
                mem.clear_messages()
                refresh()

        def do_clear_all():
            if QMessageBox.question(self, "Clear all memory",
                                    "Delete every saved fact and the whole conversation history? This can't be undone.") \
                    == QMessageBox.StandardButton.Yes:
                mem.clear_all()
                refresh()
        self.m_list.itemDoubleClicked.connect(do_edit)
        btns = QHBoxLayout()
        for label, fn in (("Edit", do_edit), ("Delete selected", do_delete),
                          ("Clear history", do_clear_history), ("Clear all", do_clear_all)):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            btns.addWidget(b)
        f.addRow(btns)
        f.addRow(self._check("memory_log_conversations", "Keep a searchable history of AI conversations"))
        self._note(f, "Memory is stored only on this laptop (%APPDATA%\\Freakyyy\\memory.db). Say “remember that …”, "
                      "“what do you remember about me”, or “forget …”. Freakyyy refuses to store passwords, PINs, "
                      "codes and card or bank numbers.")
        refresh()
        return w

    def _email(self):
        w, f = self._page()
        addr = QLineEdit(settings.get("email_address"))
        addr.setPlaceholderText("you@gmail.com")
        host = QLineEdit(settings.get("email_imap_host"))
        pw = QLineEdit()
        pw.setEchoMode(QLineEdit.EchoMode.Password)
        pw.setPlaceholderText("App password (saved securely)" if not get_secret("email_password") else "Saved. Type to replace.")
        status = QLabel("")

        def save():
            settings.set("email_address", addr.text().strip())
            settings.set("email_imap_host", host.text().strip() or "imap.gmail.com")
            if pw.text():
                set_secret("email_password", pw.text())
                pw.clear()
            status.setText("Saved. Testing…")
            try:
                from ..ai.email_client import MailClient
                with MailClient() as mc:
                    n = len(mc.recent(days=1, unread_only=True))
                status.setText(f"Connected. {n} unread email{'s' if n != 1 else ''} today.")
            except Exception as e:
                status.setText(f"Couldn't connect: {e}")
        b = QPushButton("Save and test")
        b.setObjectName("primary")
        b.clicked.connect(save)
        f.addRow("Email address", addr)
        f.addRow("IMAP server", host)
        f.addRow("App password", pw)
        f.addRow(b)
        f.addRow(status)
        self._note(f, "Gmail: turn on 2-Step Verification, then create an app password at "
                      "myaccount.google.com/apppasswords and paste it here. Freakyyy reads mail only — it never sends, "
                      "deletes or moves anything.")
        return w

    def _devices(self):
        w, f = self._page()
        self.dev_list = QListWidget()
        self.dev_list.setMinimumHeight(110)
        self._fill_devices()
        f.addRow("Paired devices", self.dev_list)
        row = QHBoxLayout()
        add = QPushButton("Add device")
        add.setObjectName("primary")
        add.clicked.connect(self.ctx.show_pairing)
        rem = QPushButton("Remove selected")
        rem.setObjectName("danger")
        rem.clicked.connect(self._remove_device)
        row.addWidget(add)
        row.addWidget(rem)
        f.addRow(row)
        f.addRow(self._check("clipboard_accept_from_devices", "Accept clipboard text sent from my phone"))
        f.addRow(self._check("clipboard_share_to_devices", "Let my phone read this laptop's clipboard when I ask"))
        folder = QLineEdit(settings.get("receive_dir"))
        pick = QPushButton("Browse")
        pick.clicked.connect(lambda: (lambda d: d and (folder.setText(d), settings.set("receive_dir", d)))(
            QFileDialog.getExistingDirectory(self, "Received files folder", folder.text())))
        r2 = QHBoxLayout()
        r2.addWidget(folder, 1)
        r2.addWidget(pick)
        f.addRow("Received files", r2)
        port = QSpinBox()
        port.setRange(1024, 65000)
        port.setValue(int(settings.get("link_port")))
        port.valueChanged.connect(lambda v: settings.set("link_port", v))
        f.addRow("Link port (restart to apply)", port)
        self._note(f, "Freakyyy Link only works on your local network, over TLS pinned to this laptop's certificate, "
                      "with per-device keys. Windows may ask once to allow Freakyyy through the firewall on private networks.")
        return w

    def _fill_devices(self):
        self.dev_list.clear()
        if self.ctx.link:
            for d in self.ctx.link.devices.values():
                self.dev_list.addItem(f"{d.name}  ·  {'online' if d.online else 'offline'}  ·  {d.device_id}")

    def _remove_device(self):
        item = self.dev_list.currentItem()
        if item and self.ctx.link:
            self.ctx.link.remove_device(item.text().split("·")[-1].strip())
            self._fill_devices()

    def _routines(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 16, 8, 8)
        info = QLabel("One step per line: <b>laptop:</b> or <b>phone:</b> followed by any command, or <b>wait 3</b>. "
                      "Say “start &lt;name&gt; mode”, or “… on both devices”.")
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{T.rgba(T.ICE, .7)};")
        lay.addWidget(info)
        top = QHBoxLayout()
        self.r_list = QListWidget()
        self.r_list.setFixedWidth(180)
        self.r_edit = QPlainTextEdit()
        self.r_name = QLineEdit()
        self.r_name.setPlaceholderText("Routine name")
        top.addWidget(self.r_list)
        right = QVBoxLayout()
        right.addWidget(self.r_name)
        right.addWidget(self.r_edit, 1)
        top.addLayout(right, 1)
        lay.addLayout(top, 1)
        btns = QHBoxLayout()
        for label, slot, obj in (("New", self._r_new, ""), ("Delete", self._r_delete, "danger"),
                                 ("Run", self._r_run, ""), ("Save", self._r_save, "primary")):
            b = QPushButton(label)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(slot)
            btns.addWidget(b)
        lay.addLayout(btns)
        self.r_status = QLabel("")
        lay.addWidget(self.r_status)
        self.r_list.currentTextChanged.connect(self._r_load)
        self._r_refresh()
        return w

    def _r_refresh(self):
        self.r_list.clear()
        for n in self.ctx.assistant.routines.items:
            self.r_list.addItem(n)

    def _r_load(self, name):
        steps = self.ctx.assistant.routines.items.get(name, [])
        self.r_name.setText(name)
        self.r_edit.setPlainText("\n".join(f"{s['device']}: {s['command']}" if not s["command"].startswith("wait") else s["command"] for s in steps))

    def _r_new(self):
        self.r_list.clearSelection()
        self.r_name.setText("")
        self.r_edit.setPlainText("laptop: open vscode\nwait 2\nphone: turn on do not disturb")

    def _r_save(self):
        from ..core import parser
        name = self.r_name.text().strip()
        if not name:
            self.r_status.setText("Give the routine a name.")
            return
        steps = []
        for line in self.r_edit.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("wait"):
                steps.append({"device": "laptop", "command": line.lower()})
                continue
            dev, _, cmd = line.partition(":")
            dev = dev.strip().lower()
            if dev not in ("laptop", "phone") or not cmd.strip():
                self.r_status.setText(f"Start each line with laptop: or phone: — “{line}”")
                return
            if dev == "laptop" and parser.parse(cmd).name == "ai.ask":
                self.r_status.setText(f"I don't understand “{cmd.strip()}” as a laptop command.")
                return
            steps.append({"device": dev, "command": cmd.strip()})
        old = self.r_list.currentItem().text() if self.r_list.currentItem() else None
        items = self.ctx.assistant.routines.items
        if old and old != name:
            items.pop(old, None)
        items[name] = steps
        self.ctx.assistant.routines.save()
        self._r_refresh()
        self.r_status.setText(f"Saved {name}.")

    def _r_delete(self):
        item = self.r_list.currentItem()
        if item:
            self.ctx.assistant.routines.items.pop(item.text(), None)
            self.ctx.assistant.routines.save()
            self._r_refresh()

    def _r_run(self):
        if self.r_name.text().strip():
            self.ctx.assistant.submit(f"start {self.r_name.text().strip()} routine", source="typed")

    def _general(self):
        w, f = self._page()
        f.addRow(self._check("start_with_windows", "Start Freakyyy when I sign in to Windows", self.ctx.set_startup))
        f.addRow(self._check("start_minimized", "Start in the background (tray)"))
        roots = QPlainTextEdit("\n".join(settings.get("project_roots")))
        roots.setFixedHeight(120)
        roots.textChanged.connect(lambda: settings.set("project_roots", [l.strip() for l in roots.toPlainText().splitlines() if l.strip()]))
        f.addRow("Project folders", roots)
        clear = QPushButton("Clear command history")
        clear.setObjectName("danger")
        clear.clicked.connect(lambda: (self.ctx.assistant.history.clear(), clear.setText("History cleared")))
        f.addRow(clear)
        self._note(f, "Freakyyy stores settings, history and routines in %APPDATA%\\Freakyyy. Secrets (AI key, email "
                      "password, device keys) live in Windows Credential Manager. Logs: %APPDATA%\\Freakyyy\\logs.")
        return w
