"""Developer workflows by voice: projects, IDEs, git, Gradle, npm, Python."""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import psutil

from ..config import DATA_DIR, settings

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010
BUILD_DIR = DATA_DIR / "builds"
BUILD_DIR.mkdir(exist_ok=True)

MARKERS = {
    "android": ("settings.gradle.kts", "settings.gradle"),
    "gradle": ("build.gradle.kts", "build.gradle", "gradlew.bat"),
    "node": ("package.json",),
    "python": ("pyproject.toml", "requirements.txt", "setup.py", "manage.py", "main.py", "app.py"),
    "dotnet": ("*.sln", "*.csproj"),
    "java": ("pom.xml",),
    "rust": ("Cargo.toml",),
    "go": ("go.mod",),
    "git": (".git",),
}


@dataclass
class Project:
    name: str
    path: Path
    kinds: set[str] = field(default_factory=set)

    @property
    def spoken(self) -> str:
        n = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", self.name)
        return re.sub(r"[_\-.]+", " ", n).strip().lower()

    @property
    def is_android(self) -> bool:
        return "android" in self.kinds or (self.path / "app" / "src" / "main" / "AndroidManifest.xml").exists()


def _kinds(p: Path) -> set[str]:
    kinds = set()
    for kind, files in MARKERS.items():
        for f in files:
            if ("*" in f and any(p.glob(f))) or (p / f).exists():
                kinds.add(kind)
                break
    if "android" in kinds and not (p / "app").exists() and not any(p.glob("*/src/main/AndroidManifest.xml")):
        kinds.discard("android")
    return kinds


_projects: list[Project] = []
_projects_at = 0.0


def projects(refresh: bool = False) -> list[Project]:
    global _projects, _projects_at
    if _projects and not refresh and time.time() - _projects_at < 300:
        return _projects
    found: dict[str, Project] = {}
    for root in settings.get("project_roots"):
        r = Path(root)
        if not r.exists():
            continue
        for child in r.iterdir():
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            k = _kinds(child)
            if k - {"git"} or "git" in k:
                found.setdefault(str(child).lower(), Project(child.name, child, k))
            else:
                # one level deeper (e.g. Documents\Projects\Foo)
                try:
                    for sub in child.iterdir():
                        if sub.is_dir() and not sub.name.startswith("."):
                            k2 = _kinds(sub)
                            if k2:
                                found.setdefault(str(sub).lower(), Project(sub.name, sub, k2))
                except OSError:
                    pass
    _projects = sorted(found.values(), key=lambda p: p.name.lower())
    _projects_at = time.time()
    return _projects


def match_projects(spoken: str) -> list[Project]:
    q = re.sub(r"\b(my|the|our|project|repo|repository|app|folder|codebase)\b", " ", spoken.lower())
    words = [w for w in re.split(r"[\s_\-.]+", q) if w]
    if not words:
        return []
    ps = projects()
    exact = [p for p in ps if p.spoken.replace(" ", "") == "".join(words)]
    if exact:
        return exact
    hits = [p for p in ps if all(w in p.spoken.split() or w in p.spoken.replace(" ", "") for w in words)]
    hits.sort(key=lambda p: (len(p.spoken), str(p.path)))
    return hits


# ======================================================================
# IDEs and terminals
# ======================================================================

def _code_cli() -> str | None:
    c = shutil.which("code") or shutil.which("code.cmd")
    if c:
        return c
    exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    return str(exe) if exe.exists() else None


def _studio_exe() -> str | None:
    for base in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Android Studio" / "bin",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Android Studio" / "bin"):
        exe = base / "studio64.exe"
        if exe.exists():
            return str(exe)
    return None


def open_in(project: Project, ide: str | None) -> tuple[bool, str]:
    ide = (ide or "").lower()
    if not ide:
        ide = "android studio" if project.is_android else "vscode"
    if ide in ("android studio", "studio", "intellij"):
        exe = _studio_exe()
        if exe:
            subprocess.Popen([exe, str(project.path)])
            return True, "Android Studio"
        return False, "Android Studio isn't installed in the usual place."
    if ide in ("vscode", "code"):
        exe = _code_cli()
        if exe:
            subprocess.Popen([exe, str(project.path)], creationflags=CREATE_NO_WINDOW)
            return True, "VS Code"
        return False, "VS Code isn't installed."
    if ide == "visual studio":
        sln = next(iter(project.path.glob("*.sln")), None)
        if sln:
            os.startfile(sln)
            return True, "Visual Studio"
        return False, "That project has no Visual Studio solution."
    if ide in ("explorer", "file explorer"):
        os.startfile(project.path)
        return True, "File Explorer"
    if ide == "terminal":
        open_terminal(project.path)
        return True, "a terminal"
    return False, f"I don't know how to open projects in {ide}."


def open_terminal(path: Path, command: list[str] | None = None) -> None:
    wt = shutil.which("wt") or shutil.which("wt.exe")
    if wt:
        args = [wt, "-d", str(path)]
        if command:
            args += ["powershell.exe", "-NoExit", "-Command", subprocess.list2cmdline(command)]
        subprocess.Popen(args)
    else:
        cmd = ["powershell.exe", "-NoExit", "-Command", f"Set-Location '{path}'" + (f"; {subprocess.list2cmdline(command)}" if command else "")]
        subprocess.Popen(cmd, creationflags=CREATE_NEW_CONSOLE)


# ======================================================================
# git
# ======================================================================

def _git(path: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW, encoding="utf-8", errors="replace")


def git_status(project: Project) -> tuple[str, dict]:
    if not (project.path / ".git").exists():
        return f"{project.name} isn't a git repository.", {}
    r = _git(project.path, "status", "--porcelain=v1", "-b")
    if r.returncode != 0:
        return f"git status failed: {r.stderr.strip()[:200]}", {}
    lines = r.stdout.splitlines()
    head = lines[0][3:] if lines and lines[0].startswith("##") else ""
    branch = re.sub(r"^(No commits yet on|Initial commit on) ", "", head.split("...")[0])
    ahead = re.search(r"ahead (\d+)", head)
    behind = re.search(r"behind (\d+)", head)
    entries = lines[1:]
    modified = sum(1 for l in entries if not l.startswith("??"))
    untracked = sum(1 for l in entries if l.startswith("??"))
    parts = [f"{project.name} is on branch {branch}"]
    if not entries:
        parts.append("and the working tree is clean")
    else:
        bits = []
        if modified:
            bits.append(f"{modified} changed file{'s' if modified != 1 else ''}")
        if untracked:
            bits.append(f"{untracked} untracked file{'s' if untracked != 1 else ''}")
        parts.append("with " + " and ".join(bits))
    if ahead:
        parts.append(f"{ahead.group(1)} commit{'s' if ahead.group(1) != '1' else ''} ahead of the remote")
    if behind:
        parts.append(f"{behind.group(1)} behind")
    files = [l[3:] for l in entries][:12]
    return ", ".join(parts) + ".", {"branch": branch, "modified": modified, "untracked": untracked, "files": files}


def git_commit(project: Project, message: str) -> tuple[bool, str]:
    r = _git(project.path, "add", "-A")
    if r.returncode != 0:
        return False, f"git add failed: {r.stderr.strip()[:200]}"
    r = _git(project.path, "commit", "-m", message)
    if r.returncode != 0:
        return False, (r.stdout + r.stderr).strip()[:300]
    sha = _git(project.path, "rev-parse", "--short", "HEAD").stdout.strip()
    return True, f"Committed {sha} on {project.name}: {message}"


def git_simple(project: Project, *args: str) -> tuple[bool, str]:
    r = _git(project.path, *args, timeout=180)
    out = (r.stdout + "\n" + r.stderr).strip()
    return r.returncode == 0, out[-400:]


def remote_url(project: Project) -> str | None:
    r = _git(project.path, "remote", "get-url", "origin")
    url = r.stdout.strip()
    if not url:
        return None
    m = re.match(r"git@([^:]+):(.+?)(\.git)?$", url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    return re.sub(r"\.git$", "", url)


# ======================================================================
# Builds and long-running commands
# ======================================================================

@dataclass
class BuildRecord:
    project: str
    command: str
    started: float
    finished: float | None = None
    ok: bool | None = None
    log_path: Path | None = None
    errors: list[str] = field(default_factory=list)


last_build: BuildRecord | None = None
servers: dict[str, psutil.Popen] = {}


def _java_home() -> str | None:
    jh = os.environ.get("JAVA_HOME")
    if jh and Path(jh, "bin", "java.exe").exists():
        return jh
    for p in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Android" / "Android Studio" / "jbr",):
        if (p / "bin" / "java.exe").exists():
            return str(p)
    return None


def extract_errors(text: str) -> list[str]:
    errs = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^(e: |error:|ERROR:|FAILURE:|\* What went wrong|> |.*error [A-Z]+\d+:|.*Error:|npm ERR!|Traceback|.*Exception:)", s):
            errs.append(s[:300])
    # Gradle puts the reason on the line after "* What went wrong:"
    return errs[:15]


def run_logged(project: Project, command: list[str], label: str, on_done: Callable[[BuildRecord], None],
               env_extra: dict | None = None, timeout: int = 1800) -> BuildRecord:
    global last_build
    log_path = BUILD_DIR / f"{project.name}-{label}-{dt.datetime.now():%Y%m%d-%H%M%S}.log"
    rec = BuildRecord(project.name, " ".join(command), time.time(), log_path=log_path)
    if label == "build":
        last_build = rec
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)

    def work():
        try:
            with open(log_path, "w", encoding="utf-8", errors="replace") as f:
                p = subprocess.run(command, cwd=project.path, stdout=f, stderr=subprocess.STDOUT, env=env,
                                   timeout=timeout, creationflags=CREATE_NO_WINDOW, shell=command[0].endswith(".cmd"))
            rec.ok = p.returncode == 0
        except subprocess.TimeoutExpired:
            rec.ok = False
            rec.errors = [f"Timed out after {timeout // 60} minutes"]
        except Exception as e:
            rec.ok = False
            rec.errors = [str(e)]
        rec.finished = time.time()
        text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if not rec.ok and not rec.errors:
            rec.errors = extract_errors(text) or text.strip().splitlines()[-5:]
        on_done(rec)

    threading.Thread(target=work, daemon=True, name=f"dev-{label}").start()
    return rec


def gradle_build(project: Project, on_done: Callable[[BuildRecord], None]) -> BuildRecord | None:
    wrapper = project.path / "gradlew.bat"
    if not wrapper.exists():
        return None
    task = "assembleDebug" if project.is_android else "build"
    env = {}
    jh = _java_home()
    if jh:
        env["JAVA_HOME"] = jh
    return run_logged(project, [str(wrapper), task, "--console=plain"], "build", on_done, env)


def npm(project: Project, args: list[str], on_done: Callable[[BuildRecord], None]) -> BuildRecord | None:
    if not (project.path / "package.json").exists():
        return None
    exe = shutil.which("npm.cmd") or shutil.which("npm")
    return run_logged(project, [exe, *args], "npm", on_done, timeout=900)


def start_dev_server(project: Project) -> tuple[bool, str]:
    import json
    pkg = project.path / "package.json"
    if not pkg.exists():
        return False, f"{project.name} has no package.json."
    scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
    script = next((s for s in ("dev", "start", "serve") if s in scripts), None)
    if not script:
        return False, f"{project.name} has no dev, start or serve script."
    if project.name in servers and servers[project.name].is_running():
        return True, f"The {project.name} dev server is already running."
    log_path = BUILD_DIR / f"{project.name}-server.log"
    f = open(log_path, "w", encoding="utf-8", errors="replace")
    exe = shutil.which("npm.cmd") or "npm"
    p = psutil.Popen([exe, "run", script], cwd=project.path, stdout=f, stderr=subprocess.STDOUT,
                     creationflags=CREATE_NO_WINDOW)
    servers[project.name] = p
    time.sleep(4)
    text = log_path.read_text(encoding="utf-8", errors="replace")
    url = re.search(r"https?://(localhost|127\.0\.0\.1)(:\d+)?\S*", text)
    if not p.is_running():
        return False, "The dev server stopped right away: " + " ".join(text.strip().splitlines()[-3:])[:300]
    return True, f"Started npm run {script} for {project.name}" + (f" at {url.group(0)}." if url else ".")


def stop_dev_servers() -> list[str]:
    stopped = []
    for name, p in list(servers.items()):
        try:
            for c in p.children(recursive=True):
                c.kill()
            p.kill()
            stopped.append(name)
        except psutil.NoSuchProcess:
            pass
        servers.pop(name, None)
    return stopped


def python_entry(project: Project) -> list[str] | None:
    py = project.path / ".venv" / "Scripts" / "python.exe"
    python = str(py) if py.exists() else (shutil.which("python") or "python")
    if (project.path / "manage.py").exists():
        return [python, "manage.py", "runserver"]
    for f in ("main.py", "app.py", "run.py", "__main__.py"):
        if (project.path / f).exists():
            return [python, f]
    if (project.path / "pyproject.toml").exists():
        name = project.path.name.replace("-", "_").lower()
        if (project.path / name).is_dir() or (project.path / "src" / name).is_dir():
            return [python, "-m", name]
    return None
