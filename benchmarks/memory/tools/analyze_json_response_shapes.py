"""Classify sampled JSON-interface failure responses from a live capture.

Read-only with respect to the capture directory. This tool never writes inside it,
never instantiates an inference client and never issues a model request, so it can
run against a collection that is still executing. Frozen scores are never recomputed
or altered. The optional value-presence pass reuses the frozen matcher and is a
separately identified exploratory upper bound, not a corrected score.

The failing response is recovered from the durable request journal rather than the
turn transcript. An adapter raises on an unusable response before the assistant
message is appended, so ``turn_finished`` records hold only the provisional messages
of a turn that already parsed. ``request_finished`` records hold every returned
completion, and the last inference response of a turn is the one whose parse decided
the turn status. This also means a failing response cannot be quoted from
``checkpoints.jsonl`` at all, which matters for the representative-failure deliverable.

Evidence is deduplicated the same way the reporting path does it: the latest record
per checkpoint id wins, because a terminal turn is persisted once per turn boundary
and again at checkpoint close.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import time

from memory_bench.assets import load_json, strict_json
from memory_bench.matching import matches_value, normalize
from memory_bench.provenance import collection_provenance, scorer_provenance
from memory_bench.reporting import load_capture
from memory_bench.scoring import score_answer

REQUEST_FINISHED = re.compile(r'"kind"\s*:\s*"inference"')
CONTEXT = re.compile(r'"checkpoint_id"\s*:\s*"([^"]+)"[\s\S]{0,120}?"message_index"\s*:\s*(\d+|null)')
OPERATION_VOCABULARY = re.compile(
    r"(?i)\b(remember|remembered|memory|memories|saved?|saving|store|stored|storing|"
    r"persist|persisted|forget|forgetful|update[ds]?|noted|note that)\b")
DECLINES_TO_PERSIST = re.compile(
    r"(?i)\b(won'?t|will not|not going to|do not|don'?t|never)\b[^.\n]{0,80}?"
    r"\b(save|saving|store|storing|persist|remember|memory)\b")

SHAPES = ("parses_as_json", "fenced_json", "json_prefix_then_prose", "json_embedded_in_prose",
          "prose_with_operation_vocabulary", "prose_other", "no_content_field", "no_response_returned")
FINALIZED = ("complete", "format_error", "deadline")


def response_shape(content):
    """Deterministic structural classification of one assistant response.

    Order matters: an envelope that parses is reported as such even when a later
    contract check rejects it, and an embedded envelope is distinguished from a
    response that merely opens with one.
    """
    if not isinstance(content, str):
        return "no_content_field"
    try:
        strict_json(content)
        return "parses_as_json"
    except (ValueError, TypeError):
        pass
    if "```" in content:
        return "fenced_json"
    if content.lstrip().startswith("{"):
        return "json_prefix_then_prose"
    if "{" in content:
        return "json_embedded_in_prose"
    if OPERATION_VOCABULARY.search(content):
        return "prose_with_operation_vocabulary"
    return "prose_other"


def delivered_answer_text(content):
    """The answer text a turn actually delivered.

    A successful JSON turn delivers a whole envelope whose "answer" field is the
    answer; a rejected turn delivered raw text. Scoring the envelope itself would
    fail every probe for reasons that have nothing to do with the answer, so the
    comparison uses the answer the turn delivered in either case.
    """
    if not isinstance(content, str):
        return None
    try:
        value = strict_json(content)
    except (ValueError, TypeError):
        return content
    if isinstance(value, dict) and isinstance(value.get("answer"), str):
        return value["answer"]
    return content


def message_content(completion):
    """Content and reasoning of the single returned choice, if the shape allows it."""
    choices = completion.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, None, None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None, None, None
    message = choice.get("message")
    if not isinstance(message, dict):
        return choice.get("finish_reason"), None, None
    return choice.get("finish_reason"), message.get("content"), message.get("reasoning_content")


def expected_targets(conversation, policy, track):
    """Expectations for one conversation, selected the way the frozen scorer selects them.

    Mirrors scoring.py: answer probes follow the per-track probe_fields, and storage
    expectations follow the per-track rule. Keeping both apart matters because most
    held-out checkpoints have no save expectation at all, so a save-only denominator
    would be dominated by turns that were never asked to save anything.
    """
    expected, common = conversation["policy_expectations"][policy], conversation["common_targets"]
    if track == "read":
        probe_fields = conversation["tracks"]["read"]["probe_fields"]
    elif track == "sequence":
        probe_fields = conversation["tracks"]["sequence"]["probe_fields"][policy]
    elif track == "write":
        probe_fields = common["probe_fields"]
    else:
        probe_fields = {}
    answer_facts = [fid for ids in probe_fields.values() for fid in ids]
    if track == "write":
        storage_facts = list(expected["required_additions"]) + [update["current"] for update in expected["required_updates"]]
    elif track in ("read", "sequence"):
        # The frozen scorer measures accumulated sequence state for both of these.
        storage_facts = list(conversation["tracks"]["sequence"]["expected_current_facts"][policy])
    else:
        # An unrecognized track yields no expectations rather than inheriting another
        # track's rule, so a malformed record cannot be read as the wrong track.
        answer_facts, storage_facts = [], []
    return {"answer_facts": list(dict.fromkeys(answer_facts)),
            "storage_facts": list(dict.fromkeys(storage_facts)),
            "probe_fields": probe_fields,
            "excluded_answer_facts": list(dict.fromkeys(common["excluded_answer_facts"]))}


def choose_sample(candidates, total):
    """Stratify by prompt and track, then round-robin personas inside each stratum.

    Fully deterministic given the candidate set: strata are visited in sorted order,
    and inside a stratum turns are taken one per persona per pass, personas in sorted
    order. No stratum or turn is chosen by inspecting its content.
    """
    strata = defaultdict(list)
    for turn in candidates:
        strata[(turn["prompt"], turn["track"])].append(turn)
    if not strata:
        return []
    base, remainder = divmod(total, len(strata))
    sample = []
    for index, key in enumerate(sorted(strata)):
        quota = base + (1 if index < remainder else 0)
        bucket = sorted(strata[key], key=lambda row: (row["persona_id"], row["checkpoint_id"], row["message_index"]))
        by_persona = defaultdict(list)
        for turn in bucket:
            by_persona[turn["persona_id"]].append(turn)
        personas = sorted(by_persona)
        depth, taken = 0, 0
        while taken < quota and any(len(by_persona[p]) > depth for p in personas):
            for persona in personas:
                if taken >= quota:
                    break
                if depth >= len(by_persona[persona]):
                    continue
                sample.append(by_persona[persona][depth])
                taken += 1
            depth += 1
    return sample


def collect_turns(rows, interface, policy_filter=None):
    """Flatten finalized turns of one interface, with the latest record per checkpoint."""
    turns = []
    for row in rows:
        evidence = row["evidence"]
        if evidence.get("status") not in FINALIZED:
            continue
        condition = evidence.get("condition") or {}
        if condition.get("interface") != interface:
            continue
        if policy_filter and condition.get("policy") not in policy_filter:
            continue
        for turn in evidence.get("turns") or []:
            turns.append({"checkpoint_id": row["checkpoint_id"], "persona_id": condition.get("persona_id"),
                          "conversation_id": row["conversation_id"], "policy": condition.get("policy"),
                          "prompt": condition.get("prompt"), "interface": interface, "track": evidence.get("track"),
                          "message_index": turn.get("message_index"), "status": turn.get("status"),
                          "duration_seconds": turn.get("duration_seconds"), "requests": turn.get("requests")})
    return turns


def read_last_responses(diagnostics, wanted):
    """One sequential pass collecting the final inference response of each wanted turn.

    The canonical writer sorts keys, so a record's discriminating fields sit at
    different offsets. Match the kind anywhere in the line, read the context from the
    head, and keep the last response per turn because that is the one whose parse
    determined the turn status. A line that claims an inference response but has no
    readable context is counted, never dropped silently.
    """
    found, seen, lines, unreadable = {}, Counter(), 0, 0
    with diagnostics.open("r", encoding="utf-8") as handle:
        for line in handle:
            lines += 1
            if not REQUEST_FINISHED.search(line):
                continue
            match = CONTEXT.search(line[:240])
            if match is None:
                unreadable += 1
                continue
            key = (match.group(1), None if match.group(2) == "null" else int(match.group(2)))
            if key not in wanted:
                continue
            value = json.loads(line)
            found[key] = value
            seen[key] += 1
    return found, seen, lines, unreadable


def file_state(path):
    stat = path.stat()
    return {"name": path.name, "bytes": stat.st_size, "modified_unix": stat.st_mtime}


def scheduled_coverage(manifest):
    schedule = manifest["schedule"]
    if any(entry["condition"]["dataset"] != "heldout" for entry in schedule):
        raise ValueError("response-shape analysis requires a held-out capture")
    return {"checkpoints_scheduled": sum(len(entry["checkpoints"]) for entry in schedule),
            "track_runs_scheduled": len(schedule)}


def output_paths(capture, output, label):
    capture, output = Path(capture).resolve(), Path(output).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", label):
        raise ValueError("label must contain only letters, digits, underscores or hyphens")
    paths = [(output / f"{label}.{extension}").resolve() for extension in ("json", "md")]
    if output == capture or capture in output.parents:
        raise ValueError("output directory must not be inside the capture directory")
    if any(path.parent != output or path == capture or capture in path.parents for path in paths):
        raise ValueError("output files must stay inside the output directory and outside the capture")
    return paths


def analyze(capture, sample_size, interface="json", policies=None):
    capture = Path(capture)
    manifest, rows = load_capture(capture)
    coverage = scheduled_coverage(manifest)
    diagnostics = capture / "diagnostics.jsonl"
    if not diagnostics.is_file():
        raise ValueError("capture has no diagnostics journal")

    scorer, collection = scorer_provenance(), collection_provenance()
    if scorer["sha256"] != manifest["collection_scoring"]["sha256"]:
        raise ValueError("installed scorer differs from the captured frozen scorer")

    turns = collect_turns(rows, interface, policies)
    failing = [turn for turn in turns if turn["status"] == "format_error"]
    control = [turn for turn in turns if turn["status"] != "format_error"]
    sample = choose_sample(failing, sample_size)
    control_sample = choose_sample(control, min(len(control), sample_size)) if control else []
    wanted = {(turn["checkpoint_id"], turn["message_index"]) for turn in sample + control_sample}

    before = file_state(diagnostics)
    responses, seen, lines, unreadable = read_last_responses(diagnostics, wanted)
    after = file_state(diagnostics)

    personas = {persona["id"]: persona for persona in load_json("corpus/heldout.json")["personas"]}
    analyzed, missing = [], []
    for turn in sample + control_sample:
        key = (turn["checkpoint_id"], turn["message_index"])
        if key not in responses:
            missing.append({"checkpoint_id": turn["checkpoint_id"], "message_index": turn["message_index"],
                            "reason": "no finished inference response in journal"})
            continue
        record = responses[key]
        completion = record.get("response")
        returned = isinstance(completion, dict)
        finish_reason, content, reasoning = message_content(completion or {})
        shape = response_shape(content) if returned else "no_response_returned"
        persona = personas[turn["persona_id"]]
        conversation = next(c for c in persona["conversations"] if c["id"] == turn["conversation_id"])
        targets = expected_targets(conversation, turn["policy"], turn["track"])
        facts = persona["facts"]
        text = content if isinstance(content, str) else ""
        answer_present = sorted(fid for fid in targets["answer_facts"] if matches_value(text, facts[fid]))
        storage_present = sorted(fid for fid in targets["storage_facts"] if matches_value(text, facts[fid]))
        workspace_evidence = sorted(
            fid for fid in dict.fromkeys(answer_present + storage_present)
            if facts[fid]["workspace"]
            and normalize(persona["workspaces"][facts[fid]["workspace"]]) in normalize(text))
        # Exploratory: apply the frozen answer scorer to a response the harness already
        # rejected, to separate what the response said from how it was delivered. The
        # frozen checkpoint score is untouched; nothing here is rematched into it.
        answer_measure = score_answer(persona, delivered_answer_text(content), targets["probe_fields"],
                                      targets["excluded_answer_facts"], executed=returned)
        analyzed.append({
            **turn, "shape": shape, "response_returned": returned, "finish_reason": finish_reason,
            "status_code": record.get("status_code"), "request_error": record.get("error"),
            "response_characters": len(text),
            "reasoning_characters": len(reasoning) if isinstance(reasoning, str) else 0,
            "responses_in_turn": seen[key], "declines_to_persist": bool(DECLINES_TO_PERSIST.search(text)),
            "answer_fact_count": len(targets["answer_facts"]),
            "answer_values_present": answer_present,
            "answer_values_absent": sorted(fid for fid in targets["answer_facts"] if fid not in answer_present),
            "storage_fact_count": len(targets["storage_facts"]),
            "storage_values_present": storage_present,
            "storage_values_absent": sorted(fid for fid in targets["storage_facts"] if fid not in storage_present),
            "present_with_workspace_evidence": workspace_evidence,
            "excluded_answer_values_mentioned": sorted(fid for fid in targets["excluded_answer_facts"]
                                                       if matches_value(text, facts[fid])),
            "answer_measure": {"scored": answer_measure["scored"], "reason": answer_measure["reason"],
                               "answer_format": answer_measure.get("answer_format"),
                               "correct": answer_measure.get("correct"),
                               "unknown": answer_measure.get("unknown"),
                               "scope_correct": answer_measure.get("scope_correct"),
                               "excluded_facts": answer_measure.get("excluded_facts", []),
                               "malformed_lines": len(answer_measure.get("malformed_lines", []))}})

    sampled = [row for row in analyzed if row["status"] == "format_error"]
    controls = [row for row in analyzed if row["status"] != "format_error"]

    def presence(rows_):
        answer_total = sum(row["answer_fact_count"] for row in rows_)
        storage_total = sum(row["storage_fact_count"] for row in rows_)
        return {"responses": len(rows_),
                "responses_with_answer_expectation": sum(1 for row in rows_ if row["answer_fact_count"]),
                "answer_fact_mentions": answer_total,
                "answer_values_present": sum(len(row["answer_values_present"]) for row in rows_),
                "responses_with_any_answer_value": sum(1 for row in rows_ if row["answer_values_present"]),
                "responses_with_storage_expectation": sum(1 for row in rows_ if row["storage_fact_count"]),
                "storage_fact_mentions": storage_total,
                "storage_values_present": sum(len(row["storage_values_present"]) for row in rows_),
                "responses_with_any_storage_value": sum(1 for row in rows_ if row["storage_values_present"]),
                "present_with_workspace_evidence": sum(len(row["present_with_workspace_evidence"]) for row in rows_),
                "excluded_answer_values_mentioned": sum(len(row["excluded_answer_values_mentioned"]) for row in rows_),
                "responses_declining_to_persist": sum(1 for row in rows_ if row["declines_to_persist"]),
                "responses_with_reasoning": sum(1 for row in rows_ if row["reasoning_characters"] > 0),
                "responses_with_no_response": sum(1 for row in rows_ if not row["response_returned"]),
                "with_answer_probe": {
                    "responses": sum(1 for row in rows_ if row["answer_measure"]["scored"]),
                    "would_be_correct": sum(1 for row in rows_ if row["answer_measure"]["correct"] is True),
                    "would_have_valid_format": sum(1 for row in rows_ if row["answer_measure"]["answer_format"] is True),
                    "would_be_unknown": sum(1 for row in rows_ if row["answer_measure"]["unknown"] is True),
                    "would_include_excluded_fact": sum(1 for row in rows_
                                                       if row["answer_measure"]["excluded_facts"])},
                "by_track": {track: {"responses": sum(1 for row in rows_ if row["track"] == track),
                                     "answer_values_present": sum(len(row["answer_values_present"]) for row in rows_
                                                                 if row["track"] == track),
                                     "answer_fact_mentions": sum(row["answer_fact_count"] for row in rows_
                                                                  if row["track"] == track),
                                     "storage_values_present": sum(len(row["storage_values_present"]) for row in rows_
                                                                  if row["track"] == track),
                                     "storage_fact_mentions": sum(row["storage_fact_count"] for row in rows_
                                                                  if row["track"] == track)}
                             for track in sorted({row["track"] for row in rows_})}}

    def shape_counts(rows_):
        counts = Counter(row["shape"] for row in rows_)
        return {shape: counts.get(shape, 0) for shape in SHAPES}

    per_cell = {}
    for row in sampled:
        per_cell.setdefault(f"{row['prompt']}|{row['track']}", Counter())[row["shape"]] += 1

    return {
        "analysis": "json-interface-response-shapes",
        "analysis_number": 1,
        "status": "interim_exploratory_partial_coverage",
        "capture": {"action": manifest.get("action"), "status": manifest.get("status"),
                    "started_at": manifest.get("started_at"), "finished_at": manifest.get("finished_at"),
                    "requested": manifest.get("requested"), "settings": manifest.get("settings"),
                    "selected_models": sorted({row["condition"]["model"] for row in manifest["schedule"]}),
                    "output_root_redacted": True, "inference_requests_by_this_analysis": 0},
        "snapshot": {"captured_at_unix": time.time(), "diagnostics_lines_scanned": lines,
                     "inference_lines_without_readable_context": unreadable,
                     "diagnostics_before": before, "diagnostics_after": after},
        "scoring_identity": {"installed_scorer_sha256": scorer["sha256"],
                             "captured_scorer_sha256": manifest["collection_scoring"]["sha256"],
                             "identical": True, "installed_collection_sha256": collection["sha256"],
                             "captured_collection_sha256": manifest["collection"]["sha256"],
                             "collection_identical": collection["sha256"] == manifest["collection"]["sha256"],
                             "frozen_protocol_unmodified": True},
        "evidence_note": (
            "A failing response is not present in the turn transcript. The adapter raises before the assistant "
            "message is appended, so turn_finished holds only provisional messages of a turn that already parsed. "
            "Responses here are the last finished inference request of each sampled turn, read from the durable "
            "request journal. A representative failing JSON response therefore cannot be quoted from "
            "checkpoints.jsonl."),
        "coverage": {**coverage,
                     "checkpoints_finalized": sum(1 for row in rows if row["evidence"].get("status") in FINALIZED),
                     "interface": interface, "interface_turns_total": len(turns),
                     "interface_turns_format_error": len(failing), "interface_turns_other": len(control)},
        "sample": {"requested": sample_size, "selected": len(sample), "control_selected": len(control_sample),
                   "unmatched_responses": len(missing), "unmatched": missing,
                   "stratification": "prompt x track, round-robin personas inside each stratum, sorted deterministic order",
                   "keys": [{"checkpoint_id": row["checkpoint_id"], "message_index": row["message_index"]}
                            for row in sample]},
        "shape_counts_sampled": shape_counts(sampled),
        "shape_counts_control": shape_counts(controls),
        "shapes_by_cell": {cell: dict(counts) for cell, counts in sorted(per_cell.items())},
        "exploratory_value_presence_sampled": presence(sampled),
        "exploratory_value_presence_control": presence(controls),
        "exploratory_answer_measure_disclaimer": (
            "Exploratory only. The frozen score_answer function is applied to the answer text each turn actually delivered: "
            "the inner `answer` field for a JSON envelope, or the raw response for a rejected one. It is applied to "
            "turns the harness already rejected, to show what that text would have scored had it been delivered as an "
            "answer. The checkpoint's frozen score is unchanged, no response is re-executed and no memory "
            "operation is replayed. A rejected response that would have scored is evidence about delivery, not a "
            "corrected benchmark result."),
        "exploratory_disclaimer": (
            "Exploratory only. The frozen matcher is applied to raw assistant prose to count whether an expected "
            "value appears anywhere in the response. There is no one-to-one assignment between facts and spans, so "
            "these counts are an upper bound: a long answer can satisfy a fact incidentally, and paraphrase or an "
            "alternative wording is invisible to lexical matching. No rematching, no corrected recall and no frozen "
            "score is derived or changed."),
        "per_response": analyzed,
    }


def markdown(report):
    coverage, sample = report["coverage"], report["sample"]
    sampled, control = report["exploratory_value_presence_sampled"], report["exploratory_value_presence_control"]
    lines = [
        "# Sampled JSON-interface response shapes",
        "",
        f"Snapshot: {report['snapshot']['captured_at_unix']:.0f} unix. The capture was still running. This analysis "
        f"made {report['capture']['inference_requests_by_this_analysis']} inference requests. Aggregate counts, the "
        "sample definition and per-response rows are in "
        "[json-interface-response-shapes-01.json](json-interface-response-shapes-01.json).",
        "",
        "This is interim, exploratory, partial-coverage evidence. It is not Phase 5 acceptance and it changes no "
        "frozen score.",
        "",
        "## Where the failing response comes from",
        "",
        report["evidence_note"],
        "",
        "## Population",
        "",
        f"- {coverage['interface_turns_total']} finalized `{coverage['interface']}` turns, of which "
        f"{coverage['interface_turns_format_error']} are `format_error` and {coverage['interface_turns_other']} "
        "are not.",
        f"- {coverage['checkpoints_finalized']} of {coverage['checkpoints_scheduled']} scheduled checkpoints are "
        "finalized.",
        "",
        "## Sample",
        "",
        f"- {sample['selected']} failing turns sampled from the {coverage['interface_turns_format_error']} "
        f"`format_error` turns, plus {sample['control_selected']} control turns without a format error.",
        f"- Stratification: {sample['stratification']}.",
        f"- Turns without a readable finished response: {sample['unmatched_responses']}.",
        "",
        "## Response shapes",
        "",
        "| Shape | Sampled `format_error` | Control |",
        "|---|---:|---:|",
    ]
    for shape in SHAPES:
        lines.append(f"| `{shape}` | {report['shape_counts_sampled'].get(shape, 0)} | "
                     f"{report['shape_counts_control'].get(shape, 0)} |")
    lines += [
        "",
        "## Exploratory value presence",
        "",
        report["exploratory_disclaimer"],
        "",
        "| Measure | Sampled `format_error` | Control |",
        "|---|---:|---:|",
        f"| Responses | {sampled['responses']} | {control['responses']} |",
        f"| Answer-probe values present | {sampled['answer_values_present']}/{sampled['answer_fact_mentions']} | "
        f"{control['answer_values_present']}/{control['answer_fact_mentions']} |",
        f"| Responses with an answer expectation | {sampled['responses_with_answer_expectation']}/{sampled['responses']} | "
        f"{control['responses_with_answer_expectation']}/{control['responses']} |",
        f"| Responses containing at least one answer value | "
        f"{sampled['responses_with_any_answer_value']}/{sampled['responses']} | "
        f"{control['responses_with_any_answer_value']}/{control['responses']} |",
        f"| Save-expectation values present | {sampled['storage_values_present']}/{sampled['storage_fact_mentions']} | "
        f"{control['storage_values_present']}/{control['storage_fact_mentions']} |",
        f"| Responses with a save expectation | {sampled['responses_with_storage_expectation']}/{sampled['responses']} | "
        f"{control['responses_with_storage_expectation']}/{control['responses']} |",
        f"| Present values with workspace evidence | {sampled['present_with_workspace_evidence']} | "
        f"{control['present_with_workspace_evidence']} |",
        f"| Responses mentioning an excluded answer value | {sampled['excluded_answer_values_mentioned']} | "
        f"{control['excluded_answer_values_mentioned']} |",
        f"| Responses explicitly declining to persist | {sampled['responses_declining_to_persist']} | "
        f"{control['responses_declining_to_persist']} |",
        f"| Responses carrying separate reasoning content | {sampled['responses_with_reasoning']} | "
        f"{control['responses_with_reasoning']} |",
        "",
        "Answer-probe and save expectations are reported separately because most held-out checkpoints were never "
        "asked to save anything; a combined denominator would be dominated by turns with no expectation at all.",
        "",
        "## What the rejected text would have scored",
        "",
        report["exploratory_answer_measure_disclaimer"],
        "",
        "| Measure | Sampled `format_error` | Control |",
        "|---|---:|---:|",
        f"| Responses with an answer probe | {sampled['with_answer_probe']['responses']} | "
        f"{control['with_answer_probe']['responses']} |",
        f"| Would have been fully correct | {sampled['with_answer_probe']['would_be_correct']} | "
        f"{control['with_answer_probe']['would_be_correct']} |",
        f"| Would have had valid probe format | {sampled['with_answer_probe']['would_have_valid_format']} | "
        f"{control['with_answer_probe']['would_have_valid_format']} |",
        f"| Would satisfy fields requiring UNKNOWN | {sampled['with_answer_probe']['would_be_unknown']} | "
        f"{control['with_answer_probe']['would_be_unknown']} |",
        f"| Would have leaked an excluded fact | "
        f"{sampled['with_answer_probe']['would_include_excluded_fact']} | "
        f"{control['with_answer_probe']['would_include_excluded_fact']} |",
        "",
        "A rejected response that is already in the required `field: value` probe format, with correct values and no "
        "excluded fact, failed only because the JSON adapter requires the whole response to be one JSON object. That "
        "is the clearest separation this sample offers between memory behaviour and envelope adherence.",
        "",
        "| Track | Sampled responses | Answer values | Save values | Control responses | Answer values | Save values |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for track in sorted(set(sampled["by_track"]) | set(control["by_track"])):
        left, right = sampled["by_track"].get(track, {}), control["by_track"].get(track, {})
        lines.append(
            f"| `{track}` | {left.get('responses', 0)} | "
            f"{left.get('answer_values_present', 0)}/{left.get('answer_fact_mentions', 0)} | "
            f"{left.get('storage_values_present', 0)}/{left.get('storage_fact_mentions', 0)} | "
            f"{right.get('responses', 0)} | "
            f"{right.get('answer_values_present', 0)}/{right.get('answer_fact_mentions', 0)} | "
            f"{right.get('storage_values_present', 0)}/{right.get('storage_fact_mentions', 0)} |")
    lines += [
        "",
        "## Limits",
        "",
        f"- The failing population and the covered conditions are still growing: only "
        f"{coverage['checkpoints_finalized']} of {coverage['checkpoints_scheduled']} checkpoints are finalized and "
        "only the policies executed so far appear.",
        "- Presence is not correctness. The frozen answer measure also requires one `field: value` line per probe "
        "field, exactly one value per field and no excluded fact, so a response can contain every expected value "
        "and still score zero. High presence counts, such as the read track above, bound what the response said, "
        "not what the frozen scorer awards.",
        "- Write-track presence is naturally low because the turn asks a question rather than a restatement; a low "
        "count there is not evidence of a lost fact.",
        f"- Control turns are not all successful answers: {control['responses_with_no_response']} of "
        f"{control['responses']} are `deadline` turns whose request returned nothing, reported as "
        "`no_response_returned` rather than as an answer shape.",
        "- Presence counts are an unassigned upper bound, not a score, and are not comparable to frozen storage "
        "precision or recall.",
        "- Controls use the same quota procedure but are not matched to failing turns. Empty or small strata "
        "can leave quotas unfilled. Differences between these samples do not establish superiority.",
        "- Shapes describe this model, server, policy, prompt and interface combination at one repetition. They do "
        "not establish the cause of JSON-mode failure. The harness requests response_format: json_object; "
        "the capture does not establish whether the server applied a grammar.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="live or finished capture directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="directory for the JSON and Markdown output")
    parser.add_argument("--sample", type=int, default=150, help="failing turns to sample")
    parser.add_argument("--interface", default="json")
    parser.add_argument("--policies", nargs="*", default=None, help="restrict to these policies")
    parser.add_argument("--label", default="json-interface-response-shapes-01")
    args = parser.parse_args()
    if args.sample < 1:
        parser.error("--sample must be positive")
    capture = args.capture.resolve()
    output = args.output_dir.resolve()
    try:
        json_path, markdown_path = output_paths(capture, output, args.label)
    except ValueError as exc:
        parser.error(str(exc))
    report = analyze(capture, args.sample, args.interface, args.policies)
    output.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown(report), encoding="utf-8")
    print(f"{args.label}: sampled {report['sample']['selected']} of "
          f"{report['coverage']['interface_turns_format_error']} failing turns; "
          f"shapes {report['shape_counts_sampled']}")


if __name__ == "__main__":
    main()
