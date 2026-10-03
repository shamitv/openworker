"""Portable scorer revision and content hashes, independent of collection provenance."""

from __future__ import annotations

import hashlib
from importlib.resources import files
import importlib.metadata
import platform

from .assets import asset_hashes, canonical_json

SCORER_REVISION = "standalone-memory-scorer-v1"
SCORER_MODULES = ("scoring.py", "matching.py", "checkpoints.py", "operations.py", "store.py",
                  "contract.py", "model_input.py", "assets.py", "provenance.py")


def scorer_provenance() -> dict:
    root = files("memory_bench")
    sources = {name: hashlib.sha256(root.joinpath(name).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
               for name in SCORER_MODULES}
    assets = asset_hashes()
    return {"revision": SCORER_REVISION,
            "sha256": hashlib.sha256(canonical_json({"revision": SCORER_REVISION, "sources": sources, "assets": assets})).hexdigest(),
            "source_hashes": sources, "asset_hashes": assets,
            "hash_algorithm": "sha256; LF UTF-8 source/text and canonical JSON assets"}


def collection_provenance() -> dict:
    root = files("memory_bench")
    sources = {node.name: hashlib.sha256(node.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
               for node in sorted(root.iterdir(), key=lambda item: item.name) if node.name.endswith(".py")}
    assets = asset_hashes()
    revision = "standalone-memory-runner-v1"
    return {"revision": revision, "source_hashes": sources, "asset_hashes": assets,
            "sha256": hashlib.sha256(canonical_json({"revision": revision, "sources": sources, "assets": assets})).hexdigest(),
            "python": platform.python_version(), "platform": platform.platform(),
            "httpx": importlib.metadata.version("httpx"), "package_version": __import__("memory_bench").__version__,
            "hash_algorithm": "sha256; LF UTF-8 source/text and canonical JSON assets"}
