import copy

import pytest

from memory_bench.assets import asset_hashes, load_json, load_text
from memory_bench.model_input import build_model_input
from memory_bench.prompts import instruction_text, validate_instructions


def test_six_variants_preserve_all_policy_requirements():
    validate_instructions()
    hashes = asset_hashes()
    for policy in ("conservative", "recurring"):
        baseline = instruction_text(policy, "baseline")
        rules = instruction_text(policy, "rules")
        examples = instruction_text(policy, "examples")
        assert baseline == load_text(f"policies/{policy}.md")
        assert rules.startswith(baseline)
        assert examples.startswith(rules)
        assert len({hashes[f"instructions/{policy}-{p}.md"] for p in ("baseline", "rules", "examples")}) == 3


def test_prompt_selection_does_not_project_gold_or_future_turns(development):
    persona = development["personas"][0]
    conversation = copy.deepcopy(persona["conversations"][0])
    conversation["policy_expectations"] = "SECRET-GOLD"
    conversation["permission_script"] = "SECRET-PERMISSION"
    for prompt in ("baseline", "rules", "examples"):
        value = build_model_input(persona, conversation, "conservative", [], [0], prompt=prompt)
        assert value["messages"] == [{"role": "user", "content": conversation["messages"][0]}]
        assert "SECRET-" not in str(value)
        assert conversation["messages"][1] not in str(value)


def test_examples_have_only_development_source_references():
    manifest = load_json("instruction-sources.json")
    assert manifest["dataset"] == "development"
    assert manifest["persona_id"] == "P02"
    assert all(source["conversation_id"].startswith("C") for source in manifest["examples"])
    for policy in ("conservative", "recurring"):
        assert "P01" not in instruction_text(policy, "examples")


@pytest.mark.parametrize("policy,prompt", [("bad", "baseline"), ("recurring", "bad")])
def test_unknown_prompt_or_policy_is_rejected(policy, prompt):
    with pytest.raises(ValueError):
        instruction_text(policy, prompt)
