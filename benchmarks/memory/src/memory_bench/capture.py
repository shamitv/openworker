"""Owned run artifacts with durable append-only diagnostics and atomic manifests."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import time

from .assets import canonical_json


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json(value) + b"\n")
    # Windows readers/scanners can briefly hold the destination without delete
    # sharing. Retry only publication of this already-written file; never repeat
    # model requests, SQLite operations, or append-only evidence writes.
    for attempt in range(4):
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 3:
                raise
            time.sleep(0.025 * 2 ** attempt)


class Capture:
    def __init__(self, output: str | Path, manifest: dict):
        self.path = Path(output).resolve()
        self.path.mkdir(parents=True, exist_ok=False)
        self.manifest = deepcopy(manifest)
        self._journal = (self.path / "diagnostics.jsonl").open("a", encoding="utf-8")
        self._checkpoints = (self.path / "checkpoints.jsonl").open("a", encoding="utf-8")
        self.save()

    @staticmethod
    def append(handle, value):
        handle.write(canonical_json(value).decode("utf-8") + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    def record(self, value):
        self.append(self._journal, value)

    def checkpoint(self, value):
        self.append(self._checkpoints, value)

    def save(self):
        write_json(self.path / "manifest.json", self.manifest)

    def close(self):
        self._journal.close()
        self._checkpoints.close()


def read_checkpoints(path: str | Path) -> list[dict]:
    latest = {}
    source = Path(path) / "checkpoints.jsonl"
    if not source.exists():
        return []
    lines = source.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        try:
            value = json.loads(line)
        except ValueError:
            # Only an interrupted trailing write may be incomplete. Never discard
            # a corrupted record in the middle of captured evidence.
            if index == len(lines) - 1 and not source.read_bytes().endswith(b"\n"):
                break
            raise
        latest[value["checkpoint_id"]] = value
    return list(latest.values())
