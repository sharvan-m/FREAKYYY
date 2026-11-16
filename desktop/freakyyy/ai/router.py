"""Chooses the AI provider and adds long-term memory to every request.

ai_provider setting:
  "auto"   - Claude when an Anthropic key is saved, otherwise the free local model
  "local"  - always the local Ollama model (free, offline)
  "claude" - always Claude (needs a key)
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from ..config import settings
from . import memory as memory_mod
from .brain import Brain
from .local_brain import LocalBrain

log = logging.getLogger(__name__)


class AIRouter:
    def __init__(self, tool_runner: Callable[[str, dict], str]) -> None:
        self.claude = Brain(tool_runner)
        self.local = LocalBrain(tool_runner)
        self.memory = memory_mod.get()

    def _pick(self):
        if not settings.get("ai_enabled"):
            return None
        mode = settings.get("ai_provider") or "auto"
        if mode in ("auto", "claude") and Brain.available():
            return self.claude
        if mode in ("auto", "local") and self.local.available():
            return self.local
        return None

    def available(self) -> bool:
        return self._pick() is not None

    def label(self) -> str:
        p = self._pick()
        if p is self.claude:
            return "AI · CLAUDE"
        if p is self.local:
            return "AI · LOCAL"
        return "AI · STARTING" if self.local.status()[1] == "Ollama is starting" else "AI · NOT SET UP"

    def unavailable_reason(self) -> str:
        if not settings.get("ai_enabled"):
            return "AI is turned off in settings"
        return self.local.status()[1] or "no AI is set up"

    def reset(self) -> None:
        self.claude.reset()
        self.local.reset()

    def warm_up(self) -> None:
        if (settings.get("ai_provider") or "auto") != "claude" and not Brain.available():
            self.local.warm_up()

    def _learn(self, text: str, reply: str) -> None:
        """Save lasting facts from what the user said (the local model rarely calls a tool for this itself)."""
        try:
            for fact in self.local.extract_facts(text, reply):
                if not memory_mod.SENSITIVE.search(fact):
                    self.memory.add(fact, source="ai")
                    log.info("learned: %s", fact)
        except Exception:
            log.exception("fact extraction")

    def ask(self, text: str, context_note: str = "", log_turn: bool = False) -> str:
        p = self._pick()
        if p is None:
            return "The AI isn't available right now."
        try:
            mem = self.memory.context_for(text)
        except Exception:
            log.exception("memory lookup")
            mem = ""
        reply = p.ask(text, context_note, mem)
        if log_turn and p is self.local:
            threading.Thread(target=self._learn, args=(text, reply), daemon=True, name="ai-learn").start()
        if log_turn and settings.get("memory_log_conversations", True):
            try:
                self.memory.log("user", text)
                self.memory.log("freakyyy", reply)
            except Exception:
                log.exception("memory log")
        return reply
