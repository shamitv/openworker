"""Descriptive comparisons of frozen scores with every other factor held fixed."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations

from .assets import canonical_json


STORAGE_MEANING = {
    "write": "new/changed current facts after subtracting equivalent prepared prior facts",
    "read": "unscored: prepared records earn no save credit",
    "sequence": "accumulated actual owner state at each checkpoint; repeated state observations",
}
POLICY_MEANING = {
    "conservative": "Explicit durability or future-chat preferences are required; incidental context remains in the chat.",
    "recurring": "Also save stable non-sensitive personal and recurring context without an explicit durability request.",
}


def outcome(values) -> dict:
    values = list(values)
    passed, failed = sum(v is True for v in values), sum(v is False for v in values)
    denominator = passed + failed
    return {"passed": passed, "failed": failed, "unscored": len(values) - denominator,
            "denominator": denominator, "rate": passed / denominator if denominator else None}


def condition_details(group: dict) -> dict:
    """Add descriptive denominators without modifying or reinterpreting scorer output."""
    cases = group["cases"]
    scope = {name: sum(len(c["scope"][name + "_ids"]) for c in cases)
             for name in ("correct", "wrong", "unmatched")}
    scope["denominator"] = scope["correct"] + scope["wrong"]
    scope["accuracy"] = scope["correct"] / scope["denominator"] if scope["denominator"] else None
    missing_state = sum(c["raw_state"]["final_records"] is None for c in cases)
    return {"storage_meaning": STORAGE_MEANING[group["track"]], "scope": scope,
            "missing_final_state_cases": missing_state,
            "consent": outcome(c["permissions"]["conformance"] if c["completed"] else None for c in cases),
            "preference_format": deepcopy(group["answers"]["facts"].get("style", outcome([]))),
            "preference_reason": deepcopy(group["answers"]["facts"].get("reason", outcome([]))),
            "temporary_state": {"records": sum(len(c["temporary_saves"] or []) for c in cases),
                                "observed_cases": len(cases) - missing_state, "missing_state_cases": missing_state},
            "case_errors": {code: sum(any(e.get("code") == code for e in c["errors"]) for c in cases)
                            for code in sorted({e["code"] for c in cases for e in c["errors"] if "code" in e})}}


def _metrics(group: dict) -> dict:
    def metric(numerator, denominator):
        return {"numerator": numerator, "denominator": denominator,
                "rate": numerator / denominator if denominator else None}
    storage, common = group["storage"], group["common"]
    return {"policy_conformance": metric(group["conformance"]["passed"], group["conformance"]["denominator"]),
            "storage_precision": metric(storage["tp"], storage["precision_denominator"]),
            "storage_recall": metric(storage["tp"], storage["recall_denominator"]),
            "common_fact_recall": metric(common["fact_presence"]["tp"], common["fact_presence"]["denominator"]),
            "common_answers": metric(common["answers"]["correct"]["passed"], common["answers"]["correct"]["denominator"])}


def comparisons(groups: list[dict]) -> dict:
    result = {kind: [] for kind in ("wording", "policy", "interface", "model")}
    for kind, factor in (("wording", "prompt"), ("policy", "policy"), ("interface", "interface"), ("model", "model")):
        matched = {}
        for group in groups:
            fixed = {k: v for k, v in group["condition"].items() if k != factor}
            fixed["track"] = group["track"]
            matched.setdefault(canonical_json(fixed), []).append(group)
        for key in sorted(matched):
            for left, right in combinations(sorted(matched[key], key=lambda g: g["condition"][factor]), 2):
                members = lambda g: {(c["persona_id"], c["condition"]["repetition"], c["conversation_id"]) for c in g["cases"]}
                matched_coverage = members(left) == members(right)
                lmetrics, rmetrics = _metrics(left), _metrics(right)
                deltas = {name: rmetrics[name]["rate"] - metric["rate"]
                          if matched_coverage and metric["rate"] is not None and rmetrics[name]["rate"] is not None else None
                          for name, metric in lmetrics.items()}
                result[kind].append({"fixed": {k: v for k, v in left["condition"].items() if k != factor} | {"track": left["track"]},
                    "factor": factor, "left": left["condition"][factor], "right": right["condition"][factor],
                    "matched_selected_cases": matched_coverage, "left_coverage": deepcopy(left["coverage"]),
                    "right_coverage": deepcopy(right["coverage"]), "left_metrics": lmetrics, "right_metrics": rmetrics,
                    "right_minus_left": deltas})
    return result


def representative_failures(groups: list[dict], per_category: int = 2) -> list[dict]:
    """Deterministic case references, retaining categories rather than cherry-picking rates."""
    output = []
    for group in groups:
        chosen = {}
        for case in sorted(group["cases"], key=lambda c: (c["persona_id"], c["condition"]["repetition"], c["conversation_id"])):
            reasons = {}
            if not case["completed"]:
                reasons["execution"] = "Checkpoint status: " + case["status"]
            if case["permissions"]["violations"]:
                reasons["consent"] = "Successful save without required prior consent."
            if case["scope"]["wrong_ids"]:
                reasons["scope"] = "Matched facts are stored in an incorrect scope."
            if case["answers"].get("answer_format") is False:
                reasons["answer_format"] = "Completed answer does not satisfy the frozen field format."
            if case["answers"].get("correct") is False:
                reasons["answer"] = "Completed answer misses required facts or UNKNOWN/exclusion rules."
            for correction in case["controls"]["corrections"]:
                if correction["exercised"] and correction["current_correction"] is False:
                    reasons["current_correction"] = "Exercised correction lacks the required current value."
                if correction["exercised"] and correction["old_history_retired"] is False:
                    reasons["history_retirement"] = "Exercised correction retains historical wording."
            if any(c["exercised"] and c["forgotten"] is False for c in case["controls"]["forgetting"]):
                reasons["forgetting"] = "Exercised forgetting leaves a current or historical copy."
            if case["temporary_save_operations"]:
                reasons["temporary_save"] = "A successful mutation saved the temporary fact."
            if case["storage"].get("duplicates", 0):
                reasons["duplicates"] = "Scored state contains duplicate current facts."
            for category, explanation in reasons.items():
                if chosen.get(category, 0) >= per_category:
                    continue
                chosen[category] = chosen.get(category, 0) + 1
                output.append({"condition": deepcopy(group["condition"]), "track": group["track"],
                    "persona_id": case["persona_id"], "repetition": case["condition"]["repetition"],
                    "conversation_id": case["conversation_id"], "category": category, "explanation": explanation})
    return output
