"""File management for voice commands."""
from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import time
import uuid
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger(__name__)

_KNOWN = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}

_FOLDER_ALIASES = {
    "download": "downloads", "document": "documents", "my documents": "documents", "picture": "pictures",
    "photo": "pictures", "photos": "pictures", "video": "videos", "screenshot": "screenshots",
    "home folder": "home", "user folder": "home",
}

SKIP_DIRS = {"node_modules", ".git", "build", ".gradle", ".idea", "__pycache__", ".venv", "venv", "AppData",
             "$Recycle.Bin", ".cache", "dist", "target", ".kotlin", "intermediates", "site-packages"}


def known_folder(name: str) -> Path | None:
    name = _FOLDER_ALIASES.get(name.lower().strip(), name.lower().strip())
    if name == "home":
        return Path.home()
    if name == "screenshots":
        return known_folder("pictures") / "Screenshots"
    guid = _KNOWN.get(name)
    if not guid:
        return None
    try:
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", wintypes.BYTE * 8)]
        u = uuid.UUID(guid)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version, (wintypes.BYTE * 8).from_buffer_copy(u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0:
            p = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return p
    except Exception:
        pass
    return Path.home() / name.capitalize()


def search_roots() -> list[Path]:
    roots = [known_folder(n) for n in ("desktop", "documents", "downloads", "pictures", "videos", "music")]
    from ..config import settings
    roots += [Path(p) for p in settings.get("project_roots")]
    seen, out = set(), []
    for r in roots:
        if r and r.exists() and str(r).lower() not in seen:
            seen.add(str(r).lower())
            out.append(r)
    return out


def _index_search(query: str, scope: Path, pdf: bool, limit: int) -> list[Path] | None:
    """Windows Search index (fast, includes file contents). None if unavailable."""
    try:
        import win32com.client
        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        q = query.replace("'", "''")
        words = [w for w in re.split(r"\s+", q) if w]
        name_clause = " AND ".join(f"System.FileName LIKE '%{w}%'" for w in words)
        content = " AND ".join(f'"{w}*"' for w in words)
        where = f"(({name_clause}) OR CONTAINS(*, '{content}'))"
        if pdf:
            where += " AND System.FileExtension = '.pdf'"
        sql = (f"SELECT TOP {limit} System.ItemPathDisplay FROM SYSTEMINDEX WHERE SCOPE='file:{scope.as_posix()}' "
               f"AND {where} AND System.ItemType <> 'Directory' ORDER BY System.DateModified DESC")
        rs = conn.Execute(sql)[0]
        out = []
        while not rs.EOF:
            out.append(Path(rs.Fields.Item("System.ItemPathDisplay").Value))
            rs.MoveNext()
        conn.Close()
        return out
    except Exception as e:
        log.info("Search index unavailable: %s", e)
        return None


def search(query: str, location: str | None = None, pdf: bool = False, limit: int = 20,
           budget_s: float = 4.0) -> list[Path]:
    query = query.strip().strip("'\"")
    scope_paths = search_roots()
    if location:
        loc = location.lower()
        kf = known_folder(loc)
        if kf:
            scope_paths = [kf]
        elif loc.startswith("project"):
            from ..config import settings
            scope_paths = [Path(p) for p in settings.get("project_roots") if Path(p).exists()]
        elif loc in ("computer", "laptop", "drive", "everywhere"):
            scope_paths = [Path.home()]
    results: list[Path] = []
    for scope in scope_paths:
        found = _index_search(query, scope, pdf, limit)
        if found:
            results += found
    if results:
        return _dedupe(results)[:limit]
    # Fallback: bounded filename walk.
    words = [w.lower() for w in query.split()]
    end = time.time() + budget_s
    for scope in scope_paths:
        for root, dirs, files in os.walk(scope):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                lf = f.lower()
                if all(w in lf for w in words) and (not pdf or lf.endswith(".pdf")):
                    results.append(Path(root) / f)
            if time.time() > end or len(results) >= limit * 3:
                break
    results.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return _dedupe(results)[:limit]


def _dedupe(paths: list[Path]) -> list[Path]:
    seen, out = set(), []
    for p in paths:
        k = str(p).lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def find_folder(name: str) -> list[Path]:
    """Folders named like `name` under the usual roots (depth-limited)."""
    kf = known_folder(name)
    if kf:
        return [kf]
    words = [w for w in re.split(r"[\s_-]+", name.lower()) if w]
    hits = []
    end = time.time() + 3
    for scope in search_roots():
        for root, dirs, _ in os.walk(scope):
            depth = len(Path(root).relative_to(scope).parts)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for d in dirs:
                key = re.sub(r"[\s_-]+", " ", d.lower())
                if all(w in key for w in words):
                    hits.append(Path(root) / d)
            if depth >= 3:
                dirs[:] = []
            if time.time() > end:
                break
    hits.sort(key=lambda p: (len(p.name), len(p.parts)))
    return _dedupe(hits)[:6]


def latest_download() -> Path | None:
    d = known_folder("downloads")
    files = [p for p in d.iterdir() if p.is_file() and not p.name.endswith((".crdownload", ".part", ".tmp"))] if d and d.exists() else []
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def explorer_selection() -> list[Path]:
    """Files selected in the frontmost File Explorer window ("this file")."""
    try:
        import win32com.client
        from . import apps
        active = apps.active_window()
        shell = win32com.client.Dispatch("Shell.Application")
        best: list[Path] = []
        for w in shell.Windows():
            try:
                items = [Path(i.Path) for i in w.Document.SelectedItems()]
            except Exception:
                continue
            if not items:
                continue
            if active and int(w.HWND) == active.hwnd:
                return items
            best = best or items
        return best
    except Exception:
        log.exception("explorer selection")
        return []


def large_files(min_mb: int = 300, limit: int = 8, budget_s: float = 8.0) -> list[tuple[Path, int]]:
    out = []
    end = time.time() + budget_s
    for root, dirs, files in os.walk(Path.home()):
        dirs[:] = [d for d in dirs if d not in {"AppData", ".gradle", ".android", "node_modules", ".git"}]
        for f in files:
            try:
                p = Path(root) / f
                size = p.stat().st_size
                if size >= min_mb * 1_000_000:
                    out.append((p, size))
            except OSError:
                pass
        if time.time() > end:
            break
    out.sort(key=lambda t: -t[1])
    return out[:limit]


def recycle(paths: list[Path]) -> bool:
    """Move to the Recycle Bin (recoverable)."""
    from win32com.shell import shell, shellcon
    flags = shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI
    res, aborted = shell.SHFileOperation((0, shellcon.FO_DELETE, "\0".join(str(p) for p in paths) + "\0", None, flags, None, None))
    return res == 0 and not aborted and not any(p.exists() for p in paths)


def delete_permanently(paths: list[Path]) -> bool:
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    return not any(p.exists() for p in paths)


def empty_recycle_bin() -> bool:
    SHERB_NOCONFIRMATION, SHERB_NOPROGRESSUI, SHERB_NOSOUND = 1, 2, 4
    r = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
    return r in (0, -2147418113)      # S_OK or "already empty"


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return name or "New folder"


def human_size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)
