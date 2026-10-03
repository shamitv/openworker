"""Independent test root: no OpenWorker fixtures, plugins or network needed."""

import builtins
import socket

import pytest

from memory_bench.assets import load_json


@pytest.fixture(autouse=True)
def forbid_runtime_network_and_openworker(monkeypatch):
    original = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "coworker" or name.startswith("coworker."):
            raise AssertionError("standalone benchmark imported OpenWorker")
        return original(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("offline benchmark attempted network access")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def development():
    return load_json("corpus/development.json")


@pytest.fixture
def heldout():
    return load_json("corpus/heldout.json")


@pytest.fixture
def required_asset_names():
    return {"contract.json", "corpus-schema.json", "corpus/development.json", "corpus/heldout.json",
            "policies/conservative.md", "policies/recurring.md", "protocol/operations.md",
            "protocol/scoring.md", "fixtures/scoring.json", "fixtures/lifecycle.json", "fixtures/native.json"}
