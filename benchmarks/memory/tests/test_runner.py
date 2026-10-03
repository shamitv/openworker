import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from memory_bench.adapters import NativeAdapter, adapter_for
from memory_bench.assets import load_json
from memory_bench.client import LocalClient
from memory_bench.operations import OperationContext, OperationDispatcher
from memory_bench.runner import run_turn
from memory_bench.store import MemoryStore


def completion(value, interface, request_index=0):
    if interface == "json":
        message = {"role": "assistant", "content": json.dumps(value)}
    elif set(value) != {"answer", "operations"}:
        message = {"content": 42}
    else:
        message = {"role": "assistant", "content": value["answer"], "tool_calls": [
            {"id": f"call-{request_index}-{i}", "type": "function", "function": {"name": op["name"],
                "arguments": json.dumps(op["arguments"])}} for i, op in enumerate(value["operations"])]}
    return {"model": "exact", "choices": [{"message": message, "finish_reason": "stop"}]}


@pytest.mark.parametrize("index", range(10))
def test_frozen_lifecycle_executes_identically_through_both_http_adapters(index):
    fixture = load_json("fixtures/lifecycle.json")["fixtures"][index]
    outputs = []
    for interface in ("json", "native"):
        current_time, observed_requests = [0], []
        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"id": "exact"}]})
            body = json.loads(request.content)
            number = len(observed_requests)
            observed_requests.append(body)
            trace = fixture["requests"][number]
            current_time[0] = trace["elapsed_seconds"]
            if number and fixture["id"] == "read_before_final":
                assert "Grade 8" in json.dumps(body["messages"][-1])
            return httpx.Response(200, json=completion(trace["response"], interface, number))
        async def scenario():
            with MemoryStore(":memory:") as store:
                if fixture["id"] == "read_before_final":
                    store.seed(fixture["requests"][0]["results"][0]["result"]["data"]["records"])
                dispatcher = OperationDispatcher(store, OperationContext("P01-owner", "P01-w1", "C1"))
                async with LocalClient("http://localhost/v1", transport=httpx.MockTransport(handler)) as client:
                    await client.verify_models(["exact"])
                    result = await run_turn(client, "exact", interface, [{"role": "user", "content": "test"}],
                        dispatcher, clock=lambda: current_time[0])
                expected = fixture["expected"]
                assert (result["status"], result["answer"], result["operation_batches"], result["requests"]) == (
                    expected["status"], expected["final_answer"], expected["batches"], expected["requests"])
                if "required_committed_records" in fixture:
                    assert store.snapshot() == fixture["required_committed_records"]
                if fixture["id"] == "ordered_mixed_batch":
                    assert [e["result"]["ok"] for e in result["operations"]] == [True, False, True]
                    assert len(observed_requests[-1]["messages"]) == (3 if interface == "json" else 5)
                return {k: result[k] for k in ("answer", "status", "operations", "provisional_answers", "operation_batches", "requests")}, store.snapshot()
        outputs.append(asyncio.run(scenario()))
    assert outputs[0] == outputs[1]


def test_native_unparseable_arguments_get_explicit_feedback_without_repair():
    calls = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "bad", "type": "function", "function": {"name": "remember", "arguments": "{broken"}}]}}]})
        assert json.loads(body["messages"][-1]["content"])["error"]["code"] == "invalid_arguments"
        return httpx.Response(200, json={"choices": [{"message": {"content": "No save."}}]})
    async def scenario():
        with MemoryStore(":memory:") as store:
            dispatcher = OperationDispatcher(store, OperationContext("u", "w", "c"))
            async with LocalClient("http://localhost/v1", transport=httpx.MockTransport(handler)) as client:
                await client.verify_models(["exact"])
                result = await run_turn(client, "exact", "native", [], dispatcher)
            assert result["status"] == "complete"
            assert result["operations"][0]["operation"]["arguments"] == "{broken"
            assert result["operations"][0]["result"]["error"]["code"] == "invalid_arguments"
            assert store.snapshot() == []
    asyncio.run(scenario())
    assert len(calls) == 2


@pytest.mark.parametrize("message", [{"content": None}, {"content": " "}, {"role": "user", "content": "bad"},
    {"content": "text", "tool_calls": None}, {"content": [], "tool_calls": []}])
def test_malformed_native_final_is_terminal(message):
    async def scenario():
        class Client:
            async def completion(self, *args, **kwargs):
                return {"choices": [{"message": message}]}
        with MemoryStore(":memory:") as store:
            result = await run_turn(Client(), "exact", "native", [], OperationDispatcher(store, OperationContext("u", "w", "c")))
            assert result["status"] == "format_error"
            assert result["requests"] == 1
            assert result["answer"] is None
    asyncio.run(scenario())


def test_deadline_includes_operations_and_retains_successful_write():
    now = [0]
    async def scenario():
        class Client:
            async def completion(self, *args, **kwargs):
                return completion({"answer": "provisional", "operations": [
                    {"name": "remember", "arguments": {"key": "fact", "value": "retained", "scope": "global"}},
                    {"name": "memory_forget", "arguments": {"memory_id": 1}}]}, "json")
        with MemoryStore(":memory:") as store:
            dispatcher = OperationDispatcher(store, OperationContext("u", "w", "c"))
            original = dispatcher.dispatch
            def slow(operation):
                result = original(operation)
                now[0] = 180
                return result
            dispatcher.dispatch = slow
            result = await run_turn(Client(), "exact", "json", [], dispatcher, clock=lambda: now[0])
            assert result["status"] == "deadline"
            assert len(result["operations"]) == 1
            assert store.snapshot()[0]["value"] == "retained"
            assert result["answer"] is None
    asyncio.run(scenario())


def test_sqlite_lock_wait_is_bounded_by_remaining_budget(tmp_path):
    import sqlite3
    import time
    path = tmp_path / "locked.sqlite"
    with MemoryStore(path) as store:
        other = sqlite3.connect(path)
        try:
            other.execute("BEGIN IMMEDIATE")
            store.set_deadline(time.monotonic() + 0.03)
            started = time.monotonic()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                store.remember("u", "w", key="k", value="v", scope="global")
            assert time.monotonic() - started < 0.5
        finally:
            store.set_deadline(None)
            other.close()
        assert store.snapshot() == []


def test_native_duplicate_call_ids_are_format_failure():
    value = completion({"answer": "", "operations": [{"name": "memory_read", "arguments": {"memory_ids": []}}]*2}, "native")
    value["choices"][0]["message"]["tool_calls"][1]["id"] = "call-0-0"
    with pytest.raises(ValueError, match="duplicate"):
        NativeAdapter().parse(value)
