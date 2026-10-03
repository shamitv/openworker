"""Offline rescoring and sanitized reports; never instantiate an inference client."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from .assets import asset_hashes, canonical_json, load_json
from .capture import read_checkpoints, write_json
from .checkpoints import checkpoint_evidence
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
    return {"inference_requests": len(inference), "catalog_requests": sum(r["kind"] == "catalog" for r in requests),
            "failed_requests": sum(r.get("error") is not None for r in inference),
            "missing_usage_requests": sum(r.get("usage") is None for r in inference), "usage": usage,
            "upstream_seconds": sum(r.get("duration_seconds") or 0 for r in inference), "cost": None}


def sanitized(value):
    private = {"authorization", "proxy-authorization", "headers", "base_url", "url", "output", "request_id",
               "request", "response", "response_text", "messages", "provisional_answers", "replay_of"}
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
    return sanitized({"schema_version": 1, "protocol": manifest["protocol"], "action": manifest["action"],
        "status": manifest["status"], "gate_passed": manifest["status"] == "complete" and coverage["unexecuted"] == 0,
        "collection": manifest["collection"], "collection_scoring": manifest["collection_scoring"], "scoring": current,
        "scoring_history": history, "settings": manifest["settings"],
        "server_effective_settings": manifest.get("server_effective_settings"), "requested": manifest["requested"],
        "schedule": manifest["schedule"], "actual_schedule": manifest["actual_schedule"],
        "actual_checkpoints": manifest["actual_checkpoints"], "coverage": coverage,
        "requests": request_summary(manifest["requests"]), "errors": manifest["errors"],
        "cleanup": manifest["cleanup"], "conditions": aggregate_scores(scores), "checkpoint_evidence": rows,
        "offline_inference_requests": 0})


def markdown(report: dict) -> str:
    def ratio(value):
        return "null" if value is None else f"{value:.3f}"
    def outcomes(value):
        return f"{value['passed']}/{value['denominator']}" if value["denominator"] else "null (0/0)"
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
    requests = report["requests"]
    lines.extend(["", "## Requests, provenance and cleanup", "",
        f"Inference requests: {requests['inference_requests']}; failed HTTP requests: {requests['failed_requests']}; missing usage: {requests['missing_usage_requests']}.",
        f"Reported tokens: input={requests['usage']['prompt_tokens']}, output={requests['usage']['completion_tokens']}; local cost=null.",
        f"Submitted settings: `{json.dumps(report['settings'], sort_keys=True)}`. Server-effective settings: `{report['server_effective_settings']}` (unavailable unless reported).",
        f"Collection hash: `{report['collection']['sha256']}`. Scoring hash: `{report['scoring']['sha256']}`.",
        f"Cleanup: **{report['cleanup']['status']}**. Offline replay/report inference requests: 0.", "", "## Case outcomes", "",
        "| Policy | Prompt | Interface | Track | Persona | Case | Execution | Conformance | Tool errors | Format errors |", "|---|---|---|---|---|---|---|---|---|---|"])
    for group in report["conditions"]:
        for case in group["cases"]:
            values = [case["policy"], case["condition"]["prompt"], case["condition"]["interface"], case["track"], case["persona_id"],
                      case["conversation_id"], case["status"], case["conformance"], len(case["tool_errors"]), sum(e.get("code") == "format_error" for e in case["errors"])]
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "This collection does not establish model or policy superiority. Phase 5 remains a separate explicit evaluation gate.", ""])
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
