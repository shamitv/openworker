from copy import deepcopy

import pytest

from memory_bench.experiments import isolated_persona, schedule


def fixed(**overrides):
    return schedule(**{"dataset": "development", "models": ["exact"], "policies": ["conservative", "recurring"],
        "prompts": ["baseline"], "interfaces": ["json", "native"], "tracks": ["write", "read", "sequence"],
        "runs": 1, "smoke": True, **overrides})


def test_smoke_has_exact_fixed_coverage_and_stable_ids():
    value = fixed()
    assert len(value) == 12
    assert sum(len(row["checkpoints"]) for row in value) == 148
    assert sum(len(c["message_indices"]) for row in value for c in row["checkpoints"]) == 172
    assert {row["condition"]["persona_id"] for row in value} == {"P01"}
    assert len({row["track_id"] for row in value}) == 12
    assert value == fixed(policies=["recurring", "conservative"], tracks=["sequence", "write", "read"], interfaces=["native", "json"])


@pytest.mark.parametrize("overrides", [{"models": ["a", "b"]}, {"runs": 2}, {"dataset": "heldout"},
    {"prompts": ["examples"]}, {"tracks": ["write"]}, {"interfaces": ["json"]}])
def test_smoke_cannot_expand_or_change_coverage(overrides):
    with pytest.raises(ValueError):
        fixed(**overrides)


def test_matrix_filters_and_repetitions_are_explicit():
    value = schedule(dataset="heldout", models=["b", "a"], policies=["recurring"], prompts=["rules"],
                     interfaces=["native"], tracks=["read"], runs=2)
    assert len(value) == 60
    assert {v["condition"]["repetition"] for v in value} == {1, 2}
    assert {v["condition"]["persona_id"] for v in value} == {f"H{i:02}" for i in range(1, 16)}
    assert len({v["condition_id"] for v in value}) == 60


@pytest.mark.parametrize("overrides", [{"runs": 0}, {"tracks": ["write", "write"]}, {"policies": []}, {"prompts": ["unknown"]}])
def test_invalid_matrix_is_rejected(overrides):
    with pytest.raises(ValueError):
        fixed(smoke=False, **overrides)


def test_namespaces_are_isolated_without_changing_messages_or_labels(development):
    persona = development["personas"][0]
    before = deepcopy(persona)
    a, b = isolated_persona(persona, "a"), isolated_persona(persona, "b")
    assert persona == before
    assert set(a["namespaces"].values()).isdisjoint(b["namespaces"].values())
    assert set(a["workspaces"].values()).isdisjoint(b["workspaces"].values())
    assert a["facts"] == persona["facts"]
    assert a["conversations"][0]["messages"] == persona["conversations"][0]["messages"]
    for conversation in a["conversations"]:
        assert conversation["user_id"].startswith("a:")
        for records in conversation["tracks"]["write"]["starting_records"].values():
            assert all(r["user_id"].startswith("a:") for r in records)
