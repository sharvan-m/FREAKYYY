"""Browser automation through supported means: the default browser for opening
pages, keyboard shortcuts sent to the user's own browser window, Windows UI
Automation to read the address bar, and plain HTTPS fetches for page text.
No CAPTCHA/login bypass, no form submission."""
from __future__ import annotations

import base64
import html
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from . import apps, system

log = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Freakyyy/1.0"
BROWSER_EXES = ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe")

SITES = {
    "youtube": "https://www.youtube.com", "github": "https://github.com", "gmail": "https://mail.google.com",
    "google": "https://www.google.com", "linkedin": "https://www.linkedin.com", "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com", "reddit": "https://www.reddit.com", "twitter": "https://x.com",
    "x": "https://x.com", "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com", "netflix": "https://www.netflix.com", "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com", "google docs": "https://docs.google.com", "docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com", "sheets": "https://sheets.google.com",
    "calendar online": "https://calendar.google.com", "maps": "https://maps.google.com", "google maps": "https://maps.google.com",
    "whatsapp web": "https://web.whatsapp.com", "outlook": "https://outlook.live.com", "leetcode": "https://leetcode.com",
    "hackerrank": "https://www.hackerrank.com", "hacker rank": "https://www.hackerrank.com", "kaggle": "https://www.kaggle.com",
    "huggingface": "https://huggingface.co", "hugging face": "https://huggingface.co", "medium": "https://medium.com",
    "wikipedia": "https://www.wikipedia.org", "internshala": "https://internshala.com", "naukri": "https://www.naukri.com",
    "indeed": "https://in.indeed.com", "glassdoor": "https://www.glassdoor.co.in", "unstop": "https://unstop.com",
}

_last_results: list[tuple[str, str]] = []
_last_query: str | None = None


def open_url(url: str) -> None:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    os.startfile(url)


def search(query: str, engine: str = "google") -> str:
    global _last_query, _last_results
    _last_query, _last_results = query, []
    q = urllib.parse.quote_plus(query)
    url = (f"https://www.youtube.com/results?search_query={q}" if engine == "youtube"
           else f"https://www.google.com/search?q={q}")
    open_url(url)
    return url


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._in_a = False
        self._href = ""
        self._text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and "result__a" in (a.get("class") or ""):
            self._in_a, self._href, self._text = True, a.get("href", ""), []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            href = self._href
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                href = urllib.parse.unquote(m.group(1))
            if href.startswith("http"):
                self.results.append(("".join(self._text).strip(), href))

    def handle_data(self, data):
        if self._in_a:
            self._text.append(data)


def _bing_target(href: str) -> str:
    """Bing wraps links as /ck/a?…&u=a1<base64url of the real URL>."""
    m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", href)
    if not m:
        return href
    raw = m.group(1)
    try:
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
    except Exception:
        return href


class _BingParser(HTMLParser):
    """Bing's result list: <li class="b_algo"> … <h2><a href>title</a></h2>."""

    def __init__(self):
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._in_result = False
        self._in_h2 = False
        self._in_a = False
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li" and "b_algo" in (a.get("class") or ""):
            self._in_result = True
        elif tag == "h2" and self._in_result:
            self._in_h2 = True
        elif tag == "a" and self._in_h2 and a.get("href", "").startswith("http"):
            self._in_a, self._href, self._text = True, a["href"], []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            title = re.sub(r"\s+", " ", "".join(self._text)).strip()
            url = _bing_target(self._href)
            if title and url.startswith("http") and url not in [u for _, u in self.results]:
                self.results.append((title, url))
        elif tag == "h2":
            self._in_h2 = False
        elif tag == "li":
            self._in_result = False

    def handle_data(self, data):
        if self._in_a:
            self._text.append(data)


def _fetch_results(url: str, parser: HTMLParser) -> list[tuple[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        parser.feed(r.read().decode("utf-8", errors="replace"))
    return parser.results


def web_results(query: str) -> list[tuple[str, str]]:
    """Organic results with no API key: DuckDuckGo first, Bing when it can't be reached.

    Some networks block DuckDuckGo outright, which used to leave search dead.
    """
    q = urllib.parse.quote_plus(query)
    errors = []
    for url, parser, skip in (("https://html.duckduckgo.com/html/?q=" + q, _ResultParser(), "duckduckgo.com"),
                              ("https://www.bing.com/search?q=" + q, _BingParser(), "bing.com")):
        try:
            hits = [(t, u) for t, u in _fetch_results(url, parser) if skip not in u]
            if hits:
                return hits[:10]
        except Exception as e:                      # blocked, offline, or markup changed
            errors.append(f"{urllib.parse.urlparse(url).netloc}: {e}")
    if errors:
        log.info("web_results failed - %s", "; ".join(errors))
    return []


def open_result(index: int, query: str | None = None) -> tuple[str, str] | None:
    global _last_results
    q = query or _last_query
    if not q:
        return None
    if not _last_results:
        _last_results = web_results(q)
    if 0 < index <= len(_last_results):
        title, url = _last_results[index - 1]
        open_url(url)
        return title, url
    return None


# ----------------------------------------------------------------------
# The user's browser window
# ----------------------------------------------------------------------

def browser_window() -> apps.Window | None:
    w = apps.active_window()
    if w and w.process.lower() in BROWSER_EXES:
        return w
    wins = [x for x in apps.list_windows() if x.process.lower() in BROWSER_EXES]
    return wins[0] if wins else None


def current_url() -> str | None:
    w = browser_window()
    if not w:
        return None
    try:
        import uiautomation as auto
        ctrl = auto.ControlFromHandle(w.hwnd)
        for name in ("Address and search bar", "Search or enter web address", "Search with Google or enter address"):
            edit = ctrl.EditControl(Name=name, searchDepth=12)
            if edit.Exists(0.5, 0.1):
                val = edit.GetValuePattern().Value
                if val:
                    return val if re.match(r"^\w+://", val) else "https://" + val
    except Exception:
        log.exception("Reading the address bar failed")
    return None


def keys_to_browser(*vks: int) -> bool:
    w = browser_window()
    if not w:
        return False
    apps.focus(w.hwnd)
    time.sleep(0.15)
    system.send_keys(*vks)
    return True


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "h1", "h2", "h3", "li", "div", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def fetch_text(url: str, limit: int = 30_000) -> tuple[str, str, str]:
    """(title, text, content_type) for a public page."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        ctype = r.headers.get("Content-Type", "")
        raw = r.read(3_000_000)
    if "pdf" in ctype:
        return Path(urllib.parse.urlparse(url).path).name, "", ctype
    p = _TextParser()
    p.feed(raw.decode("utf-8", errors="replace"))
    text = html.unescape(re.sub(r"\n\s*\n+", "\n", "".join(p.parts)))
    text = re.sub(r"[ \t]+", " ", text).strip()
    return p.title.strip(), text[:limit], ctype


def pdf_links(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        page = r.read(3_000_000).decode("utf-8", errors="replace")
    links = re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', page, re.I)
    return list(dict.fromkeys(urllib.parse.urljoin(url, l) for l in links))


def download(url: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(urllib.parse.urlparse(url).path).name or "download.pdf"
    name = re.sub(r'[<>:"/\\|?*]', "_", urllib.parse.unquote(name))
    target = folder / name
    i = 1
    while target.exists():
        target = folder / f"{Path(name).stem} ({i}){Path(name).suffix}"
        i += 1
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    tmp.replace(target)
    return target
