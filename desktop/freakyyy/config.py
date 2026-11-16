"""Paths, settings and secrets for Freakyyy Desktop."""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

APP_NAME = "Freakyyy"
APP_VERSION = "1.0.0"

# %APPDATA%\Freakyyy holds settings, history, routines and link keys.
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
_OLD_DATA_DIR = DATA_DIR.with_name("Dexter")          # the app's previous name
if not DATA_DIR.exists() and _OLD_DATA_DIR.is_dir():
    import shutil
    # Copy (not move): settings, memory, history, routines and link keys carry over; the old folder stays as a backup.
    shutil.copytree(_OLD_DATA_DIR, DATA_DIR, ignore=shutil.ignore_patterns("logs", "*.tmp"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def app_root() -> Path:
    """Folder containing the executable (frozen) or the desktop project."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    return app_root() / "models"


def resource(path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / path


DEFAULTS: dict[str, Any] = {
    "wake_word": "hey freaky",
    "wake_enabled": True,
    "wake_sensitivity": "normal",          # strict | normal | sensitive
    "mic_device": None,                     # sounddevice index or None = default
    "push_to_talk_hotkey": "ctrl+alt+d",
    "follow_up_seconds": 6,
    "listen_timeout_seconds": 7,
    "stt_model": "base.en",
    "voice_enabled": True,
    "voice_id": "am_onyx",
    "voice_speed": 1.08,
    "start_with_windows": False,
    "start_minimized": True,
    "ai_enabled": True,
    "ai_model": "claude-opus-5-5",
    "ai_effort": "low",                     # spoken replies favour speed
    "ai_provider": "auto",                  # auto | local | claude
    "local_model": "qwen3:4b-instruct-2507-q4_K_M",
    "local_num_ctx": 8192,
    "local_temperature": 0.15,              # steady tool use beats creative wording
    "memory_log_conversations": True,
    "ui_control_enabled": True,              # let the AI read the screen and click/type
    "email_address": "",
    "email_imap_host": "imap.gmail.com",
    "link_port": 47800,
    "link_allow_public_peers": False,
    "clipboard_accept_from_devices": True,
    "clipboard_share_to_devices": False,
    "receive_dir": str(Path.home() / "Downloads" / "Freakyyy"),
    "max_receive_mb": 2048,
    "project_roots": [
        str(Path.home() / "AndroidStudioProjects"),
        str(Path.home() / "source" / "repos"),
        str(Path.home() / "Projects"),
        str(Path.home() / "Documents"),
        str(Path.home() / "Desktop"),
        str(Path.home() / "PycharmProjects"),
        str(Path.home() / "IdeaProjects"),
    ],
    "theme": "dark",
    "island_enabled": True,
    "island_collapse_ms": 2500,
    "island_screen": None,
    "island_dx": 0,
    "island_dy": 4,
    "activation_sound": True,
}


class Settings:
    """JSON-backed settings with defaults; thread-safe."""

    def __init__(self, path: Path = DATA_DIR / "settings.json") -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = dict(DEFAULTS)
        if path.exists():
            try:
                # utf-8-sig: tolerate a BOM from editors / PowerShell 5 instead of discarding settings.
                self._data.update(json.loads(path.read_text(encoding="utf-8-sig")))
            except Exception:  # corrupt file: keep defaults, keep a copy
                logging.exception("Settings unreadable; using defaults")
                path.rename(path.with_suffix(".bad.json"))

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(self._path)

    def update(self, values: dict[str, Any]) -> None:
        for k, v in values.items():
            self.set(k, v)


# ---------------------------------------------------------------- secrets

_SERVICE = "Freakyyy"
_OLD_SERVICE = "Dexter"


def get_secret(name: str) -> str | None:
    try:
        import keyring
        value = keyring.get_password(_SERVICE, name)
        if value is None:
            value = keyring.get_password(_OLD_SERVICE, name)     # saved under the old name: carry it over
            if value is not None:
                keyring.set_password(_SERVICE, name, value)
        return value
    except Exception:
        logging.exception("Credential store unavailable")
        return None


def set_secret(name: str, value: str | None) -> None:
    import keyring
    if value:
        keyring.set_password(_SERVICE, name, value)
    else:
        try:
            keyring.delete_password(_SERVICE, name)
        except Exception:
            pass


def setup_logging() -> None:
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(LOG_DIR / "freakyyy.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


settings = Settings()
