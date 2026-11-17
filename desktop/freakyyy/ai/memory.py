"""Freakyyy's long-term memory: saved facts plus a searchable conversation log.

Everything lives in %APPDATA%\\Freakyyy\\memory.db on this laptop only. Models don't
learn from chats, so before each AI request Freakyyy looks up the facts and past
messages related to it and passes them along as context.

The user stays in control: "remember …", "what do you remember", "forget …",
and the Memory page in Settings (view, delete, clear).
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass

from ..config import DATA_DIR

DB_PATH = DATA_DIR / "memory.db"

_STOP = set("""a an the and or but if then so of to in on at for from by with about into over is are was were be been
being am do does did have has had i me my mine you your yours it its this that these those what which who whom
whose when where why how can could would should will shall may might must please tell show find any some all
freakyyy hey ok okay just also too very really now there here them they their our we us he she his her""".split())


# Never kept in memory: passwords, codes, card/bank/ID numbers, keys.
SENSITIVE = re.compile(r"\b(password|passcode|passwd|pin( code| number)?|otp|one[- ]time code|cvv|cvc|"
                       r"card number|account number|ifsc|routing number|ssn|aadhaar|pan number|api key|secret key)\b|"
                       r"\b\d(?:[ -]?\d){11,18}\b", re.I)


@dataclass
class Fact:
    id: int
    text: str
    created: float
    source: str           # "user" (told to remember) or "ai" (saved by the assistant)

    def when(self) -> str:
        return time.strftime("%d %b %Y", time.localtime(self.created))


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'+#.-]*", text.lower())
    return [w.strip(".'") for w in words if len(w) > 1 and w not in _STOP][:12]


class Memory:
    def __init__(self, path=DB_PATH) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT NOT NULL,
                created REAL NOT NULL, source TEXT NOT NULL DEFAULT 'user');
            CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, ts REAL NOT NULL,
                role TEXT NOT NULL, text TEXT NOT NULL);
        """)
        self.fts = True
        try:
            self._db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, content='facts', content_rowid='id', tokenize='porter unicode61');
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, content='messages', content_rowid='id', tokenize='porter unicode61');
                CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text); END;
                CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
                CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
                    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
                    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text); END;
                CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text); END;
                CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
            """)
        except sqlite3.OperationalError:       # SQLite built without FTS5: fall back to LIKE
            self.fts = False
        self._db.commit()

    # ---------------------------------------------------------------- facts
    def add(self, text: str, source: str = "user") -> Fact:
        text = re.sub(r"\s+", " ", text).strip().rstrip(".") + "."
        text = text[0].upper() + text[1:]
        with self._lock:
            row = self._db.execute("SELECT id, text, created, source FROM facts WHERE lower(text) = lower(?)", (text,)).fetchone()
            if row:
                return Fact(*row)
            cur = self._db.execute("INSERT INTO facts(text, created, source) VALUES (?, ?, ?)", (text, time.time(), source))
            self._db.commit()
            return Fact(cur.lastrowid, text, time.time(), source)

    def update(self, fact_id: int, text: str) -> None:
        with self._lock:
            self._db.execute("UPDATE facts SET text = ? WHERE id = ?", (text.strip(), fact_id))
            self._db.commit()

    def delete(self, fact_id: int) -> None:
        with self._lock:
            self._db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            self._db.commit()

    def facts(self) -> list[Fact]:
        with self._lock:
            return [Fact(*r) for r in self._db.execute("SELECT id, text, created, source FROM facts ORDER BY created DESC")]

    def find_facts(self, query: str, limit: int = 8) -> list[Fact]:
        return [f for f, _ in self._search("facts", query, limit)]

    def matching_facts(self, query: str) -> list[Fact]:
        """Facts that clearly mention every keyword of `query` (used by "forget …")."""
        keys = _keywords(query)
        if not keys:
            return []
        return [f for f in self.facts() if all(k in f.text.lower() for k in keys)]

    # ---------------------------------------------------------------- conversation log
    def log(self, role: str, text: str) -> None:
        if not text.strip():
            return
        with self._lock:
            self._db.execute("INSERT INTO messages(ts, role, text) VALUES (?, ?, ?)", (time.time(), role, text.strip()[:4000]))
            self._db.commit()

    def find_messages(self, query: str, limit: int = 6, exclude_recent_s: float = 0) -> list[tuple[float, str, str]]:
        cutoff = time.time() - exclude_recent_s
        return [m for m, _ in self._search("messages", query, limit * 2) if m[0] < cutoff][:limit]

    def message_count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT count(*) FROM messages").fetchone()[0]

    def clear_messages(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM messages")
            self._db.commit()

    def clear_all(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM facts")
            self._db.execute("DELETE FROM messages")
            self._db.commit()

    # ---------------------------------------------------------------- search
    def _search(self, table: str, query: str, limit: int):
        keys = _keywords(query)
        if not keys:
            return []
        cols = "id, text, created, source" if table == "facts" else "ts, role, text"
        with self._lock:
            if self.fts:
                match = " OR ".join('"' + k.replace('"', "") + '"*' for k in keys)
                sql = (f"SELECT {', '.join('t.' + c.strip() for c in cols.split(','))}, bm25({table}_fts) AS score "
                       f"FROM {table}_fts JOIN {table} t ON t.id = {table}_fts.rowid "
                       f"WHERE {table}_fts MATCH ? ORDER BY score LIMIT ?")
                try:
                    rows = self._db.execute(sql, (match, limit)).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            else:
                like = " OR ".join("lower(text) LIKE ?" for _ in keys)
                rows = [r + (0,) for r in self._db.execute(
                    f"SELECT {cols} FROM {table} WHERE {like} ORDER BY id DESC LIMIT ?",
                    [f"%{k}%" for k in keys] + [limit]).fetchall()]
        if table == "facts":
            return [(Fact(*r[:4]), r[4]) for r in rows]
        return [(tuple(r[:3]), r[3]) for r in rows]

    # ---------------------------------------------------------------- context for the model
    def context_for(self, query: str, max_facts: int = 25) -> str:
        """Facts and related past messages to put in front of the model."""
        all_facts = self.facts()
        if len(all_facts) <= max_facts:
            facts = all_facts
        else:
            related = self.find_facts(query, 12)
            ids = {f.id for f in related}
            facts = related + [f for f in all_facts if f.id not in ids][:max_facts - len(related)]
        parts = []
        if facts:
            parts.append("Things the user asked you to remember (most recent first):\n" +
                         "\n".join(f"- {f.text} (saved {f.when()})" for f in facts))
        past = self.find_messages(query, 6, exclude_recent_s=1200)
        if past:
            parts.append("Possibly related earlier conversation:\n" + "\n".join(
                f"- {time.strftime('%d %b %Y', time.localtime(ts))} {role}: {text[:300]}" for ts, role, text in past))
        return "\n\n".join(parts)


_memory: Memory | None = None


def get() -> Memory:
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory
