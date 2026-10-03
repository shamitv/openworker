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
        raise AssertionError("Phase 1 attempted network access")

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
