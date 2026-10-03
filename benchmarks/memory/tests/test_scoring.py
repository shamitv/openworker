import copy
import json
import sqlite3

import pytest

from memory_bench.assets import canonical_json, load_json
from memory_bench.checkpoints import checkpoint_evidence
from memory_bench.matching import matches_record, matches_value, normalize
from memory_bench.operations import OperationContext, OperationDispatcher
from memory_bench.provenance import scorer_provenance
from memory_bench.scoring import aggregate_scores, score_answer, score_checkpoint, score_controls, score_facts, score_permissions, score_storage
from memory_bench.store import MemoryStore

FIXTURES = load_json("fixtures/scoring.json")


def persona():
    return load_json("corpus/development.json")["personas"][0]


def fact_row(p, fact_id, memory_id=1, **changes):
    fact = p["facts"][fact_id]
    return {"id": memory_id, "user_id": p["namespaces"]["peer" if fact["subject"] == "peer" else "owner"],
            "workspace_id": p["workspaces"].get(fact["workspace"]), "scope": fact["scope"],
            "key": fact["key"], "value": fact["value"], "history": [], **changes}


def captured(c, track, before, after, *, events=None, answers=None, status="complete", condition=None):
    indices = c["tracks"][track]["message_indices"]
    turns = [{"message_index": i, "answer": (answers or {}).get(i, "Done."), "status": "complete", "operations": events or [] if i == 0 else []} for i in indices]
    if status == "unexecuted":
        turns = []
    return checkpoint_evidence(condition=condition or {"model": "scripted", "dataset": "development", "repetition": 1},
        track=track, starting_records=before, final_records=after, turns=turns, status=status)


def fixture_score(f):
    p = persona()
    p["facts"] = FIXTURES["facts"]
    c = copy.deepcopy(p["conversations"][0])
    c["id"] = f["id"]
    before, after = f.get("starting_records", []), f.get("actual_records", [])
    expected = f.get("expected_facts", [])
    updates = [{"previous": "original", "current": "corrected"}] if "corrected" in expected or f.get("prerequisites") else []
    deletions = ["notebook"] if f["id"].startswith("forget_") else []
    prior_facts = [fid for fid, fact in p["facts"].items() if any(matches_record(row, fact, p) for row in before)]
    retained = [fid for fid in prior_facts if fid not in deletions + [u["previous"] for u in updates]]
    probe_fields = {field: [] for field in f.get("required_fields", [])}
    current = list(dict.fromkeys(retained + expected))
    for policy in ("conservative", "recurring"):
        c["policy_expectations"][policy] = {"required_additions": [fid for fid in expected if fid not in [u["current"] for u in updates]],
            "required_updates": updates, "required_deletions": deletions, "retained_prior_facts": retained,
            "expected_current_facts": current, "forbidden_new_facts": [], "permission": "not_required"}
        c["tracks"]["sequence"]["expected_current_facts"][policy] = expected
        c["tracks"]["sequence"]["probe_fields"][policy] = probe_fields
    c["common_targets"].update(saved_facts=expected, probe_fields=probe_fields, excluded_answer_facts=f.get("excluded_facts", []))
    c["tracks"]["read"]["probe_fields"] = probe_fields
    for track in ("write", "read", "sequence"):
        c["tracks"][track].update(enabled=True, message_indices=[0])
    status = "complete"
    if "raw_response" in f:
        try:
            json.loads(f["raw_response"])
        except json.JSONDecodeError:
            status = "format_error"
    result = score_checkpoint(p, c, "recurring", f["track"], captured(c, f["track"], before, after,
        answers={0: f.get("answer", "Done.")}, status=status))
    flattened = {**result["storage"], "conformance": result["conformance"], "preserved_prior": result["preserved_prior"]}
    flattened.update({key: value for key, value in result["answers"].items() if key in ("answer_format", "unknown", "scope_correct")})
    if result["controls"]["corrections"]:
        flattened.update(result["controls"]["corrections"][0])
    if result["controls"]["forgetting"]:
        flattened["forgotten"] = result["controls"]["forgetting"][0]["forgotten"]
    if result["errors"]:
        flattened["error"] = result["errors"][0]["code"]
    return result, flattened


@pytest.mark.parametrize("fixture", FIXTURES["fixtures"], ids=lambda f: f["id"])
def test_all_frozen_fixtures_execute_scorer(fixture):
    result, actual = fixture_score(fixture)
    for key, expected in fixture["expected_outcome"].items():
        assert actual[key] == expected, (fixture["id"], key, actual)
    canonical_json(result)


def test_frozen_aggregate_sums_counts_before_dividing():
    by_id = {f["id"]: f for f in FIXTURES["fixtures"]}
    scores = [fixture_score(by_id[name])[0] for name in FIXTURES["aggregate_fixture"]["members"]]
    aggregate = aggregate_scores(scores)[0]
    for key, expected in FIXTURES["aggregate_fixture"]["expected_outcome"].items():
        assert aggregate["storage"][key] == expected
    assert aggregate["storage"]["precision_denominator"] == 3
    assert aggregate["storage"]["recall_denominator"] == 3
    assert len(aggregate["cases"]) == 3


@pytest.mark.parametrize("text,expected", [("４４_ＫＨｚ", "44 khz"), ("80 g/m²", "80 gsm"),
    ("44.1kHz", "44.1 khz"), ("Hello—WORLD!", "hello world")])
def test_frozen_normalization(text, expected):
    assert normalize(text) == expected


def test_whole_phrases_decimals_units_and_key_identity():
    p = persona()
    assert not matches_value("Grade 80 CBSE", p["facts"]["original"])
    assert not matches_value("80.0 Hz", {"value_alias_groups": [["80 gsm"]]})
    assert not matches_value("44.1 kHz", {"value_alias_groups": [["44 kHz"]]})
    p["facts"]["another"] = {**p["facts"]["original"], "key": "another", "key_aliases": ["another"]}
    result = score_facts(p, ["original", "another"], [fact_row(p, "another")])
    assert (result["tp"], result["fp"], result["fn"]) == (1, 0, 1)
    assert result["missing_facts"] == ["original"]


def test_history_only_write_has_no_credit_but_old_history_is_measured():
    p = persona()
    before = [fact_row(p, "corrected")]
    after = [{**before[0], "history": [p["facts"]["original"]["value"]]}]
    score = score_storage(p, [], after, track="write", starting_records=before)
    assert score["tp"] == score["fp"] == score["fn"] == 0
    assert score["precision"] is None
    assert score["unchanged"] == [{"before_id": 1, "after_id": 1}]


def test_correction_and_forgetting_inspect_all_keys_scopes_and_history():
    p = persona()
    old = fact_row(p, "original")
    stale = fact_row(p, "original", 2, key="wrong_key", scope="workspace", workspace_id=p["workspaces"]["B"])
    final = [fact_row(p, "corrected"), stale]
    result = score_controls(p, [old, stale], final, updates=[{"previous": "original", "current": "corrected"}], deletions=[])
    assert result["corrections"][0]["current_correction"] is True
    assert result["corrections"][0]["old_current_retired"] is False
    notebook = fact_row(p, "notebook")
    hidden = fact_row(p, "style", 2, history=[p["facts"]["notebook"]["value"]])
    result = score_controls(p, [notebook, hidden], [hidden], updates=[], deletions=["notebook"])
    assert result["forgetting"][0]["forgotten"] is False
    assert result["forgetting"][0]["remaining_history_ids"] == [2]
    foreign = {**hidden, "user_id": p["namespaces"]["peer"]}
    assert score_controls(p, [notebook], [foreign], updates=[], deletions=["notebook"])["forgetting"][0]["forgotten"] is True


def test_answer_preference_format_and_reason_are_independent():
    p = persona()
    answer = "style: numbered worked examples"
    score = score_answer(p, answer, {"style": ["style", "reason"]}, [])
    assert score["fields"]["style"]["facts"] == {"style": True, "reason": False}
    assert score["correct"] is False
    for answer in ("style: unknown", "style: UNKNOWN because unavailable", "style: UNKNOWN\nstyle: UNKNOWN", "style:", "style: UNKNOWN\nextra prose"):
        assert score_answer(p, answer, {"style": []}, [])["correct"] is False
        assert score_answer(p, answer, {"style": []}, [])["unknown"] is False


def test_c5_scores_first_turn_answer_before_later_save():
    p = persona()
    c = p["conversations"][4]
    before = c["tracks"]["write"]["starting_records"]["recurring"]
    after = before + [fact_row(p, "B", 100)]
    answer = "\n".join(f"{field}: " + ("; ".join(p["facts"][fid]["value"] for fid in ids) if ids else "UNKNOWN")
                       for field, ids in c["common_targets"]["probe_fields"].items())
    score = score_checkpoint(p, c, "recurring", "write", captured(c, "write", before, after, answers={0: answer, 1: "Saved the new heading."}))
    assert score["answers"]["correct"] is True
    assert score["storage"]["tp"] == 1
    assert score["conformance"] is True
    evidence = captured(c, "write", before, after, answers={0: answer})
    evidence["turns"] = evidence["turns"][1:]
    assert score_checkpoint(p, c, "recurring", "write", evidence)["completed"] is False


def test_conservative_no_save_conforms_while_common_targets_are_missing():
    p = persona()
    c = p["conversations"][0]
    before = c["tracks"]["write"]["starting_records"]["conservative"]
    score = score_checkpoint(p, c, "conservative", "write", captured(c, "write", before, before))
    assert score["conformance"] is True
    assert score["storage"]["precision"] is None
    assert score["common"]["fact_presence"]["recall"] == 0
    c = p["conversations"][2]
    before = p["sequence_start"]["peer_controls"]
    answer = "context: UNKNOWN\nstyle: UNKNOWN\ntemporary_label: UNKNOWN"
    score = score_checkpoint(p, c, "conservative", "sequence", captured(c, "sequence", before, before, answers={0: answer}))
    assert score["conformance"] is True
    assert score["answers"]["correct"] is True
    assert score["common"]["answers"]["correct"] is False


@pytest.mark.parametrize("kind", ["matching", "denied", "wrong_value", "wrong_key", "wrong_scope", "late", "other_conversation", "other_user", "other_workspace"])
def test_consent_is_exact_chronological_and_bound_to_context(kind):
    p = persona()
    c = p["conversations"][10]
    f = p["facts"]["sensitive_granted"]
    proposal = {key: f[key] for key in ("key", "value", "scope")}
    grant_proposal = {**proposal}
    if kind == "wrong_value":
        grant_proposal["value"] = "another fact"
    elif kind == "wrong_key":
        grant_proposal["key"] = "another_key"
    elif kind == "wrong_scope":
        grant_proposal["scope"] = "workspace"
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]), {"granted": kind != "denied", "reply": "scripted"})
        permission = {"name": "request_permission", "arguments": {"question": "Save?", **grant_proposal}}
        save = {"name": "remember", "arguments": proposal}
        dispatcher.dispatch_batch([save, permission] if kind == "late" else [permission, save])
        events = dispatcher.events
        if kind in ("other_conversation", "other_user", "other_workspace"):
            events[0]["context"][{"other_conversation": "conversation_id", "other_user": "user_id", "other_workspace": "workspace_id"}[kind]] = "different"
        score = score_permissions(p, c, "recurring", events)
        assert score["conformance"] is (kind == "matching")
        assert len(score["violations"]) == (0 if kind == "matching" else 1)


def test_sensitive_save_deleted_after_denial_still_violates_consent():
    p = persona()
    c = p["conversations"][11]
    f = p["facts"]["sensitive_denied"]
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]), c["permission_reply"])
        args = {key: f[key] for key in ("key", "value", "scope")}
        dispatcher.dispatch({"name": "request_permission", "arguments": {"question": "Save?", **args}})
        dispatcher.dispatch({"name": "remember", "arguments": args})
        dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": 1}})
        assert store.snapshot() == []
        assert score_permissions(p, c, "recurring", dispatcher.events)["conformance"] is False


def test_explicit_consent_needs_no_question_and_reasking_fails():
    p = persona()
    c = p["conversations"][12]
    f = p["facts"]["sensitive_explicit"]
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]), c["permission_reply"])
        args = {key: f[key] for key in ("key", "value", "scope")}
        dispatcher.dispatch({"name": "remember", "arguments": args})
        assert score_permissions(p, c, "recurring", dispatcher.events)["conformance"] is True
        dispatcher.dispatch({"name": "request_permission", "arguments": {"question": "Save?", **args}})
        assert score_permissions(p, c, "recurring", dispatcher.events)["conformance"] is False


def test_not_required_permission_request_is_a_separate_metric():
    p = persona()
    c = p["conversations"][0]
    with MemoryStore(":memory:") as store:
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
        dispatcher.dispatch({"name": "request_permission", "arguments": {"question": "Save?", "key": "fact", "value": "value", "scope": "global"}})
        score = score_permissions(p, c, "conservative", dispatcher.events)
        assert score["conformance"] is True
        assert score["unnecessary_requests"] == 1


@pytest.mark.parametrize("status,after", [("format_error", "saved"), ("failed", None), ("unexecuted", [])])
def test_failures_keep_storage_evidence_without_successful_noop(status, after):
    p = persona()
    c = p["conversations"][0]
    actual = [fact_row(p, "original")] if after == "saved" else after
    score = score_checkpoint(p, c, "recurring", "write", captured(c, "write", [], actual, status=status))
    assert score["conformance"] is not True
    assert score["completed"] is False
    if after == "saved":
        assert score["storage"]["tp"] == 1
    else:
        assert score["storage"]["scored"] is False
        assert score["storage"]["tp"] is None
    aggregate = aggregate_scores([score])[0]
    assert aggregate["coverage"]["completed"] == 0


def test_missing_sequence_prerequisites_are_independent_null_outcomes():
    p = persona()
    c = p["conversations"][7]
    before = [fact_row(p, "notebook")]
    result = score_checkpoint(p, c, "recurring", "sequence", captured(c, "sequence", before, []))
    assert result["controls"]["corrections"][0]["current_correction"] is None
    assert result["controls"]["corrections"][0]["reason"] == "missing prerequisite"
    assert result["controls"]["forgetting"][0]["forgotten"] is True
    assert aggregate_scores([result])[0]["coverage"]["controls_unexercised"] == 1


def test_read_history_mutation_and_reverted_mutation_are_reported():
    p = persona()
    c = p["conversations"][2]
    before = c["tracks"]["read"]["starting_records"]
    answer = "context: " + p["facts"]["original"]["value"] + "\nstyle: " + p["facts"]["style"]["value"] + "; " + p["facts"]["reason"]["value"] + "\ntemporary_label: UNKNOWN"
    with MemoryStore(":memory:") as store:
        store.seed(before)
        target = next(r for r in before if r["key"] == p["facts"]["original"]["key"])
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
        dispatcher.dispatch({"name": "memory_update", "arguments": {"memory_id": target["id"], "value": target["value"], "history": ["historical edit"]}})
        result = score_checkpoint(p, c, "recurring", "read", captured(c, "read", before, store.snapshot(), events=dispatcher.events, answers={0: answer}))
        assert result["answers"]["correct"] is True
        assert result["storage"]["scored"] is False
        assert result["read_mutations"]["state_changed"] is True
        assert result["conformance"] is False
        dispatcher.dispatch({"name": "memory_update", "arguments": {"memory_id": target["id"], "value": target["value"]}})
        result = score_checkpoint(p, c, "recurring", "read", captured(c, "read", before, store.snapshot(), events=dispatcher.events, answers={0: answer}))
        assert result["read_mutations"]["state_changed"] is False
        assert len(result["read_mutations"]["successful_operations"]) == 2
        assert result["conformance"] is False


def test_aggregation_keeps_tracks_conditions_nulls_and_errors():
    f = FIXTURES["fixtures"][0]
    write = fixture_score(f)[0]
    other = copy.deepcopy(write)
    other["condition"]["repetition"] = 2
    read = copy.deepcopy(write)
    read["track"] = "read"
    read["storage"] = score_storage(persona(), [], [], track="read")
    different = copy.deepcopy(write)
    different["condition"]["model"] = "other"
    groups = aggregate_scores([write, other, read, different])
    assert len(groups) == 3
    repeated = next(g for g in groups if g["track"] == "write" and g["condition"]["model"] == "scripted")
    assert repeated["storage"]["tp"] == 2
    read_group = next(g for g in groups if g["track"] == "read")
    assert read_group["storage"]["precision"] is None
    assert read_group["coverage"]["storage_unscored"] == 1


def test_provenance_and_evidence_are_stable_detached_and_serializable():
    hashes = scorer_provenance()
    assert hashes == scorer_provenance()
    assert len(hashes["sha256"]) == 64
    assert len(hashes["asset_hashes"]) == 11
    p = persona()
    c = p["conversations"][0]
    before = [fact_row(p, "original")]
    evidence = captured(c, "write", before, before)
    before[0]["value"] = "changed"
    assert evidence["starting_records"][0]["value"] != "changed"
    canonical_json(evidence)
    for indices in ([0, 0], [1, 0], [-1]):
        evidence["turns"] = [{"message_index": i, "answer": "Done", "status": "complete", "operations": []} for i in indices]
        with pytest.raises(ValueError):
            checkpoint_evidence(**{k: v for k, v in evidence.items() if k != "schema_version"})


def test_missing_starting_snapshot_cannot_conform():
    p = persona()
    c = p["conversations"][0]
    after = [fact_row(p, fid, index + 1) for index, fid in enumerate(["original", "style", "reason"])]
    result = score_checkpoint(p, c, "recurring", "write", captured(c, "write", None, after))
    assert result["storage"]["scored"] is False
    assert result["conformance"] is None
    assert result["conformance_reason"] == "missing state evidence"


def test_evidence_rejects_fabricated_success_for_invalid_operation():
    p = persona()
    c = p["conversations"][0]
    evidence = captured(c, "write", [], [])
    evidence["turns"][0]["operations"] = [{"context": {"user_id": c["user_id"], "workspace_id": c["workspace_id"], "conversation_id": c["id"]},
        "operation": {"name": "unknown", "arguments": {}}, "result": {"ok": True, "data": {}, "error": None}}]
    with pytest.raises((ValueError, KeyError)):
        score_checkpoint(p, c, "recurring", "write", evidence)


def test_infrastructure_error_cannot_pass_even_with_claimed_complete_status():
    p = persona()
    c = p["conversations"][0]
    store = MemoryStore(":memory:")
    dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        dispatcher.dispatch({"name": "memory_read", "arguments": {"memory_ids": [1]}})
    evidence = captured(c, "write", [], [], events=dispatcher.events)
    result = score_checkpoint(p, c, "conservative", "write", evidence)
    assert result["completed"] is False
    assert result["conformance"] is False
    assert result["errors"][0]["type"] == "ProgrammingError"
    assert aggregate_scores([result])[0]["coverage"]["failed"] == 1
