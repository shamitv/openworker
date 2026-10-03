"""Independent SQLite current-fact storage. Policy violations are not filtered."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .contract import ContractError, validate_operation, validate_record
from .model_input import selected_memory

MAX_SQLITE_ID = 2**63 - 1


class MemoryStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        try:
            with self._db:
                self._db.execute("""CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL, workspace_id TEXT,
                    scope TEXT NOT NULL CHECK(scope IN ('global', 'workspace')),
                    key TEXT NOT NULL, value TEXT NOT NULL, history TEXT NOT NULL,
                    CHECK ((scope = 'global' AND workspace_id IS NULL) OR
                           (scope = 'workspace' AND workspace_id IS NOT NULL)))""")
                self._db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                self._db.execute("CREATE INDEX IF NOT EXISTS namespace ON memories(user_id, workspace_id)")
        except Exception:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def set_deadline(self, deadline: float | None, clock=time.monotonic) -> None:
        """Bound SQLite lock waits and long queries by the runner's turn budget."""
        self._db.set_progress_handler(None, 0)
        if deadline is None:
            self._db.execute("PRAGMA busy_timeout=5000")
            return
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError("operation deadline expired")
        self._db.execute(f"PRAGMA busy_timeout={int(remaining * 1000)}")
        self._db.set_progress_handler(lambda: int(clock() >= deadline), 20)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def _record(row) -> dict:
        record = dict(row)
        record["history"] = json.loads(record["history"])
        validate_record(record)
        return record

    def seed(self, records: list[dict]) -> None:
        """Initialize an empty store once, atomically, preserving fixture IDs."""
        for record in records:
            validate_record(record)
        if len({row["id"] for row in records}) != len(records):
            raise ValueError("duplicate seeded record IDs")
        with self._db:
            if self._db.execute("SELECT 1 FROM memories LIMIT 1").fetchone() or self._db.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
                raise ValueError("store has already been initialized")
            self._db.executemany(
                "INSERT INTO memories(id,user_id,workspace_id,scope,key,value,history) VALUES (?,?,?,?,?,?,?)",
                [(r["id"], r["user_id"], r["workspace_id"], r["scope"], r["key"], r["value"], json.dumps(r["history"], ensure_ascii=False)) for r in records],
            )
            self._db.execute("INSERT INTO metadata VALUES ('seeded','true')")

    def snapshot(self) -> list[dict]:
        return [self._record(row) for row in self._db.execute("SELECT * FROM memories ORDER BY id")]

    def selected(self, user_id: str, workspace_id: str) -> list[dict]:
        return selected_memory(self.snapshot(), user_id, workspace_id)

    def read(self, user_id: str, memory_ids: list[int]) -> dict:
        validate_operation({"name": "memory_read", "arguments": {"memory_ids": memory_ids}})
        records, missing = [], []
        for memory_id in memory_ids:
            row = self._db.execute("SELECT * FROM memories WHERE id=? AND user_id=?", (memory_id, user_id)).fetchone() if memory_id <= MAX_SQLITE_ID else None
            if row is None:
                missing.append(memory_id)
            else:
                records.append(self._record(row))
        return {"records": records, "missing_ids": missing}

    def remember(self, user_id: str, workspace_id: str, **arguments) -> dict:
        validate_operation({"name": "remember", "arguments": arguments})
        record = {"id": 1, "user_id": user_id, "workspace_id": workspace_id if arguments["scope"] == "workspace" else None,
                  "scope": arguments["scope"], "key": arguments["key"], "value": arguments["value"], "history": arguments.get("history", [])}
        validate_record(record)
        with self._db:
            cursor = self._db.execute("INSERT INTO memories(user_id,workspace_id,scope,key,value,history) VALUES (?,?,?,?,?,?)",
                                      (record["user_id"], record["workspace_id"], record["scope"], record["key"], record["value"], json.dumps(record["history"], ensure_ascii=False)))
            record["id"] = cursor.lastrowid
        return self.read(user_id, [record["id"]])["records"][0]

    def update(self, user_id: str, **arguments) -> dict:
        validate_operation({"name": "memory_update", "arguments": arguments})
        if arguments["memory_id"] > MAX_SQLITE_ID:
            raise ContractError("unavailable_id", "memory ID is unavailable")
        with self._db:
            cursor = self._db.execute("UPDATE memories SET value=?,history=? WHERE id=? AND user_id=?",
                                      (arguments["value"], json.dumps(arguments.get("history", []), ensure_ascii=False), arguments["memory_id"], user_id))
            if not cursor.rowcount:
                raise ContractError("unavailable_id", "memory ID is unavailable")
        return self.read(user_id, [arguments["memory_id"]])["records"][0]

    def forget(self, user_id: str, memory_id: int) -> int:
        validate_operation({"name": "memory_forget", "arguments": {"memory_id": memory_id}})
        if memory_id > MAX_SQLITE_ID:
            raise ContractError("unavailable_id", "memory ID is unavailable")
        with self._db:
            cursor = self._db.execute("DELETE FROM memories WHERE id=? AND user_id=?", (memory_id, user_id))
            if not cursor.rowcount:
                raise ContractError("unavailable_id", "memory ID is unavailable")
        return memory_id
