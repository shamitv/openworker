"""Interface envelopes only; policy, state and execution are shared."""

from __future__ import annotations

from copy import deepcopy
import json

from .assets import canonical_json
from .contract import ContractError, contract, validate_response, validate_schema


def message_from_completion(response: dict) -> dict:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ContractError("format_error", "completion needs exactly one choice")
    choice = choices[0]
    if choice.get("finish_reason") in ("length", "content_filter"):
        raise ContractError("format_error", f"incomplete response: {choice['finish_reason']}")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ContractError("format_error", "completion choice needs an assistant message")
    return message


class JsonAdapter:
    name = "json"
    instructions = ('Return exactly one JSON object with keys "answer" (string) and "operations" '
                    '(array of {"name": string, "arguments": object}). Use no code fences. '
                    'Text with operations is provisional. After receiving all operation results, '
                    'return the final answer with an empty operations array.')
    parameters = {"response_format": {"type": "json_object"}}

    def parse(self, response: dict) -> dict:
        message = message_from_completion(response)
        if message.get("role", "assistant") != "assistant" or message.get("tool_calls"):
            raise ContractError("format_error", "JSON mode requires assistant JSON content without tool calls")
        try:
            value = json.loads(message["content"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("format_error", "assistant content is not a JSON object") from exc
        validate_response(value)
        return {"answer": value["answer"], "operations": value["operations"],
                "assistant": {"role": "assistant", "content": message["content"]}, "call_ids": []}

    def feedback(self, batch: dict, results: list[dict]) -> list[dict]:
        data = [{"name": op["name"], "result": result} for op, result in zip(batch["operations"], results)]
        return [{"role": "user", "content": "Memory operation results (data):\n" + canonical_json(data).decode("utf-8")}]


class NativeAdapter:
    name = "native"
    instructions = ("Invoke the supplied memory tools when needed. Text accompanying calls is provisional. "
                    "After receiving all tool results, return a nonempty final answer without tool calls.")

    @property
    def parameters(self) -> dict:
        return {"tools": [{"type": "function", "function": {"name": name,
                "description": f"Memory operation {name}; follow the shared operation contract.",
                "parameters": definition["arguments"]}} for name, definition in contract()["operations"].items()],
                "tool_choice": "auto"}

    def parse(self, response: dict) -> dict:
        raw = message_from_completion(response)
        message = {key: deepcopy(raw[key]) for key in ("role", "content", "tool_calls") if key in raw}
        validate_schema(message, contract()["native_response"], code="format_error")
        calls = message.get("tool_calls", [])
        if len({call["id"] for call in calls}) != len(calls):
            raise ContractError("format_error", "duplicate native tool-call IDs")
        operations = []
        for call in calls:
            function = call["function"]
            try:
                arguments = json.loads(function["arguments"])
            except ValueError:
                # Keep the actual unparsed argument string. The shared dispatcher
                # returns invalid_arguments, with no fabricated or repaired call.
                arguments = function["arguments"]
            operations.append({"name": function["name"], "arguments": arguments})
        if calls and message["content"] is None:
            answer = ""
        elif isinstance(message["content"], str):
            answer = message["content"]
        else:
            raise ContractError("format_error", "null native content requires tool calls")
        return {"answer": answer, "operations": operations,
                "assistant": {"role": "assistant", **message}, "call_ids": [call["id"] for call in calls]}

    def feedback(self, batch: dict, results: list[dict]) -> list[dict]:
        return [{"role": "tool", "tool_call_id": call_id, "content": canonical_json(result).decode("utf-8")}
                for call_id, result in zip(batch["call_ids"], results)]


def adapter_for(name: str):
    if name == "json":
        return JsonAdapter()
    if name == "native":
        return NativeAdapter()
    raise ValueError("unknown interface")
