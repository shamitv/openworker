"""Sequential collection with isolated stores and resumable offline evidence."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import time

from .adapters import adapter_for
from .assets import load_json
from .capture import Capture
from .checkpoints import checkpoint_evidence, create_checkpoint_store, reopen_sequence_store
from .client import ClientError, LocalClient, SETTINGS
from .experiments import isolated_persona
from .model_input import build_model_input, render_state
from .operations import OperationContext, OperationDispatcher
from .provenance import collection_provenance, scorer_provenance
from .runner import run_turn
from .validation import validate_all

FATAL_CODES = {"configuration_error", "routing_error", "catalog_error", "unsupported_settings", "api_error", "infrastructure_error"}


async def collect(*, base_url: str, models: list[str], output: str | Path, schedule: list[dict],
                  requested: dict, smoke: bool = False, transport=None, progress=None) -> dict:
    manifest = {"schema_version": 1, "protocol": "standalone-memory-benchmark-v1", "action": "smoke" if smoke else "run",
                "status": "running", "requested": deepcopy(requested), "schedule": schedule,
                "actual_schedule": [], "actual_checkpoints": [], "collection": collection_provenance(),
                "collection_scoring": scorer_provenance(), "settings": SETTINGS.copy(),
                "server_effective_settings": None, "catalog": None, "requests": [], "errors": [],
                "cost": None, "started_at": time.time(), "finished_at": None, "cleanup": {"status": "pending", "files": []}}
    capture = Capture(output, manifest)
    manifest = capture.manifest
    store_dir = capture.path / "stores"
    owned_paths, captured_ids = [], set()
    context = {"track_id": None, "checkpoint_id": None, "message_index": None}
    client = None
    stop = False
    progress = progress or (lambda value: None)

    def record(value):
        capture.record({"context": context.copy(), **value})

    def persist(entry, checkpoint, before, after, turns, status, errors, injected=None):
        evidence = checkpoint_evidence(condition=entry["condition"], track=entry["track"],
            starting_records=before, final_records=after, turns=turns, status=status, errors=errors)
        capture.checkpoint({"checkpoint_id": checkpoint["checkpoint_id"], "condition_id": entry["condition_id"],
            "track_id": entry["track_id"], "persona_id": entry["condition"]["persona_id"],
            "conversation_id": checkpoint["conversation_id"], "injected_memory": injected, "evidence": evidence})
        captured_ids.add(checkpoint["checkpoint_id"])
        checkpoint["status"] = status
        capture.save()

    try:
        validate_all()
        store_dir.mkdir()
        client = LocalClient(base_url, transport=transport, record=record)
        async with client:
            manifest["catalog"] = await client.verify_models(models)
            corpora = {name: {p["id"]: p for p in load_json(f"corpus/{name}.json")["personas"]}
                       for name in {row["condition"]["dataset"] for row in schedule}}
            for entry in manifest["schedule"]:
                if stop:
                    break
                condition, track = entry["condition"], entry["track"]
                persona = isolated_persona(corpora[condition["dataset"]][condition["persona_id"]], entry["track_id"])
                conversations = {c["id"]: c for c in persona["conversations"]}
                context.update(track_id=entry["track_id"], checkpoint_id=None, message_index=None)
                entry["status"] = "running"
                manifest["actual_schedule"].append(entry["track_id"])
                capture.save()
                store = None
                try:
                    for checkpoint in entry["checkpoints"]:
                        if stop:
                            break
                        conversation = conversations[checkpoint["conversation_id"]]
                        context.update(checkpoint_id=checkpoint["checkpoint_id"], message_index=None)
                        manifest["actual_checkpoints"].append(checkpoint["checkpoint_id"])
                        before, after, injected, turns, errors = None, None, None, [], []
                        status = "complete"
                        try:
                            if track != "sequence" or store is None:
                                path = store_dir / (entry["track_id"] + ("-sequence" if track == "sequence" else f"-{conversation['id']}") + ".sqlite")
                                owned_paths.append(path)
                                store = create_checkpoint_store(path, persona, conversation, condition["policy"], track)
                            elif conversation["restart_before"]:
                                path = store.path
                                store.close()
                                store = None
                                store = reopen_sequence_store(path)
                                record({"type": "store_reopened"})
                            before = store.snapshot()
                            projection = build_model_input(persona, conversation, condition["policy"], before, [], prompt=condition["prompt"])
                            injected = projection["memories"]
                            messages = [{"role": "system", "content": projection["instructions"] + "\n\n" + render_state(projection)},
                                        {"role": "system", "content": adapter_for(condition["interface"]).instructions}]
                            record({"type": "conversation_started", "injected_memory": injected,
                                    "context_data": projection["context"], "messages": messages, "starting_records": before})
                            dispatcher = OperationDispatcher(store, OperationContext(conversation["user_id"],
                                conversation["workspace_id"], conversation["id"]), permission_reply=conversation["permission_reply"])
                            for message_index in checkpoint["message_indices"]:
                                context["message_index"] = message_index
                                messages.append({"role": "user", "content": conversation["messages"][message_index]})
                                record({"type": "turn_started", "message": messages[-1]})
                                def operation_record(value):
                                    # Persist each successful write before the next HTTP request.
                                    try:
                                        snapshot = store.snapshot()
                                    except Exception:
                                        snapshot = None
                                    record({**value, "snapshot": snapshot})
                                turn = await run_turn(client, condition["model"], condition["interface"], messages,
                                                      dispatcher, record=operation_record)
                                messages = turn.pop("messages")
                                turn["message_index"] = message_index
                                turns.append(turn)
                                record({"type": "turn_finished", "turn": turn, "messages": messages})
                                after = store.snapshot()
                                status = turn["status"]
                                persist(entry, checkpoint, before, after, turns, "running" if status == "complete" else status, errors, injected)
                                if status != "complete":
                                    if status in FATAL_CODES:
                                        manifest["errors"].extend(turn["errors"])
                                        stop = True
                                    elif status == "interrupted":
                                        manifest["errors"].append({"code": "interrupted"})
                                        stop = True
                                    break
                        except BaseException as exc:
                            status = "interrupted" if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)) else "infrastructure_error"
                            errors.append({"code": status, "type": type(exc).__name__, "message": str(exc)})
                            manifest["errors"].extend(errors)
                            stop = True
                        finally:
                            if store is not None:
                                try:
                                    after = store.snapshot()
                                except Exception as exc:
                                    after = None
                                    status = "infrastructure_error"
                                    errors.append({"code": status, "message": str(exc)})
                                    manifest["errors"].append(errors[-1])
                                    stop = True
                                if track != "sequence":
                                    store.close()
                                    store = None
                            persist(entry, checkpoint, before, after, turns, status, errors, injected)
                        progress({"checkpoint_id": checkpoint["checkpoint_id"], "condition": condition, "track": track,
                                  "conversation_id": conversation["id"], "status": status})
                    states = [c["status"] for c in entry["checkpoints"]]
                    entry["status"] = "complete" if all(s == "complete" for s in states) else "failed"
                    capture.save()
                finally:
                    if store is not None:
                        store.close()
    except BaseException as exc:
        code = exc.code if isinstance(exc, ClientError) else "interrupted" if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)) else "infrastructure_error"
        manifest["errors"].append({"code": code, "type": type(exc).__name__, "message": str(exc)})
    finally:
        if client is not None:
            manifest["requests"] = [{key: deepcopy(e.get(key)) for key in ("index", "kind", "model", "duration_seconds",
                "status_code", "usage", "error", "server", "request_id", "response_model", "response_id", "system_fingerprint")} for e in client.events]
        for entry in manifest["schedule"]:
            for checkpoint in entry["checkpoints"]:
                if checkpoint["checkpoint_id"] not in captured_ids:
                    persist(entry, checkpoint, None, None, [], "unexecuted", [], None)
        cleanup_failed = False
        for path in owned_paths:
            try:
                if path.resolve().parent != store_dir.resolve():
                    raise ValueError("cleanup path escaped owned store directory")
                for candidate in (path, Path(str(path) + "-journal"), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
                    candidate.unlink(missing_ok=True)
                manifest["cleanup"]["files"].append({"name": path.name, "status": "removed"})
            except Exception as exc:
                cleanup_failed = True
                manifest["cleanup"]["files"].append({"name": path.name, "status": "failed", "error": str(exc)})
        if store_dir.exists():
            try:
                store_dir.rmdir()
            except OSError:
                cleanup_failed = True
        manifest["cleanup"]["status"] = "failed" if cleanup_failed else "complete"
        if cleanup_failed:
            manifest["errors"].append({"code": "infrastructure_error", "message": "owned store cleanup failed"})
        statuses = [c["status"] for row in manifest["schedule"] for c in row["checkpoints"]]
        manifest["coverage"] = {"track_runs": len(schedule), "checkpoints": len(statuses),
            "completed": statuses.count("complete"), "failed": sum(s not in ("complete", "unexecuted") for s in statuses),
            "unexecuted": statuses.count("unexecuted")}
        manifest["status"] = "interrupted" if any(e["code"] == "interrupted" for e in manifest["errors"]) else (
            "failed" if manifest["errors"] or manifest["coverage"]["unexecuted"] else "complete")
        manifest["finished_at"] = time.time()
        capture.save()
        capture.close()
    return deepcopy(manifest)
