"""Freakyyy's command pipeline.

speech / typed / phone text
  -> parser.parse (deterministic, offline)      -> Intent (+ target device)
  -> confirmation / clarification / context
  -> handler (Windows APIs, Freakyyy Link, AI brain)
  -> Result (COMPLETED / OPENED / ... / DEVICE_OFFLINE)
  -> UI + Kokoro voice + history
"""
from __future__ import annotations

import json
import logging
import queue
import re
import secrets
import threading
import time
import uuid
import winsound
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import DATA_DIR, settings
from ..windows import apps, browser, browser_profiles, dev, files, system
from ..windows import ui_control
from . import parser
from .actions import (Clarification, Device, Intent, Outcome, Result, clarify, confirm, done, failed, info,
                      opened)

log = logging.getLogger(__name__)

YES = re.compile(r"^(yes|yeah|yep|yup|sure|ok|okay|do it|go ahead|confirm|continue|proceed|of course|please do|"
                 r"affirmative|correct|right|yes please|absolutely|aama|seri|ama)\b")
NO = re.compile(r"^(no|nope|nah|cancel|don'?t|stop|never ?mind|not now|abort|negative|leave it|illa|venda)\b")


@dataclass
class Context:
    last_text: str = ""
    last_intent: Intent | None = None
    last_device: Device = Device.LAPTOP
    last_app: str | None = None
    last_project: dev.Project | None = None
    candidates: list = field(default_factory=list)      # alternatives for "the other one"
    chosen: object = None
    last_files: list[Path] = field(default_factory=list)
    last_folder: Path | None = None
    last_reply: str = ""
    pending: Result | None = None
    pending_at: float = 0.0
    clarification: Clarification | None = None


class History:
    def __init__(self) -> None:
        self.path = DATA_DIR / "history.json"
        self.items: list[dict] = []
        if self.path.exists():
            try:
                self.items = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.items = []

    def add(self, command: str, label: str, outcome: str, message: str, source: str) -> dict:
        entry = {"t": time.time(), "command": command[:200], "action": label, "outcome": outcome,
                 "message": message[:400], "source": source}
        self.items.insert(0, entry)
        del self.items[300:]
        try:
            self.path.write_text(json.dumps(self.items), encoding="utf-8")
        except Exception:
            pass
        return entry

    def clear(self) -> None:
        self.items = []
        self.path.unlink(missing_ok=True)


class Routines:
    """Ordered steps, each a normal command on a device: {'device': 'laptop'|'phone', 'command': '...'}."""

    DEFAULTS = {
        "Study": [
            {"device": "laptop", "command": "set volume to 25 percent"},
            {"device": "laptop", "command": "set brightness to 70 percent"},
            {"device": "phone", "command": "turn on do not disturb"},
            {"device": "phone", "command": "set media volume to 20 percent"},
        ],
        "Work": [
            {"device": "laptop", "command": "open vscode"},
            {"device": "laptop", "command": "open chrome"},
            {"device": "laptop", "command": "open documents"},
            {"device": "phone", "command": "turn off do not disturb"},
        ],
        "Sleep": [
            {"device": "laptop", "command": "turn on dark mode"},
            {"device": "laptop", "command": "set brightness to 20 percent"},
            {"device": "laptop", "command": "set volume to 10 percent"},
            {"device": "phone", "command": "turn on do not disturb"},
            {"device": "phone", "command": "set brightness to 10 percent"},
        ],
    }

    def __init__(self) -> None:
        self.path = DATA_DIR / "routines.json"
        if self.path.exists():
            self.items = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.items = dict(self.DEFAULTS)
            self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.items, indent=2), encoding="utf-8")

    def find(self, name: str) -> tuple[str, list] | None:
        key = re.sub(r"\b(my|the|routine|mode)\b", "", name.lower()).strip()
        for n, steps in self.items.items():
            if n.lower() == key or key in n.lower() or n.lower() in key:
                return n, steps
        return None


_DESCRIPTIONS = {
    "app.open": "Launching {name}", "app.close": "Closing {name}", "app.kill": "Force-closing {name}",
    "app.search": "Looking for {name}", "app.list_running": "Listing open apps",
    "window.switch": "Switching to {name}", "window.minimize": "Minimising {name}", "window.maximize": "Maximising {name}",
    "window.close": "Closing {name}", "window.show_desktop": "Showing the desktop",
    "file.search": "Searching files for {query}", "file.open": "Opening {query}", "file.open_known": "Opening {name}",
    "file.open_folder": "Opening the {name} folder", "folder.create": "Creating folder {name}", "file.rename": "Renaming {target}",
    "file.copy": "Copying {target}", "file.move": "Moving {target}", "file.delete": "Preparing to delete {target}",
    "file.latest_download": "Finding your latest download", "file.large": "Scanning for large files",
    "sys.volume": "Setting volume", "sys.brightness": "Setting brightness", "sys.settings": "Opening {page} settings",
    "sys.battery": "Reading the battery", "sys.performance": "Reading CPU and memory", "sys.storage": "Reading disk space",
    "sys.status": "Collecting system status", "sys.screenshot": "Taking a screenshot", "sys.lock": "Locking the laptop",
    "sys.dark_mode": "Changing the theme", "sys.shutdown": "Preparing to shut down", "sys.restart": "Preparing to restart",
    "dev.open_project": "Opening project {project}", "dev.git_status": "Checking git status", "dev.git_commit": "Preparing a commit",
    "dev.gradle_build": "Starting the Gradle build", "dev.npm_install": "Running npm install", "dev.terminal": "Opening a terminal",
    "dev.server_start": "Starting the dev server", "dev.run_python": "Preparing to run the Python project",
    "web.search": "Searching for {query}", "web.open_site": "Opening {site}", "web.lucky": "Finding {query}",
    "web.read_page": "Reading the current page", "web.download_pdf": "Downloading the PDF",
    "mail.check": "Checking your inbox", "mail.search": "Searching email for {query}", "mail.latest": "Reading your latest email",
    "remote.command": "Asking your phone: {text}", "link.ring": "Ringing your phone", "link.send_file": "Sending a file to your phone",
    "link.status": "Getting phone status", "routine.run": "Running the {name} routine", "chain": "Running several steps",
    "ai.ask": "Working out what you mean",
    "memory.add": "Saving to memory", "memory.list": "Reading my memory", "memory.recall": "Searching my memory",
    "memory.forget": "Forgetting that", "memory.forget_all": "Clearing my memory",
    "browser.profile_open": "Opening {browser} with the {profile} profile",
    "browser.profile_clear": "Resetting the {browser} profile",
}


def describe(intent: Intent) -> str:
    template = _DESCRIPTIONS.get(intent.name)
    if not template:
        return intent.name.split(".")[-1].replace("_", " ").capitalize()
    params = {k: (v if v not in (None, "") else "it") for k, v in intent.params.items()}
    for k in ("name", "site", "project", "browser"):
        if isinstance(params.get(k), str) and params[k] != "it":
            params[k] = params[k].title()
    try:
        return template.format(**params)
    except KeyError:
        return template.split(" {")[0]


from ..ai import memory as memory_mod

_UI_TOOLS = {"screen_read", "screen_text", "ui_click", "ui_type", "ui_press", "ui_scroll",
             "focus_window", "wait_seconds"}

_SENSITIVE = memory_mod.SENSITIVE



class Assistant:
    def __init__(self, emit: Callable[[str, dict], None]) -> None:
        self.emit = emit
        self.ctx = Context()
        self.history = History()
        self.routines = Routines()
        self.app_index = apps.AppIndex()
        self.voice = None          # set by app after construction
        self.listener = None
        self.link = None
        self.brain = None
        self._queue: queue.Queue = queue.Queue()
        self._routine_cancel = threading.Event()
        self._remote_pending: dict[str, tuple[float, Callable[[], Result]]] = {}
        self._ui_typed = False
        self._handlers = {name[2:].replace("__", "."): getattr(self, name) for name in dir(self) if name.startswith("h_")}
        threading.Thread(target=self._worker, daemon=True, name="freakyyy-commands").start()

    # ================================================================ entry points
    def submit(self, text: str, source: str = "voice") -> None:
        """Queue a command. 'stop' is handled immediately so it can interrupt."""
        t = parser.normalize(text)
        if re.fullmatch(r"(stop|cancel|quiet|be quiet|shut up|stop talking|enough|never ?mind|cancel that)( it| that| everything| all)?", t or "-"):
            self._stop_everything()
            self._finish(text, "assistant.stop", Result(Outcome.COMPLETED, "Stopped.", spoken=""), source)
            return
        self._queue.put((text, source, None))

    def run_sync(self, text: str, source: str = "remote", speak: bool = False) -> Result:
        """Run a command and wait for its result (phone requests, AI tools)."""
        box: queue.Queue = queue.Queue()
        self._queue.put((text, source, box))
        return box.get()

    def wake_only(self) -> None:
        """'Hey Freaky' with no command."""
        self.emit("state", {"state": "LISTENING"})
        self._say("Yes?")
        if self.listener:
            self.listener.expect_reply(6)

    def _worker(self) -> None:
        while True:
            text, source, box = self._queue.get()
            try:
                result, label = self._process(text, source)
            except Exception as e:
                log.exception("Command failed: %s", text)
                result, label = failed(f"Something went wrong: {e}", "Sorry, something went wrong with that."), "ERROR"
            if box is not None:
                box.put(result)
                self._finish(text, label, result, source, speak=False)
            else:
                self._finish(text, label, result, source)

    # ================================================================ pipeline
    def _process(self, text: str, source: str) -> tuple[Result, str]:
        self.emit("state", {"state": "THINKING"})
        self.emit("transcript", {"text": text, "source": source})
        answer = parser.normalize(text)

        # 1. A pending yes/no question
        if self.ctx.pending and time.time() - self.ctx.pending_at < 120:
            pending = self.ctx.pending
            if YES.match(answer):
                self.ctx.pending = None
                self.emit("state", {"state": "EXECUTING"})
                return pending.confirm(), "CONFIRMED"
            if NO.match(answer):
                self.ctx.pending = None
                return info("Okay, I won't do that."), "DECLINED"
            intent = parser.parse(text)
            if intent.name in ("ai.ask", "assistant.greeting"):
                return Result(Outcome.NEEDS_CONFIRMATION, f"Please say yes or no. {pending.message}",
                              confirm=pending.confirm), "AWAITING"
            self.ctx.pending = None

        # 2. A pending clarification ("which project?")
        if self.ctx.clarification:
            c = self.ctx.clarification
            self.ctx.clarification = None
            if NO.match(answer):
                return info("Okay, cancelled."), "CANCELLED"
            resolved = c.resolve(answer)
            if resolved is not None:
                return resolved, "CLARIFIED"

        intent = parser.parse(text)
        self.ctx.last_text, self.ctx.last_intent = text, intent
        self.emit("action", {"label": intent.label, "device": intent.device.value, "description": describe(intent)})
        return self.execute(intent), intent.label

    def execute(self, intent: Intent) -> Result:
        if intent.device == Device.PHONE and intent.name not in self._phone_native:
            return self._remote(intent.params.get("text") or intent.text, intent)
        handler = self._handlers.get(intent.name)
        if not handler:
            return self.h_ai__ask(Intent("ai.ask", {"text": self.ctx.last_text}))
        self.emit("state", {"state": "EXECUTING"})
        result = handler(intent)
        if intent.device == Device.BOTH and intent.name != "routine.run":
            phone = self._remote(intent.text, intent)
            result = Result(result.outcome, f"Laptop: {result.message} Phone: {phone.message}",
                            spoken=f"{result.speech} On your phone: {phone.speech}")
        self.ctx.last_device = intent.device
        return result

    _phone_native = {"link.ring", "link.status", "link.send_file", "link.send_page", "link.clipboard_push",
                     "link.clipboard_pull", "routine.run", "remote.command"}

    def _finish(self, text: str, label: str, result: Result, source: str, speak: bool = True) -> None:
        if result.outcome == Outcome.NEEDS_CONFIRMATION and result.confirm:
            self.ctx.pending, self.ctx.pending_at = result, time.time()
        if result.outcome == Outcome.CLARIFY and result.clarify:
            self.ctx.clarification = result.clarify
        entry = self.history.add(text, label, result.outcome.value, result.message, source)
        self.emit("activity", entry)
        self.emit("reply", {"text": result.message, "outcome": result.outcome.value})
        self.ctx.last_reply = result.speech
        state = {"NEEDS_CONFIRMATION": "WAITING_FOR_CONFIRMATION", "FAILED": "ERROR"}.get(result.outcome.value, "IDLE")
        self.emit("state", {"state": state})
        if speak and result.speech:
            self._say(result.speech)
        if self.listener and (result.outcome in (Outcome.NEEDS_CONFIRMATION, Outcome.CLARIFY)
                              or result.speech.rstrip().endswith("?")):
            self.listener.expect_reply(8)

    def _say(self, text: str) -> None:
        if self.voice and text:
            self.voice.speak(text)

    def _stop_everything(self) -> None:
        self._routine_cancel.set()
        self.ctx.pending = None
        self.ctx.clarification = None
        if self.voice:
            self.voice.stop()

    # ================================================================ remote (phone)
    def _remote(self, text: str, intent: Intent | None = None) -> Result:
        if not self.link:
            return Result(Outcome.DEVICE_OFFLINE, "Freakyyy Link isn't running.")
        self.emit("state", {"state": "EXECUTING"})
        r = self.link.request("run_command", {"text": text[:300]})
        return self._from_remote(r)

    def _from_remote(self, r: dict) -> Result:
        outcome = Outcome(r.get("outcome", "FAILED")) if r.get("outcome") in Outcome._value2member_map_ else Outcome.FAILED
        msg = r.get("message", "")
        if outcome == Outcome.NEEDS_CONFIRMATION and r.get("confirm_token"):
            token = r["confirm_token"]
            return confirm(f"Your phone asks: {msg}", lambda: self._from_remote(
                self.link.request("confirm", {"confirm_token": token, "accept": True})))
        return Result(outcome, msg)

    def handle_link_request(self, action: str, params: dict, device) -> dict:
        """Requests coming from the phone (runs on a link worker thread)."""
        self.emit("activity", self.history.add(f"[{device.name}] {action} {params.get('text', '')}".strip(),
                                               f"LINK · {action}", "INFO", "Received", "phone"))
        if action == "run_command":
            text = str(params.get("text", ""))[:300]
            result = self.run_sync(text, source=f"phone:{device.name}")
            out = {"outcome": result.outcome.value, "message": result.message}
            if result.outcome == Outcome.NEEDS_CONFIRMATION and result.confirm:
                token = secrets.token_urlsafe(16)
                self._remote_pending[token] = (time.time(), result.confirm)
                self.ctx.pending = None            # the phone answers this one
                out["confirm_token"] = token
            return out
        if action == "confirm":
            item = self._remote_pending.pop(str(params.get("confirm_token", "")), None)
            if not item or time.time() - item[0] > 60:
                return {"outcome": "FAILED", "message": "That confirmation expired."}
            if not params.get("accept"):
                return {"outcome": "INFO", "message": "Cancelled."}
            r = item[1]()
            return {"outcome": r.outcome.value, "message": r.message}
        if action == "get_status":
            snap = system.status_snapshot()
            return {"outcome": "INFO", "message": self._laptop_status_text(snap), "data": snap}
        if action == "open_url":
            url = str(params.get("url", ""))
            if not re.match(r"^https?://", url):
                return {"outcome": "FAILED", "message": "Only web links can be opened."}
            browser.open_url(url)
            return {"outcome": "COMPLETED", "message": "Opened on your laptop."}
        if action == "ring":
            threading.Thread(target=self._ring, args=(min(int(params.get("seconds", 10)), 30),), daemon=True).start()
            self.emit("show_window", {})
            return {"outcome": "COMPLETED", "message": "Your laptop is ringing."}
        if action == "clipboard_push":
            if not settings.get("clipboard_accept_from_devices"):
                return {"outcome": "NEEDS_PERMISSION", "message": "Clipboard sharing is off on the laptop."}
            system.clipboard_set(str(params.get("text", ""))[:100_000])
            self.emit("toast", {"title": "Clipboard", "text": f"Received text from {device.name}."})
            return {"outcome": "COMPLETED", "message": "Copied to your laptop's clipboard."}
        if action == "clipboard_pull":
            if not settings.get("clipboard_share_to_devices"):
                return {"outcome": "NEEDS_PERMISSION", "message": "The laptop doesn't share its clipboard. Turn it on in Freakyyy settings on the laptop."}
            return {"outcome": "COMPLETED", "message": "Here's your laptop clipboard.", "data": {"text": system.clipboard_get()[:100_000]}}
        if action == "notify":
            self.emit("toast", {"title": str(params.get("title", device.name))[:80], "text": str(params.get("text", ""))[:300]})
            return {"outcome": "COMPLETED", "message": "Shown on the laptop."}
        if action == "routine_run":
            r = self.run_sync(f"start {params.get('name', '')} routine", source=f"phone:{device.name}")
            return {"outcome": r.outcome.value, "message": r.message}
        return {"outcome": "NOT_SUPPORTED", "message": "Not supported."}

    def _ring(self, seconds: int) -> None:
        end = time.time() + seconds
        while time.time() < end:
            for f in (880, 1320, 1760):
                winsound.Beep(f, 180)
            time.sleep(0.4)

    @staticmethod
    def _laptop_status_text(s: dict) -> str:
        bat = f"battery {s['battery']}%{' charging' if s['charging'] else ''}, " if s.get("battery") is not None else ""
        return f"Laptop: {bat}CPU {s['cpu']:.0f}%, memory {s['mem']:.0f}%, {s['disk_free_gb']:.0f} GB free."

    # ================================================================ handlers: assistant
    def h_assistant__greeting(self, i: Intent) -> Result:
        hour = time.localtime().tm_hour
        part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 17 else "Good evening" if hour < 22 else "Hello"
        return info(f"{part}. What can I do for you?")

    def h_assistant__identity(self, i):
        return info("I'm Freakyyy, your personal assistant across this laptop and your phone.")

    def h_assistant__thanks(self, i):
        return info("Anytime.")

    def h_assistant__help(self, i):
        return info("Say Hey Freaky, then things like: open VS Code, open my Freakyyy project in Android Studio, "
                    "set volume to 40 percent, take a screenshot, search my documents for resume, check git status, "
                    "any important emails, turn on my phone flashlight, send this file to my phone, or start study mode on both devices.",
                    spoken="Just say Hey Freaky and ask. I can open apps and projects, control settings, manage files, "
                           "run builds and git, check your email, and control your phone.")

    def h_assistant__repeat(self, i):
        return info(self.ctx.last_reply or "I haven't said anything yet.")

    def h_assistant__stop(self, i):
        self._stop_everything()
        return Result(Outcome.COMPLETED, "Stopped.", spoken="")

    def h_assistant__stop_listening(self, i):
        if self.listener:
            self.listener.set_enabled(False)
        self.emit("listening", {"enabled": False})
        return done("I've stopped listening. The microphone is off; press the hotkey or the mic button to talk.",
                    spoken="Okay, I've stopped listening.")

    def h_assistant__idle(self, i):
        self._stop_everything()
        self.emit("idle", {})
        return Result(Outcome.COMPLETED, "Standing by.", spoken="Standing by.")

    def h_assistant__island(self, i):
        self.emit("island", {"show": i.params["show"]})
        return done("Notch shown." if i.params["show"] else "Notch hidden. Say show the notch to bring it back.",
                    spoken="Done.")

    def h_assistant__start_listening(self, i):
        if self.listener:
            self.listener.set_enabled(True)
        self.emit("listening", {"enabled": True})
        return done("Listening for Hey Freaky.")

    def h_assistant__exit(self, i):
        return confirm("Should I shut myself down? I won't hear Hey Freaky until you start me again.",
                       lambda: (self.emit("quit", {}), done("Goodbye."))[1])

    def h_assistant__restart(self, i):
        self.emit("restart", {})
        return done("Restarting myself.")

    def h_assistant__window(self, i):
        self.emit("show_window" if i.params.get("show") else "hide_window", {})
        return done("Here I am." if i.params.get("show") else "Minimised to the tray.")

    def h_assistant__settings(self, i):
        self.emit("open_settings", {})
        return opened("Opening my settings.")

    def h_assistant__routines(self, i):
        self.emit("open_settings", {"tab": "routines"})
        names = ", ".join(self.routines.items)
        return info(f"Your routines: {names}.")

    def h_info__time(self, i):
        return info(time.strftime("It's %I:%M %p.").replace(" 0", " "))

    def h_info__date(self, i):
        return info(time.strftime("Today is %A, %d %B %Y."))

    # ================================================================ multi-step ("open X and load Y")
    def h_chain(self, i: Intent) -> Result:
        messages, spoken = [], []
        result = info("")
        for n, part in enumerate(i.params["parts"]):
            step = parser.parse(part)
            result = self.execute(step)
            messages.append(result.message)
            spoken.append(result.speech)
            if result.outcome in (Outcome.NEEDS_CONFIRMATION, Outcome.CLARIFY, Outcome.FAILED, Outcome.DEVICE_OFFLINE):
                break
            if n < len(i.params["parts"]) - 1 and step.name in ("app.open", "web.open_site", "web.search"):
                time.sleep(1.5)          # let the app come up before the next step
        return Result(result.outcome, " ".join(m for m in messages if m), spoken=" ".join(s for s in spoken if s),
                      confirm=result.confirm, clarify=result.clarify)

    # ================================================================ context
    def h_context__redo(self, i: Intent) -> Result:
        prev = self.ctx.last_intent
        if not prev:
            return info("There's nothing to repeat yet.")
        if i.params["device"] == "phone":
            return self._remote(prev.text or self.ctx.last_text)
        local = parser.parse(prev.text or self.ctx.last_text)
        local.device = Device.LAPTOP
        return self.execute(local)

    def h_context__other(self, i: Intent) -> Result:
        others = [c for c in self.ctx.candidates if c is not self.ctx.chosen]
        if not others:
            return info("There's no other option I know of.")
        pick = others[0]
        if isinstance(pick, dev.Project):
            return self._open_project(pick, None)
        if isinstance(pick, Path):
            return self._open_path(pick)
        if isinstance(pick, apps.App):
            return self._launch_app(pick)
        return info("I'm not sure which one you mean.")

    def _choose(self, question: str, items: list, label: Callable[[object], str],
                act: Callable[[object], Result]) -> Result:
        self.ctx.candidates = items
        names = [label(x) for x in items[:4]]
        ordinals = ["first", "second", "third", "fourth"]

        def resolve(answer: str) -> Result | None:
            a = answer.lower()
            for n, word in enumerate(ordinals):
                if re.search(rf"\b({word}|{n + 1})\b", a) and n < len(items):
                    return act(items[n])
            scored = []
            for item, name in zip(items, names):
                words = [w for w in re.split(r"\W+", name.lower()) if len(w) > 2]
                score = sum(1 for w in words if w in a)
                scored.append((score, item))
            scored.sort(key=lambda s: -s[0])
            if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                return act(scored[0][1])
            return None

        spoken_list = ", ".join(names[:-1]) + f" or {names[-1]}" if len(names) > 1 else names[0]
        return clarify(f"{question} {spoken_list}?", names, resolve)

    # ================================================================ apps & windows
    def h_app__open(self, i: Intent) -> Result:
        name = i.params["name"].strip()
        then = i.params.get("then")
        result = self._open_by_name(name)
        if then and result.outcome in (Outcome.COMPLETED, Outcome.OPENED):
            time.sleep(1.5)
            follow = parser.parse(then)
            if follow.name == "ai.ask":
                follow = parser.parse("search for " + then)
            r2 = self.execute(follow)
            return Result(r2.outcome, f"{result.message} {r2.message}", spoken=f"{result.speech} {r2.speech}")
        return result

    def _open_by_name(self, name: str) -> Result:
        hits = self.app_index.find(name)
        if len(hits) == 1:
            return self._launch_app(hits[0])
        if len(hits) > 1:
            return self._choose("I found a few matches:", hits, lambda a: a.name, self._launch_app)
        # Not an app: maybe a project, a folder, a website or a settings page.
        projects = dev.match_projects(name)
        if len(projects) == 1:
            return self._open_project(projects[0], None)
        site = browser.SITES.get(name.lower())
        if site:
            browser.open_url(site)
            return done(f"Opening {name.title()}.")
        folder = files.known_folder(name)
        if folder:
            return self._open_path(folder)
        if name.lower() in system.SETTINGS_PAGES:
            return system.open_settings(name)
        return failed(f"I couldn't find an app called {name}.")

    def h_browser__profile_open(self, i: Intent) -> Result:
        key = browser_profiles.browser_key(i.params["browser"])
        name = browser_profiles.display(key)
        if not browser_profiles.exe(key):
            return failed(f"{name} isn't installed.")
        if browser_profiles.is_private(i.params["profile"]):
            if browser_profiles.launch(key, None, private=True):
                return done(f"Opening a private {name} window.")
            return failed(f"I couldn't start {name}.")
        hits = browser_profiles.match(key, i.params["profile"])
        if not hits:
            names = [n for _, n in browser_profiles.profiles(key)]
            listing = ", ".join(names[:8]) if names else "none"
            return failed(f"{name} has no profile called {browser_profiles.clean_profile(i.params['profile'])}. Its profiles: {listing}.",
                          spoken=f"{name} has no profile called {browser_profiles.clean_profile(i.params['profile'])}.")
        if len(hits) > 1:
            return self._choose(f"{name} has a few matching profiles:", hits, lambda p: p[1],
                                lambda p: self._open_profile(key, p, i.params.get("always", False)))
        return self._open_profile(key, hits[0], i.params.get("always", False))

    def _open_profile(self, key: str, profile: tuple[str, str], always: bool) -> Result:
        name = browser_profiles.display(key)
        if always:
            prefs = dict(settings.get("browser_profiles") or {})
            prefs[key] = profile[0]
            settings.set("browser_profiles", prefs)
        if not browser_profiles.launch(key, profile[0]):
            return failed(f"I couldn't start {name}.")
        self.ctx.last_app = name
        msg = f"Opening {name} with your {profile[1]} profile."
        if always:
            msg += f" From now on, “open {name}” uses {profile[1]}. Say “open {name} normally” to undo."
            return done(msg, spoken=f"Done. {name} will always open with your {profile[1]} profile.")
        return done(msg)

    def h_browser__profile_clear(self, i: Intent) -> Result:
        key = browser_profiles.browser_key(i.params["browser"])
        prefs = dict(settings.get("browser_profiles") or {})
        had = prefs.pop(key, None)
        settings.set("browser_profiles", prefs)
        name = browser_profiles.display(key)
        browser_profiles.launch(key, None) if "open" in (self.ctx.last_text or "").lower() else None
        return done(f"{name} will open normally again." if had else f"{name} wasn't set to a profile.")

    def _launch_app(self, app: apps.App) -> Result:
        self.ctx.chosen = app
        key = browser_profiles.browser_key(app.name)
        saved = (settings.get("browser_profiles") or {}).get(key) if key else None
        if saved:
            label = dict(browser_profiles.profiles(key)).get(saved, saved)
            if browser_profiles.launch(key, saved):
                self.ctx.last_app = app.name
                return done(f"Opening {app.name} with your {label} profile.")
        if self.app_index.launch(app):
            self.ctx.last_app = app.name
            return done(f"Opening {app.name}.")
        return failed(f"Windows couldn't start {app.name}.")

    def h_app__search(self, i: Intent) -> Result:
        hits = self.app_index.find(i.params["name"])
        if not hits:
            return info(f"{i.params['name']} doesn't seem to be installed.")
        return info("Installed: " + ", ".join(h.name for h in hits[:5]) + ".")

    def h_app__list_running(self, i: Intent) -> Result:
        wins = apps.list_windows()
        names = []
        for w in wins:
            n = w.process.replace(".exe", "")
            if n.lower() not in [x.lower() for x in names] and n.lower() not in ("textinputhost", "applicationframehost", "shellexperiencehost"):
                names.append(n)
        return info(f"{len(names)} apps have open windows: " + ", ".join(names[:12]) + ".",
                    spoken=f"You have {len(names)} apps open, including " + ", ".join(names[:5]) + ".")

    def _window_target(self, name: str | None) -> list[apps.Window]:
        if name:
            return apps.find_windows(name)
        w = apps.active_window()
        return [w] if w else []

    def h_window__switch(self, i: Intent) -> Result:
        wins = apps.find_windows(i.params["name"])
        if not wins:
            return self._open_by_name(i.params["name"])
        ok = apps.focus(wins[0].hwnd)
        return done(f"Switched to {wins[0].title[:60]}.", spoken=f"Switched to {i.params['name']}.") if ok \
            else failed(f"Windows didn't let me bring {i.params['name']} to the front.")

    def _win_op(self, i: Intent, cmd: int, verb: str) -> Result:
        wins = self._window_target(i.params.get("name"))
        if not wins:
            return failed("I couldn't find that window.")
        for w in wins[:5]:
            apps.show(w.hwnd, cmd)
        return done(f"{verb} {i.params.get('name') or wins[0].title[:50]}.")

    def h_window__minimize(self, i):
        return self._win_op(i, apps.SW_MINIMIZE, "Minimised")

    def h_window__maximize(self, i):
        return self._win_op(i, apps.SW_MAXIMIZE, "Maximised")

    def h_window__restore(self, i):
        return self._win_op(i, apps.SW_RESTORE, "Restored")

    def h_window__snap_left(self, i):
        wins = self._window_target(i.params.get("name"))
        if wins and apps.focus(wins[0].hwnd):
            system.send_keys(system.VK_LWIN, system.VK_LEFT)
            return done("Snapped left.")
        return failed("I couldn't find that window.")

    def h_window__snap_right(self, i):
        wins = self._window_target(i.params.get("name"))
        if wins and apps.focus(wins[0].hwnd):
            system.send_keys(system.VK_LWIN, system.VK_RIGHT)
            return done("Snapped right.")
        return failed("I couldn't find that window.")

    def h_window__show_desktop(self, i):
        system.send_keys(system.VK_LWIN, system.VK_D)
        return done("Showing the desktop.")

    def h_window__close(self, i: Intent) -> Result:
        wins = self._window_target(i.params.get("name"))
        if not wins:
            return failed("I couldn't find that window.")
        target = wins[0]
        apps.close(target.hwnd)
        time.sleep(0.8)
        if apps.is_window(target.hwnd):
            return Result(Outcome.OPENED, f"{target.process.replace('.exe', '')} is asking something before it closes — "
                                          "probably about unsaved work. Please check it.")
        return done(f"Closed {target.title[:60]}.", spoken=f"Closed {i.params.get('name') or target.process.replace('.exe', '')}.")

    def h_app__kill(self, i: Intent) -> Result:
        wins = self._window_target(i.params.get("name"))
        if not wins:
            return failed("I couldn't find that app.")
        w = wins[0]

        def go():
            import psutil
            try:
                psutil.Process(w.pid).kill()
                return done(f"Force-closed {w.process}.")
            except Exception as e:
                return failed(f"Couldn't force-close it: {e}")
        return confirm(f"Force-close {w.process.replace('.exe', '')}? Unsaved work in it will be lost.", go)

    # ================================================================ system
    def h_sys__lock(self, i): return system.lock()
    def h_sys__sleep(self, i): return system.sleep()
    def h_sys__restart(self, i): return system.restart()
    def h_sys__shutdown(self, i): return system.shutdown()
    def h_sys__signout(self, i): return system.signout()
    def h_sys__cancel_shutdown(self, i): return system.cancel_shutdown()
    def h_sys__screenshot(self, i):
        r = system.screenshot()
        if r.data:
            self.ctx.last_files = [Path(r.data["path"])]
        return r
    def h_sys__battery(self, i): return system.battery()

    def h_sys__status(self, i):
        snap = system.status_snapshot()
        snap["cpu"] = __import__("psutil").cpu_percent(interval=0.3)
        return info(self._laptop_status_text(snap), data=snap)
    def h_sys__performance(self, i): return system.performance()
    def h_sys__storage(self, i): return system.storage()
    def h_sys__settings(self, i): return system.open_settings(i.params["page"])
    def h_sys__radio(self, i): return system.radio(i.params["page"], i.params["on"])
    def h_sys__dark_mode(self, i): return system.dark_mode(i.params["on"])
    def h_media__key(self, i): return system.media_key(i.params["key"])

    def h_sys__volume(self, i: Intent) -> Result:
        p = i.params
        return system.volume(p.get("value"), p.get("delta"), p.get("mute"))

    def h_sys__brightness(self, i: Intent) -> Result:
        return system.brightness(i.params.get("value"), i.params.get("delta"))

    def h_clipboard__read(self, i):
        text = system.clipboard_get().strip()
        if not text:
            return info("Your clipboard is empty or holds something that isn't text.")
        return info(f"Your clipboard says: {text[:300]}", spoken=f"Your clipboard says: {text[:200]}")

    # ================================================================ files
    def _open_path(self, p: Path) -> Result:
        import os
        self.ctx.chosen = p
        if not p.exists():
            return failed(f"{p} no longer exists.")
        os.startfile(p)
        if p.is_dir():
            self.ctx.last_folder = p
        else:
            self.ctx.last_files = [p]
        return done(f"Opening {p.name}.", spoken=f"Opening {p.stem if p.is_file() else p.name}.")

    def h_file__open_known(self, i):
        p = files.known_folder(i.params["name"])
        return self._open_path(p) if p else failed("I don't know that folder.")

    def h_file__open_folder(self, i):
        hits = files.find_folder(i.params["name"])
        if not hits:
            projects = dev.match_projects(i.params["name"])
            hits = [p.path for p in projects]
        if not hits:
            return failed(f"I couldn't find a folder called {i.params['name']}.")
        if len(hits) == 1:
            return self._open_path(hits[0])
        return self._choose("Which folder:", hits, lambda p: f"{p.name} in {p.parent.name}", self._open_path)

    def h_file__latest_download(self, i):
        p = files.latest_download()
        if not p:
            return info("Your Downloads folder is empty.")
        self.ctx.last_files = [p]
        if i.params.get("open"):
            return self._open_path(p)
        age = (time.time() - p.stat().st_mtime) / 3600
        when = f"{age * 60:.0f} minutes ago" if age < 1 else f"{age:.0f} hours ago" if age < 48 else time.strftime("%d %B", time.localtime(p.stat().st_mtime))
        return info(f"Your latest download is {p.name}, {files.human_size(p.stat().st_size)}, from {when}. Say open it to open it.",
                    spoken=f"Your latest download is {p.stem}, from {when}.")

    def h_file__search(self, i: Intent) -> Result:
        q = i.params["query"]
        hits = files.search(q, i.params.get("location"), i.params.get("pdf", False))
        if not hits:
            return info(f"I couldn't find any files matching {q}.")
        self.ctx.last_files = hits
        self.emit("files", {"items": [str(h) for h in hits[:20]]})
        if len(hits) == 1:
            return info(f"Found {hits[0].name} in {hits[0].parent}. Say open it to open it.",
                        spoken=f"I found {hits[0].stem}. Want me to open it?")
        top = ", ".join(h.name for h in hits[:3])
        return self._choose(f"I found {len(hits)} files. The newest are", hits[:4],
                            lambda p: p.stem[:40], self._open_path)

    def h_file__open(self, i: Intent) -> Result:
        if re.fullmatch(r"(it|this|that)", i.params["query"]) and self.ctx.last_files:
            return self._open_path(self.ctx.last_files[0])
        hits = files.search(i.params["query"], pdf=i.params.get("ext") == "pdf")
        if not hits:
            return failed(f"I couldn't find {i.params['query']}.")
        if len(hits) == 1 or hits[0].stem.lower() == i.params["query"].lower():
            return self._open_path(hits[0])
        return self._choose("Which one:", hits[:4], lambda p: p.stem[:40], self._open_path)

    def _resolve_target(self, ref: str) -> list[Path] | Result:
        ref = (ref or "").strip()
        if re.fullmatch(r"(it|this|that|these|those|this file|that file|the file|selected( file| files)?|the selection)", ref):
            sel = files.explorer_selection()
            if sel:
                return sel
            if self.ctx.last_files:
                return self.ctx.last_files[:1]
            return failed("Select the file in File Explorer first, or tell me its name.")
        if re.fullmatch(r"(this|that|the|selected) folder", ref):
            sel = [p for p in files.explorer_selection() if p.is_dir()]
            if sel:
                return sel
            if self.ctx.last_folder:
                return [self.ctx.last_folder]
            return failed("Select the folder in File Explorer first, or tell me its name.")
        hits = files.search(ref)
        folders = files.find_folder(ref) if not hits else []
        hits = hits or folders
        if not hits:
            return failed(f"I couldn't find {ref}.")
        return hits

    def _dest_folder(self, name: str) -> Path | None:
        kf = files.known_folder(name)
        if kf:
            return kf
        hits = files.find_folder(name)
        if hits:
            return hits[0]
        projects = dev.match_projects(name)
        return projects[0].path if projects else None

    def h_folder__create(self, i: Intent) -> Result:
        name = files.safe_name(i.params.get("name") or "New folder")
        loc = i.params.get("location")
        base = self._dest_folder(loc) if loc else (self.ctx.last_folder or files.known_folder("desktop"))
        if base is None:
            return failed(f"I couldn't find {loc}.")
        target = base / name
        if target.exists():
            return info(f"A folder called {name} already exists in {base.name}.")
        target.mkdir(parents=True)
        self.ctx.last_folder = target
        return done(f"Created the folder {name} in {base}.", spoken=f"Created {name} on your {base.name}.") if target.is_dir() \
            else failed("The folder couldn't be created.")

    def h_file__rename(self, i: Intent) -> Result:
        t = self._resolve_target(i.params["target"])
        if isinstance(t, Result):
            return t
        if len(t) > 1 and not re.fullmatch(r"(it|this|that|selected.*)", i.params["target"]):
            return self._choose("Rename which one:", t[:4], lambda p: p.name,
                                lambda p: self._rename(p, i.params["new_name"]))
        return self._rename(t[0], i.params["new_name"])

    def _rename(self, p: Path, new: str) -> Result:
        new = files.safe_name(new)
        if p.is_file() and not Path(new).suffix:
            new += p.suffix
        target = p.with_name(new)
        if target.exists():
            return failed(f"{new} already exists there.")
        p.rename(target)
        self.ctx.last_files = [target]
        return done(f"Renamed {p.name} to {target.name}.")

    def _copy_move(self, i: Intent, move: bool) -> Result:
        import shutil
        t = self._resolve_target(i.params["target"])
        if isinstance(t, Result):
            return t
        dest = self._dest_folder(i.params["dest"])
        if not dest:
            return failed(f"I couldn't find the folder {i.params['dest']}.")
        src = t[0] if len(t) == 1 or re.fullmatch(r"(it|this|that|selected.*)", i.params["target"]) else None
        if src is None:
            return self._choose(f"{'Move' if move else 'Copy'} which one:", t[:4], lambda p: p.name,
                                lambda p: self._copy_move(Intent(i.name, {**i.params, "target": str(p)}), move))
        items = t if len(t) > 1 else [src]
        for p in items:
            target = dest / p.name
            if target.exists():
                return failed(f"{p.name} already exists in {dest.name}.")
            if move:
                shutil.move(str(p), target)
            elif p.is_dir():
                shutil.copytree(p, target)
            else:
                shutil.copy2(p, target)
        self.ctx.last_files = [dest / p.name for p in items]
        verb = "Moved" if move else "Copied"
        names = items[0].name if len(items) == 1 else f"{len(items)} items"
        return done(f"{verb} {names} to {dest}.", spoken=f"{verb} {names} to {dest.name}.")

    def h_file__copy(self, i): return self._copy_move(i, False)
    def h_file__move(self, i): return self._copy_move(i, True)

    def h_file__delete(self, i: Intent) -> Result:
        t = self._resolve_target(i.params["target"])
        if isinstance(t, Result):
            return t
        if len(t) > 1 and not re.fullmatch(r"(these|those|selected.*)", i.params["target"]):
            return self._choose("Delete which one:", t[:4], lambda p: p.name,
                                lambda p: self.h_file__delete(Intent(i.name, {**i.params, "target": str(p)})))
        home = Path.home().resolve()
        for p in t:
            rp = p.resolve()
            if rp == home or home not in rp.parents or rp in [files.known_folder(n) for n in ("desktop", "documents", "downloads", "pictures")]:
                return Result(Outcome.NOT_SUPPORTED, f"I won't delete {p}. It's a protected or system location.")
        names = t[0].name if len(t) == 1 else f"{len(t)} items"
        kind = "folder" if t[0].is_dir() else "file"
        if i.params.get("permanent"):
            return confirm(f"This will permanently delete {names}. It can't be recovered. Should I continue?",
                           lambda: done(f"Permanently deleted {names}.") if files.delete_permanently(t) else failed("Delete failed."))
        return confirm(f"This will move the {kind} {names} to the Recycle Bin. Should I continue?",
                       lambda: done(f"Moved {names} to the Recycle Bin.") if files.recycle(t) else failed("Windows couldn't delete it; it may be open in another app."))

    def h_file__empty_recycle_bin(self, i):
        return confirm("Empty the Recycle Bin? Everything in it will be gone for good.",
                       lambda: done("Recycle Bin emptied.") if files.empty_recycle_bin() else failed("Couldn't empty it."))

    def h_file__large(self, i):
        self.emit("state", {"state": "EXECUTING"})
        big = files.large_files()
        if not big:
            return info("I didn't find any files over 300 megabytes in your user folder.")
        self.ctx.last_files = [p for p, _ in big]
        self.emit("files", {"items": [str(p) for p, _ in big]})
        lines = "; ".join(f"{p.name} {files.human_size(s)}" for p, s in big[:5])
        return info(f"Largest files: {lines}.", spoken=f"The largest is {big[0][0].stem}, at {files.human_size(big[0][1])}. I've listed the rest on screen.")

    # ================================================================ development
    def _project(self, ref: str | None, allow_context: bool = True) -> dev.Project | Result:
        if ref:
            hits = dev.match_projects(ref)
            if len(hits) == 1:
                self.ctx.last_project = hits[0]
                return hits[0]
            if len(hits) > 1:
                return hits      # caller asks
            return failed(f"I couldn't find a project called {ref}.")
        if allow_context and self.ctx.last_project:
            return self.ctx.last_project
        # The project open in the foreground editor, if any
        w = apps.active_window()
        if w:
            for p in dev.projects():
                if p.name.lower() in w.title.lower():
                    self.ctx.last_project = p
                    return p
        return failed("Which project? Say, for example, check git status in my Freakyyy project.")

    def _with_project(self, ref, act: Callable[[dev.Project], Result]) -> Result:
        p = self._project(ref)
        if isinstance(p, list):
            return self._choose("Which project:", p, lambda x: x.spoken, lambda x: (setattr(self.ctx, "last_project", x), act(x))[1])
        if isinstance(p, Result):
            return p
        return act(p)

    def h_dev__open_project(self, i: Intent) -> Result:
        ref, ide = i.params.get("project"), i.params.get("ide")
        if not ide and self.ctx.last_app and re.search(r"android studio|code|visual studio", self.ctx.last_app.lower()):
            ide = "android studio" if "android" in self.ctx.last_app.lower() else \
                "visual studio" if self.ctx.last_app.lower().startswith("visual studio 2") else "vscode"
        if not ref:
            if not self.ctx.last_project:
                return failed("Which project should I open?")
            return self._open_project(self.ctx.last_project, ide)
        hits = dev.match_projects(ref)
        if not hits:
            return failed(f"I couldn't find a project called {ref}. I look in your project folders, set in my settings.")
        if len(hits) == 1:
            return self._open_project(hits[0], ide)
        return self._choose("Which project:", hits, lambda p: p.spoken, lambda p: self._open_project(p, ide))

    def _open_project(self, p: dev.Project, ide: str | None) -> Result:
        self.ctx.chosen = p
        self.ctx.last_project = p
        ok, where = dev.open_in(p, ide)
        if not ok:
            return failed(where)
        return done(f"Opening {p.name} in {where}.", spoken=f"Loading {p.spoken.title()} in {where}.")

    def h_dev__list_projects(self, i):
        ps = dev.projects(refresh=True)
        if not ps:
            return info("I didn't find any projects in your project folders.")
        return info(f"{len(ps)} projects: " + ", ".join(p.name for p in ps[:15]) + ".",
                    spoken=f"I know {len(ps)} projects, including " + ", ".join(p.spoken for p in ps[:4]) + ".")

    def h_dev__terminal(self, i: Intent) -> Result:
        if i.params.get("here") and self.ctx.last_folder and not i.params.get("project"):
            dev.open_terminal(self.ctx.last_folder)
            return done(f"Terminal opened in {self.ctx.last_folder.name}.")
        def act(p):
            dev.open_terminal(p.path)
            return done(f"Terminal opened in {p.name}.")
        return self._with_project(i.params.get("project"), act)

    def h_dev__git_status(self, i: Intent) -> Result:
        def act(p):
            msg, data = dev.git_status(p)
            if data.get("files"):
                self.emit("files", {"items": data["files"], "title": f"Changes in {p.name}"})
            return info(msg)
        return self._with_project(i.params.get("project"), act)

    def h_dev__git_commit(self, i: Intent) -> Result:
        def act(p):
            summary, data = dev.git_status(p)
            if not data or not (data.get("modified") or data.get("untracked")):
                return info(f"There's nothing to commit in {p.name}.")
            message = i.params.get("message") or self._commit_message(p, data)
            n = data["modified"] + data["untracked"]
            return confirm(f"Commit {n} changed file{'s' if n != 1 else ''} in {p.name} on {data['branch']} "
                           f"with the message: {message}. Should I continue?",
                           lambda: (lambda ok_msg: done(ok_msg[1]) if ok_msg[0] else failed(ok_msg[1]))(dev.git_commit(p, message)))
        return self._with_project(i.params.get("project"), act)

    def _commit_message(self, p: dev.Project, data: dict) -> str:
        files_changed = data.get("files", [])
        if self.brain and self.brain.available():
            try:
                diff = dev._git(p.path, "diff", "--stat").stdout[-3000:]
                text = self.brain.ask("Write one concise git commit message (imperative, max 60 characters, no quotes) "
                                      f"for these changes:\n{diff}\nFiles: {files_changed}")
                return text.strip().strip('"').splitlines()[0][:72]
            except Exception:
                pass
        stems = sorted({Path(f.split(" -> ")[-1]).stem for f in files_changed})[:3]
        return "Update " + ", ".join(stems) if stems else "Update project files"

    def h_dev__git_push(self, i):
        def act(p):
            return confirm(f"Push {p.name} to its remote?",
                           lambda: (lambda r: done(f"Pushed {p.name}.") if r[0] else failed(f"Push failed: {r[1][-200:]}"))(dev.git_simple(p, "push")))
        return self._with_project(None, act)

    def h_dev__git_pull(self, i):
        def act(p):
            ok, out = dev.git_simple(p, "pull", "--ff-only")
            return done(f"Pulled the latest changes into {p.name}.") if ok else failed(f"Pull failed: {out[-200:]}")
        return self._with_project(None, act)

    def _build_done(self, rec: dev.BuildRecord) -> None:
        secs = int((rec.finished or time.time()) - rec.started)
        took = f"{secs // 60} minutes {secs % 60} seconds" if secs >= 60 else f"{secs} seconds"
        if rec.ok:
            msg = f"The {rec.project} build succeeded in {took}."
            outcome = "COMPLETED"
        else:
            first = rec.errors[0] if rec.errors else "see the log"
            msg = f"The {rec.project} build failed after {took}. First error: {first}"
            outcome = "FAILED"
        self.emit("activity", self.history.add(f"build {rec.project}", "DEV · gradle_build", outcome, msg, "background"))
        self.emit("reply", {"text": msg, "outcome": outcome})
        self._say(msg if rec.ok else f"The {rec.project} build failed. Say show me the latest build errors for details.")
        if not rec.ok:
            self.emit("files", {"items": rec.errors, "title": f"{rec.project} build errors"})

    def h_dev__gradle_build(self, i: Intent) -> Result:
        def act(p):
            rec = dev.gradle_build(p, self._build_done)
            if not rec:
                return failed(f"{p.name} has no Gradle wrapper.")
            return Result(Outcome.OPENED, f"Started the Gradle build for {p.name}. I'll tell you when it finishes.",
                          spoken=f"Building {p.spoken}. I'll let you know when it's done.")
        return self._with_project(i.params.get("project"), act)

    def h_dev__build_status(self, i):
        rec = dev.last_build
        if not rec:
            return info("I haven't run a build in this session. Say build my project to start one.")
        if rec.ok is None:
            return info(f"The {rec.project} build is still running, {int(time.time() - rec.started)} seconds so far.")
        return info(f"The last {rec.project} build {'succeeded' if rec.ok else 'failed'}.")

    def h_dev__build_errors(self, i):
        rec = dev.last_build
        if not rec or rec.ok is None:
            return info("There's no finished build to report on.")
        if rec.ok:
            return info(f"The last {rec.project} build had no errors.")
        self.emit("files", {"items": rec.errors, "title": f"{rec.project} build errors"})
        import os
        if rec.log_path and rec.log_path.exists():
            os.startfile(rec.log_path)
        errs = rec.errors[:3]
        return info("Build errors: " + " | ".join(errs), spoken=f"The first error is: {errs[0][:160]}. I've opened the full log." if errs else "I've opened the build log.")

    def h_dev__npm_install(self, i):
        def act(p):
            def finished(rec):
                msg = f"npm install in {p.name} {'finished' if rec.ok else 'failed: ' + (rec.errors[0] if rec.errors else '')}."
                self.emit("activity", self.history.add("npm install", "DEV · npm_install", "COMPLETED" if rec.ok else "FAILED", msg, "background"))
                self._say(msg)
            if not dev.npm(p, ["install"], finished):
                return failed(f"{p.name} has no package.json.")
            return Result(Outcome.OPENED, f"Running npm install in {p.name}. I'll tell you when it's done.")
        return self._with_project(i.params.get("project"), act)

    def h_dev__server_start(self, i):
        def act(p):
            ok, msg = dev.start_dev_server(p)
            return done(msg) if ok else failed(msg)
        return self._with_project(i.params.get("project"), act)

    def h_dev__server_stop(self, i):
        stopped = dev.stop_dev_servers()
        return done("Stopped the dev server for " + ", ".join(stopped) + ".") if stopped else info("No dev server is running.")

    def h_dev__run_python(self, i: Intent) -> Result:
        def act(p):
            cmd = dev.python_entry(p)
            if not cmd:
                return failed(f"I couldn't find an entry point like main.py in {p.name}.")
            shown = " ".join(Path(c).name if n == 0 else c for n, c in enumerate(cmd))
            return confirm(f"Run {shown} in {p.name}? It opens in a terminal so you can see the output.",
                           lambda: (dev.open_terminal(p.path, cmd), done(f"Running {shown} in {p.name}."))[1])
        return self._with_project(i.params.get("project"), act)

    # ================================================================ browser
    def h_web__open_site(self, i):
        url = browser.SITES.get(i.params["site"].replace(" ", "")) or browser.SITES.get(i.params["site"])
        browser.open_url(url)
        return done(f"Opening {i.params['site'].title()}.")

    def h_web__open_url(self, i):
        browser.open_url(i.params["url"])
        return done(f"Opening {i.params['url']}.")

    def h_web__search(self, i):
        browser.search(i.params["query"], i.params.get("engine", "google"))
        where = "YouTube" if i.params.get("engine") == "youtube" else "the web"
        return done(f"Searching {where} for {i.params['query']}.")

    def h_web__lucky(self, i):
        try:
            results = browser.web_results(i.params["query"])
        except Exception:
            results = []
        if not results:
            browser.search(i.params["query"])
            return done(f"Searching for {i.params['query']}.")
        title, url = results[0]
        browser.open_url(url)
        return done(f"Opening {title}.", spoken=f"Opening {title[:80]}.")

    def h_web__open_result(self, i):
        try:
            r = browser.open_result(i.params["index"])
        except Exception as e:
            return failed(f"I couldn't load the search results: {e}")
        if not r:
            return failed("Search for something first, then ask me to open a result.")
        return done(f"Opening {r[0]}.", spoken=f"Opening {r[0][:80]}.")

    def h_web__open_repo(self, i):
        p = self.ctx.last_project
        if p:
            url = dev.remote_url(p)
            if url:
                browser.open_url(url)
                return done(f"Opening the {p.name} repository.")
        browser.open_url("https://github.com")
        return done("Opening GitHub." + (" That project has no remote." if p else ""))

    def _browser_key(self, label: str, *vks: int) -> Result:
        return done(label) if browser.keys_to_browser(*vks) else failed("I don't see a browser window.")

    def h_web__scroll(self, i):
        return self._browser_key("Scrolled.", system.VK_NEXT if i.params["down"] else system.VK_PRIOR)

    def h_web__back(self, i): return self._browser_key("Going back.", system.VK_MENU, system.VK_LEFT)
    def h_web__forward(self, i): return self._browser_key("Going forward.", system.VK_MENU, system.VK_RIGHT)
    def h_web__refresh(self, i): return self._browser_key("Refreshed.", system.VK_F5)
    def h_web__close_tab(self, i): return self._browser_key("Tab closed.", system.VK_CONTROL, ord("W"))
    def h_web__new_tab(self, i): return self._browser_key("New tab.", system.VK_CONTROL, ord("T"))

    def h_web__bookmark(self, i):
        if not browser.keys_to_browser(system.VK_CONTROL, ord("D")):
            return failed("I don't see a browser window.")
        time.sleep(0.6)
        system.send_keys(system.VK_RETURN)
        return done("Bookmarked this page.", spoken="Bookmarked.")

    def h_web__read_page(self, i: Intent) -> Result:
        url = browser.current_url()
        if not url:
            return failed("I can't see a page in Chrome, Edge or Firefox right now.")
        try:
            title, text, _ = browser.fetch_text(url)
        except Exception as e:
            return failed(f"I couldn't load that page: {e}")
        if not text:
            return info(f"That page is {title or url}, and it has no readable text for me (it may need you to be signed in).")
        if self.brain and self.brain.available():
            self.emit("state", {"state": "THINKING"})
            ask = "Summarize this page in two or three spoken sentences." if i.params.get("summarize") else \
                "Read me the main content of this page as a short spoken digest."
            reply = self.brain.ask(f"{ask}\nURL: {url}\nTitle: {title}\n\n{text[:20000]}")
            return info(reply)
        first = re.split(r"(?<=[.!?])\s+", text)
        excerpt = " ".join(first[:4])[:600]
        return info(f"{title}. {excerpt}", spoken=f"{title}. {excerpt}")

    def h_web__download_pdf(self, i):
        url = browser.current_url()
        if not url:
            return failed("I don't see a page open in your browser.")
        try:
            _, _, ctype = browser.fetch_text(url, limit=10)
            links = [url] if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf") else browser.pdf_links(url)
        except Exception as e:
            return failed(f"I couldn't read that page: {e}")
        if not links:
            return info("I don't see a PDF on this page.")

        def get(link):
            try:
                path = browser.download(link, files.known_folder("downloads"))
                self.ctx.last_files = [path]
                return done(f"Downloaded {path.name} to Downloads.")
            except Exception as e:
                return failed(f"The download failed: {e}")
        if len(links) == 1:
            return get(links[0])
        return self._choose(f"This page links {len(links)} PDFs:", links[:4],
                            lambda l: Path(l.split("?")[0]).stem[:40], get)

    # ================================================================ email
    def _mail_missing(self) -> Result:
        self.emit("open_settings", {"tab": "email"})
        return Result(Outcome.NEEDS_PERMISSION, "Email isn't connected yet. In Freakyyy settings, Email tab, add your address "
                                                "and an app password. I only read mail; I never send or delete.",
                      spoken="Your email isn't connected yet. I've opened settings so you can add it.")

    def h_mail__check(self, i: Intent) -> Result:
        from ..ai import email_client
        if not email_client.configured():
            return self._mail_missing()
        if self.brain and self.brain.available():
            self.emit("state", {"state": "THINKING"})
            return info(self.brain.ask("Check my inbox for new emails from the last two days and tell me which ones matter, "
                                       "briefly. " + ("Focus on important ones." if i.params.get("important") else "")))
        try:
            with email_client.MailClient() as mc:
                mails = mc.recent(days=2, unread_only=True, important_only=bool(i.params.get("important")))
        except Exception as e:
            return failed(f"I couldn't reach your mailbox: {e}")
        self.emit("files", {"items": [f"{m.sender} — {m.subject}" for m in mails], "title": "Inbox"})
        return info(email_client.spoken_summary(mails, "important unread" if i.params.get("important") else "new"))

    def h_mail__latest(self, i):
        from ..ai import email_client
        if not email_client.configured():
            return self._mail_missing()
        try:
            with email_client.MailClient() as mc:
                mails = mc.recent(days=7, unread_only=False, limit=1)
        except Exception as e:
            return failed(f"I couldn't reach your mailbox: {e}")
        if not mails:
            return info("Your inbox has nothing from the last week.")
        m = mails[0]
        return info(f"Latest email: from {m.sender}, {m.subject}. {m.snippet}", spoken=f"Your latest email is from {m.sender}, about {m.subject}.")

    def h_mail__search(self, i):
        from ..ai import email_client
        if not email_client.configured():
            return self._mail_missing()
        q = i.params["query"]
        if self.brain and self.brain.available():
            self.emit("state", {"state": "THINKING"})
            return info(self.brain.ask(f"Search my email about {q} and tell me what's important or the latest status."))
        try:
            with email_client.MailClient() as mc:
                mails = mc.search(q)
        except Exception as e:
            return failed(f"I couldn't search your mailbox: {e}")
        self.emit("files", {"items": [f"{m.date} · {m.sender} — {m.subject}" for m in mails], "title": f"Mail: {q}"})
        if not mails:
            return info(f"No emails about {q} in the last four months.")
        m = mails[0]
        return info(f"{len(mails)} emails about {q}. Latest: {m.sender}, {m.subject}, {m.date}.",
                    spoken=f"I found {len(mails)} emails about {q}. The latest is from {m.sender}: {m.subject}.")

    # ================================================================ memory
    def h_memory__add(self, i: Intent) -> Result:
        # Prefer the original wording (capitals, names) over the normalised text.
        raw = self.ctx.last_text or ""
        m = parser._MEM_ADD.search(raw) if parser.normalize(raw) == i.text else None
        fact = (m.group("x") if m else i.params["text"]).strip(" .")
        if _SENSITIVE.search(fact):
            return failed("I won't keep passwords, PINs, codes or card and bank numbers in memory. "
                          "A password manager is the safe place for those.",
                          spoken="I'd rather not store passwords or codes. A password manager is safer for those.")
        f = memory_mod.get().add(fact)
        self.emit("memory", {})
        return done(f"Remembered: {f.text}", spoken="Got it. I'll remember that.")

    def h_memory__list(self, i: Intent) -> Result:
        facts = memory_mod.get().facts()
        if not facts:
            return info("I haven't saved anything about you yet. Say “remember that …” to teach me.",
                        spoken="I haven't saved anything about you yet. Just say remember that, and tell me.")
        shown = facts[:8]
        more = f" And {len(facts) - 8} more in settings." if len(facts) > 8 else ""
        return info("I remember: " + " ".join(f.text for f in shown) + more,
                    spoken="Here's what I remember. " + " ".join(f.text for f in shown[:5]) +
                           (f" Plus {len(facts) - 5} more in settings." if len(facts) > 5 else ""))

    def h_memory__recall(self, i: Intent) -> Result:
        q = i.params["query"]
        if self.brain and self.brain.available():
            return self.h_ai__ask(Intent("ai.ask", {"text": self.ctx.last_text or f"What do you remember about {q}?"}))
        facts = memory_mod.get().find_facts(q, 5)
        if not facts:
            return info(f"I don't have anything saved about {q}.")
        return info(" ".join(f.text for f in facts))

    def h_memory__forget(self, i: Intent) -> Result:
        q = i.params["query"]
        mem = memory_mod.get()
        hits = mem.matching_facts(q) or mem.find_facts(q, 3)
        if not hits:
            return info(f"I don't have anything saved about {q}.")

        def go() -> Result:
            for f in hits:
                mem.delete(f.id)
            self.emit("memory", {})
            return done(f"Forgot {len(hits)} saved item{'s' if len(hits) > 1 else ''}.", spoken="Done. I've forgotten that.")
        if len(hits) == 1:
            return go()
        return confirm(f"I have {len(hits)} saved items about {q}: " + " ".join(f.text for f in hits) +
                       " Should I forget all of them?", go)

    def h_memory__forget_all(self, i: Intent) -> Result:
        mem = memory_mod.get()
        n = len(mem.facts())

        def go() -> Result:
            mem.clear_all()
            self.emit("memory", {})
            return done("Memory cleared: saved facts and conversation history are deleted.",
                        spoken="Done. I've cleared my memory.")
        return confirm(f"This permanently deletes all {n} saved facts and my conversation history. Should I continue?", go)

    # ================================================================ AI
    def h_ai__ask(self, i: Intent) -> Result:
        text = i.params.get("text") or self.ctx.last_text
        if not (self.brain and self.brain.available()):
            why = self.brain.unavailable_reason() if self.brain else "no AI is set up"
            if why == "Ollama is starting":
                return Result(Outcome.UNKNOWN, "The local AI is still starting. Ask me again in a few seconds.",
                              spoken="My AI is still waking up. Ask me again in a few seconds.")
            return Result(Outcome.UNKNOWN, f"I don't have a command for “{text}” yet ({why}). Say “help” to hear what I can do.",
                          spoken="Sorry, I don't know how to do that yet.")
        self.emit("state", {"state": "THINKING"})
        phone = self.link.phone() if self.link else None
        note = f"phone {'connected' if phone and phone.online else 'not connected'}"
        if self.ctx.last_project:
            note += f"; current project {self.ctx.last_project.name}"
        reply = self.brain.ask(text, note, log_turn=True)
        return info(reply)

    def ai_tool(self, name: str, args: dict) -> str:
        from ..ai import brain as brain_mod, email_client
        if name == "freakyyy_command":
            device = args.get("device", "laptop")
            text = args["text"]
            if device == "phone":
                r = self._remote(text)
            else:
                intent = parser.parse(text)
                if intent.name == "ai.ask":
                    return "UNKNOWN_COMMAND: Freakyyy has no automation for that; answer the user directly instead."
                intent.device = Device.BOTH if device == "both" else Device.LAPTOP
                r = self.execute(intent)
            if r.outcome == Outcome.NEEDS_CONFIRMATION and r.confirm:
                self.ctx.pending, self.ctx.pending_at = r, time.time()
                return f"NEEDS_CONFIRMATION (not done yet). Ask the user: {r.message}"
            if r.outcome == Outcome.CLARIFY and r.clarify:
                self.ctx.clarification = r.clarify
                return f"CLARIFY: ask the user: {r.message}"
            self.emit("activity", self.history.add(text, f"AI · {device}", r.outcome.value, r.message, "ai"))
            return f"{r.outcome.value}: {r.message}"
        if name in ("email_recent", "email_search", "email_read"):
            if not email_client.configured():
                return "Email is not connected. Tell the user to add their email and app password in Freakyyy settings."
            with email_client.MailClient() as mc:
                if name == "email_recent":
                    data = [m.as_dict() for m in mc.recent(min(max(args["days"], 1), 30), args["unread_only"], args["important_only"], limit=15)]
                elif name == "email_search":
                    data = [m.as_dict() for m in mc.search(args["query"], min(max(args["days"], 1), 365), limit=15)]
                else:
                    data = mc.read(args["uid"])
            return brain_mod.as_json(data)
        if name == "current_browser_page":
            url = browser.current_url()
            if not url:
                return "No browser page is open."
            title, text, _ = browser.fetch_text(url)
            return brain_mod.as_json({"url": url, "title": title, "text": text[:20000]})
        if name == "file_search":
            hits = files.search(args["query"], limit=15)
            return brain_mod.as_json([{"path": str(h), "modified": time.strftime("%Y-%m-%d", time.localtime(h.stat().st_mtime))} for h in hits if h.exists()])
        if name == "read_text_file":
            return brain_mod.read_text_file(args["path"])
        if name == "remember":
            fact = (args.get("fact") or "").strip()
            if not fact:
                return "Nothing to remember."
            if _SENSITIVE.search(fact):
                return "Refused: Freakyyy doesn't store passwords, PINs, codes or card and bank numbers in memory."
            f = memory_mod.get().add(fact, source="ai")
            self.emit("memory", {})
            return f"Saved to memory: {f.text}"
        if name == "recall":
            mem = memory_mod.get()
            facts = mem.find_facts(args.get("query", ""), 10)
            msgs = mem.find_messages(args.get("query", ""), 8)
            if not (facts or msgs):
                return "Nothing in memory about that."
            return brain_mod.as_json({
                "facts": [f"{f.text} (saved {f.when()})" for f in facts],
                "past_messages": [f"{time.strftime('%d %b %Y', time.localtime(ts))} {role}: {t[:400]}" for ts, role, t in msgs],
            })
        if name == "web_search":
            hits = browser.web_results(args.get("query", ""))
            return brain_mod.as_json([{"title": t, "url": u} for t, u in hits[:8]]) if hits else "No results."
        if name == "web_fetch":
            url = args.get("url", "")
            if not url.startswith(("http://", "https://")):
                return "Only http and https pages can be fetched."
            title, text, ctype = browser.fetch_text(url, 8000)
            return brain_mod.as_json({"title": title, "text": text or f"(no text: {ctype})"})
        if name in _UI_TOOLS:
            if not settings.get("ui_control_enabled", True):
                return "Refused: screen control is switched off in Freakyyy's settings."
            return self._ui_tool(name, args)
        if name == "device_status":
            phone = self.link.phone() if self.link else None
            return brain_mod.as_json({"laptop": system.status_snapshot(),
                                      "phone": phone.public() if phone else "not paired"})
        return f"Unknown tool {name}"

    def _ui_tool(self, name: str, args: dict) -> str:
        """Screen reading and clicking. Irreversible clicks become a question for the user."""
        from ..ai import brain as brain_mod
        if name == "screen_read":
            snap = ui_control.snapshot(args.get("window") or None, args.get("find") or "")
            return brain_mod.as_json(snap)
        if name == "screen_text":
            return brain_mod.as_json(ui_control.window_text(args.get("window") or None))
        if name == "focus_window":
            title = args.get("title", "")
            return f"Brought {title} to the front." if ui_control.focus_window(title) else f"I couldn't find a window for {title}."
        if name == "wait_seconds":
            time.sleep(max(1, min(int(args.get("seconds") or 2), 10)))
            return "Waited."
        if name == "ui_scroll":
            return ui_control.scroll(args.get("direction", "down"), int(args.get("amount") or 3))
        if name == "ui_type":
            text, ref = args.get("text", ""), args.get("ref") or None
            if _SENSITIVE.search(text):
                return ("Refused: that looks like a password, code or card number. Freakyyy never types those. "
                        "Tell the user to enter it themselves.")
            out = ui_control.type_text(ref, text, bool(args.get("clear_first")))
            if out.startswith("Typed"):
                self._ui_typed = True          # the next Enter would submit it
            return out
        if name == "ui_press":
            keys = args.get("keys", "")
            if self._ui_typed and re.search(r"\b(enter|return)\b", keys, re.I):
                self._ui_typed = False
                return self._ui_confirm("Press Enter to submit what I typed?", lambda: ui_control.press(keys))
            return ui_control.press(keys)
        if name == "ui_click":
            ref, how = args.get("ref", ""), args.get("how", "left")
            label = ui_control.describe(ref)
            double, right = how == "double", how == "right"
            if ui_control.is_risky(ref):
                self._ui_typed = False
                return self._ui_confirm(f"Should I click “{label}”?",
                                        lambda: ui_control.click(ref, double=double, right=right))
            return ui_control.click(ref, double=double, right=right)
        return f"Unknown tool {name}"

    def _ui_confirm(self, question: str, action: Callable[[], str]) -> str:
        """Hand the decision to the user; the click runs only when they say yes."""
        def go() -> Result:
            out = action()
            self.emit("activity", self.history.add(question, "AI · screen", "COMPLETED", out, "ai"))
            return done(out)
        self.ctx.pending, self.ctx.pending_at = Result(Outcome.NEEDS_CONFIRMATION, question, confirm=go), time.time()
        return f"NEEDS_CONFIRMATION (not done yet). Ask the user exactly this and stop: {question}"

    # ================================================================ routines
    def h_routine__run(self, i: Intent) -> Result:
        found = self.routines.find(i.params["name"])
        if i.device == Device.PHONE:
            return self._remote(f"start my {i.params['name']} routine")
        if not found:
            if i.device == Device.BOTH:
                return self._remote(f"start my {i.params['name']} routine")
            return failed(f"I don't have a routine called {i.params['name']}. You can create one in settings.")
        name, steps = found
        return self._run_routine(name, steps, also_phone=i.device == Device.BOTH)

    def _run_routine(self, name: str, steps: list[dict], also_phone: bool) -> Result:
        self._routine_cancel.clear()
        self._say(f"Starting {name} mode.")
        results = []
        has_phone_steps = any(s.get("device") == "phone" for s in steps)
        for n, step in enumerate(steps, 1):
            if self._routine_cancel.is_set():
                results.append((step, Result(Outcome.FAILED, "cancelled")))
                break
            self.emit("routine", {"name": name, "step": n, "total": len(steps), "current": step["command"]})
            cmd = step["command"]
            m = re.fullmatch(r"wait (\d+)( seconds?)?", cmd)
            if m:
                time.sleep(min(int(m.group(1)), 120))
                continue
            if step.get("device") == "phone":
                r = self._remote(cmd)
            else:
                intent = parser.parse(cmd)
                if intent.name in ("routine.run", "ai.ask"):
                    r = failed("not a supported routine step")
                else:
                    r = self.execute(intent)
            if r.outcome == Outcome.NEEDS_CONFIRMATION:
                r = Result(Outcome.NEEDS_CONFIRMATION, "skipped — needs your confirmation")
            results.append((step, r))
            time.sleep(0.4)
        if also_phone and not has_phone_steps:
            results.append(({"device": "phone", "command": f"{name} routine"}, self._remote(f"start my {name} routine")))
        self.emit("routine", {})
        ok = [s for s, r in results if r.outcome in (Outcome.COMPLETED, Outcome.INFO)]
        yours = [s for s, r in results if r.outcome in (Outcome.OPENED, Outcome.NEEDS_PERMISSION, Outcome.NEEDS_CONFIRMATION)]
        bad = [(s, r) for s, r in results if r.outcome in (Outcome.FAILED, Outcome.NOT_SUPPORTED, Outcome.DEVICE_OFFLINE)]
        detail = f"{name} mode: {len(ok)} of {len(results)} steps done."
        if yours:
            detail += " Needs you: " + ", ".join(f"{s['device']}: {s['command']}" for s in yours) + "."
        if bad:
            detail += " Failed: " + ", ".join(f"{s['device']}: {s['command']} ({r.message[:60]})" for s, r in bad) + "."
        spoken = f"{name} mode is on." if not bad and not yours else \
            f"{name} mode is set. {len(ok)} of {len(results)} steps done" + \
            (f"; your phone was offline" if any(r.outcome == Outcome.DEVICE_OFFLINE for _, r in bad) else "") + "."
        return Result(Outcome.COMPLETED if not bad else Outcome.FAILED, detail, spoken=spoken)

    # ================================================================ link / phone
    def h_remote__command(self, i: Intent) -> Result:
        return self._remote(i.params["text"])

    def h_link__pair(self, i):
        self.emit("pair", {})
        return opened("Showing the pairing code. Scan it with Freakyyy on your phone.")

    def h_link__status(self, i):
        if not self.link:
            return Result(Outcome.DEVICE_OFFLINE, "Freakyyy Link isn't running.")
        r = self.link.request("get_status", {})
        return self._from_remote(r)

    def h_link__ring(self, i):
        if not self.link:
            return Result(Outcome.DEVICE_OFFLINE, "Freakyyy Link isn't running.")
        return self._from_remote(self.link.request("ring", {"seconds": 20}))

    def h_link__send_page(self, i):
        url = browser.current_url()
        if not url:
            return failed("I don't see a page open in your browser.")
        return self._from_remote(self.link.request("open_url", {"url": url}))

    def h_link__clipboard_push(self, i):
        text = system.clipboard_get()
        if not text.strip():
            return info("Your clipboard has no text to send.")
        looks_secret = len(text) < 80 and " " not in text.strip() and re.search(r"[A-Z]", text) and re.search(r"\d", text) \
            and re.search(r"[^\w]", text)
        send = lambda: self._from_remote(self.link.request("clipboard_push", {"text": text[:100_000]}))
        if looks_secret:
            return confirm("Your clipboard looks like it might be a password. Send it to your phone anyway?", send)
        return send()

    def h_link__clipboard_pull(self, i):
        r = self.link.request("clipboard_pull", {})
        text = (r.get("data") or {}).get("text")
        if r.get("outcome") == "COMPLETED" and text is not None:
            system.clipboard_set(text)
            return done("Copied your phone's clipboard to the laptop.", spoken=f"Got it. Your phone's clipboard says: {text[:120]}")
        return self._from_remote(r)

    def h_link__send_file(self, i: Intent) -> Result:
        if not self.link or not self.link.phone() or not self.link.phone().online:
            return Result(Outcome.DEVICE_OFFLINE, "Your phone isn't connected. Open Freakyyy on it, on the same Wi-Fi.")
        name = i.params.get("name") or "this"
        t = self._resolve_target(name if name else "this")
        if isinstance(t, Result):
            return t
        if len(t) > 1 and not re.fullmatch(r"(this|that|it|selected.*)", name):
            return self._choose("Send which file:", t[:4], lambda p: p.name, self._send_file)
        return self._send_file(t[0])

    def _send_file(self, p: Path) -> Result:
        if p.is_dir():
            return Result(Outcome.NOT_SUPPORTED, "I can send files, not whole folders. Zip it first.")
        size = files.human_size(p.stat().st_size)

        def work():
            r = self.link.send_file(p)
            res = self._from_remote(r)
            self.emit("activity", self.history.add(f"send {p.name}", "LINK · send_file", res.outcome.value, res.message, "background"))
            self.emit("reply", {"text": res.message, "outcome": res.outcome.value})
            self._say(res.speech)
        threading.Thread(target=work, daemon=True, name="send-file").start()
        return Result(Outcome.OPENED, f"Sending {p.name} ({size}) to your phone…", spoken=f"Sending {p.stem} to your phone.")
