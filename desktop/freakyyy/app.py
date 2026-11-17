"""Freakyyy Desktop entry point."""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import APP_NAME, app_root, settings, setup_logging
from .core.actions import Outcome, Result, confirm, done

log = logging.getLogger("freakyyy")
SINGLETON = "FreakyyyDesktopSingleton"


class Bridge(QObject):
    """Carries events from worker threads to the GUI thread."""
    event = Signal(str, object)


def make_icon(live: bool = False) -> QIcon:
    """The Freakyyy app icon (brand SVG), with a red dot when the microphone is open."""
    from PySide6.QtSvg import QSvgRenderer
    from .config import resource
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(resource("ui/assets/freakyyy-app-icon.svg"))).render(p, QRectF(0, 0, 64, 64))
    if live:
        p.setBrush(QColor("#FF4D5E"))
        p.setPen(QPen(QColor("#02040A"), 3))
        p.drawEllipse(QRectF(40, 40, 22, 22))
    p.end()
    return QIcon(pm)


class HotkeyThread(threading.Thread):
    """Global push-to-talk hotkey via RegisterHotKey (Ctrl+Alt+D)."""

    def __init__(self, callback):
        super().__init__(daemon=True, name="hotkey")
        self.callback = callback

    def run(self):
        user32 = ctypes.windll.user32
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("D")):
            log.warning("Push-to-talk hotkey Ctrl+Alt+D is taken by another app")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:      # WM_HOTKEY
                self.callback()


class FreakyyyApp:
    def __init__(self, qt: QApplication, background: bool):
        from .ui import theme
        from .ui.main_window import MainWindow
        self.qt = qt
        qt.setStyleSheet(theme.STYLESHEET)
        qt.setQuitOnLastWindowClosed(False)
        self.bridge = Bridge()
        self.bridge.event.connect(self._on_event)
        self.voice = self.listener = self.link = self.brain = None
        self.pair_dialog = None
        self.settings_dialog = None
        self.phone_state: dict | None = None
        self.state = "IDLE"

        self.window = MainWindow()
        self.window.command.connect(lambda t: self.assistant.submit(t, "typed"))
        self.window.mic_pressed.connect(self.push_to_talk)
        self.window.open_settings.connect(self.show_settings)
        self.window.pair_requested.connect(self.show_pairing)
        self.window.hide_requested.connect(self.hide_window)

        from .ui.island import DynamicIsland
        self.island = DynamicIsland()
        self.island.command.connect(lambda t: self.assistant.submit(t, "typed"))
        self.island.push_to_talk.connect(self.push_to_talk)
        self.island.cancel_voice.connect(self.cancel_voice)
        self.island.mute_toggled.connect(self._set_muted)
        self.island.open_settings.connect(self.show_settings)
        self.island.open_dashboard.connect(self.show_window)
        self.island.pair_device.connect(self.show_pairing)
        self.island.hide_requested.connect(lambda: self.set_island(False))
        self.island.exit_requested.connect(lambda: self.assistant.submit("quit freakyyy", "typed"))

        self.splash = None
        if not background:
            from .ui.dialogs import Splash
            self.splash = Splash()
            self.splash.show()

        self._build_tray()
        QTimer.singleShot(50, self._start_services)

        self.sys_timer = QTimer(timeout=self._refresh_system)
        self.sys_timer.start(2000)
        self.fg_timer = QTimer(timeout=self._track_fg)
        self.fg_timer.start(500)
        self.background = background

    # ------------------------------------------------------------------ services
    def emit(self, name: str, data: dict | None = None):
        self.bridge.event.emit(name, data or {})

    def _start_services(self):
        from .ai.router import AIRouter
        from .core.assistant import Assistant
        from .link.server import LinkServer
        from .voice.listener import Listener
        from .voice.tts import FreakyyyVoice

        self.assistant = Assistant(self.emit)
        self.voice = FreakyyyVoice(on_state=lambda s: self.emit("voice", {"status": s}),
                                 on_level=lambda v: self.emit("level", {"value": v}))
        self.listener = Listener(on_command=self._heard,
                                 on_state=lambda s: self.emit("state", {"state": s, "from": "listener"}),
                                 on_level=lambda v: self.emit("level", {"value": v}),
                                 is_speaking=lambda: bool(self.voice and self.voice.speaking),
                                 on_partial=lambda t: self.emit("partial", {"text": t}))
        self.island.get_apps = lambda: [a.name for a in self.assistant.app_index.apps]
        self.island.get_history = lambda: self.assistant.history.items
        self.link = LinkServer(self.assistant.handle_link_request, self.emit)
        self.brain = AIRouter(self.assistant.ai_tool)
        self.brain.warm_up()
        self.assistant.voice, self.assistant.listener = self.voice, self.listener
        self.assistant.link, self.assistant.brain = self.link, self.brain
        self.link.start()
        HotkeyThread(lambda: self.emit("ptt")).start()
        self._boot_timer = QTimer(timeout=self._boot_progress)
        self._boot_timer.start(150)
        self._refresh_chips()

    def _boot_progress(self):
        ready = {
            0: self.voice.status != "loading",
            1: self.listener.ready or bool(self.listener.error),
            2: self.listener.ready or bool(self.listener.error),
            3: self.link.running or bool(self.link.error),
            4: bool(self.assistant.app_index.apps),
        }
        if self.splash:
            for i, ok in ready.items():
                if ok:
                    self.splash.mark(i)
        if all(ready.values()) or (self.splash and self.splash.t0 and __import__("time").time() - self.splash.t0 > 40):
            self._boot_timer.stop()
            if self.splash:
                QTimer.singleShot(500, lambda: self.splash.fade_out(self._show_after_boot))
            else:
                self._show_after_boot()

    def _show_after_boot(self):
        self.splash = None
        if settings.get("island_enabled"):
            self.island.show()
        if not self.background or not settings.get("start_minimized"):
            self.show_window()
            self.window.play_entrance()
        else:
            self.tray.showMessage("Freakyyy", "Listening for “Hey Freaky”. The microphone indicator is in the tray.",
                                  make_icon(), 4000)
        if self.voice.status == "ready":
            hour = __import__("time").localtime().tm_hour
            part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
            if not self.background:
                self.voice.speak(f"{part}. Freakyyy is online.")
        self._refresh_chips()

    def _heard(self, text: str):
        if not text:
            self.emit("wake_only")
        else:
            self.assistant.submit(text, "voice")

    def push_to_talk(self):
        if self.voice:
            self.voice.stop()
        if self.listener:
            self.play_chime()
            self.listener.push_to_talk()

    def cancel_voice(self):
        if self.listener:
            self.listener.cancel()
        if self.voice:
            self.voice.stop()

    def _set_muted(self, muted: bool):
        if self.listener:
            self.listener.set_enabled(not muted)
        self._refresh_chips()

    def play_chime(self):
        """Subtle two-note activation sound (generated, about 0.18 s, quiet)."""
        if not settings.get("activation_sound"):
            return
        try:
            import numpy as np
            import sounddevice as sd
            sr = 24000
            t = np.arange(int(sr * 0.09)) / sr
            env = np.sin(np.pi * t / t[-1]) ** 2
            tone = np.concatenate([np.sin(2 * np.pi * 880 * t) * env, np.sin(2 * np.pi * 1320 * t) * env]) * 0.11
            sd.play(tone.astype(np.float32), sr)
        except Exception:
            pass

    def set_island(self, show: bool):
        settings.set("island_enabled", show)
        if self.act_island.isChecked() != show:
            self.act_island.setChecked(show)
        if show:
            self.island.show()
        else:
            self.island.hide()

    # ------------------------------------------------------------------ events (GUI thread)
    def _on_event(self, name: str, data: dict):
        w = self.window
        if name == "state":
            st = data["state"]
            if data.get("from") == "listener" and st == "IDLE" and self.voice and self.voice.speaking:
                return
            if st == "IDLE" and self.listener and not self.listener.enabled:
                st = "OFFLINE"
            if st == "WAKE_DETECTED" and data.get("from") == "listener":
                self.play_chime()
            self.state = st
            w.set_state(st)
            self.island.set_state(st)
            self._refresh_chips()
        elif name == "level":
            w.orb.set_level(data["value"])
            self.island.set_level(data["value"])
        elif name == "partial":
            self.island.set_partial(data["text"])
        elif name == "idle":
            self.island.set_mode(0)
        elif name == "island":
            self.set_island(data["show"])
        elif name == "voice":
            s = data["status"]
            if s == "speaking":
                w.set_state("SPEAKING")
                self.island.set_state("SPEAKING")
            elif s == "ready" and self.state not in ("LISTENING", "RECOGNIZING", "WAITING_FOR_CONFIRMATION"):
                idle = "OFFLINE" if self.listener and not self.listener.enabled else "IDLE"
                w.set_state(idle)
                self.island.set_state(idle)
            self._refresh_chips()
        elif name == "transcript":
            src = data.get("source", "")
            w.set_transcript(data["text"] if not src.startswith("phone") else f"{data['text']}  (from phone)")
            self.island.set_transcript(data["text"], src)
        elif name == "reply":
            w.set_reply(data["text"], data["outcome"])
            self.island.set_reply(data["text"], data["outcome"])
        elif name == "action":
            w.action.setText(data["label"])
            self.island.set_action(data)
        elif name == "activity":
            w.add_activity(data)
            self.island.add_activity(data)
        elif name == "files":
            w.show_results(data.get("title", "Results"), data.get("items", []))
        elif name == "routine":
            w.routine_label.setText(f"{data['name']} · step {data['step']} of {data['total']} · {data['current']}" if data else "")
        elif name == "wake_only":
            self.assistant.wake_only()
        elif name == "ptt":
            self.push_to_talk()
        elif name == "listening":
            self._refresh_chips()
            w.set_state("IDLE" if data["enabled"] else "OFFLINE")
        elif name in ("device_online", "device_offline", "device_status"):
            self.phone_state = data
            w.update_phone(data)
            self.island.set_devices(data)
            self._refresh_chips()
            if name == "device_online":
                self.tray.showMessage("Freakyyy Link", f"{data['name']} connected.", make_icon(), 2500)
        elif name == "devices":
            p = self.link.phone()
            w.update_phone(p.public() if p else None)
        elif name == "link_ready":
            p = self.link.phone()
            w.update_phone(p.public() if p else None)
            self._refresh_chips()
        elif name == "link_error":
            w.chip_link.set("LINK ERROR", QColor("#FF7A8A"))
            w.add_activity({"command": "Freakyyy Link", "outcome": "FAILED", "message": data["error"]})
        elif name == "pair":
            self.show_pairing()
        elif name == "pair_request":
            if self.pair_dialog:
                self.pair_dialog.show_request(data["name"], data["code"])
                self.show_window()
            code = " ".join(data["code"])
            self.assistant.ctx.pending = confirm(
                f"Pair with {data['name']}? The code is {code}. Say yes if your phone shows the same code.",
                lambda: (self.link.decide_pairing(True), done("Pairing approved."))[1])
            self.assistant.ctx.pending_at = __import__("time").time()
            self.voice.speak(f"{data['name']} wants to pair. Check the code on both screens, then say yes.")
            self.listener.expect_reply(10)
        elif name == "pair_done":
            if self.pair_dialog:
                self.pair_dialog.finished_pairing(data["ok"], data.get("name"))
            self.assistant.ctx.pending = None
            if data["ok"]:
                self.voice.speak(f"Paired with {data.get('name')}.")
            p = self.link.phone()
            w.update_phone(p.public() if p else None)
        elif name == "file_progress":
            pct = int(100 * data["done"] / max(1, data["size"]))
            arrow = "→ phone" if data["direction"] == "out" else "← from phone"
            w.transfer.setText(f"{data['name']} {arrow}  {pct}%")
        elif name == "file_done":
            arrow = "sent" if data["direction"] == "out" else "received"
            w.transfer.setText(f"{data['name']} {arrow}" if data["ok"] else f"{data['name']}: transfer failed")
            if data["ok"] and data["direction"] == "in":
                self.tray.showMessage("File received", f"{data['name']} from {data.get('device', 'your phone')}", make_icon(), 4000)
                self.voice.speak(f"Received {os.path.splitext(data['name'])[0]} from your phone.")
                w.add_activity({"command": f"Received {data['name']}", "outcome": "COMPLETED",
                                "message": data.get("path", ""), "t": __import__("time").time()})
        elif name == "toast":
            self.tray.showMessage(data.get("title", "Freakyyy"), data.get("text", ""), make_icon(), 4000)
        elif name == "show_window":
            self.show_window()
        elif name == "hide_window":
            self.hide_window()
        elif name == "open_settings":
            self.show_settings(data.get("tab", ""))
        elif name == "quit":
            QTimer.singleShot(1500, self.quit)
        elif name == "restart":
            QTimer.singleShot(1200, self.restart)

    def _refresh_chips(self):
        w = self.window
        from .ui import theme as T
        if self.listener:
            if not self.listener.enabled:
                w.chip_wake.set("WAKE WORD · OFF", T.MUTED)
            elif self.listener.error:
                w.chip_wake.set("MIC ERROR", T.DANGER)
            else:
                w.chip_wake.set("“HEY FREAKYYY” · ON", T.SUCCESS)
            live = self.listener.mic_active
            capturing = self.state in ("LISTENING", "WAKE_DETECTED", "RECOGNIZING")
            w.chip_mic.set("MIC LIVE" if capturing else ("MIC ON · WAKE ONLY" if live else "MIC OFF"),
                           T.DANGER if capturing else (T.SUCCESS if live else T.MUTED), pulse=capturing)
            self.tray.setIcon(make_icon(live))
            self.island.set_mic(live, capturing, not self.listener.enabled)
            self.tray.setToolTip("Freakyyy — microphone on (wake word)" if live else "Freakyyy — microphone off")
            self.act_listen.setChecked(self.listener.enabled)
        if self.voice:
            s = self.voice.status
            w.chip_voice.set({"ready": "VOICE · KOKORO", "speaking": "SPEAKING", "loading": "VOICE LOADING",
                              "offline": "VOICE OFFLINE"}.get(s, s.upper()),
                             {"offline": T.DANGER, "loading": T.WARNING}.get(s, T.SUCCESS), pulse=s == "speaking")
        if self.brain is not None:
            ok = self.brain.available()
            w.chip_ai.set(self.brain.label(), T.SUCCESS if ok else T.MUTED)
        if self.link and not self.link.devices:
            w.chip_link.set("PHONE · NOT PAIRED", T.MUTED)

    def _refresh_system(self):
        try:
            from .windows import system
            snap = system.status_snapshot()
            self.window.update_system(snap)
            phone = self.link.phone().public() if self.link and self.link.phone() else None
            self.island.set_devices(phone, snap)
        except Exception:
            pass

    def _track_fg(self):
        try:
            from .windows import apps
            apps.track_foreground()
        except Exception:
            pass

    # ------------------------------------------------------------------ windows, tray
    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self.qt)
        menu = QMenu()
        menu.addAction("Open Freakyyy", self.show_window)
        menu.addAction("Push to talk  (Ctrl+Alt+D)", self.push_to_talk)
        self.act_listen = QAction("Listen for “Hey Freaky”", menu, checkable=True)
        self.act_listen.setChecked(bool(settings.get("wake_enabled")))
        self.act_listen.toggled.connect(lambda v: self.listener and self.listener.set_enabled(v) or self._refresh_chips())
        menu.addAction(self.act_listen)
        self.act_island = QAction("Show the notch", menu, checkable=True)
        self.act_island.setChecked(bool(settings.get("island_enabled")))
        self.act_island.toggled.connect(self.set_island)
        menu.addAction(self.act_island)
        menu.addSeparator()
        menu.addAction("Add a device…", self.show_pairing)
        menu.addAction("Settings…", self.show_settings)
        menu.addSeparator()
        menu.addAction("Restart Freakyyy", self.restart)
        menu.addAction("Quit Freakyyy", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.ActivationReason.Trigger and self.show_window())
        self.tray.setToolTip("Freakyyy")
        self.tray.show()
        self._menu = menu

    def show_window(self):
        if not getattr(self, "_centered", False):
            self._centered = True
            scr = self.qt.primaryScreen().availableGeometry()
            self.window.resize(min(1360, scr.width() - 80), min(860, scr.height() - 60))
            self.window.move(scr.center() - self.window.rect().center())
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def hide_window(self):
        self.window.hide()
        if not getattr(self, "_hint_shown", False):
            self._hint_shown = True
            self.tray.showMessage("Freakyyy is still here", "Say “Hey Freaky” any time. Right-click the tray icon to quit.",
                                  make_icon(), 3500)

    def show_pairing(self):
        from .ui.dialogs import PairingDialog
        if not self.link or not self.link.running:
            self.tray.showMessage("Freakyyy Link", "The link service isn't running yet.", make_icon(), 3000)
            return
        uri = self.link.create_pairing()
        self.pair_dialog = PairingDialog(uri, self.window)
        self.pair_dialog.decided.connect(self.link.decide_pairing)
        self.pair_dialog.show()

    def show_settings(self, tab: str = ""):
        from .ui.dialogs import SettingsDialog
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self, self.window)
            self.settings_dialog.changed.connect(lambda _: self._refresh_chips())
        if tab:
            self.settings_dialog.show_tab(tab)
        self.settings_dialog.show()
        self.settings_dialog.raise_()

    def set_startup(self, enabled: bool):
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}" --background'
                else:
                    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                    cmd = f'"{pyw}" -m freakyyy --background'
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass

    def restart(self):
        from PySide6.QtCore import QProcess
        args = sys.argv[1:] if getattr(sys, "frozen", False) else ["-m", "freakyyy", *sys.argv[1:]]
        QProcess.startDetached(sys.executable, args, str(app_root()))
        self.quit()

    def quit(self):
        self.tray.hide()
        self.island.hide()
        if self.voice:
            self.voice.stop()
        self.qt.quit()


def main():
    setup_logging()
    background = "--background" in sys.argv
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Freakyyy.Desktop")
    qt = QApplication(sys.argv)
    qt.setApplicationName(APP_NAME)
    qt.setWindowIcon(make_icon())

    # Single instance: a second launch just shows the running Freakyyy.
    sock = QLocalSocket()
    sock.connectToServer(SINGLETON)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(SINGLETON)
    server.listen(SINGLETON)

    app = FreakyyyApp(qt, background)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), app.show_window()))
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
