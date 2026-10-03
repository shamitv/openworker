"""Execute annotated decisions through SQLite and the dispatcher without inference."""


import pytest

from memory_bench.assets import load_json
from memory_bench.checkpoints import checkpoint_evidence, create_checkpoint_store, reopen_sequence_store
from memory_bench.matching import matches_record, matches_value
from memory_bench.operations import OperationContext, OperationDispatcher
from memory_bench.scoring import aggregate_scores, score_checkpoint


def answer_for(persona, probe_fields):
    if not probe_fields:
        return "Done."
    return "\n".join(field + ": " + ("; ".join(persona["facts"][fid]["value"] for fid in ids) if ids else "UNKNOWN")
                     for field, ids in probe_fields.items())


def execute_annotations(store, persona, conversation, policy, track):
    expected = conversation["policy_expectations"][policy]
    before = store.snapshot()
    turns = []
    for message_index in conversation["tracks"][track]["message_indices"]:
        dispatcher = OperationDispatcher(store, OperationContext(conversation["user_id"], conversation["workspace_id"], conversation["id"]), conversation["permission_reply"])
        # C5 first asks a blind question, then supplies the write target.
        mutation_index = 1 if conversation["id"] == "C5" else 0
        if track != "read" and message_index == mutation_index:
            additions = expected["required_additions"]
            if expected["permission"] in ("ask_then_grant", "ask_then_deny"):
                target = "sensitive_granted" if expected["permission"] == "ask_then_grant" else "sensitive_denied"
                fact = persona["facts"][target]
                dispatcher.dispatch({"name": "request_permission", "arguments": {
                    "question": "Save this for future chats?", **{key: fact[key] for key in ("key", "value", "scope")}}})
            for fact_id in additions:
                fact = persona["facts"][fact_id]
                dispatcher.dispatch({"name": "remember", "arguments": {key: fact[key] for key in ("key", "value", "scope")}})
            for update in expected["required_updates"]:
                previous = persona["facts"][update["previous"]]
                for record in store.snapshot():
                    if record["user_id"] == conversation["user_id"] and matches_value(record["value"], previous):
                        dispatcher.dispatch({"name": "memory_update", "arguments": {"memory_id": record["id"], "value": persona["facts"][update["current"]]["value"]}})
            for fact_id in expected["required_deletions"]:
                for record in store.snapshot():
                    if record["user_id"] == conversation["user_id"] and any(matches_value(text, persona["facts"][fact_id]) for text in [record["value"], *record["history"]]):
                        dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": record["id"]}})
        fields = (conversation["tracks"]["sequence"]["probe_fields"][policy] if track == "sequence" else conversation["common_targets"]["probe_fields"]) if message_index == 0 else {}
        turns.append({"message_index": message_index, "answer": answer_for(persona, fields), "status": "complete", "operations": dispatcher.events})
    evidence = checkpoint_evidence(condition={"dataset": persona["split"], "model": "scripted", "prompt": "baseline", "interface": "dispatcher", "repetition": 1},
        track=track, starting_records=before, final_records=store.snapshot(), turns=turns, status="complete")
    score = score_checkpoint(persona, conversation, policy, track, evidence)
    assert score["conformance"] is True, (persona["id"], conversation["id"], policy, track, score)
    if track != "read":
        actual = {(r["key"], r["value"], r["scope"], r["workspace_id"]) for r in store.snapshot() if r["user_id"] == persona["namespaces"]["owner"]}
        annotated = {(f["key"], f["value"], f["scope"], persona["workspaces"].get(f["workspace"]))
                     for fid in expected["expected_current_facts"] for f in [persona["facts"][fid]]}
        assert actual == annotated
    assert score["tool_errors"] == []
    return score


@pytest.mark.parametrize("split", ["development", "heldout"])
@pytest.mark.parametrize("persona_index", range(15))
def test_all_corpus_tracks_execute_policy_conforming_decisions(tmp_path, split, persona_index):
    persona = load_json(f"corpus/{split}.json")["personas"][persona_index]
    scores = []
    for policy in ("conservative", "recurring"):
        for track in ("write", "read"):
            for c in persona["conversations"]:
                if not c["tracks"][track]["enabled"]:
                    continue
                path = tmp_path / f"{policy}-{track}-{c['id']}.sqlite"
                with create_checkpoint_store(path, persona, c, policy, track) as store:
                    scores.append(execute_annotations(store, persona, c, policy, track))
        path = tmp_path / f"{policy}-sequence.sqlite"
        store = create_checkpoint_store(path, persona, persona["conversations"][0], policy, "sequence")
        try:
            for c in persona["conversations"]:
                if c["restart_before"]:
                    store.close()
                    store = reopen_sequence_store(path)
                scores.append(execute_annotations(store, persona, c, policy, "sequence"))
        finally:
            store.close()
    aggregates = aggregate_scores(scores)
    assert len(aggregates) == 6
    assert all(g["coverage"]["failed"] == 0 for g in aggregates)
    assert all(g["coverage"]["controls_unexercised"] == 0 for g in aggregates)


def test_track_order_does_not_change_state_or_scores(tmp_path):
    persona = load_json("corpus/development.json")["personas"][0]
    c = persona["conversations"][4]
    outputs = []
    for order_index, tracks in enumerate((("write", "read", "sequence"), ("sequence", "read", "write"))):
        result = {}
        for track in tracks:
            path = tmp_path / f"{order_index}-{track}.sqlite"
            with create_checkpoint_store(path, persona, c, "recurring", track) as store:
                # Sequence C5 intentionally has missing earlier writes.
                if track == "sequence":
                    result[track] = store.snapshot()
                else:
                    result[track] = execute_annotations(store, persona, c, "recurring", track)
        outputs.append(result)
    assert outputs[0] == outputs[1]


def test_dispatcher_derived_duplicate_forgetting_row_churn_and_preservation(tmp_path):
    persona = load_json("corpus/development.json")["personas"][0]
    c = persona["conversations"][16]
    with create_checkpoint_store(tmp_path / "copies.sqlite", persona, c, "recurring", "write") as store:
        copies = [r for r in store.snapshot() if matches_record(r, persona["facts"]["A"], persona)]
        assert len(copies) == 2
        before = store.snapshot()
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
        dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": copies[0]["id"]}})
        evidence = checkpoint_evidence(condition={}, track="write", starting_records=before, final_records=store.snapshot(),
            turns=[{"message_index": 0, "answer": "Forgotten.", "status": "complete", "operations": dispatcher.events}], status="complete")
        score = score_checkpoint(persona, c, "recurring", "write", evidence)
        assert score["controls"]["forgetting"][0]["forgotten"] is False
        assert score["conformance"] is False
        dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": copies[1]["id"]}})
        evidence["final_records"] = store.snapshot()
        evidence["turns"][0]["operations"] = dispatcher.events
        assert score_checkpoint(persona, c, "recurring", "write", evidence)["conformance"] is True
    c = persona["conversations"][17]
    with create_checkpoint_store(tmp_path / "unchanged.sqlite", persona, c, "recurring", "write") as store:
        before = store.snapshot()
        target = next(r for r in before if matches_record(r, persona["facts"]["style"], persona))
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
        dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": target["id"]}})
        dispatcher.dispatch({"name": "remember", "arguments": {key: target[key] for key in ("key", "value", "scope")}})
        evidence = checkpoint_evidence(condition={}, track="write", starting_records=before, final_records=store.snapshot(),
            turns=[{"message_index": 0, "answer": "Done.", "status": "complete", "operations": dispatcher.events}], status="complete")
        score = score_checkpoint(persona, c, "recurring", "write", evidence)
        assert score["storage"]["tp"] == score["storage"]["fp"] == 0
        assert score["conformance"] is True
        dispatcher.dispatch({"name": "remember", "arguments": {key: target[key] for key in ("key", "value", "scope")}})
        evidence["final_records"] = store.snapshot()
        evidence["turns"][0]["operations"] = dispatcher.events
        score = score_checkpoint(persona, c, "recurring", "write", evidence)
        assert score["storage"]["fp"] == score["storage"]["duplicates"] == 1
        assert score["conformance"] is False


def test_recovered_tool_error_stays_visible_with_conforming_state(tmp_path):
    persona = load_json("corpus/development.json")["personas"][0]
    c = persona["conversations"][3]
    with create_checkpoint_store(tmp_path / "recover.sqlite", persona, c, "recurring", "write") as store:
        before = store.snapshot()
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
        dispatcher.dispatch(None)
        for fid in c["policy_expectations"]["recurring"]["required_additions"]:
            dispatcher.dispatch({"name": "remember", "arguments": {key: persona["facts"][fid][key] for key in ("key", "value", "scope")}})
        evidence = checkpoint_evidence(condition={}, track="write", starting_records=before, final_records=store.snapshot(),
            turns=[{"message_index": 0, "answer": "Done.", "status": "complete", "operations": dispatcher.events}], status="complete")
        result = score_checkpoint(persona, c, "recurring", "write", evidence)
        assert result["conformance"] is True
        assert len(result["tool_errors"]) == 1
        assert len(aggregate_scores([result])[0]["cases"][0]["tool_errors"]) == 1


@pytest.mark.parametrize("change", ["scope", "value", "key", "temporary"])
def test_dispatcher_derived_incorrect_changes_and_transient_forbidden_save(tmp_path, change):
    persona = load_json("corpus/development.json")["personas"][0]
    c = persona["conversations"][17]
    with create_checkpoint_store(tmp_path / "change.sqlite", persona, c, "recurring", "write") as store:
        before = store.snapshot()
        target = next(r for r in before if matches_record(r, persona["facts"]["style"], persona))
        dispatcher = OperationDispatcher(store, OperationContext(c["user_id"], c["workspace_id"], c["id"]))
        if change == "temporary":
            fact = persona["facts"]["temporary"]
            saved = dispatcher.dispatch({"name": "remember", "arguments": {key: fact[key] for key in ("key", "value", "scope")}})
            dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": saved["data"]["record"]["id"]}})
        else:
            dispatcher.dispatch({"name": "memory_forget", "arguments": {"memory_id": target["id"]}})
            args = {key: target[key] for key in ("key", "value", "scope")}
            args[{"scope": "scope", "value": "value", "key": "key"}[change]] = {"scope": "workspace", "value": "unrelated current value", "key": "incorrect_key"}[change]
            dispatcher.dispatch({"name": "remember", "arguments": args})
        evidence = checkpoint_evidence(condition={}, track="write", starting_records=before, final_records=store.snapshot(),
            turns=[{"message_index": 0, "answer": "Done.", "status": "complete", "operations": dispatcher.events}], status="complete")
        result = score_checkpoint(persona, c, "recurring", "write", evidence)
        assert result["conformance"] is False
        if change == "temporary":
            assert result["storage"]["fp"] == 0
            assert len(result["temporary_save_operations"]) == 1
            assert aggregate_scores([result])[0]["diagnostics"]["temporary_save_operations"] == 1
        else:
            assert result["storage"]["fp"] == 1
            assert result["preserved_prior"] is False
            assert result["unnecessary_saves"]["count"] == 1
