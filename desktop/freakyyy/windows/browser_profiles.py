"""Browser profiles: list, match by spoken name, launch, and remember a default.

Chromium browsers (Brave, Chrome, Edge) keep profile names in "Local State";
Firefox keeps them in profiles.ini.
"""
from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
from pathlib import Path

LOCAL = Path(os.environ.get("LOCALAPPDATA", ""))
APPDATA = Path(os.environ.get("APPDATA", ""))
PF = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")), Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")), LOCAL]

BROWSERS = {
    "brave": ("Brave", LOCAL / "BraveSoftware" / "Brave-Browser" / "User Data", r"BraveSoftware\Brave-Browser\Application\brave.exe"),
    "chrome": ("Google Chrome", LOCAL / "Google" / "Chrome" / "User Data", r"Google\Chrome\Application\chrome.exe"),
    "edge": ("Microsoft Edge", LOCAL / "Microsoft" / "Edge" / "User Data", r"Microsoft\Edge\Application\msedge.exe"),
    "firefox": ("Firefox", APPDATA / "Mozilla" / "Firefox", r"Mozilla Firefox\firefox.exe"),
}

ALIASES = {"brave": "brave", "brave browser": "brave", "chrome": "chrome", "google chrome": "chrome",
           "edge": "edge", "microsoft edge": "edge", "firefox": "firefox", "mozilla firefox": "firefox"}


def browser_key(name: str) -> str | None:
    n = re.sub(r"\s+(browser|app)$", "", name.lower().strip())
    return ALIASES.get(n)


def display(key: str) -> str:
    return BROWSERS[key][0]


def exe(key: str) -> str | None:
    for base in PF:
        p = base / BROWSERS[key][2]
        if p.exists():
            return str(p)
    return None


def profiles(key: str) -> list[tuple[str, str]]:
    """[(profile id, display name)] - id is the Chromium directory or the Firefox profile name."""
    data = BROWSERS[key][1]
    out: list[tuple[str, str]] = []
    try:
        if key == "firefox":
            cp = configparser.ConfigParser()
            cp.read(data / "profiles.ini", encoding="utf-8")
            for sec in cp.sections():
                if sec.startswith("Profile") and cp.has_option(sec, "Name"):
                    out.append((cp.get(sec, "Name"), cp.get(sec, "Name")))
        else:
            state = json.loads((data / "Local State").read_text(encoding="utf-8"))
            for pdir, info in state.get("profile", {}).get("info_cache", {}).items():
                out.append((pdir, info.get("name") or pdir))
    except (OSError, ValueError, configparser.Error):
        pass
    return out


def match(key: str, spoken: str) -> list[tuple[str, str]]:
    q = clean_profile(spoken)
    all_p = profiles(key)
    exact = [p for p in all_p if p[1].lower() == q or p[0].lower() == q]
    if exact:
        return exact[:1]
    if q in ("default", "main", "first"):
        return [p for p in all_p if p[0] == "Default"][:1]
    starts = [p for p in all_p if p[1].lower().startswith(q)]
    if starts:
        return starts
    return [p for p in all_p if q in p[1].lower()]


def clean_profile(spoken: str) -> str:
    q = spoken.lower().strip(" .\"'“”")
    q = re.sub(r"^(the|my|a)\s+", "", q)
    q = re.sub(r"^(profile\s+)?(named|called)\s+", "", q)
    q = re.sub(r"^profile\s+", "", q)
    q = re.sub(r"\s+(profile|account|user)$", "", q)
    return q.strip()


PRIVATE_FLAGS = {"brave": "--incognito", "chrome": "--incognito", "edge": "--inprivate", "firefox": "-private-window"}


def is_private(spoken: str) -> bool:
    return clean_profile(spoken) in ("incognito", "private", "inprivate", "private window", "incognito mode", "private mode")


def launch(key: str, profile_id: str | None, private: bool = False) -> bool:
    path = exe(key)
    if not path:
        return False
    if private:
        args = [path, PRIVATE_FLAGS[key]]
    elif not profile_id:
        args = [path]
    elif key == "firefox":
        args = [path, "-P", profile_id]
    else:
        args = [path, f"--profile-directory={profile_id}"]
    subprocess.Popen(args)
    return True
