"""Installed-application index, launching and window management."""
from __future__ import annotations

import ctypes
import difflib
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from ..config import DATA_DIR

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = 0x08000000


@dataclass
class App:
    name: str
    target: str          # .lnk/.exe path, or "shell:AppsFolder\\<AUMID>"
    kind: str            # "lnk" | "uwp" | "exe" | "builtin"

    @property
    def key(self) -> str:
        return _norm(self.name)


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\(.*?\)|\b(x64|x86|64-bit|32-bit|preview|beta)\b", " ", s)
    s = re.sub(r"[^a-z0-9+#]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Spoken names -> canonical app names (matched against the index).
ALIASES = {
    "vscode": "visual studio code", "code": "visual studio code", "vs": "visual studio code",
    "chrome": "google chrome", "google": "google chrome", "browser": "@browser", "web browser": "@browser",
    "edge": "microsoft edge", "firefox": "firefox", "brave": "brave",
    "word": "word", "ms word": "word", "microsoft word": "word", "excel": "excel", "powerpoint": "powerpoint",
    "ppt": "powerpoint", "outlook": "outlook", "teams": "microsoft teams", "onenote": "onenote",
    "studio": "android studio", "android studio": "android studio", "intellij": "intellij idea",
    "pycharm": "pycharm", "visual studio": "visual studio 2022",
    "terminal": "@terminal", "windows terminal": "@terminal", "command prompt": "@cmd", "cmd": "@cmd",
    "powershell": "@powershell", "file explorer": "@explorer", "explorer": "@explorer", "files": "@explorer",
    "my files": "@explorer", "this pc": "@explorer",
    "settings": "@settings", "windows settings": "@settings", "task manager": "@taskmgr",
    "calculator": "@calc", "calc": "@calc", "notepad": "@notepad", "paint": "@mspaint",
    "control panel": "@control", "device manager": "@devmgmt", "snipping tool": "@snip",
    "camera": "@camera", "photos": "@photos", "store": "@store", "microsoft store": "@store",
    "clock": "@clock", "alarms": "@clock", "calendar": "@calendar", "mail": "@mail",
    "disk management": "@diskmgmt", "services": "@services", "registry editor": "@regedit",
    "event viewer": "@eventvwr", "system information": "@msinfo",
    "whatsapp": "whatsapp", "spotify": "spotify", "discord": "discord", "telegram": "telegram",
    "zoom": "zoom", "slack": "slack", "notion": "notion", "obs": "obs studio", "vlc": "vlc media player",
    "steam": "steam", "postman": "postman", "docker": "docker desktop", "github desktop": "github desktop",
}

BUILTINS = {
    "@terminal": ("Windows Terminal", ["wt.exe"]),
    "@cmd": ("Command Prompt", ["cmd.exe", "/k"]),
    "@powershell": ("PowerShell", ["powershell.exe", "-NoExit"]),
    "@explorer": ("File Explorer", ["explorer.exe"]),
    "@settings": ("Settings", ["explorer.exe", "ms-settings:"]),
    "@taskmgr": ("Task Manager", ["taskmgr.exe"]),
    "@calc": ("Calculator", ["calc.exe"]),
    "@notepad": ("Notepad", ["notepad.exe"]),
    "@mspaint": ("Paint", ["mspaint.exe"]),
    "@control": ("Control Panel", ["control.exe"]),
    "@devmgmt": ("Device Manager", ["mmc.exe", "devmgmt.msc"]),
    "@diskmgmt": ("Disk Management", ["mmc.exe", "diskmgmt.msc"]),
    "@services": ("Services", ["mmc.exe", "services.msc"]),
    "@regedit": ("Registry Editor", ["regedit.exe"]),
    "@eventvwr": ("Event Viewer", ["eventvwr.exe"]),
    "@msinfo": ("System Information", ["msinfo32.exe"]),
    "@snip": ("Snipping Tool", ["explorer.exe", "ms-screenclip:"]),
    "@camera": ("Camera", ["explorer.exe", "microsoft.windows.camera:"]),
    "@photos": ("Photos", ["explorer.exe", "ms-photos:"]),
    "@store": ("Microsoft Store", ["explorer.exe", "ms-windows-store:"]),
    "@clock": ("Clock", ["explorer.exe", "ms-clock:"]),
    "@calendar": ("Calendar", ["explorer.exe", "outlookcal:"]),
    "@mail": ("Mail", ["explorer.exe", "mailto:"]),
}


class AppIndex:
    """Start Menu shortcuts + Store apps, cached on disk and refreshed in the background."""

    def __init__(self) -> None:
        self._apps: list[App] = []
        self._lock = threading.Lock()
        self._cache = DATA_DIR / "apps_cache.json"
        if self._cache.exists():
            try:
                self._apps = [App(**a) for a in json.loads(self._cache.read_text(encoding="utf-8"))]
            except Exception:
                pass
        threading.Thread(target=self.refresh, daemon=True, name="app-index").start()

    @property
    def apps(self) -> list[App]:
        with self._lock:
            return list(self._apps)

    def refresh(self) -> None:
        found: dict[str, App] = {}
        roots = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
            Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        ]
        skip = re.compile(r"uninstall|readme|help|documentation|release notes|website|license|manual|support", re.I)
        for root in roots:
            for lnk in root.rglob("*.lnk"):
                if skip.search(lnk.stem):
                    continue
                found.setdefault(_norm(lnk.stem), App(lnk.stem, str(lnk), "lnk"))
        try:
            out = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
                creationflags=CREATE_NO_WINDOW,
            ).stdout
            for item in json.loads(out or "[]"):
                name, aumid = item.get("Name"), item.get("AppID")
                if name and aumid and not skip.search(name):
                    found.setdefault(_norm(name), App(name, f"shell:AppsFolder\\{aumid}", "uwp"))
        except Exception:
            log.exception("Get-StartApps failed")
        apps = sorted(found.values(), key=lambda a: a.name.lower())
        with self._lock:
            self._apps = apps
        try:
            self._cache.write_text(json.dumps([a.__dict__ for a in apps]), encoding="utf-8")
        except Exception:
            pass
        log.info("App index: %d apps", len(apps))

    # ------------------------------------------------------------------
    def find(self, spoken: str) -> list[App]:
        q = _norm(spoken)
        q = re.sub(r"^(the|my) ", "", q)
        alias = ALIASES.get(q)
        if alias and alias.startswith("@"):
            if alias == "@browser":
                return [App("default browser", "@browser", "builtin")]
            name, _ = BUILTINS[alias]
            return [App(name, alias, "builtin")]
        if alias:
            q = alias
        apps = self.apps
        exact = [a for a in apps if a.key == q]
        if exact:
            return exact[:1]
        starts = [a for a in apps if a.key.startswith(q + " ") or a.key.startswith(q)]
        if len(starts) == 1:
            return starts
        words = q.split()
        contains = [a for a in apps if all(w in a.key.split() or w in a.key for w in words)]
        if contains:
            contains.sort(key=lambda a: (len(a.key), a.kind != "lnk"))
            # Prefer a dominant shortest match ("android studio" over "android studio sdk manager")
            if len(contains) == 1 or len(contains[0].key) + 4 < len(contains[1].key):
                return contains[:1]
            return contains[:5]
        if alias:
            return []          # an alias names one specific app; don't guess a look-alike
        close = difflib.get_close_matches(q, [a.key for a in apps], n=3, cutoff=0.8)
        return [a for a in apps if a.key in close][:3]

    def launch(self, app: App, args: list[str] | None = None) -> bool:
        try:
            if app.kind == "builtin":
                if app.target == "@browser":
                    os.startfile("https://www.google.com")
                    return True
                _, cmd = BUILTINS[app.target]
                subprocess.Popen(cmd + (args or []), creationflags=0)
            elif app.kind == "uwp":
                subprocess.Popen(["explorer.exe", app.target])
            elif args:
                exe = resolve_shortcut(app.target) if app.target.endswith(".lnk") else app.target
                subprocess.Popen([exe, *args])
            else:
                os.startfile(app.target)
            return True
        except Exception:
            log.exception("Launch failed: %s", app)
            return False

    def exe_for(self, spoken: str) -> str | None:
        """Executable path for apps that accept arguments (IDEs)."""
        for app in self.find(spoken):
            if app.kind == "lnk":
                return resolve_shortcut(app.target)
        return None


def resolve_shortcut(lnk: str) -> str:
    try:
        import win32com.client
        return win32com.client.Dispatch("WScript.Shell").CreateShortcut(lnk).TargetPath or lnk
    except Exception:
        return lnk


# ======================================================================
# Windows
# ======================================================================

user32 = ctypes.windll.user32
SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
WM_CLOSE = 0x0010


@dataclass
class Window:
    hwnd: int
    title: str
    process: str
    pid: int


def list_windows() -> list[Window]:
    import win32gui
    import win32process
    result: list[Window] = []
    me = os.getpid()

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        ex =win32gui.GetWindowLong(hwnd, -20)
        if ex & 0x80:  # WS_EX_TOOLWINDOW
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == me:
                return True
            pname = psutil.Process(pid).name()
        except Exception:
            return True
        if not title.strip() or title == "Program Manager":
            return True
        result.append(Window(hwnd, title, pname, pid))
        return True

    win32gui.EnumWindows(cb, None)
    return result


def find_windows(name: str | None) -> list[Window]:
    wins = list_windows()
    if not name:
        return wins
    q = _norm(ALIASES.get(_norm(name), name)).replace("@", "")
    proc_alias = {
        "visual studio code": "code.exe", "google chrome": "chrome.exe", "microsoft edge": "msedge.exe",
        "android studio": "studio64.exe", "explorer": "explorer.exe", "terminal": "windowsterminal.exe",
        "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe", "spotify": "spotify.exe",
        "whatsapp": "whatsapp", "notepad": "notepad.exe", "file explorer": "explorer.exe",
    }
    proc = proc_alias.get(q)
    hits = [w for w in wins if (proc and proc in w.process.lower())
            or q in _norm(w.title) or q.replace(" ", "") in w.process.lower()]
    return hits


_last_foreground: int | None = None


def track_foreground() -> None:
    """Remember the last non-Freakyyy foreground window ("close the selected app")."""
    global _last_foreground
    import win32process
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid != os.getpid():
                _last_foreground = hwnd
        except Exception:
            pass


def active_window() -> Window | None:
    import win32gui
    import win32process
    hwnd = _last_foreground or user32.GetForegroundWindow()
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return Window(hwnd, win32gui.GetWindowText(hwnd), psutil.Process(pid).name(), pid)
    except Exception:
        return None


def focus(hwnd: int) -> bool:
    import win32con
    import win32gui
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, SW_RESTORE)
        # Alt key press lets a background process take the foreground.
        user32.keybd_event(0x12, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.05)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def show(hwnd: int, cmd: int) -> None:
    user32.ShowWindow(hwnd, cmd)


def close(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def is_window(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd))
