import json
import sqlite3

import pytest

from memory_bench.assets import load_json
from memory_bench.checkpoints import create_checkpoint_store, reopen_sequence_store
from memory_bench.contract import ContractError, validate_result
from memory_bench.operations import OperationContext, OperationDispatcher
from memory_bench.store import MemoryStore


def row(memory_id=1, *, user="owner", workspace=None, key="fact", value="current", history=None):
    return {"id": memory_id, "user_id": user, "workspace_id": workspace,
            "scope": "workspace" if workspace else "global", "key": key, "value": value, "history": history or []}


def operation(name, **args):
    return {"name": name, "arguments": args}


def test_persistence_seeded_ids_duplicates_and_history_reset(tmp_path):
    path = tmp_path / "memory.sqlite"
    with MemoryStore(path) as store:
        store.seed([row(40, workspace="B", history=["earlier"])])
        dispatcher = OperationDispatcher(store, OperationContext("owner", "A", "C1"))
        original = store.snapshot()[0]
        updated = dispatcher.dispatch(operation("memory_update", memory_id=40, value="replacement"))
        assert updated["data"]["record"] == {**original, "value": "replacement", "history": []}
        for _ in range(2):
            saved = dispatcher.dispatch(operation("remember", key="fact", value="same", scope="global"))
            assert saved["data"]["record"] in store.snapshot()
        assert [r["id"] for r in store.snapshot()] == [40, 41, 42]
        assert dispatcher.dispatch(operation("memory_forget", memory_id=42))["ok"]
    with MemoryStore(path) as store:
        assert [r["id"] for r in store.snapshot()] == [40, 41]
        assert store.remember("owner", "A", key="fact", value="same", scope="global")["id"] == 43
        with pytest.raises(ValueError, match="initialized"):
            store.seed([])


def test_namespace_scope_selection_and_read_order():
    with MemoryStore(":memory:") as store:
        records = [row(1), row(2, workspace="A"), row(3, workspace="B"), row(4, user="peer")]
        store.seed(records)
        dispatcher = OperationDispatcher(store, {"user_id": "owner", "workspace_id": "A", "conversation_id": "C1"})
        assert [r["id"] for r in store.selected("owner", "A")] == [1, 2]
        result = dispatcher.dispatch(operation("memory_read", memory_ids=[3, 4, 99, 1]))
        assert result["data"] == {"records": [records[2], records[0]], "missing_ids": [4, 99]}
        assert dispatcher.dispatch(operation("memory_read", memory_ids=[]))["data"] == {"records": [], "missing_ids": []}
        for name in ("memory_update", "memory_forget"):
            args = {"memory_id": 4, **({"value": "bad"} if name == "memory_update" else {})}
            foreign = dispatcher.dispatch(operation(name, **args))
            args["memory_id"] = 99
            assert foreign == dispatcher.dispatch(operation(name, **args))
        assert store.snapshot() == records
        assert dispatcher.dispatch(operation("memory_forget", memory_id=3))["ok"]
        saved = dispatcher.dispatch(operation("remember", key="project", value="label", scope="workspace"))
        assert saved["data"]["record"]["workspace_id"] == "A"


def test_unrepresentably_large_valid_ids_are_unavailable():
    with MemoryStore(":memory:") as store:
        store.seed([row()])
        dispatcher = OperationDispatcher(store, OperationContext("owner", "A", "C1"))
        huge = 10**100
        result = dispatcher.dispatch(operation("memory_read", memory_ids=[huge, 1]))
        assert result["data"] == {"records": [row()], "missing_ids": [huge]}
        for name in ("memory_update", "memory_forget"):
            args = {"memory_id": huge, **({"value": "value"} if name == "memory_update" else {})}
            assert dispatcher.dispatch(operation(name, **args))["error"]["code"] == "unavailable_id"
        assert store.snapshot() == [row()]


@pytest.mark.parametrize("op,code", [
    (None, "invalid_arguments"), ({}, "invalid_arguments"),
    (operation("unknown"), "unknown_operation"),
    (operation("remember", key="fact", value="value", scope="wrong"), "invalid_scope"),
    (operation("remember", key="", value="value", scope="global"), "invalid_arguments"),
    (operation("remember", key="fact", value="value", scope="global", user_id="peer"), "invalid_arguments"),
    (operation("remember", key="fact", value="value", scope="global", workspace_id="B"), "invalid_arguments"),
    (operation("remember", key="fact", value="value"), "invalid_arguments"),
    (operation("memory_update", memory_id=True, value="value"), "invalid_arguments"),
    (operation("memory_update", memory_id=1, value="value", key="changed"), "invalid_arguments"),
    (operation("memory_read", memory_ids=[1, 1]), "invalid_arguments"),
    (operation("memory_forget", memory_id=1), "unavailable_id"),
])
def test_invalid_operations_are_recorded_without_mutation(op, code):
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext("owner", "A", "C1"))
        result = dispatcher.dispatch(op)
        assert result["error"]["code"] == code
        assert store.snapshot() == []
        assert dispatcher.events[0]["operation"] == op
        assert dispatcher.events[0]["result"] == result


def test_ordered_partial_success_batch():
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext("owner", "A", "C1"))
        ops = [operation("remember", key="fact", value="one", scope="global"),
               operation("memory_update", memory_id=99, value="missing"),
               operation("remember", key="fact", value="two", scope="global"),
               operation("memory_read", memory_ids=[2, 1])]
        results = dispatcher.dispatch_batch(ops)
        assert [r["ok"] for r in results] == [True, False, True, True]
        assert [r["value"] for r in results[-1]["data"]["records"]] == ["two", "one"]
        assert len(store.snapshot()) == 2
        for op, result in zip(ops, results):
            validate_result(op["name"], result)
        events = dispatcher.events
        assert [e["index"] for e in events] == list(range(4))
        events[0]["result"]["data"]["record"]["value"] = "tampered"
        assert dispatcher.events[0]["result"]["data"]["record"]["value"] == "one"


@pytest.mark.parametrize("reply", [None, {"granted": False, "reply": "No"}, {"granted": True, "reply": "Yes"}])
def test_permission_reply_is_only_exposed_by_operation(reply):
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext("owner", "A", "C1"), reply)
        assert dispatcher.events == []
        result = dispatcher.dispatch(operation("request_permission", question="Save this?", key="health", value="label", scope="global"))
        assert result["data"]["granted"] == (reply["granted"] if reply else False)
        assert dispatcher.events[0]["proposal"] == {"key": "health", "value": "label", "scope": "global"}
        assert store.snapshot() == []
        # Policy and consent violations remain observable persisted operations.
        assert dispatcher.dispatch(operation("remember", key="health", value="label", scope="global"))["ok"]
        json.dumps(dispatcher.events)


def test_infrastructure_failure_is_recorded_and_raised():
    store = MemoryStore(":memory:")
    dispatcher = OperationDispatcher(store, OperationContext("owner", "A", "C1"))
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        dispatcher.dispatch(operation("remember", key="fact", value="value", scope="global"))
    assert dispatcher.events[0]["result"] is None
    assert dispatcher.events[0]["infrastructure_error"]["type"] == "ProgrammingError"


def test_seed_validation_is_atomic_and_empty_seed_cannot_repeat():
    with MemoryStore(":memory:") as store:
        with pytest.raises(ValueError, match="duplicate"):
            store.seed([row(), row()])
        invalid = row(2)
        invalid["scope"] = "workspace"
        with pytest.raises(ContractError):
            store.seed([row(), invalid])
        assert store.snapshot() == []
        store.seed([])
        with pytest.raises(ValueError):
            store.seed([])


def test_checkpoint_isolation_and_sequence_restart(tmp_path):
    persona = load_json("corpus/development.json")["personas"][0]
    first, correction = persona["conversations"][0], persona["conversations"][7]
    with create_checkpoint_store(tmp_path / "first.sqlite", persona, first, "recurring", "write") as store:
        assert all(r["user_id"] != persona["namespaces"]["owner"] for r in store.snapshot())
    with create_checkpoint_store(tmp_path / "correction.sqlite", persona, correction, "recurring", "write") as store:
        assert any(r["value"] == persona["facts"]["original"]["value"] for r in store.snapshot())
    path = tmp_path / "sequence.sqlite"
    with create_checkpoint_store(path, persona, first, "recurring", "sequence") as store:
        assert store.snapshot() == persona["sequence_start"]["peer_controls"]
        saved = store.remember(persona["namespaces"]["owner"], first["workspace_id"], key="actual", value="failure retained", scope="global")
    with reopen_sequence_store(path) as store:
        assert saved in store.snapshot()
        assert len(store.snapshot()) == 5
    with pytest.raises(ValueError, match="new database"):
        create_checkpoint_store(path, persona, correction, "recurring", "sequence")
    with pytest.raises(ValueError):
        reopen_sequence_store(tmp_path / "missing.sqlite")
    for policy in ("conservative", "recurring"):
        with create_checkpoint_store(tmp_path / (policy + ".sqlite"), persona, persona["conversations"][4], policy, "read") as store:
            assert store.snapshot() == sorted(persona["conversations"][4]["tracks"]["read"]["starting_records"], key=lambda r: r["id"])
