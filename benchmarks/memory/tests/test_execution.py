import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from memory_bench.capture import read_checkpoints
from memory_bench.execution import collect
from memory_bench.experiments import schedule
from memory_bench.scoring import score_checkpoint
from memory_bench.experiments import isolated_persona


def tiny_schedule(tracks=("write", "read", "sequence")):
    rows = schedule(dataset="development", models=["exact"], policies=["recurring"], prompts=["baseline"],
                    interfaces=["json"], tracks=list(tracks), runs=1)
    rows = [row for row in rows if row["condition"]["persona_id"] == "P01"]
    for row in rows:
        allowed = {"C1", "C4", "C5", "C10"} if row["track"] != "read" else {"C5"}
        row["checkpoints"] = [c for c in row["checkpoints"] if c["conversation_id"] in allowed]
    return rows


def test_collection_preserves_boundaries_injection_operations_and_cleanup(tmp_path, development):
    requests = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        body = json.loads(request.content)
        requests.append(body)
        messages = body["messages"]
        current = messages[-1]["content"]
        if current.startswith("Memory operation results"):
            value = {"answer": "Saved.", "operations": []}
        elif "Remember for all my future chats" in current:
            value = {"answer": "provisional", "operations": [{"name": "remember", "arguments": {
                "key": "personal_planning_notebook_label", "value": "Solace-P01", "scope": "global"}}]}
        else:
            value = {"answer": "UNKNOWN", "operations": []}
        return httpx.Response(200, json={"model": "exact", "choices": [{"message": {"content": json.dumps(value)}}]})
    manifest = asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=tmp_path / "run",
                                   schedule=tiny_schedule(), requested={}, transport=httpx.MockTransport(handler)))
    captures = read_checkpoints(tmp_path / "run")
    assert manifest["status"] == "complete"
    assert manifest["cleanup"]["status"] == "complete"
    assert not (tmp_path / "run" / "stores").exists()
    assert manifest["coverage"]["unexecuted"] == 0
    sequence = {c["conversation_id"]: c for c in captures if c["evidence"]["track"] == "sequence"}
    assert all(r["user_id"].endswith("-peer") for r in sequence["C1"]["evidence"]["starting_records"])
    assert any(r["value"] == "Solace-P01" for r in sequence["C5"]["injected_memory"])
    assert sequence["C4"]["evidence"]["turns"][0]["provisional_answers"] == ["provisional"]
    first_followup = requests[1]["messages"]
    assert len(first_followup) == 4
    assert first_followup[1]["role"] == "user" and first_followup[2]["role"] == "assistant"
    # All new conversations begin with only their current user turn.
    for body in requests:
        if len(body["messages"]) == 2:
            assert body["messages"][-1]["role"] == "user"
        assert sum(m["role"] == "system" for m in body["messages"]) == 1
        assert body["messages"][0]["role"] == "system"
        assert "Interface response envelope (instructions):" in body["messages"][0]["content"]
        assert "policy_expectations" not in json.dumps(body)
        assert "permission_reply" not in json.dumps(body)
    assert all(e["usage"] is None for e in manifest["requests"])
    for row in captures:
        p = isolated_persona(development["personas"][0], row["track_id"])
        c = next(c for c in p["conversations"] if c["id"] == row["conversation_id"])
        assert score_checkpoint(p, c, "recurring", row["evidence"]["track"], row["evidence"])
    journal = [json.loads(line) for line in (tmp_path / "run" / "diagnostics.jsonl").read_text().splitlines()]
    assert any(e["type"] == "store_reopened" for e in journal)
    assert any(e["type"] == "operation" and e["snapshot"] for e in journal)


def test_catalog_failure_preserves_all_unexecuted_coverage_without_inference(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": []})
    value = asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=tmp_path / "failed",
        schedule=tiny_schedule(), requested={}, transport=httpx.MockTransport(handler)))
    assert value["status"] == "failed"
    assert value["errors"][0]["code"] == "catalog_error"
    assert value["coverage"]["unexecuted"] == value["coverage"]["checkpoints"]
    assert len(read_checkpoints(tmp_path / "failed")) == value["coverage"]["checkpoints"]
    assert len(calls) == 1


def test_model_format_failures_are_measured_and_do_not_hide_coverage(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "exact"}]} if request.method == "GET" else
            {"choices": [{"message": {"content": "bad json"}}]})
    value = asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=tmp_path / "measured",
        schedule=tiny_schedule(), requested={}, transport=httpx.MockTransport(handler)))
    assert value["status"] == "complete"
    assert value["coverage"]["failed"] == value["coverage"]["checkpoints"]
    assert value["coverage"]["unexecuted"] == 0


def test_api_failure_stops_without_retry_and_retains_partial_evidence(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        raise httpx.ConnectError("disconnected")
    value = asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=tmp_path / "failed",
        schedule=tiny_schedule(), requested={}, transport=httpx.MockTransport(handler)))
    assert value["status"] == "failed"
    assert len(calls) == 2
    assert value["coverage"]["failed"] == 1
    assert value["coverage"]["unexecuted"] > 0
    assert read_checkpoints(tmp_path / "failed")[0]["evidence"]["turns"][0]["status"] == "api_error"


def test_track_order_does_not_change_scores_or_snapshots(tmp_path, development):
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "exact"}]} if request.method == "GET" else
            {"choices": [{"message": {"content": '{"answer":"UNKNOWN","operations":[]}'}}]})
    results = []
    rows = tiny_schedule()
    for i, ordered in enumerate((rows, list(reversed(rows)))):
        path = tmp_path / str(i)
        asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=path,
            schedule=ordered, requested={}, transport=httpx.MockTransport(handler)))
        scores = {}
        for row in read_checkpoints(path):
            p = isolated_persona(development["personas"][0], row["track_id"])
            c = next(c for c in p["conversations"] if c["id"] == row["conversation_id"])
            evidence = deepcopy(row["evidence"])
            for turn in evidence["turns"]:
                turn.pop("duration_seconds")
            scores[row["checkpoint_id"]] = score_checkpoint(p, c, "recurring", evidence["track"], evidence)
        results.append(scores)
    assert results[0] == results[1]


def test_interrupt_retains_current_turn_and_unexecuted_coverage(tmp_path):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        raise asyncio.CancelledError()
    path = tmp_path / "interrupted"
    result = asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=path,
        schedule=tiny_schedule(), requested={}, transport=httpx.MockTransport(handler)))
    assert result["status"] == "interrupted"
    assert result["coverage"]["failed"] == 1
    assert result["coverage"]["unexecuted"] > 0
    assert result["cleanup"]["status"] == "complete"
    assert read_checkpoints(path)[0]["evidence"]["turns"][0]["status"] == "interrupted"
