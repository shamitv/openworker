"""Reproducible matrix scheduling and deterministic namespace isolation."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import product

from .assets import canonical_json, load_json

FACTORS = {"dataset": ("development", "heldout"), "policies": ("conservative", "recurring"),
           "prompts": ("baseline", "rules", "examples"), "interfaces": ("json", "native"),
           "tracks": ("write", "read", "sequence")}


def identity(value: dict) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()[:24]


def selections(values: list[str], allowed: tuple[str, ...], name: str) -> list[str]:
    if not values or len(values) != len(set(values)) or not set(values) <= set(allowed):
        raise ValueError(f"invalid or duplicate {name} selection")
    return [value for value in allowed if value in values]


def schedule(*, dataset: str, models: list[str], policies: list[str], prompts: list[str],
             interfaces: list[str], tracks: list[str], runs: int, smoke: bool = False) -> list[dict]:
    if dataset not in FACTORS["dataset"] or type(runs) is not int or runs < 1:
        raise ValueError("invalid dataset or repetition count")
    if not models or len(models) != len(set(models)):
        raise ValueError("select unique model IDs")
    chosen = {name: selections(values, FACTORS[name], name) for name, values in
              (("policies", policies), ("prompts", prompts), ("interfaces", interfaces), ("tracks", tracks))}
    if smoke and (dataset != "development" or len(models) != 1 or runs != 1 or
                  chosen != {"policies": ["conservative", "recurring"], "prompts": ["baseline"],
                             "interfaces": ["json", "native"], "tracks": ["write", "read", "sequence"]}):
        raise ValueError("smoke selections are fixed")
    personas = load_json(f"corpus/{dataset}.json")["personas"]
    if smoke:
        personas = [p for p in personas if p["id"] == "P01"]
    output = []
    for model, policy, prompt, interface, persona, repetition in product(sorted(models), chosen["policies"],
            chosen["prompts"], chosen["interfaces"], personas, range(1, runs + 1)):
        condition = {"dataset": dataset, "model": model, "policy": policy, "prompt": prompt,
                     "interface": interface, "persona_id": persona["id"], "repetition": repetition}
        condition_id = identity(condition)
        for track in chosen["tracks"]:
            track_id = identity({"condition": condition, "track": track})
            checkpoints = [{"checkpoint_id": f"{track_id}-{c['id']}", "conversation_id": c["id"],
                            "message_indices": c["tracks"][track]["message_indices"][:], "status": "unexecuted"}
                           for c in persona["conversations"] if c["tracks"][track]["enabled"]]
            output.append({"condition": condition.copy(), "condition_id": condition_id, "track": track,
                           "track_id": track_id, "status": "unexecuted", "checkpoints": checkpoints})
    return output


def isolated_persona(persona: dict, track_id: str) -> dict:
    """Qualify all abstract namespaces; facts/messages/gold meanings stay intact."""
    value = deepcopy(persona)
    users = {old: f"{track_id}:{old}" for old in value["namespaces"].values()}
    workspaces = {old: f"{track_id}:{old}" for old in value["workspaces"].values()}
    def visit(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "user_id" and isinstance(child, str):
                    node[key] = users[child]
                elif key == "workspace_id" and child is not None:
                    node[key] = workspaces[child]
                else:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    value["namespaces"] = {name: users[old] for name, old in value["namespaces"].items()}
    value["workspaces"] = {name: workspaces[old] for name, old in value["workspaces"].items()}
    return value
