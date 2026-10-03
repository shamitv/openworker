"""Load installed resources; never resolve resources against the checkout or cwd."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files


def resource(name: str):
    parts = name.split("/")
    if not parts or any(part in ("", ".", "..") or "\\" in part for part in parts):
        raise ValueError("asset names must be relative, slash-separated paths")
    node = files("memory_bench").joinpath("assets")
    for part in parts:
        node = node.joinpath(part)
    return node


def load_text(name: str) -> str:
    return resource(name).read_text(encoding="utf-8")


def load_json(name: str):
    return json.loads(load_text(name))


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def asset_hashes() -> dict[str, str]:
    """JSON hashes use canonical JSON; text hashes use LF-normalized UTF-8."""
    hashes = {}

    def visit(node, prefix=""):
        for child in sorted(node.iterdir(), key=lambda item: item.name):
            name = prefix + child.name
            if child.is_dir():
                visit(child, name + "/")
            elif child.name.endswith((".json", ".md")):
                content = child.read_text(encoding="utf-8")
                data = canonical_json(json.loads(content)) if child.name.endswith(".json") else content.replace("\r\n", "\n").encode("utf-8")
                hashes[name] = hashlib.sha256(data).hexdigest()

    visit(files("memory_bench").joinpath("assets"))
    return hashes
