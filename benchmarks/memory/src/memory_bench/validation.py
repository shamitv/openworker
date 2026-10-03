"""Offline contract/corpus/fixture checks. This module is not an execution scorer."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata

from . import __version__
from .assets import asset_hashes, canonical_json, load_json, load_text
from .contract import ContractError, contract, validate_operation, validate_record, validate_response, validate_result, validate_schema
from .model_input import build_model_input

PROTOCOL = "standalone-memory-benchmark-v1"
POLICIES = ("conservative", "recurring")
TRACKS = ("write", "read", "sequence")
REQUIRED_COVERAGE = {
    "implicit_context", "preference_format", "preference_reason", "policy_difference", "repetition",
    "temporary_detail", "explicit_remember", "global_scope", "workspace_scope", "workspace_switch",
    "blind_recall", "user_isolation", "correction", "forgetting", "history_retirement", "fresh_conversation",
    "consent_granted", "consent_denied", "explicit_sensitive_consent", "quoted_information",
    "third_person_information", "authorized_third_party_project", "duplicate_forgetting", "unchanged_prior",
}


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("_", " ")
    text = re.sub(r"g\s*/\s*m(?:2|²)", "gsm", text)
    text = re.sub(r"\b(\d+)\s*gsm\b", r"\1 gsm", text)
    text = re.sub(r"(?<=\d)\s*(khz|hz)\b", r" \1", text)
    return " ".join(re.sub(r"(?<!\d)\.|\.(?!\d)|[^\w\s.]", " ", text).split())


def matches_value(value: str, fact: dict) -> bool:
    normalized = " " + normalize(value) + " "
    return all(any(" " + normalize(alias) + " " in normalized for alias in group) for group in fact["value_alias_groups"])


def matches_record(record: dict, fact: dict, persona: dict) -> bool:
    actor = "peer" if fact["subject"] == "peer" else "owner"
    workspace = persona["workspaces"][fact["workspace"]] if fact["workspace"] else None
    return (
        record["user_id"] == persona["namespaces"][actor]
        and record["workspace_id"] == workspace and record["scope"] == fact["scope"]
        and normalize(record["key"]) in {normalize(alias) for alias in fact["key_aliases"]}
        and matches_value(record["value"], fact)
    )


def validate_contract():
    schemas = contract()
    require(schemas["schema_version"] == 1 and schemas["protocol"] == PROTOCOL, "unsupported contract")
    require(set(schemas["operations"]) == {"remember", "memory_read", "memory_update", "memory_forget", "request_permission"}, "operation set changed")
    require(schemas["lifecycle"]["max_operation_batches"] == 6 and schemas["lifecycle"]["max_requests"] == 7 and schemas["lifecycle"]["whole_turn_seconds"] == 180, "lifecycle limits changed")
    require(set(schemas["record"]["required"]) == {"id", "user_id", "workspace_id", "scope", "key", "value", "history"}, "record fields changed")
    require(set(schemas["defaults"]["update_preserves"]) == {"id", "user_id", "key", "scope", "workspace_id"}, "immutable record fields changed")
    for name, definition in schemas["operations"].items():
        require(not {"user_id", "workspace_id"} & definition["arguments"]["properties"].keys(), f"{name}: identity must come from runner")
    require("scope" in schemas["operations"]["remember"]["arguments"]["required"], "remember must require scope")
    require(not {"scope", "key"} & schemas["operations"]["memory_update"]["arguments"]["properties"].keys(), "updates cannot change key or scope")
    require(schemas["operations"]["remember"]["arguments"]["properties"]["key"].get("enum") is None, "keys must be free form")
    supported = {"type", "properties", "required", "additionalProperties", "items", "uniqueItems", "minItems", "maxItems", "minLength", "minimum", "enum", "pattern"}

    def check_schema(schema):
        require(isinstance(schema, dict), "schema must be an object")
        require(not schema.keys() - supported, f"unsupported schema keywords: {schema.keys() - supported}")
        if "type" in schema:
            kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            require(set(kinds) <= {"string", "object", "array", "integer", "number", "boolean", "null"}, "unsupported schema type")
        for child in schema.get("properties", {}).values():
            check_schema(child)
        for name in ("items", "additionalProperties"):
            if isinstance(schema.get(name), dict):
                check_schema(schema[name])

    for name in ("record", "operation_envelope", "error", "result_envelope", "json_response", "native_response"):
        check_schema(schemas[name])
    for definition in schemas["operations"].values():
        check_schema(definition["arguments"])
        check_schema(definition["success"])
    check_schema(load_json("corpus-schema.json"))


def validate_snapshot(records, persona, label):
    ids = []
    for row in records:
        validate_record(row)
        ids.append(row["id"])
        require(row["user_id"] in persona["namespaces"].values(), f"{label}: unknown user namespace")
        require(row["workspace_id"] is None or row["workspace_id"] in persona["workspaces"].values(), f"{label}: unknown workspace")
        require(any(matches_record(row, fact, persona) for fact in persona["facts"].values()), f"{label}: snapshot record has no annotated fact")
    require(len(ids) == len(set(ids)), f"{label}: duplicate record IDs")


def validate_corpus(corpus: dict, split: str) -> dict:
    validate_schema(corpus, load_json("corpus-schema.json"))
    require(corpus["split"] == split, "corpus split mismatch")
    prefix = "P" if split == "development" else "H"
    require([p["id"] for p in corpus["personas"]] == [f"{prefix}{i:02d}" for i in range(1, 16)], "expected exactly 15 ordered persona IDs")
    if split == "development":
        require(set(corpus["source"]) == {"protocol", "sha256"} and corpus["source"]["protocol"] == "hosted-memory-personas-v1", "development source provenance missing")
        require(re.fullmatch(r"[a-f0-9]{64}", corpus["source"]["sha256"]) is not None, "invalid development source hash")
    else:
        require(corpus["source"] == {"authored": "heldout-v1", "prompt_tuning": False}, "held-out provenance changed")
    controls, namespaces, workspaces = set(), set(), set()
    conversations, turns, enabled = 0, 0, {track: 0 for track in TRACKS}
    for persona in corpus["personas"]:
        pid = persona["id"]
        require(persona["split"] == split, f"{pid}: mixed split")
        users = set(persona["namespaces"].values())
        spaces = set(persona["workspaces"].values())
        require(len(users) == 2 and not users & namespaces, f"{pid}: duplicate user namespace")
        require(len(spaces) == 2 and not spaces & workspaces, f"{pid}: duplicate workspace namespace")
        namespaces.update(users)
        workspaces.update(spaces)
        facts = persona["facts"]
        require(set(facts) == {"original", "corrected", "style", "reason", "A", "B", "notebook", "temporary", "sensitive_granted", "sensitive_denied", "sensitive_explicit", "quoted", "third_person", "third_party_project", "peer_context", "peer_style", "peer_notebook", "peer_heading"}, f"{pid}: incomplete fact annotations")
        require(facts["style"]["key"] != facts["reason"]["key"], f"{pid}: format and reason must be independent")
        require(facts["original"]["key"] == facts["corrected"]["key"], f"{pid}: correction must retain fact identity")
        for fid, fact in facts.items():
            require(matches_value(fact["value"], fact), f"{pid}/{fid}: canonical value does not match aliases")
            require(normalize(fact["key"]) in {normalize(alias) for alias in fact["key_aliases"]}, f"{pid}/{fid}: canonical key is not accepted")
            require(all(normalize(alias) for group in fact["value_alias_groups"] for alias in group), f"{pid}/{fid}: empty normalized value alias")
            require((fact["scope"] == "global") == (fact["workspace"] is None), f"{pid}/{fid}: invalid fact scope")
            require(fact["workspace"] is None or fact["workspace"] in persona["workspaces"], f"{pid}/{fid}: unknown fact workspace")
            if fact["control"]:
                value = normalize(fact["value"])
                require(value not in controls, f"{pid}/{fid}: duplicate control")
                controls.add(value)
        require(not matches_value(facts["original"]["value"], facts["corrected"]) and not matches_value(facts["corrected"]["value"], facts["original"]), f"{pid}: original/corrected aliases overlap")
        require(persona["sequence_start"]["owner_records"] == [], f"{pid}: sequence owner state must be empty")
        peer = persona["sequence_start"]["peer_controls"]
        validate_snapshot(peer, persona, f"{pid}/peer controls")
        require(len(peer) == 4 and all(row["user_id"] == persona["namespaces"]["peer"] for row in peer), f"{pid}: peer controls must be explicit and peer-owned")
        require([c["id"] for c in persona["conversations"]] == [f"C{i}" for i in range(1, 19)], f"{pid}: missing conversation")
        coverage = set()
        previous = {policy: [] for policy in POLICIES}
        for c in persona["conversations"]:
            label = f"{pid}/{c['id']}"
            conversations += 1
            turns += len(c["messages"])
            coverage.update(c["coverage"])
            require(c["user_id"] == persona["namespaces"][c["actor"]] and c["workspace_id"] in spaces, f"{label}: actor/workspace mismatch")
            require(c["new_conversation"] is True, f"{label}: conversation boundary missing")
            require(c["source_messages"] == c["messages"], f"{label}: exact messages changed")
            require(all(message.endswith("Answer in chat. Do not browse, write files, or use tools other than memory.") for message in c["messages"]), f"{label}: memory-only instruction missing")
            referenced = set(c["common_targets"]["saved_facts"] + c["common_targets"]["excluded_answer_facts"] + c["common_targets"]["retired_current_facts"])
            for required in c["common_targets"]["probe_fields"].values():
                referenced.update(required)
            for prerequisite in c["prerequisites"]:
                referenced.update(prerequisite["facts"])
            require(referenced <= facts.keys(), f"{label}: unknown fact reference")
            for track, data in c["tracks"].items():
                require(all(index < len(c["messages"]) for index in data["message_indices"]), f"{label}/{track}: invalid message index")
                require(data["message_indices"] == sorted(data["message_indices"]), f"{label}/{track}: message order changed")
                if data["enabled"]:
                    enabled[track] += 1
                    require(data["message_indices"], f"{label}/{track}: no messages")
            require(c["tracks"]["sequence"]["enabled"] and c["tracks"]["sequence"]["starting_records"] is None, f"{label}: sequence cannot seed owner facts")
            require(c["tracks"]["sequence"]["storage_scored"] == (c["actor"] == "owner"), f"{label}: peer controls cannot earn storage credit")
            require(c["tracks"]["sequence"]["message_indices"] == list(range(len(c["messages"]))), f"{label}: incomplete sequence conversation")
            pure_probe = bool(c["common_targets"]["probe_fields"]) and len(c["messages"]) == 1
            require(c["tracks"]["write"]["enabled"] == (not pure_probe), f"{label}: writing checkpoint coverage changed")
            require(c["tracks"]["write"]["message_indices"] == list(range(len(c["messages"]))), f"{label}: incomplete write conversation")
            read = c["tracks"]["read"]
            validate_snapshot(read["starting_records"], persona, label + "/read")
            require(read["expected_mutations"] == [], f"{label}: prepared read must not expect writes")
            require(read["probe_fields"] == c["common_targets"]["probe_fields"], f"{label}: prepared read targets differ")
            require(read["enabled"] == bool(read["probe_fields"]), f"{label}: read selection differs from probe")
            if read["enabled"]:
                require(read["message_indices"] == [0], f"{label}: read must run only the blind question")
                question = c["messages"][0]
                for fid, fact in facts.items():
                    require(not matches_value(question, fact), f"{label}: blind question leaks {fid}")
                selected = build_model_input(persona, c, "conservative", read["starting_records"], [0])["memories"]
                for field, required in read["probe_fields"].items():
                    for fid in required:
                        require(any(matches_record(row, facts[fid], persona) for row in read["starting_records"] if row["user_id"] == c["user_id"] and (row["scope"] == "global" or row["workspace_id"] == c["workspace_id"])), f"{label}/{field}: unsatisfiable prepared read")
                require(all(row["scope"] == "global" or row["workspace_id"] == c["workspace_id"] for row in selected), f"{label}: wrong workspace injected")
            for policy, expected in c["policy_expectations"].items():
                for name in ("required_additions", "required_deletions", "retained_prior_facts", "expected_current_facts", "forbidden_new_facts"):
                    require(set(expected[name]) <= facts.keys(), f"{label}/{policy}: unknown {name} reference")
                starting = c["tracks"]["write"]["starting_records"][policy]
                validate_snapshot(starting, persona, label + "/write/" + policy)
                owner_facts = {fid for fid, fact in facts.items() if fact["subject"] != "peer" and any(matches_record(row, fact, persona) for row in starting)}
                require(owner_facts == set(previous[policy]), f"{label}/{policy}: prepared prior differs from annotated progression")
                require(not set(expected["required_additions"]) & owner_facts, f"{label}/{policy}: unchanged prepared fact earns addition credit")
                update_old, update_new = set(), set()
                for update in expected["required_updates"]:
                    require(update["previous"] in facts and update["current"] in facts, f"{label}: unknown update reference")
                    require(update["previous"] in owner_facts and facts[update["previous"]]["key"] == facts[update["current"]]["key"], f"{label}: unsatisfiable update prerequisite")
                    update_old.add(update["previous"])
                    update_new.add(update["current"])
                removals = set(expected["required_deletions"]) | update_old
                require(removals <= owner_facts, f"{label}: unsatisfiable deletion prerequisite")
                final = (owner_facts - removals) | set(expected["required_additions"]) | update_new
                require(final == set(expected["expected_current_facts"]), f"{label}/{policy}: inconsistent expected final state")
                require(set(expected["retained_prior_facts"]) == owner_facts - removals, f"{label}: preservation annotations incomplete")
                require(not final & set(expected["forbidden_new_facts"]), f"{label}: forbidden fact in expected state")
                for prerequisite in c["prerequisites"]:
                    require(set(prerequisite["facts"]) <= owner_facts, f"{label}: unsatisfiable write prerequisite")
                require(c["tracks"]["sequence"]["expected_current_facts"][policy] == expected["expected_current_facts"], f"{label}: sequence gold state differs")
                sequence_fields = c["tracks"]["sequence"]["probe_fields"][policy]
                require(sequence_fields == {field: [fid for fid in required if facts[fid]["subject"] == "peer" or fid in previous[policy]] for field, required in c["common_targets"]["probe_fields"].items()}, f"{label}: sequence probe annotations inconsistent")
                permission = expected["permission"]
                if permission == "ask_then_grant":
                    require(c["permission_reply"]["granted"] is True, f"{label}: grant has denied reply")
                if permission in ("ask_then_deny", "explicitly_granted"):
                    require(c["permission_reply"]["granted"] is False, f"{label}: unexpected extra consent")
                projected = build_model_input(persona, c, policy, starting, c["tracks"]["write"]["message_indices"])
                require(set(projected) == set(contract()["model_input_fields"]), f"{label}: model-input whitelist changed")
                previous[policy] = expected["expected_current_facts"][:]
        require(REQUIRED_COVERAGE <= coverage, f"{pid}: missing behavior coverage {sorted(REQUIRED_COVERAGE - coverage)}")
        require(persona["conversations"][0]["policy_expectations"]["conservative"]["required_additions"] == [], f"{pid}: conservative implicit save")
        require(set(persona["conversations"][0]["policy_expectations"]["recurring"]["required_additions"]) == {"original", "style", "reason"}, f"{pid}: recurring implicit targets missing")
    return {"personas": len(corpus["personas"]), "conversations": conversations, "scripted_turns": turns, "enabled_checkpoints": enabled, "controls": len(controls)}


def validate_lifecycle_fixture(fixture: dict) -> None:
    """Check a declarative trace; never execute operations or a model request."""
    batches, requests, status, final, elapsed = 0, 0, None, None, 0
    committed = []
    for request in fixture["requests"]:
        require(status is None, f"{fixture['id']}: request after termination")
        requests += 1
        require(requests <= 7, f"{fixture['id']}: more than seven requests")
        require(type(request["elapsed_seconds"]) in (int, float) and math.isfinite(request["elapsed_seconds"]) and request["elapsed_seconds"] >= elapsed, "invalid whole-turn timestamp")
        elapsed = request["elapsed_seconds"]
        results = request["results"]
        if elapsed >= 180:
            require(not results, "operations executed past deadline")
            status = "deadline"
            continue
        try:
            validate_response(request["response"])
        except ContractError:
            require(not results, "operations executed from malformed envelope")
            status = "format_error"
            continue
        response = request["response"]
        operations = response["operations"]
        if not operations:
            require(not results, "final response has operation results")
            status = "complete" if response["answer"].strip() else "format_error"
            final = response["answer"] if status == "complete" else None
        elif batches == 6:
            require(not results, "seventh batch was executed")
            status = "round_exhaustion"
        else:
            batches += 1
            require(len(results) == len(operations), "operation/result count mismatch")
            for operation, item in zip(operations, results):
                require(item["name"] == operation["name"], "operation result order changed")
                validate_result(item["name"], item["result"])
                try:
                    validate_operation(operation)
                except ContractError as exc:
                    require(not item["result"]["ok"] and item["result"]["error"]["code"] == exc.code, "invalid operation must return its explicit error")
                if item["result"]["ok"] and item["name"] in ("remember", "memory_update"):
                    committed.append(item["result"]["data"]["record"])
    require(status is not None, f"{fixture['id']}: incomplete trace")
    require(fixture["expected"] == {"status": status, "batches": batches, "requests": requests, "final_answer": final}, f"{fixture['id']}: lifecycle expectation mismatch")
    require(all(row in committed for row in fixture.get("required_committed_records", [])), "mixed batch lost successful mutation evidence")


def validate_native_fixture(fixture):
    error = None
    try:
        validate_schema(fixture["response"], contract()["native_response"], code="format_error")
        response = fixture["response"]
        calls = response.get("tool_calls", [])
        require(len({call["id"] for call in calls}) == len(calls), "duplicate native call IDs")
        if not calls and (not response["content"] or not response["content"].strip()):
            error = "format_error"
        for call in calls:
            try:
                arguments = json.loads(call["function"]["arguments"])
            except json.JSONDecodeError:
                error = "invalid_arguments"
                break
            validate_operation({"name": call["function"]["name"], "arguments": arguments})
    except ContractError as exc:
        error = exc.code
    require(error == fixture["expected_error"], f"{fixture['id']}: native schema expectation mismatch")


def validate_scoring_fixtures(data):
    validate_fixture_header(data)
    fixtures = data["fixtures"]
    require(len({f["id"] for f in fixtures}) == len(fixtures), "duplicate scoring fixture")
    required = {"positive_current_fact", "empty_expected_and_actual", "missing_required_save", "unnecessary_save", "duplicate_current_fact", "wrong_key", "wrong_scope", "wrong_current_value", "unchanged_prepared_fact", "unchanged_row_id_churn", "duplicate_added_to_prepared_fact", "current_correction_with_history", "complete_correction", "forget_all_copies", "forget_leaves_copy", "scope_only_change", "destructive_prior_change", "verbal_save_without_rows", "malformed_response", "missing_answer_field", "duplicate_answer_field", "valid_unknown", "unknown_with_forgotten_control", "correct_heading_with_wrong_workspace", "missing_sequence_prerequisite"}
    require({f["id"] for f in fixtures} == required, "scoring fixture coverage changed")
    for fixture in fixtures:
        require(fixture["track"] in TRACKS, "unknown scoring fixture track")
        for name in ("starting_records", "actual_records"):
            rows = fixture.get(name, [])
            require(len({row["id"] for row in rows}) == len(rows), "duplicate scoring record IDs")
            for record in rows:
                validate_record(record)
        require(set(fixture.get("expected_facts", []) + fixture.get("excluded_facts", []) + fixture.get("prerequisites", [])) <= data["facts"].keys(), "unknown scoring fact")
        expected = fixture["expected_outcome"]
        if "tp" in expected:
            check_counts(expected)
    aggregate = data["aggregate_fixture"]
    outcomes = {fixture["id"]: fixture["expected_outcome"] for fixture in fixtures}
    require(set(aggregate["members"]) <= outcomes.keys(), "unknown aggregate fixture member")
    require(all(aggregate["expected_outcome"][key] == sum(outcomes[name][key] for name in aggregate["members"]) for key in ("tp", "fp", "fn")), "aggregate fixture counts inconsistent")
    check_counts(aggregate["expected_outcome"])


def validate_fixture_header(data):
    require(data.get("schema_version") == 1 and data.get("protocol") == PROTOCOL, "unsupported fixture protocol/version")


def check_counts(expected):
    require(all(type(expected[key]) is int and expected[key] >= 0 for key in ("tp", "fp", "fn")), "invalid scoring counts")
    for name, denominator in (("precision", expected["tp"] + expected["fp"]), ("recall", expected["tp"] + expected["fn"])):
        value = expected[name]
        require(value is None if denominator == 0 else type(value) in (int, float) and math.isclose(value, expected["tp"] / denominator), f"invalid {name} denominator fixture")


def validate_all() -> dict:
    validate_contract()
    corpora = {split: load_json(f"corpus/{split}.json") for split in ("development", "heldout")}
    counts = {split: validate_corpus(corpus, split) for split, corpus in corpora.items()}
    development, heldout = (corpora[name]["personas"] for name in ("development", "heldout"))
    dev_values = {normalize(fact["value"]) for p in development for fact in p["facts"].values()}
    held_values = {normalize(fact["value"]) for p in heldout for fact in p["facts"].values()}
    require(not dev_values & held_values, "facts or controls shared across splits")
    for name in ("namespaces", "workspaces"):
        dev_ids = {value for p in development for value in p[name].values()}
        held_ids = {value for p in heldout for value in p[name].values()}
        require(not dev_ids & held_ids, f"{name} shared across splits")
    for policy in POLICIES:
        text = load_text(f"policies/{policy}.md")
        require("explicit request to remember a sensitive fact is consent" in text, f"{policy}: consent rule missing")
        require("separate facts" in text and "third-person" in text, f"{policy}: policy requirements missing")
    lifecycle = load_json("fixtures/lifecycle.json")
    validate_fixture_header(lifecycle)
    require({f["id"] for f in lifecycle["fixtures"]} == {"final_answer", "ordered_mixed_batch", "read_before_final", "six_batches_then_final", "seventh_batch_not_executed", "malformed_envelope", "deadline", "empty_final_answer", "unknown_operation_feedback", "invalid_argument_feedback"}, "lifecycle fixture coverage changed")
    for fixture in lifecycle["fixtures"]:
        validate_lifecycle_fixture(fixture)
    native = load_json("fixtures/native.json")
    validate_fixture_header(native)
    require({fixture["id"] for fixture in native["fixtures"]} == {"native_batch", "native_final", "native_malformed_arguments", "native_malformed_envelope"}, "native fixture coverage changed")
    for fixture in native["fixtures"]:
        validate_native_fixture(fixture)
    scoring = load_json("fixtures/scoring.json")
    validate_scoring_fixtures(scoring)
    hashes = asset_hashes()
    return {"status": "valid", "package_version": __version__, "protocol": PROTOCOL, "counts": counts, "scoring_fixtures": len(scoring["fixtures"]), "lifecycle_fixtures": len(lifecycle["fixtures"]), "native_schema_fixtures": len(native["fixtures"]), "hash_algorithm": "sha256; canonical JSON / LF UTF-8 text", "asset_hashes": hashes, "bundle_hash": hashlib.sha256(canonical_json(hashes)).hexdigest(), "inference_requests": 0}
