import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest


@pytest.fixture
def analyzer():
    path = Path(__file__).resolve().parents[1] / "tools" / "analyze_json_response_shapes.py"
    spec = importlib.util.spec_from_file_location("review_json_response_shapes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completion(content, reasoning=None, finish_reason="stop"):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {"choices": [{"finish_reason": finish_reason, "message": message}]}


@pytest.mark.parametrize("content,expected", [
    ('{"answer": "ok", "operations": []}', "parses_as_json"),
    ('{"answer": "a", "answer": "b", "operations": []}', "json_prefix_then_prose"),
    ('```json\n{"answer": "ok", "operations": []}\n```', "fenced_json"),
    ('{"answer": "ok", "operations": []} Hope this helps!', "json_prefix_then_prose"),
    ('Let me check.\n\n{"answer": "", "operations": []}', "json_embedded_in_prose"),
    ("I will not save that label; it is temporary for this draft.", "prose_with_operation_vocabulary"),
    ("A crease reverses when the layer stack flips sense.", "prose_other"),
    (None, "no_content_field"),
    (12345, "no_content_field"),
])
def test_response_shape_is_structural_and_total(analyzer, content, expected):
    assert analyzer.response_shape(content) == expected


def test_response_shape_prefers_a_parseable_envelope_over_surrounding_prose(analyzer):
    # A parseable envelope is reported as such even though a later contract check
    # may still reject it; the shape never claims the response was correct.
    assert analyzer.response_shape('{"answer": "ok", "operations": []}') == "parses_as_json"


def test_delivered_answer_text_unwraps_an_envelope_but_keeps_rejected_text(analyzer):
    assert analyzer.delivered_answer_text('{"answer": "hi", "operations": []}') == "hi"
    assert analyzer.delivered_answer_text("context: a\nstyle: b") == "context: a\nstyle: b"
    assert analyzer.delivered_answer_text('{"operations": []}') == '{"operations": []}'
    assert analyzer.delivered_answer_text(None) is None


def test_message_content_survives_missing_and_malformed_choices(analyzer):
    assert analyzer.message_content(completion("text", "because")) == ("stop", "text", "because")
    assert analyzer.message_content(completion(None)) == ("stop", None, None)
    assert analyzer.message_content({"choices": []}) == (None, None, None)
    assert analyzer.message_content({"choices": [{"finish_reason": "stop"}]}) == ("stop", None, None)
    assert analyzer.message_content({}) == (None, None, None)


def conversation_fixture():
    return {
        "policy_expectations": {"conservative": {
            "required_additions": ["f1", "f2"], "required_updates": [{"current": "f2"}, {"current": "f3"}],
            "forbidden_new_facts": ["f9", "f9"]}},
        "common_targets": {"probe_fields": {"common": ["c1"]}, "excluded_answer_facts": ["e1"]},
        "tracks": {"read": {"probe_fields": {"answer": ["r1"]}},
                   "sequence": {"probe_fields": {"conservative": {"answer": ["s1"]}},
                                "expected_current_facts": {"conservative": ["s1", "s2"]}}}}


def test_expected_targets_deduplicates_and_selects_per_track(analyzer):
    conversation = conversation_fixture()
    write = analyzer.expected_targets(conversation, "conservative", "write")
    assert write["storage_facts"] == ["f1", "f2", "f3"]
    assert write["answer_facts"] == ["c1"]
    assert write["excluded_answer_facts"] == ["e1"]

    read = analyzer.expected_targets(conversation, "conservative", "read")
    assert read["answer_facts"] == ["r1"]
    assert read["storage_facts"] == ["s1", "s2"]

    sequence = analyzer.expected_targets(conversation, "conservative", "sequence")
    assert sequence["answer_facts"] == ["s1"]
    assert sequence["storage_facts"] == ["s1", "s2"]


def test_expected_targets_are_empty_rather_than_invented_for_unknown_tracks(analyzer):
    conversation = conversation_fixture()
    unknown = analyzer.expected_targets(conversation, "conservative", "unknown")
    assert unknown["storage_facts"] == []
    assert unknown["answer_facts"] == []


def test_choose_sample_is_deterministic_and_exact(analyzer):
    candidates = [{"prompt": prompt, "track": track, "persona_id": f"H{n:02d}",
                   "checkpoint_id": f"{track}-{prompt}-H{n:02d}-C{message_index + 1}", "message_index": message_index}
                  for prompt in ("baseline", "rules", "examples") for track in ("write", "read", "sequence")
                  for n in range(1, 16) for message_index in range(3)]
    first = analyzer.choose_sample(candidates, 150)
    second = analyzer.choose_sample(list(reversed(candidates)), 150)
    assert first == second
    assert len(first) == 150
    assert len({(row["checkpoint_id"], row["message_index"]) for row in first}) == 150
    assert len({(row["prompt"], row["track"]) for row in first}) == 9


def test_choose_sample_gives_every_stratum_its_own_quota(analyzer):
    # A global cap would starve later strata; each stratum must fill its own quota.
    candidates = [{"prompt": prompt, "track": track, "persona_id": f"H{n:02d}",
                   "checkpoint_id": f"{track}-{prompt}-H{n:02d}-C{message_index + 1}", "message_index": message_index}
                  for prompt in ("baseline", "rules", "examples") for track in ("write", "read", "sequence")
                  for n in range(1, 16) for message_index in range(3)]
    sample = analyzer.choose_sample(candidates, 150)
    counts = Counter((row["prompt"], row["track"]) for row in sample)
    assert sorted(counts.values()) == [16, 16, 16, 17, 17, 17, 17, 17, 17]
    assert sum(counts.values()) == 150


def test_choose_sample_spreads_personas_inside_each_stratum(analyzer):
    candidates = [{"prompt": "baseline", "track": "write", "persona_id": f"H{n:02d}",
                   "checkpoint_id": f"w-baseline-H{n:02d}-C1", "message_index": 0} for n in range(1, 16)]
    assert [row["persona_id"] for row in analyzer.choose_sample(candidates, 6)] == [
        "H01", "H02", "H03", "H04", "H05", "H06"]


def test_choose_sample_never_exceeds_available_turns(analyzer):
    candidates = [{"prompt": "baseline", "track": "write", "persona_id": "H01",
                   "checkpoint_id": "w-baseline-H01-C1", "message_index": index} for index in range(2)]
    assert len(analyzer.choose_sample(candidates, 10)) == 2
    assert analyzer.choose_sample([], 6) == []


def test_collect_turns_keeps_only_finalized_evidence_of_one_interface(analyzer):
    def row(checkpoint_id, interface, status, message_indices=(0,)):
        return {"checkpoint_id": checkpoint_id, "conversation_id": "C1",
                "evidence": {"status": status, "track": "write",
                             "condition": {"interface": interface, "policy": "conservative", "prompt": "baseline",
                                           "persona_id": "H01", "model": "m", "repetition": 1},
                             "turns": [{"message_index": index, "status": "complete", "duration_seconds": 1.0,
                                        "requests": 1} for index in message_indices]}}
    rows = [row("a", "json", "format_error"), row("b", "native", "complete"), row("c", "json", "unexecuted"),
            row("d", "json", "running"), row("e", "json", "complete", (0, 1))]
    turns = analyzer.collect_turns(rows, "json")
    assert [(turn["checkpoint_id"], turn["message_index"]) for turn in turns] == [("a", 0), ("e", 0), ("e", 1)]


def write_journal(path, records):
    path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records),
                    encoding="utf-8")


def inference_record(checkpoint_id, message_index, content, index=0, kind="inference"):
    return {"context": {"checkpoint_id": checkpoint_id, "message_index": message_index, "track_id": "t"},
            "index": index, "kind": kind, "status_code": 200, "type": "request_finished",
            "response": completion(content)}


def test_read_last_responses_keeps_the_final_response_of_a_turn(analyzer, tmp_path):
    journal = tmp_path / "diagnostics.jsonl"
    write_journal(journal, [
        {"context": {"checkpoint_id": "t-C1", "message_index": 0, "track_id": "t"}, "index": 0,
         "kind": "catalog", "type": "request_finished", "response": {"data": []}},
        inference_record("t-C1", 0, '{"answer": "", "operations": []}', index=1),
        # The last response of a turn is the one whose parse decided the turn status.
        inference_record("t-C1", 0, "final prose answer", index=2),
        inference_record("other-C1", 0, "unwanted", index=3),
    ])
    wanted = {("t-C1", 0)}
    found, seen, lines, unreadable = analyzer.read_last_responses(journal, wanted)
    assert lines == 4
    assert unreadable == 0
    assert seen[("t-C1", 0)] == 2
    assert analyzer.message_content(found[("t-C1", 0)]["response"])[1] == "final prose answer"


def test_read_last_responses_counts_unreadable_context_instead_of_dropping_it(analyzer, tmp_path):
    journal = tmp_path / "diagnostics.jsonl"
    corrupt = {"context": {"track_id": "t"}, "index": 0, "kind": "inference", "type": "request_finished",
               "response": completion("x")}
    write_journal(journal, [inference_record("t-C1", 0, "kept"), corrupt])
    found, _, lines, unreadable = analyzer.read_last_responses(journal, {("t-C1", 0)})
    assert lines == 2
    assert unreadable == 1
    assert set(found) == {("t-C1", 0)}


def test_read_last_responses_tolerates_a_non_canonical_writer(analyzer, tmp_path):
    journal = tmp_path / "diagnostics.jsonl"
    journal.write_text(json.dumps(inference_record("t-C1", 0, "loose spacing")) + "\n", encoding="utf-8")
    found, _, _, unreadable = analyzer.read_last_responses(journal, {("t-C1", 0)})
    assert unreadable == 0
    assert analyzer.message_content(found[("t-C1", 0)]["response"])[1] == "loose spacing"


def test_declining_to_persist_is_a_narrow_nearby_pattern(analyzer):
    assert analyzer.DECLINES_TO_PERSIST.search("I won't save that; it is temporary.")
    assert analyzer.DECLINES_TO_PERSIST.search("Understood - I will not store it.")
    assert not analyzer.DECLINES_TO_PERSIST.search("I saved all five facts to memory.")


def test_markdown_names_the_evidence_source_and_the_limits(analyzer):
    def side(responses, answer_hits, answer_total, storage_hits, storage_total):
        return {"responses": responses, "answer_fact_mentions": answer_total, "answer_values_present": answer_hits,
                "responses_with_answer_expectation": responses, "responses_with_any_answer_value": answer_hits,
                "storage_fact_mentions": storage_total, "storage_values_present": storage_hits,
                "responses_with_storage_expectation": responses // 2, "present_with_workspace_evidence": 1,
                "excluded_answer_values_mentioned": 0, "responses_declining_to_persist": 1,
                "responses_with_reasoning": responses,
                "responses_with_no_response": 1,
                "with_answer_probe": {"responses": responses, "would_be_correct": 1,
                                      "would_have_valid_format": 2, "would_be_unknown": 0,
                                      "would_include_excluded_fact": 0},
                "by_track": {"write": {"responses": responses // 2, "answer_values_present": 0,
                                       "answer_fact_mentions": 0, "storage_values_present": storage_hits,
                                       "storage_fact_mentions": storage_total}}}
    report = {"snapshot": {"captured_at_unix": 1.0},
              "capture": {"inference_requests_by_this_analysis": 0},
              "evidence_note": "note", "exploratory_disclaimer": "disclaimer",
              "exploratory_answer_measure_disclaimer": "answer measure disclaimer",
              "coverage": {"interface": "json", "interface_turns_total": 10, "interface_turns_format_error": 9,
                           "interface_turns_other": 1, "checkpoints_finalized": 5, "checkpoints_scheduled": 10},
              "sample": {"selected": 3, "control_selected": 1, "unmatched_responses": 0, "stratification": "s"},
              "shape_counts_sampled": {shape: 0 for shape in analyzer.SHAPES},
              "shape_counts_control": {shape: 0 for shape in analyzer.SHAPES},
              "exploratory_value_presence_sampled": side(4, 2, 6, 1, 3),
              "exploratory_value_presence_control": side(2, 1, 2, 0, 0)}
    text = analyzer.markdown(report)
    assert "note" in text and "disclaimer" in text
    assert "2/6" in text and "1/3" in text and "1/2" in text
    assert "## Limits" in text
    assert "| Track |" in text
    assert "What the rejected text would have scored" in text
    for shape in analyzer.SHAPES:
        assert f"`{shape}`" in text