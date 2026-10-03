"""Strict validation of the frozen contract, with no store or model client."""

from __future__ import annotations

import re

from .assets import load_json


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def validate_schema(value, schema: dict, path: str = "$", code: str = "invalid_arguments") -> None:
    """Validate the deliberately small JSON Schema subset used by our assets."""
    kind = schema.get("type")
    valid = {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: type(value) is int,
        "number": lambda: type(value) in (int, float),
        "boolean": lambda: type(value) is bool,
        "null": lambda: value is None,
    }
    kinds = kind if isinstance(kind, list) else [kind]
    if kind is not None and not any(valid[item]() for item in kinds):
        raise ContractError(code, f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(code, f"{path}: value is outside the allowed enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ContractError(code, f"{path}: missing fields {sorted(missing)}")
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            raise ContractError(code, f"{path}: unexpected fields {sorted(value.keys() - properties.keys())}")
        for key, item in value.items():
            child = properties.get(key, schema.get("additionalProperties", {}))
            if isinstance(child, dict):
                validate_schema(item, child, f"{path}.{key}", code)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ContractError(code, f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractError(code, f"{path}: too many items")
        if schema.get("uniqueItems") and any(item in value[:i] for i, item in enumerate(value)):
            raise ContractError(code, f"{path}: duplicate items")
        for index, item in enumerate(value):
            validate_schema(item, schema.get("items", {}), f"{path}[{index}]", code)
    if isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            raise ContractError(code, f"{path}: empty or short string")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ContractError(code, f"{path}: invalid string pattern")
    if type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        raise ContractError(code, f"{path}: below minimum")


def contract() -> dict:
    return load_json("contract.json")


def validate_record(record: dict) -> None:
    validate_schema(record, contract()["record"])
    if (record["scope"] == "global") != (record["workspace_id"] is None):
        raise ContractError("invalid_scope", "global records need null workspace; workspace records need a workspace")


def validate_operation(operation: dict) -> None:
    validate_schema(operation, contract()["operation_envelope"])
    schema = contract()["operations"].get(operation["name"])
    if schema is None:
        raise ContractError("unknown_operation", f"unknown operation {operation['name']!r}")
    arguments = operation["arguments"]
    if "scope" in arguments and arguments["scope"] not in ("global", "workspace"):
        raise ContractError("invalid_scope", "scope must be global or workspace")
    validate_schema(arguments, schema["arguments"])


def validate_result(name: str, result: dict) -> None:
    schemas = contract()
    validate_schema(result, schemas["result_envelope"])
    if result["ok"]:
        if result["error"] is not None:
            raise ContractError("invalid_arguments", "successful result cannot have an error")
        validate_schema(result["data"], schemas["operations"][name]["success"])
        if name in ("remember", "memory_update"):
            validate_record(result["data"]["record"])
        if name == "memory_read":
            for row in result["data"]["records"]:
                validate_record(row)
    else:
        if result["data"] is not None:
            raise ContractError("invalid_arguments", "failed result cannot have data")
        validate_schema(result["error"], schemas["error"])


def validate_response(response: dict) -> None:
    # Parsed argument errors belong to the dispatcher, not the response envelope.
    validate_schema(response, contract()["json_response"], code="format_error")
