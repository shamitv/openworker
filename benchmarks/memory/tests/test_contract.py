import pytest

from memory_bench.contract import ContractError, contract, validate_operation, validate_record, validate_response, validate_result
from memory_bench.validation import validate_contract


def row():
    return {"id": 1, "user_id": "owner", "workspace_id": None, "scope": "global", "key": "my own descriptive key", "value": "current fact", "history": []}


def test_frozen_contract():
    validate_contract()
    validate_record(row())
    validate_record({**row(), "workspace_id": "A", "scope": "workspace"})


@pytest.mark.parametrize("changes", [
    {"id": True}, {"id": 0}, {"id": "1"}, {"user_id": " "},
    {"scope": "session"}, {"scope": "workspace", "workspace_id": None},
    {"scope": "global", "workspace_id": "A"}, {"history": "old text"},
    {"key": ""}, {"value": " "}, {"unexpected": "field"},
])
def test_record_rejects_invalid_types_and_scope(changes):
    with pytest.raises(ContractError):
        validate_record({**row(), **changes})


@pytest.mark.parametrize("name,args", [
    ("remember", {"key": "unlisted invented key", "value": "new", "scope": "global"}),
    ("remember", {"key": "another", "value": "new", "scope": "workspace", "history": ["previous value"]}),
    ("memory_read", {"memory_ids": [1, 99]}),
    ("memory_read", {"memory_ids": []}),
    ("memory_update", {"memory_id": 1, "value": "corrected"}),
    ("memory_forget", {"memory_id": 1}),
    ("request_permission", {"question": "Save this?", "key": "private label", "value": "synthetic", "scope": "global"}),
])
def test_valid_operations_and_free_form_keys(name, args):
    validate_operation({"name": name, "arguments": args})


@pytest.mark.parametrize("call,code", [
    ({"name": "unknown", "arguments": {}}, "unknown_operation"),
    ({"name": "remember", "arguments": {"key": "k", "value": "v", "scope": "session"}}, "invalid_scope"),
    ({"name": "remember", "arguments": {"key": "k", "value": "v"}}, "invalid_arguments"),
    ({"name": "memory_forget", "arguments": {"memory_id": True}}, "invalid_arguments"),
    ({"name": "memory_read", "arguments": {"memory_ids": [1, 1]}}, "invalid_arguments"),
    ({"name": "memory_update", "arguments": {"memory_id": 1, "value": "v", "scope": "global"}}, "invalid_arguments"),
    ({"name": "memory_update", "arguments": {"memory_id": 1, "value": "v", "key": "changed"}}, "invalid_arguments"),
    ({"name": "remember", "arguments": {"key": "k", "value": "v", "scope": "global", "user_id": "peer"}}, "invalid_arguments"),
    ({"name": "remember", "arguments": {"key": "k", "value": "v", "scope": "workspace", "workspace_id": "B"}}, "invalid_arguments"),
])
def test_operation_errors_are_explicit(call, code):
    with pytest.raises(ContractError) as caught:
        validate_operation(call)
    assert caught.value.code == code


@pytest.mark.parametrize("response", [
    {}, {"answer": "done"}, {"answer": None, "operations": []},
    {"answer": "done", "operations": "none"},
    {"answer": "done", "operations": [{"name": "remember"}]},
    {"answer": "done", "operations": [], "extra": True},
])
def test_malformed_envelopes_are_terminal_format_errors(response):
    with pytest.raises(ContractError) as caught:
        validate_response(response)
    assert caught.value.code == "format_error"


def test_parsed_argument_error_is_not_an_envelope_failure():
    response = {"answer": "provisional", "operations": [{"name": "memory_forget", "arguments": {"memory_id": "bad"}}]}
    validate_response(response)
    with pytest.raises(ContractError):
        validate_operation(response["operations"][0])


def test_success_and_error_results():
    validate_result("remember", {"ok": True, "data": {"record": row()}, "error": None})
    validate_result("memory_read", {"ok": True, "data": {"records": [], "missing_ids": [99]}, "error": None})
    validate_result("memory_forget", {"ok": False, "data": None, "error": {"code": "unavailable_id", "message": "Unavailable"}})
    for bad in ({"ok": False, "data": {}, "error": None}, {"ok": True, "data": None, "error": None}, {"ok": True, "data": {"record": row()}, "error": {"code": "unavailable_id", "message": "bad"}}):
        with pytest.raises(ContractError):
            validate_result("remember", bad)


def test_contract_has_no_gold_keys_or_values(development):
    schema = contract()["operations"]["remember"]["arguments"]["properties"]["key"]
    assert "enum" not in schema
    assert "default" not in schema
    assert schema == {"type": "string", "minLength": 1}
