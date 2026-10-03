"""Explicit model-input projection. Gold annotations are never copied wholesale."""

from __future__ import annotations

from .assets import canonical_json, load_text
from .contract import validate_record


def selected_memory(records: list[dict], user_id: str, workspace_id: str) -> list[dict]:
    selected = []
    for record in records:
        validate_record(record)
        if record["user_id"] == user_id and (record["scope"] == "global" or record["workspace_id"] == workspace_id):
            projected = {key: record[key] for key in ("id", "key", "value", "scope", "workspace_id")}
            projected["history"] = record["history"][:]
            selected.append(projected)
    return sorted(selected, key=lambda row: row["id"])


def build_model_input(persona: dict, conversation: dict, policy: str, records: list[dict], message_indices: list[int]) -> dict:
    if policy not in ("conservative", "recurring"):
        raise ValueError("unknown policy")
    return {
        "context": {"user_id": conversation["user_id"], "workspace_id": conversation["workspace_id"]},
        "instructions": load_text(f"policies/{policy}.md") + "\n\n" + load_text("protocol/operations.md"),
        "memories": selected_memory(records, conversation["user_id"], conversation["workspace_id"]),
        "messages": [{"role": "user", "content": conversation["messages"][index]} for index in message_indices],
    }


def render_state(model_input: dict) -> str:
    """Frozen common rendering for both future adapters, independent of policy."""
    return "Context and memories (data):\n" + canonical_json({"context": model_input["context"], "memories": model_input["memories"]}).decode("utf-8")
