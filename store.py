"""Хранилище мазков общего холста (SQLite).

Одно постоянное соединение вместо нового на каждое сообщение, режим WAL и замок:
обращаться к хранилищу из асинхронного кода нужно через run_in_threadpool / asyncio.to_thread,
чтобы запись на диск не останавливала весь сервер. Модуль не зависит от FastAPI.
"""
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional


class LineStore:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prevX REAL, prevY REAL, currX REAL, currY REAL,
                    color TEXT, size REAL, timestamp REAL,
                    lid TEXT DEFAULT '', cid TEXT DEFAULT '', brush TEXT DEFAULT 'w'
                )
            """)
            # Старая база без колонок lid/cid/brush: добавляем их
            columns = {row[1] for row in self._conn.execute("PRAGMA table_info(lines)")}
            for name in ("lid", "cid", "brush"):
                if name not in columns:
                    default = "w" if name == "brush" else ""
                    self._conn.execute(f"ALTER TABLE lines ADD COLUMN {name} TEXT DEFAULT '{default}'")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lines_lid ON lines(lid)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lines_cid ON lines(cid)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lines_ts ON lines(timestamp)")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- запись ---
    def insert_many(self, lines: Iterable[dict], cid: str) -> None:
        now = time.time()
        rows = [(l["prevX"], l["prevY"], l["currX"], l["currY"], l["color"], l["size"], now,
                 l["lid"], cid, l["brush"]) for l in lines]
        if not rows:
            return
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.executemany(
                    "INSERT INTO lines (prevX, prevY, currX, currY, color, size, timestamp, lid, cid, brush) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def insert(self, line: dict, cid: str) -> None:
        self.insert_many([line], cid)

    # --- чтение ---
    def recent(self, limit: int, lifetime: Optional[float] = None) -> List[tuple]:
        """Не больше limit самых свежих мазков в порядке рисования (и не старше lifetime секунд)."""
        where, args = "", []
        if lifetime is not None:
            where, args = "WHERE ? - timestamp <= ?", [time.time(), lifetime]
        with self._lock:
            rows = self._conn.execute(
                "SELECT prevX, prevY, currX, currY, color, size, lid, cid, brush FROM "
                f"(SELECT * FROM lines {where} ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                [*args, int(limit)]).fetchall()
        return rows

    def owned(self, cid: str, lids: List[str]) -> List[str]:
        """Какие из переданных отрезков действительно принадлежат этому посетителю."""
        if not lids:
            return []
        marks = ",".join("?" * len(lids))
        with self._lock:
            return [r[0] for r in self._conn.execute(
                f"SELECT lid FROM lines WHERE cid = ? AND lid IN ({marks})", [cid, *lids])]

    # --- удаление ---
    def delete_owned(self, cid: str, lids: List[str]) -> List[str]:
        """Удаляет и возвращает только свои отрезки (чужие стереть нельзя)."""
        if not lids:
            return []
        marks = ",".join("?" * len(lids))
        with self._lock:
            owned = [r[0] for r in self._conn.execute(
                f"SELECT lid FROM lines WHERE cid = ? AND lid IN ({marks})", [cid, *lids])]
            if owned:
                self._conn.execute(f"DELETE FROM lines WHERE cid = ? AND lid IN ({marks})", [cid, *lids])
        return owned

    def clear_owned(self, cid: str) -> List[str]:
        with self._lock:
            lids = [r[0] for r in self._conn.execute(
                "SELECT lid FROM lines WHERE cid = ? AND lid != ''", (cid,))]
            self._conn.execute("DELETE FROM lines WHERE cid = ?", (cid,))
        return lids

    def purge(self, lifetime: float, max_lines: int, now: Optional[float] = None) -> int:
        """Убирает мазки старше lifetime секунд и всё, что сверх лимита. Возвращает, сколько удалено."""
        now = time.time() if now is None else now
        with self._lock:
            before = self._conn.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
            self._conn.execute("DELETE FROM lines WHERE ? - timestamp > ?", (now, lifetime))
            self._conn.execute(
                "DELETE FROM lines WHERE id NOT IN (SELECT id FROM lines ORDER BY id DESC LIMIT ?)",
                (int(max_lines),))
            after = self._conn.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
        return before - after

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
