"""Track setup and serializable evidence; no model execution or expected-state repair."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .assets import canonical_json
from .contract import ContractError, validate_operation, validate_record, validate_result
from .operations import OperationContext
from .store import MemoryStore

TRACKS = ("write", "read", "sequence")
POLICIES = ("conservative", "recurring")


def starting_records(persona: dict, conversation: dict, policy: str, track: str) -> list[dict]:
    if policy not in POLICIES or track not in TRACKS:
        raise ValueError("unknown policy or track")
    if track == "sequence":
        if persona["sequence_start"]["owner_records"]:
            raise ValueError("sequence owner state must start empty")
        records = persona["sequence_start"]["peer_controls"]
    else:
        checkpoint = conversation["tracks"][track]
        if not checkpoint["enabled"]:
            raise ValueError("checkpoint is disabled")
        records = checkpoint["starting_records"]
        if track == "write":
            records = records[policy]
    return deepcopy(records)


def create_checkpoint_store(path: str | Path, persona: dict, conversation: dict, policy: str, track: str) -> MemoryStore:
    records = starting_records(persona, conversation, policy, track)
    if str(path) != ":memory:" and Path(path).exists():
        raise ValueError("checkpoint requires a new database path")
    store = MemoryStore(path)
    try:
        store.seed(records)
    except Exception:
        store.close()
        raise
    return store


def reopen_sequence_store(path: str | Path) -> MemoryStore:
    if not Path(path).is_file():
        raise ValueError("sequence database does not exist")
    return MemoryStore(path)


def validate_snapshot(records: list[dict] | None) -> None:
    if records is None:
        return
    if not isinstance(records, list):
        raise ValueError("snapshot must be a list or null")
    for record in records:
        validate_record(record)
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("duplicate snapshot record IDs")


def checkpoint_evidence(*, condition: dict, track: str, starting_records: list[dict] | None,
                        final_records: list[dict] | None, turns: list[dict], status: str,
                        errors: list[dict] | None = None) -> dict:
    """Copy captured evidence. A turn has message_index, answer, status, operations.

    operations are dispatcher events in execution order, excluding provisional text
    from the final answer. Missing state is represented by null, never an empty list.
    """
    evidence = {"schema_version": 1, "condition": condition, "track": track,
                "starting_records": starting_records, "final_records": final_records,
                "turns": turns, "status": status, "errors": errors or []}
    validate_evidence(evidence)
    return deepcopy(evidence)


def validate_evidence(evidence: dict) -> None:
    if evidence.get("schema_version") != 1 or evidence.get("track") not in TRACKS:
        raise ValueError("unsupported checkpoint evidence")
    if not isinstance(evidence["condition"], dict) or not isinstance(evidence["status"], str) or not evidence["status"]:
        raise ValueError("invalid condition or execution status")
    validate_snapshot(evidence["starting_records"])
    validate_snapshot(evidence["final_records"])
    if not isinstance(evidence["turns"], list) or not isinstance(evidence["errors"], list):
        raise ValueError("turns and errors must be lists")
    indices = []
    for turn in evidence["turns"]:
        index = turn["message_index"]
        if type(index) is not int or index < 0:
            raise ValueError("invalid message index")
        indices.append(index)
        if not isinstance(turn["status"], str) or not turn["status"]:
            raise ValueError("invalid turn status")
        if turn["answer"] is not None and not isinstance(turn["answer"], str):
            raise ValueError("answer must be text or null")
        if not isinstance(turn["operations"], list):
            raise ValueError("operations must be ordered dispatcher events")
        for event in turn["operations"]:
            if not isinstance(event, dict) or not {"context", "operation", "result"} <= event.keys():
                raise ValueError("incomplete operation evidence")
            OperationContext(**event["context"])
            operation, result = event["operation"], event["result"]
            if result is None:
                if "infrastructure_error" not in event:
                    raise ValueError("missing operation result without infrastructure failure")
                continue
            name = operation.get("name", "") if isinstance(operation, dict) else ""
            validate_result(name, result)
            try:
                validate_operation(operation)
            except ContractError as exc:
                if result["ok"] or result["error"]["code"] != exc.code:
                    raise ValueError("invalid operation has inconsistent result") from exc
    if indices != sorted(set(indices)):
        raise ValueError("turn indices must be unique and ordered")
    canonical_json(evidence)
