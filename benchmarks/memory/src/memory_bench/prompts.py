"""Frozen instruction variants; examples have explicit development-only sources."""

from __future__ import annotations

from .assets import load_json, load_text

PROMPTS = ("baseline", "rules", "examples")
POLICIES = ("conservative", "recurring")


def instruction_text(policy: str, prompt: str) -> str:
    if policy not in POLICIES or prompt not in PROMPTS:
        raise ValueError("unknown policy or prompt")
    return load_text(f"instructions/{policy}-{prompt}.md")


def validate_instructions() -> None:
    manifest = load_json("instruction-sources.json")
    if manifest.get("dataset") != "development" or manifest.get("persona_id") != "P02":
        raise ValueError("instruction examples must use the frozen development P02 sources")
    persona = next(p for p in load_json("corpus/development.json")["personas"] if p["id"] == "P02")
    conversations = {c["id"]: c for c in persona["conversations"]}
    for policy in POLICIES:
        baseline = instruction_text(policy, "baseline")
        rules = instruction_text(policy, "rules")
        examples = instruction_text(policy, "examples")
        if baseline != load_text(f"policies/{policy}.md") or not rules.startswith(baseline) or not examples.startswith(rules):
            raise ValueError("variants must retain the complete frozen policy requirements")
        for source in manifest["examples"]:
            message = conversations[source["conversation_id"]]["messages"][source["message_index"]]
            if source["excerpt"] not in message or source["excerpt"] not in examples:
                raise ValueError("example differs from its development source")
        if any(word in examples for word in ("policy_expectations", "accepted_aliases", "expected_current_facts")):
            raise ValueError("private gold annotation in instruction text")
