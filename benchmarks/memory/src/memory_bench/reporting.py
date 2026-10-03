"""Offline rescoring and sanitized reports; never instantiate an inference client."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import statistics

from .assets import asset_hashes, canonical_json, load_json
from .capture import read_checkpoints, write_json
from .checkpoints import checkpoint_evidence
from .comparison import POLICY_MEANING, comparisons, condition_details, representative_failures
from .experiments import isolated_persona
from .provenance import scorer_provenance
from .scoring import aggregate_scores, score_checkpoint


def load_capture(path: str | Path) -> tuple[dict, list[dict]]:
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("protocol") != "standalone-memory-benchmark-v1":
        raise ValueError("unsupported captured evidence")
    frozen, installed = manifest["collection"]["asset_hashes"], asset_hashes()
    required = {"contract.json", "corpus-schema.json", "protocol/operations.md"}
    required.update(f"corpus/{row['condition']['dataset']}.json" for row in manifest["schedule"])
    if any(frozen.get(name) != installed.get(name) for name in required):
        raise ValueError("captured corpus/contract/lifecycle differs from installed scoring inputs")
    rows = {row["checkpoint_id"]: row for row in read_checkpoints(path)}
    ordered = []
    for entry in manifest["schedule"]:
        for checkpoint in entry["checkpoints"]:
            identifier = checkpoint["checkpoint_id"]
            if identifier in rows:
                row = rows.pop(identifier)
                if (row["track_id"] != entry["track_id"] or row["evidence"]["condition"] != entry["condition"] or
                        row["evidence"]["track"] != entry["track"] or row["conversation_id"] != checkpoint["conversation_id"]):
                    raise ValueError("checkpoint does not match captured schedule")
            else:
                row = {"checkpoint_id": identifier, "track_id": entry["track_id"], "condition_id": entry["condition_id"],
                       "persona_id": entry["condition"]["persona_id"], "conversation_id": checkpoint["conversation_id"],
                       "injected_memory": None, "evidence": checkpoint_evidence(condition=entry["condition"], track=entry["track"],
                        starting_records=None, final_records=None, turns=[], status="unexecuted")}
            # A process killed between turns retains snapshots, but cannot claim a
            # finished checkpoint. Raw status and diagnostics remain on disk.
            if row["evidence"]["status"] == "running":
                row = deepcopy(row)
                row["evidence"]["status"] = "interrupted"
                row["evidence"]["errors"].append({"code": "interrupted"})
            ordered.append(row)
    if rows:
        raise ValueError("captured checkpoint is outside the declared schedule")
    return manifest, ordered


def request_summary(requests: list[dict]) -> dict:
    inference = [r for r in requests if r["kind"] == "inference"]
    usage = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [r["usage"].get(field) for r in inference if isinstance(r.get("usage"), dict)]
        values = [v for v in values if type(v) is int and v >= 0]
        usage[field] = sum(values) if values else None
        usage[field + "_reported_requests"] = len(values)
    durations = sorted(r["duration_seconds"] for r in inference if type(r.get("duration_seconds")) in (int, float)
                       and r["duration_seconds"] >= 0)
    return {"inference_requests": len(inference), "catalog_requests": sum(r["kind"] == "catalog" for r in requests),
            "failed_requests": sum(r.get("error") is not None for r in inference),
            "missing_usage_requests": sum(r.get("usage") is None for r in inference), "usage": usage,
            "upstream_seconds": sum(durations), "latency_seconds": {
                "reported_requests": len(durations), "missing_requests": len(inference) - len(durations),
                "min": min(durations) if durations else None, "median": statistics.median(durations) if durations else None,
                "p90": durations[max(0, (9 * len(durations) + 9) // 10 - 1)] if durations else None,
                "max": max(durations) if durations else None, "p90_method": "nearest rank"}, "cost": None}


def reporting_provenance() -> dict:
    root = files("memory_bench")
    sources = {name: hashlib.sha256(root.joinpath(name).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()
               for name in ("reporting.py", "comparison.py")}
    revision = "standalone-memory-report-v1"
    return {"revision": revision, "source_hashes": sources,
            "sha256": hashlib.sha256(canonical_json({"revision": revision, "sources": sources})).hexdigest()}


def turn_coverage(manifest: dict, rows: list[dict]) -> dict:
    scheduled = sum(len(cp["message_indices"]) for entry in manifest["schedule"] for cp in entry["checkpoints"])
    turns = [turn for row in rows for turn in row["evidence"]["turns"]]
    return {"scheduled": scheduled, "executed": len(turns), "completed": sum(t["status"] == "complete" for t in turns),
            "failed": sum(t["status"] != "complete" for t in turns), "unexecuted": scheduled - len(turns)}


def model_metadata(manifest: dict) -> dict:
    requests = [r for r in manifest["requests"] if r["kind"] == "inference"]
    advertised = (manifest.get("catalog") or {}).get("data", [])
    return {"advertised": [{key: deepcopy(row.get(key)) for key in ("id", "owned_by", "created", "meta")}
                           for row in advertised],
            "response_models": sorted({r["response_model"] for r in requests if isinstance(r.get("response_model"), str)}),
            "missing_response_model_requests": sum(r.get("response_model") is None for r in requests),
            "servers": sorted({r["server"] for r in requests if isinstance(r.get("server"), str)}),
            "system_fingerprints": sorted({r["system_fingerprint"] for r in requests if isinstance(r.get("system_fingerprint"), str)})}


def sanitized(value):
    private = {"authorization", "proxy-authorization", "headers", "base_url", "url", "output", "request_id",
               "request", "response", "response_text", "messages", "provisional_answers", "reasoning_content", "replay_of"}
    if isinstance(value, dict):
        # Public errors retain codes/types/counts; raw server messages stay private.
        return {key: sanitized(child) for key, child in value.items() if key.lower() not in private
                and not (key == "message" and ("code" in value or "type" in value))}
    if isinstance(value, list):
        return [sanitized(child) for child in value]
    return value


def scored_report(manifest: dict, rows: list[dict]) -> dict:
    corpora = {name: {p["id"]: p for p in load_json(f"corpus/{name}.json")["personas"]}
               for name in {row["condition"]["dataset"] for row in manifest["schedule"]}}
    scores = []
    for row in rows:
        condition = row["evidence"]["condition"]
        persona = isolated_persona(corpora[condition["dataset"]][condition["persona_id"]], row["track_id"])
        conversation = next(c for c in persona["conversations"] if c["id"] == row["conversation_id"])
        scores.append(score_checkpoint(persona, conversation, condition["policy"], row["evidence"]["track"], row["evidence"]))
    coverage = {"track_runs": len(manifest["schedule"]), "checkpoints": len(rows),
                "completed": sum(row["evidence"]["status"] == "complete" for row in rows),
                "failed": sum(row["evidence"]["status"] not in ("complete", "unexecuted") for row in rows),
                "unexecuted": sum(row["evidence"]["status"] == "unexecuted" for row in rows)}
    current = scorer_provenance()
    history = deepcopy(manifest.get("scoring_history", [manifest["collection_scoring"]]))
    if history[-1] != current:
        history.append(current)
    groups = aggregate_scores(scores)
    for group in groups:
        group["details"] = condition_details(group)
    repetitions = sorted({row["condition"]["repetition"] for row in manifest["schedule"]})
    return sanitized({"schema_version": 1, "protocol": manifest["protocol"], "action": manifest["action"],
        "status": manifest["status"], "gate_passed": manifest["status"] == "complete" and coverage["unexecuted"] == 0,
        "collection": manifest["collection"], "collection_scoring": manifest["collection_scoring"], "scoring": current,
        "scoring_history": history, "settings": manifest["settings"],
        "server_effective_settings": manifest.get("server_effective_settings"), "requested": manifest["requested"],
        "schedule": manifest["schedule"], "actual_schedule": manifest["actual_schedule"],
        "actual_checkpoints": manifest["actual_checkpoints"], "coverage": coverage,
        "requests": request_summary(manifest["requests"]), "errors": manifest["errors"],
        "cleanup": manifest["cleanup"], "conditions": groups, "checkpoint_evidence": rows,
        "turn_coverage": turn_coverage(manifest, rows), "model_metadata": model_metadata(manifest),
        "reporting": reporting_provenance(), "comparisons": comparisons(groups),
        "representative_failures": representative_failures(groups),
        "comparison_limits": {"repetitions": repetitions, "one_repetition": repetitions == [1],
            "policy_requirements": POLICY_MEANING, "confidence_intervals": None,
            "notes": ["Descriptive measurements; no statistical superiority claim or prompt-independent model ranking.",
                "Every comparison keeps dataset and track fixed, plus all condition factors except the named factor.",
                "Selected case identities must match to calculate rate differences; failed and unexecuted cases remain visible.",
                "Policies have different conformance requirements; use fixed common outcomes when contrasting policies.",
                "Sequence storage sums repeated checkpoint-state observations, not distinct facts or independent samples.",
                "Null denominators, missing answers and unexercised prerequisites do not count as passes.",
                "Fixed lexical matching can miss paraphrases; results remain separate from historical benchmarks."]},
        "offline_inference_requests": 0})


def markdown(report: dict) -> str:
    def ratio(value):
        return "null" if value is None else f"{value:.3f}"
    def outcomes(value):
        return (f"{value['passed']}/{value['denominator']}" if value["denominator"] else "null (0/0)") + f"; {value.get('unscored', 0)} unscored"
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# Standalone memory benchmark report", "", f"Collection status: **{report['status']}**. Infrastructure gate: **{'passed' if report['gate_passed'] else 'failed'}**.",
        "", "Model misses, false recall, consent questions and format/tool failures are measured outcomes; they do not become infrastructure successes or disappear when a later response finishes.",
        "", f"Coverage: {report['coverage']['track_runs']} track runs; {report['coverage']['completed']} completed, {report['coverage']['failed']} failed and {report['coverage']['unexecuted']} unexecuted checkpoints.",
        "", "## Conditions and separate tracks", "",
        "| Model | Policy | Prompt | Interface | Track | Policy conformance | Storage TP/FP/FN | Precision | Recall | Common fact recall | Common answers |", 
        "|---|---|---|---|---|---|---|---|---|---|---|"]
    for group in report["conditions"]:
        condition, storage = group["condition"], group["storage"]
        values = [condition["model"], group["policy"], condition["prompt"], condition["interface"], group["track"],
                  outcomes(group["conformance"]), f"{storage['tp']}/{storage['fp']}/{storage['fn']}", ratio(storage["precision"]),
                  ratio(storage["recall"]), ratio(group["common"]["fact_presence"]["recall"]), outcomes(group["common"]["answers"]["correct"])]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "## Scoring meaning and detailed outcomes", "",
        "Write storage measures new/changed current facts after subtracting equivalent prepared prior facts. Prepared reads earn no save credit. Sequence storage measures accumulated actual owner state at each checkpoint; summed counts include repeated state observations.",
        "Unexecuted/missing answers and absent control prerequisites remain unscored; denominators are retained in JSON. Scope/temporary-state counts are repeated observed records, with missing-state cases explicit.", "",
        "| Model | Policy | Prompt | Interface | Track | Storage precision TP/(TP+FP) | Storage recall TP/(TP+FN) | Format | Preference format | Preference reason | Scope correct/known | Consent | Duplicates | Temporary operations | Tool errors | Format-failed cases | API-failed cases |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"])
    for g in report["conditions"]:
        d, s = g["details"], g["storage"]
        values = [g["condition"]["model"], g["policy"], g["condition"]["prompt"], g["condition"]["interface"], g["track"],
            f"{s['tp']}/{s['precision_denominator']}" if s["precision_denominator"] else "null (0/0)",
            f"{s['tp']}/{s['recall_denominator']}" if s["recall_denominator"] else "null (0/0)",
            outcomes(g["answers"]["format"]), outcomes(d["preference_format"]), outcomes(d["preference_reason"]),
            f"{d['scope']['correct']}/{d['scope']['denominator']}" if d["scope"]["denominator"] else "null (0/0)",
            outcomes(d["consent"]), g["diagnostics"]["duplicate_records"], g["diagnostics"]["temporary_save_operations"],
            g["diagnostics"]["tool_errors"], d["case_errors"].get("format_error", 0), d["case_errors"].get("api_error", 0)]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "| Model | Policy | Prompt | Interface | Track | Current correction | Old current retired | Historical wording retired | All old wording retired | Forgetting | Controls exercised/unexercised | Completed/failed/unexecuted |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|"])
    for g in report["conditions"]:
        values = [g["condition"]["model"], g["policy"], g["condition"]["prompt"], g["condition"]["interface"], g["track"],
            *(outcomes(g["controls"]["corrections"][key]) for key in ("current_correction", "old_current_retired", "old_history_retired", "old_value_retired")),
            outcomes(g["controls"]["forgetting"]), f"{g['coverage']['controls_exercised']}/{g['coverage']['controls_unexercised']}",
            f"{g['coverage']['completed']}/{g['coverage']['failed']}/{g['coverage']['unexecuted']}"]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "## Comparisons with fixed factors", "",
        "Conservative requires explicit durability; recurring additionally saves stable non-sensitive incidental context. Their conformance labels differ. Common behavioral outcomes use fixed targets."])
    for kind, pairs in report["comparisons"].items():
        lines.extend(["", f"### {kind.capitalize()}", ""])
        if not pairs:
            lines.append("No matched comparison selected." + (" A model comparison requires at least two advertised IDs." if kind == "model" else ""))
            continue
        lines.extend(["Each row keeps all shown factors fixed; differences are right minus left and are descriptive. JSON preserves both sides' counts, denominators and failed/unexecuted coverage.", "",
            "| Fixed factors | Left → right | Matched selected cases | Conformance difference | Storage recall difference | Common fact recall difference | Common answer difference |",
            "|---|---|---|---|---|---|---|"])
        for pair in pairs:
            delta = pair["right_minus_left"]
            values = [json.dumps(pair["fixed"], sort_keys=True), f"{pair['left']} → {pair['right']}", pair["matched_selected_cases"],
                *(ratio(delta[key]) for key in ("policy_conformance", "storage_recall", "common_fact_recall", "common_answers"))]
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    requests = report["requests"]
    lines.extend(["", "## Requests, provenance and cleanup", "",
        f"Inference requests: {requests['inference_requests']}; failed HTTP requests: {requests['failed_requests']}; missing usage: {requests['missing_usage_requests']}.",
        f"Reported tokens: input={requests['usage']['prompt_tokens']}, output={requests['usage']['completion_tokens']}; local cost=null.",
        f"Turn coverage: `{json.dumps(report['turn_coverage'], sort_keys=True)}`. Unexecuted follow-ups and unexecuted checkpoints remain distinct.",
        f"Latency in seconds: `{json.dumps(requests['latency_seconds'], sort_keys=True)}`.",
        f"Submitted settings: `{json.dumps(report['settings'], sort_keys=True)}`. Server-effective settings: `{json.dumps(report['server_effective_settings'])}` (unavailable unless reported).",
        f"Model/server metadata: `{json.dumps(report['model_metadata'], sort_keys=True)}`.",
        f"Collection hash: `{report['collection']['sha256']}`. Scoring hash: `{report['scoring']['sha256']}`.",
        f"Reporting hash: `{report['reporting']['sha256']}`. Python={report['collection']['python']}; platform={report['collection']['platform']}; httpx={report['collection']['httpx']}; package={report['collection']['package_version']}.",
        f"Cleanup: **{report['cleanup']['status']}**. Offline replay/report inference requests: 0.", "", "## Case outcomes", "",
        "| Model | Policy | Prompt | Interface | Track | Persona | Repetition | Case | Execution | Conformance | Tool errors | Format errors |", "|---|---|---|---|---|---|---|---|---|---|---|---|"])
    for group in report["conditions"]:
        for case in group["cases"]:
            values = [case["condition"]["model"], case["policy"], case["condition"]["prompt"], case["condition"]["interface"], case["track"], case["persona_id"], case["condition"]["repetition"],
                      case["conversation_id"], case["status"], case["conformance"], len(case["tool_errors"]), sum(e.get("code") == "format_error" for e in case["errors"])]
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "## Representative failures", "", "Examples are selected deterministically per condition/category. Case identities refer to full captured/scored evidence in JSON.", "",
        "| Condition | Track | Persona/repetition/case | Category | Observation |", "|---|---|---|---|---|"])
    for failure in report["representative_failures"]:
        values = [json.dumps(failure["condition"], sort_keys=True), failure["track"],
            f"{failure['persona_id']}/{failure['repetition']}/{failure['conversation_id']}", failure["category"], failure["explanation"]]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "## Limitations", ""])
    if report["comparison_limits"]["one_repetition"]:
        lines.append("Only one repetition per persona-condition was selected; run-to-run uncertainty is unmeasured. No confidence intervals or statistical superiority claims are supplied.")
    lines.extend(report["comparison_limits"]["notes"])
    if report["action"] == "smoke":
        lines.extend(["", "Phase 5 remains a separate explicit evaluation gate."])
    lines.append("")
    return "\n".join(lines)


def write_report(input_path: str | Path, output: str | Path | None = None) -> dict:
    manifest, rows = load_capture(input_path)
    report = scored_report(manifest, rows)
    destination = Path(input_path) if output is None else Path(output)
    if output is not None:
        destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "results.json", report)
    (destination / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def replay(input_path: str | Path, output: str | Path) -> dict:
    manifest, rows = load_capture(input_path)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=False)
    manifest = deepcopy(manifest)
    manifest["replay_of"] = str(Path(input_path).resolve())
    history = manifest.setdefault("scoring_history", [manifest["collection_scoring"]])
    history.append(scorer_provenance())
    write_json(destination / "manifest.json", manifest)
    (destination / "checkpoints.jsonl").write_bytes(b"".join(canonical_json(row) + b"\n" for row in rows))
    return write_report(destination)
