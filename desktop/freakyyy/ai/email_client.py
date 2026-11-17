"""Read-only email access over IMAP (Gmail app password or any IMAP account).

Freakyyy never sends, deletes or moves mail. The password lives in Windows
Credential Manager, never in settings files.
"""
from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import get_secret, settings

log = logging.getLogger(__name__)


@dataclass
class Mail:
    uid: str
    sender: str
    subject: str
    date: str
    snippet: str
    unread: bool

    def as_dict(self) -> dict:
        return self.__dict__


def configured() -> bool:
    return bool(settings.get("email_address") and get_secret("email_password"))


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for text, enc in email.header.decode_header(value):
        parts.append(text.decode(enc or "utf-8", errors="replace") if isinstance(text, bytes) else text)
    return " ".join(parts).strip()


def _body_text(msg: email.message.Message, limit: int) -> str:
    plain, htmlpart = "", ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not htmlpart:
            htmlpart = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", text))
    body = plain or htmlpart
    return re.sub(r"\s+", " ", body).strip()[:limit]


class MailClient:
    def __init__(self) -> None:
        self.host = settings.get("email_imap_host") or "imap.gmail.com"
        self.user = settings.get("email_address")
        self.password = get_secret("email_password")

    def __enter__(self):
        if not (self.user and self.password):
            raise RuntimeError("Email isn't set up. Add your address and app password in Freakyyy settings.")
        self.imap = imaplib.IMAP4_SSL(self.host, timeout=20)
        self.imap.login(self.user, self.password)
        self.imap.select("INBOX", readonly=True)
        self.gmail = "gmail" in self.host or "googlemail" in self.host
        return self

    def __exit__(self, *exc):
        try:
            self.imap.logout()
        except Exception:
            pass

    def _search(self, criteria: list[str] | None = None, gmail_raw: str | None = None) -> list[bytes]:
        if self.gmail and gmail_raw:
            typ, data = self.imap.uid("SEARCH", "X-GM-RAW", f'"{gmail_raw}"')
        else:
            typ, data = self.imap.uid("SEARCH", *(criteria or ["ALL"]))
        return data[0].split() if typ == "OK" and data and data[0] else []

    def _fetch(self, uids: list[bytes], snippet_len: int = 220) -> list[Mail]:
        out = []
        for uid in uids:
            typ, data = self.imap.uid("FETCH", uid, "(FLAGS BODY.PEEK[])")
            if typ != "OK" or not data or not isinstance(data[0], tuple):
                continue
            flags = data[0][0].decode(errors="ignore")
            msg = email.message_from_bytes(data[0][1])
            name, addr = email.utils.parseaddr(_decode(msg.get("From")))
            date = msg.get("Date", "")
            try:
                date = email.utils.parsedate_to_datetime(date).strftime("%a %d %b, %I:%M %p")
            except Exception:
                pass
            out.append(Mail(uid.decode(), name or addr, _decode(msg.get("Subject")) or "(no subject)", date,
                            _body_text(msg, snippet_len), "\\Seen" not in flags))
        return out

    def recent(self, days: int = 2, unread_only: bool = True, important_only: bool = False, limit: int = 10) -> list[Mail]:
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        raw = f"newer_than:{days}d" + (" is:unread" if unread_only else "") + (" is:important" if important_only else "") \
            + " -category:promotions -category:social"
        crit = ["SINCE", since] + (["UNSEEN"] if unread_only else [])
        uids = self._search(crit, raw)
        return list(reversed(self._fetch(uids[-limit:])))

    def search(self, query: str, days: int = 120, limit: int = 10) -> list[Mail]:
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        uids = self._search(["SINCE", since, "TEXT", f'"{query}"'], f"{query} newer_than:{days}d")
        return list(reversed(self._fetch(uids[-limit:])))

    def read(self, uid: str, limit: int = 8000) -> dict:
        typ, data = self.imap.uid("FETCH", uid.encode(), "(BODY.PEEK[])")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise RuntimeError("Message not found")
        msg = email.message_from_bytes(data[0][1])
        return {"from": _decode(msg.get("From")), "to": _decode(msg.get("To")), "subject": _decode(msg.get("Subject")),
                "date": msg.get("Date", ""), "body": _body_text(msg, limit)}


def spoken_summary(mails: list[Mail], label: str) -> str:
    if not mails:
        return f"No {label} emails."
    head = f"You have {len(mails)} {label} email{'s' if len(mails) != 1 else ''}."
    tops = [f"{m.sender.split('<')[0].strip() or 'someone'} about {m.subject}" for m in mails[:3]]
    return head + " " + ("From " + "; ".join(tops) + "." if tops else "")
