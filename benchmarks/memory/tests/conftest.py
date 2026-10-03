"""Independent test root: no OpenWorker fixtures, plugins or network needed."""

import asyncio
import builtins
import socket

import pytest

from memory_bench.assets import load_json


@pytest.fixture(scope="session")
def offline_event_loop():
    # Windows initializes its asyncio self-pipe with a local socketpair. Create it
    # before the network guard; no HTTP socket may connect while tests execute.
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def forbid_runtime_network_and_openworker(monkeypatch, offline_event_loop):
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
    monkeypatch.setattr(asyncio, "run", lambda coroutine, **kwargs: offline_event_loop.run_until_complete(coroutine))


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
