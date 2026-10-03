from copy import deepcopy
from itertools import product

from memory_bench.checkpoints import checkpoint_evidence
from memory_bench.comparison import comparisons, condition_details, representative_failures
from memory_bench.scoring import aggregate_scores, score_checkpoint


def group(persona, *, model="one", policy="conservative", prompt="baseline", interface="json", status="complete", cid="C3"):
    conversation = next(c for c in persona["conversations"] if c["id"] == cid)
    records = deepcopy(conversation["tracks"]["read"]["starting_records"])
    condition = {"dataset": "development", "model": model, "policy": policy, "prompt": prompt,
                 "interface": interface, "persona_id": persona["id"], "repetition": 1}
    evidence = checkpoint_evidence(condition=condition, track="read", starting_records=records, final_records=records,
        turns=[{"message_index": 0, "status": status, "answer": "UNKNOWN" if status == "complete" else None,
                "operations": [], "errors": []}], status=status, errors=[{"code": status}] if status != "complete" else [])
    return aggregate_scores([score_checkpoint(persona, conversation, policy, "read", evidence)])[0]


def test_factor_comparisons_never_pool_interfaces_tracks_policies_or_models(development):
    groups = [group(development["personas"][0], model=model, policy=policy, prompt=prompt, interface=interface)
              for model, policy, prompt, interface in product(["one", "two"], ["conservative", "recurring"],
                                                            ["baseline", "rules", "examples"], ["json", "native"])]
    before = deepcopy(groups)
    result = comparisons(groups)
    assert {kind: len(rows) for kind, rows in result.items()} == {"wording": 24, "policy": 12, "interface": 12, "model": 12}
    assert groups == before
    for kind, factor in (("wording", "prompt"), ("policy", "policy"), ("interface", "interface"), ("model", "model")):
        for pair in result[kind]:
            assert factor not in pair["fixed"]
            assert pair["fixed"]["track"] == "read"
            assert pair["matched_selected_cases"]
            assert pair["left_metrics"]["storage_recall"]["rate"] is None
            assert pair["right_minus_left"]["storage_recall"] is None
    assert comparisons(list(reversed(groups))) == result


def test_unequal_selected_cases_disable_rate_differences(development):
    left = group(development["personas"][0])
    right = group(development["personas"][1], prompt="rules")
    pair = comparisons([left, right])["wording"][0]
    assert not pair["matched_selected_cases"]
    assert all(value is None for value in pair["right_minus_left"].values())
    assert comparisons([left])["model"] == []


def test_failed_cases_remain_in_pair_coverage_and_missing_probes_are_unscored(development):
    left = group(development["personas"][0])
    right = group(development["personas"][0], prompt="rules", status="format_error")
    pair = comparisons([left, right])["wording"][0]
    assert pair["right_coverage"]["failed"] == 1
    assert pair["matched_selected_cases"]
    assert pair["right_metrics"]["common_answers"]["denominator"] == 0
    assert pair["right_minus_left"]["common_answers"] is None
    details = condition_details(right)
    assert details["preference_format"]["denominator"] == 0
    assert details["preference_reason"]["rate"] is None
    assert details["case_errors"]["format_error"] == 1  # multiple raw entries, one failed case
    assert details["consent"]["unscored"] == 1


def test_preference_scope_and_representative_failures_use_existing_scored_facts(development):
    value = group(development["personas"][0])
    details = condition_details(value)
    assert details["storage_meaning"].startswith("unscored")
    assert details["preference_format"]["denominator"] == 1
    assert details["preference_reason"]["denominator"] == 1
    assert details["scope"]["denominator"] > 0
    before = deepcopy(value)
    failures = representative_failures([value])
    assert {f["category"] for f in failures} == {"answer", "answer_format"}
    assert all(f["persona_id"] == "P01" and f["conversation_id"] == "C3" for f in failures)
    assert value == before


def test_missing_state_stays_explicit_in_scope_and_temporary_diagnostics(development):
    value = group(development["personas"][0])
    value["cases"][0]["raw_state"]["final_records"] = None
    value["cases"][0]["scope"] = {"correct_ids": [], "wrong_ids": [], "unmatched_ids": [], "denominator": 0, "accuracy": None}
    value["cases"][0]["temporary_saves"] = None
    details = condition_details(value)
    assert details["missing_final_state_cases"] == 1
    assert details["scope"]["accuracy"] is None
    assert details["temporary_state"]["observed_cases"] == 0
