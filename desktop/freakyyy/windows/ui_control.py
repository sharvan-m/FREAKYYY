"""Whole-computer UI control: read the controls of any window, then click and type in them.

This is how Freakyyy does multi-step work inside apps and web pages — the parts no
command can cover, like "open Instagram, go to messages and type hi". It reads the
Windows UI Automation tree (the same information screen readers use), so it works in
native apps, Office, Explorer, Settings and Chromium browsers, without screenshots.

Safety lives here as well as in the caller:
  * text is never typed into a password box,
  * controls whose name suggests sending, buying or deleting are flagged `risky`
    so the assistant asks the user first,
  * refs expire with each new snapshot, so a click can't land on a stale control.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

# Controls worth offering to the model. Chromium maps web pages onto these too.
ACTIONABLE = {"ButtonControl", "EditControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl",
              "ListItemControl", "MenuItemControl", "TabItemControl", "HyperlinkControl", "TreeItemControl",
              "SliderControl", "SplitButtonControl", "CustomControl", "DocumentControl"}
READABLE = {"TextControl", "DocumentControl", "HeadingControl", "ImageControl", "GroupControl"}

# Anything that sends, spends or destroys: the assistant confirms with the user first.
RISKY = re.compile(r"\b(send|post|publish|tweet|reply|share|submit|confirm|pay|buy|order|checkout|place order|"
                   r"delete|remove|discard|erase|clear all|uninstall|format|wipe|block|report|unfriend|unfollow|"
                   r"log ?out|sign ?out|shut ?down|restart|empty|archive|transfer|withdraw|donate|subscribe|"
                   r"accept|agree|allow|grant|install|move to trash)\b", re.I)

_lock = threading.Lock()
_cache: dict[str, object] = {}
_snapshot_id = 0
_target: dict[str, object] = {}        # the window the last snapshot/focus was about


def _remember(w) -> None:
    try:
        _target.clear()
        _target.update({"pid": w.ProcessId, "name": _label(w)})
    except Exception:
        pass


def _focus_check() -> str:
    """Why typing blind is unsafe right now, or "" when the right window has focus.

    Typing with no target goes wherever the keyboard happens to point. If that is not
    the window Freakyyy just read, the text lands in someone else's app - a chat box,
    a document - so refuse and make the caller focus first.
    """
    if not _target:
        return "I haven't read a window yet. Call screen_read first."
    try:
        fg = foreground_window(skip_own=False)
        if fg is None:
            return "I can't tell which window has focus."
        if fg.ProcessId != _target.get("pid"):
            return (f"Focus is on “{_label(fg)}”, not “{_target.get('name')}”. "
                    f"Call focus_window first so the text can't land in the wrong app.")
    except Exception:
        return "I can't tell which window has focus."
    return ""


def _auto():
    import uiautomation as auto
    auto.SetGlobalSearchTimeout(2)
    return auto


# ------------------------------------------------------------------ reading

def _label(el) -> str:
    """The best short name for a control."""
    for attr in ("Name",):
        try:
            v = (getattr(el, attr, "") or "").strip()
        except Exception:
            v = ""
        if v:
            return re.sub(r"\s+", " ", v)[:90]
    try:
        v = (el.AutomationId or "").strip()
    except Exception:
        v = ""
    return v[:90]


def _value(el) -> str:
    try:
        p = el.GetValuePattern()
    except Exception:
        return ""
    try:
        return re.sub(r"\s+", " ", (p.Value or "").strip())[:120]
    except Exception:
        return ""


def _is_password(el) -> bool:
    try:
        return bool(el.IsPassword)
    except Exception:
        return False


def _visible(el) -> bool:
    try:
        if el.IsOffscreen:
            return False
        r = el.BoundingRectangle
        return r.width() > 2 and r.height() > 2
    except Exception:
        return False


def _own_pids() -> set[int]:
    """This process, so Freakyyy never reads or clicks its own window by mistake."""
    pids = {os.getpid()}
    try:
        import psutil
        me = psutil.Process()
        pids |= {c.pid for c in me.children(recursive=True)}
        if me.parent():
            pids.add(me.parent().pid)
    except Exception:
        pass
    return pids


def foreground_window(skip_own: bool = True):
    """The window the user is working in.

    When the user has just typed into Freakyyy's own window, that window is in front;
    the one they mean is the next one down, so skip ourselves.
    """
    from . import apps
    own = _own_pids() if skip_own else set()
    try:
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not skip_own or pid not in own:
                return _from_handle(hwnd)
    except Exception:
        log.debug("foreground lookup failed", exc_info=True)
    for w in apps.list_windows():         # EnumWindows order is front to back
        if w.pid not in own:
            return _from_handle(w.hwnd)
    return None


def _from_handle(hwnd: int):
    auto = _auto()
    try:
        return auto.ControlFromHandle(hwnd)
    except Exception:
        return None


def find_window(title: str):
    """Top-level window whose title or app name contains `title` (case-insensitive).

    Windows are listed through Win32 rather than the automation tree: the tree's root
    enumeration intermittently misses live windows, which made this fail at random.
    Minimized windows count too - they are still the window the user means, and
    focus_window restores them.
    """
    from . import apps
    want = title.lower().strip()
    if not want:
        return None
    hits = []
    for w in apps.list_windows():
        t, p = w.title.lower(), w.process.lower()
        app = p.removesuffix(".exe")
        if want in t or want in app:
            # An app-name match beats a passing mention in some other window's title.
            hits.append((0 if want in app else 1, w))
    if not hits:
        return None
    hits.sort(key=lambda h: h[0])
    return _from_handle(hits[0][1].hwnd)


def _restore(w) -> None:
    """Bring a window up, un-minimizing it first so its controls become readable."""
    auto = _auto()
    try:
        if w.IsOffscreen or not _visible(w):
            try:
                w.ShowWindow(auto.SW.Restore)
            except Exception:
                pass
    except Exception:
        pass
    try:
        w.SetActive()
        w.SetFocus()
    except Exception:
        pass


def focus_window(title: str) -> bool:
    """Bring a window to the front, and confirm it really got there."""
    w = find_window(title)
    if not w:
        return False
    _restore(w)
    for _ in range(6):
        time.sleep(0.25)
        try:
            fg = foreground_window(skip_own=False)
            if fg is not None and fg.ProcessId == w.ProcessId:
                _remember(w)
                return True
        except Exception:
            pass
    return False


def snapshot(window_title: str | None = None, query: str = "", limit: int = 55, depth: int = 28) -> dict:
    """Interactive controls of a window, each with a short ref the model can act on.

    Chromium only builds its accessibility tree once something asks for it, so the
    first read of a browser tab is retried after a moment.
    """
    global _snapshot_id
    auto = _auto()
    with _lock:
        win = find_window(window_title) if window_title else foreground_window()
        if win is None:
            return {"error": "No window found."}
        _restore(win)                     # a minimized window exposes no controls
        time.sleep(0.3)
        _remember(win)
        title = _label(win)
        try:
            import psutil
            app = psutil.Process(win.ProcessId).name()
        except Exception:
            app = ""

        items: list[dict] = []
        for attempt in (0, 1):
            items = _walk(win, query, limit, depth)
            if items or attempt:
                break
            time.sleep(1.2)          # give Chromium time to expose the page

        _snapshot_id += 1
        _cache.clear()
        out = []
        for n, (el, info) in enumerate(items, 1):
            ref = f"e{n}"
            _cache[ref] = el
            out.append({"ref": ref, **info})
        return {"window": title, "app": app, "elements": out,
                "note": "Refs are valid until the next screen_read." if out else
                        "No controls were readable. The app may not support automation; try keyboard keys instead."}


def _walk(root, query: str, limit: int, depth: int) -> list[tuple[object, dict]]:
    q = query.lower().strip()
    found: list[tuple[object, dict]] = []
    seen: set[tuple] = set()

    def visit(el, level: int):
        if len(found) >= limit or level > depth:
            return
        try:
            kids = el.GetChildren()
        except Exception:
            kids = []
        for child in kids:
            if len(found) >= limit:
                return
            try:
                kind = child.ControlTypeName
                if not _visible(child):
                    continue
                name = _label(child)
                val = _value(child)
                editable = kind == "EditControl" or (kind in ("DocumentControl", "CustomControl") and _editable(child))
                useful = kind in ACTIONABLE and (name or val or editable)
                if useful and (not q or q in name.lower() or q in val.lower() or q in kind.lower()):
                    key = (kind, name, val[:40])
                    if key not in seen:
                        seen.add(key)
                        info = {"role": kind.replace("Control", ""), "name": name}
                        if val:
                            info["value"] = val
                        if editable:
                            info["editable"] = True
                        if _is_password(child):
                            info["password"] = True
                        if RISKY.search(name):
                            info["risky"] = True
                        try:
                            if not child.IsEnabled:
                                info["disabled"] = True
                        except Exception:
                            pass
                        found.append((child, info))
                visit(child, level + 1)
            except Exception:
                continue

    visit(root, 0)
    return found


def _editable(el) -> bool:
    try:
        return bool(el.GetValuePattern()) and not el.GetValuePattern().IsReadOnly
    except Exception:
        try:
            return bool(el.GetTextPattern())
        except Exception:
            return False


def window_text(window_title: str | None = None, limit: int = 6000) -> dict:
    """The readable text of a window (for "what does this page say?")."""
    auto = _auto()
    win = find_window(window_title) if window_title else foreground_window()
    if win is None:
        return {"error": "No window found."}
    parts: list[str] = []

    def visit(el, level=0):
        if level > 26 or sum(len(p) for p in parts) > limit:
            return
        try:
            kids = el.GetChildren()
        except Exception:
            return
        for child in kids:
            try:
                if not _visible(child):
                    continue
                if child.ControlTypeName in READABLE:
                    t = _label(child) or _value(child)
                    if t and len(t) > 1 and (not parts or parts[-1] != t):
                        parts.append(t)
                visit(child, level + 1)
            except Exception:
                continue

    visit(win)
    text = re.sub(r"\s*\n\s*", "\n", "\n".join(parts))[:limit]
    return {"window": _label(win), "text": text or "(no readable text)"}


# ------------------------------------------------------------------ acting

def get(ref: str):
    el = _cache.get(ref.strip().lower())
    return el


def describe(ref: str) -> str:
    el = get(ref)
    if el is None:
        return ref
    return f"{_label(el) or el.ControlTypeName.replace('Control', '')}"


def is_risky(ref: str) -> bool:
    el = get(ref)
    return bool(el is not None and RISKY.search(_label(el)))


def click(ref: str, double: bool = False, right: bool = False) -> str:
    el = get(ref)
    if el is None:
        return "That ref has expired. Read the screen again."
    try:
        if not el.IsEnabled:
            return f"“{_label(el)}” is disabled."
    except Exception:
        pass
    name = _label(el) or el.ControlTypeName
    try:
        el.GetTopLevelControl().SetActive()
    except Exception:
        pass
    try:
        if right:
            el.RightClick(simulateMove=False)
        elif double:
            el.DoubleClick(simulateMove=False)
        else:
            try:
                el.GetInvokePattern().Invoke()     # cleaner than a mouse click when supported
            except Exception:
                el.Click(simulateMove=False)
        time.sleep(0.6)
        return f"Clicked “{name}”."
    except Exception as e:
        return f"Couldn't click “{name}”: {e}"


def type_text(ref: str | None, text: str, clear: bool = False) -> str:
    """Type into a control (or wherever the keyboard focus is when ref is empty)."""
    auto = _auto()
    el = get(ref) if ref else None
    if ref and el is None:
        return "That ref has expired. Read the screen again."
    if el is None:
        problem = _focus_check()           # typing blind must not land in another app
        if problem:
            return "Refused: " + problem
    if el is not None:
        if _is_password(el):
            return "Refused: that is a password box. Freakyyy never types into password fields."
        try:
            top = el.GetTopLevelControl()
            _restore(top)
            el.SetFocus()
            _remember(top)
            time.sleep(0.25)
        except Exception:
            pass
        if clear:
            # Select-all inside a document would wipe the user's work, so only small fields clear.
            try:
                role = el.ControlTypeName
            except Exception:
                role = ""
            if role != "EditControl":
                return ("Refused: I only clear single fields, not whole documents. "
                        "Ask the user to clear it, or type without clearing.")
            try:
                auto.SendKeys("{Ctrl}a{Delete}", waitTime=0.05)
            except Exception:
                pass
    try:
        auto.SendKeys(_escape(text), waitTime=0.02)
        time.sleep(0.3)
        return f"Typed: {text[:120]}"
    except Exception as e:
        return f"Couldn't type: {e}"


_SPECIAL = {"enter": "{Enter}", "return": "{Enter}", "tab": "{Tab}", "escape": "{Esc}", "esc": "{Esc}",
            "space": "{Space}", "backspace": "{Back}", "delete": "{Delete}", "up": "{Up}", "down": "{Down}",
            "left": "{Left}", "right": "{Right}", "home": "{Home}", "end": "{End}", "pageup": "{PageUp}",
            "pagedown": "{PageDown}", "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}", "f5": "{F5}",
            "f6": "{F6}", "f11": "{F11}", "f12": "{F12}"}
_MODS = {"ctrl": "{Ctrl}", "control": "{Ctrl}", "alt": "{Alt}", "shift": "{Shift}", "win": "{Win}", "cmd": "{Win}"}


def press(keys: str) -> str:
    """Press a key or a combination: "enter", "ctrl+t", "alt+tab", "ctrl+shift+n".

    Keys go to whatever has focus, so the window Freakyyy last read must still be in front.
    """
    auto = _auto()
    problem = _focus_check()
    if problem:
        return "Refused: " + problem
    seq = ""
    for chunk in keys.replace(",", " ").split():
        parts = [p.strip().lower() for p in chunk.split("+") if p.strip()]
        mods = [_MODS[p] for p in parts if p in _MODS]
        rest = [p for p in parts if p not in _MODS]
        if not rest:
            seq += "".join(mods)
            continue
        last = rest[-1]
        key = _SPECIAL.get(last, last if len(last) == 1 else "")
        if not key:
            return f"I don't know the key “{last}”."
        seq += "".join(mods) + key
    if not seq:
        return "No keys given."
    try:
        auto.SendKeys(seq, waitTime=0.05)
        time.sleep(0.4)
        return f"Pressed {keys}."
    except Exception as e:
        return f"Couldn't press {keys}: {e}"


def scroll(direction: str = "down", amount: int = 3) -> str:
    auto = _auto()
    try:
        win = foreground_window()
        if win is not None:
            r = win.BoundingRectangle
            auto.SetCursorPos(r.xcenter(), r.ycenter())
        n = max(1, min(int(amount), 10))
        if direction.lower().startswith("u"):
            auto.WheelUp(n)
        else:
            auto.WheelDown(n)
        time.sleep(0.4)
        return f"Scrolled {direction} {n}."
    except Exception as e:
        return f"Couldn't scroll: {e}"


def _escape(text: str) -> str:
    """uiautomation treats {...} as key syntax; send the user's text literally.

    One pass, because escaping "{" introduces a "}" that must not be escaped again.
    """
    return re.sub(r"[{}]", lambda m: "{{}" if m.group() == "{" else "{}}", text)
