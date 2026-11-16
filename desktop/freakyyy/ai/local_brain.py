"""Free, offline AI for Freakyyy through Ollama (http://127.0.0.1:11434).

Same job and the same tools as the Claude brain, so device actions still go
through Freakyyy's own engine (permissions and confirmations unchanged). Web
search uses DuckDuckGo's HTML results instead of a paid search API.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests

from ..config import settings
from . import brain as claude_brain

log = logging.getLogger(__name__)

HOST = "http://127.0.0.1:11434"

SYSTEM = claude_brain.SYSTEM + """
- Web search: call web_search, then web_fetch on the most useful result if the snippets aren't enough.
- Memory: Freakyyy saves lasting facts the user shares automatically, so don't claim you noted or saved anything. \
Each message may start with a [Context] block holding the time and memory notes about the user; use them naturally \
and call recall for older details. Never mention the [Context] block itself.
- If you don't know something and no tool can find it, say so plainly instead of guessing.
- Reply in plain spoken English only."""

# A 4B model sometimes answers "I can't see your screen" even with the tools in front of it.
_REFUSAL = re.compile(r"\b(can'?t|cannot|can not|unable to|don'?t have (the )?(access|ability)|no access|"
                      r"not able to)\b.{0,60}\b(see|view|read|access|interact|control|click|type|open|window|"
                      r"screen|browser|page)\b", re.I | re.S)
NUDGE = ("You can see and control this computer. Call screen_read now (window empty for the active window) to list "
         "the controls, then act on the refs it returns with ui_click and ui_type. Do not say you cannot see it.")

EXTRA_TOOLS = [
    {"name": "web_search", "description": "Search the web. Returns result titles and URLs.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "web_fetch", "description": "Get the readable text of a web page by URL.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
]


def _tool_specs() -> list[dict]:
    specs = []
    for t in claude_brain.TOOLS:
        # Server tools are replaced below; memory is automatic; current_browser_page is dropped because a small
        # model reaches for it when it actually needs screen_read (screen_text reads the open page just as well).
        if "input_schema" not in t or t["name"] in ("remember", "current_browser_page"):
            continue
        schema = {k: v for k, v in t["input_schema"].items() if k != "additionalProperties"}
        specs.append({"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": schema}})
    for t in EXTRA_TOOLS:
        specs.append({"type": "function", "function": t})
    return specs


def ollama_exe() -> str | None:
    for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
              Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Ollama" / "ollama.exe"):
        if p.exists():
            return str(p)
    return None


class LocalBrain:
    def __init__(self, tool_runner: Callable[[str, dict], str]) -> None:
        self.run_tool = tool_runner
        self.messages: list[dict] = []
        self.last_used = 0.0
        self._status = (0.0, False, "")          # (checked at, ok, reason)
        self._started = False
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- status
    @property
    def model(self) -> str:
        return settings.get("local_model") or "qwen3:4b"

    def status(self, max_age: float = 15) -> tuple[bool, str]:
        """(ready, reason). Cached; starts Ollama in the background if it's installed but not running."""
        checked, ok, why = self._status
        if time.time() - checked < max_age:
            return ok, why
        try:
            tags = requests.get(HOST + "/api/tags", timeout=0.6).json()
            names = {m["name"] for m in tags.get("models", [])}
            want = self.model if ":" in self.model else self.model + ":latest"
            ok, why = (want in names), ("" if want in names else f"model {self.model} isn't downloaded")
        except (requests.RequestException, ValueError):
            exe = ollama_exe()
            ok, why = False, ("Ollama isn't installed" if not exe else "Ollama is starting")
            if exe and not self._started:
                self._started = True
                subprocess.Popen([exe, "serve"], creationflags=subprocess.CREATE_NO_WINDOW,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._status = (time.time(), ok, why)
        return ok, why

    def available(self) -> bool:
        return bool(settings.get("ai_enabled")) and self.status()[0]

    def reset(self) -> None:
        self.messages = []
        self._status = (0.0, False, "")

    def _options(self) -> dict:
        # Low temperature: a 4B model picks its tools far more consistently, and these replies are
        # instructions to a computer rather than creative writing.
        return {"num_ctx": int(settings.get("local_num_ctx") or 8192),
                "temperature": float(settings.get("local_temperature") or 0.15)}

    def warm_up(self) -> None:
        """Load the model and pre-read the fixed instructions + tools, so later questions start fast."""
        def run():
            for _ in range(20):                  # Ollama may still be starting at login
                if self.status(0)[0]:
                    break
                time.sleep(3)
            else:
                return
            try:
                requests.post(HOST + "/api/chat", timeout=300, json={
                    "model": self.model, "stream": False, "think": False, "keep_alive": "30m",
                    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hi"}],
                    "tools": _tool_specs(), "options": {**self._options(), "num_predict": 1}})
                log.info("local AI warmed up")
            except requests.RequestException:
                pass
        threading.Thread(target=run, daemon=True, name="ai-warmup").start()

    def extract_facts(self, user_text: str, reply: str) -> list[str]:
        """Lasting personal facts in the user's message (runs in the background after replying)."""
        if not re.search(r"\b(i|i'm|im|i've|my|me|mine|we|our)\b", user_text.lower()) or len(user_text) < 12:
            return []
        prompt = ("Extract lasting facts about the user from their message: name, studies, work, job or internship "
                  "applications, people in their life, preferences, plans and important dates. Ignore requests, "
                  "questions, small talk and anything temporary. Never include passwords, codes or account numbers. "
                  "Write each fact as one short sentence starting with 'The user' and include dates if given. "
                  'Answer only JSON: {"facts": [...]} (empty list if none).\n\n'
                  f"Today: {datetime.now():%d %B %Y}\nUser message: {user_text}")
        with self._lock:
            try:
                r = requests.post(HOST + "/api/chat", timeout=180, json={
                    "model": self.model, "stream": False, "think": False, "keep_alive": "30m", "format": "json",
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {**self._options(), "temperature": 0}})
                facts = json.loads(r.json()["message"]["content"]).get("facts", [])
            except (requests.RequestException, ValueError, KeyError, AttributeError):
                return []
        return [f.strip() for f in facts if isinstance(f, str) and 8 < len(f.strip()) < 300][:5]

    # ---------------------------------------------------------------- chat
    def ask(self, text: str, context_note: str = "", memory: str = "") -> str:
        with self._lock:
            return self._ask(text, context_note, memory)

    def _ask(self, text: str, context_note: str, memory: str) -> str:
        if time.time() - self.last_used > 1200 or len(self.messages) > 30:
            self.messages = []
        self.last_used = time.time()
        start_len = len(self.messages)
        # The system prompt and tools never change, so Ollama reuses its cache of them; the time and memory go
        # into the newest user message only (older turns are sent as plain text).
        stamp = datetime.now().strftime("%A %d %B %Y, %I:%M %p")
        ctx = f"[Context] Now: {stamp}{'; ' + context_note if context_note else ''}."
        if memory:
            ctx += "\n" + memory
        self.messages.append({"role": "user", "content": text})
        tools = _tool_specs()
        last_user = len(self.messages) - 1
        nudged = False
        try:
            for _ in range(8):
                r = requests.post(HOST + "/api/chat", timeout=240, json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": SYSTEM}] + self.messages[:last_user] +
                                [{"role": "user", "content": f"{ctx}\n[/Context]\n\n{text}"}] + self.messages[last_user + 1:],
                    "tools": tools,
                    "stream": False,
                    "think": False,
                    "keep_alive": "30m",
                    "options": self._options(),
                })
                if r.status_code >= 400:
                    raise RuntimeError(r.json().get("error", r.text)[:200])
                msg = r.json().get("message", {})
                calls = msg.get("tool_calls") or []
                self.messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
                if not calls:
                    reply = _clean(msg.get("content", "")) or "Done."
                    # A small model sometimes claims it can't see the screen instead of looking. Nudge it once.
                    if not nudged and _REFUSAL.search(reply):
                        nudged = True
                        self.messages.append({"role": "user", "content": NUDGE})
                        continue
                    return reply
                for c in calls:
                    fn = c.get("function", {})
                    name, args = fn.get("name", ""), fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    try:
                        out = self.run_tool(name, args)
                    except Exception as e:
                        log.exception("local tool %s", name)
                        out = f"Error: {e}"
                    self.messages.append({"role": "tool", "tool_name": name, "content": str(out)[:6000]})
            return "That took too many steps. Try asking in a simpler way."
        except requests.ConnectionError:
            del self.messages[start_len:]
            self._status = (0.0, False, "")
            return "The local AI isn't running. Give it a moment to start and try again."
        except requests.Timeout:
            del self.messages[start_len:]
            return "The local AI took too long to answer. Try a shorter question."
        except Exception as e:
            log.exception("local AI error")
            del self.messages[start_len:]
            return f"The local AI hit an error: {e}"


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"[*_#`]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()
