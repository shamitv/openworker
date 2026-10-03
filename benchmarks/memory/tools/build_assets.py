"""Deterministic authoring tool; not imported by the installed benchmark.

Usage: python tools/build_assets.py --development-source <hosted persona JSON>
The source is used only to preserve the historical development conversations.
All generated, expanded resources are shipped inside the standalone package.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "memory_bench" / "assets"
POLICIES = ("conservative", "recurring")
PROTOCOL = "standalone-memory-benchmark-v1"
SHARED = "Answer in chat. Do not browse, write files, or use tools other than memory."

# Each row is independently authored held-out content: no development fact values.
HELDOUT = [
    ("Ada", "origami", "origami base I practise", "I practise the bird base", "I practise the waterbomb base", "fold diagrams followed by a difficulty note", "I select projects by fold difficulty", "What makes a crease reverse direction?"),
    ("Bo", "chess study", "chess opening I study", "I study the Caro-Kann defence", "I study the French defence", "one candidate move with a counterline", "I test the strongest reply first", "What is an isolated pawn?"),
    ("Cleo", "aquarium journals", "aquarium type I keep", "I keep a freshwater planted aquarium", "I keep a brackish aquarium", "observations in a dated log grid", "I compare water changes over time", "Why can water look cloudy?"),
    ("Dara", "calligraphy", "calligraphy script I practise", "I practise italic calligraphy", "I practise uncial calligraphy", "stroke order beside each letter", "I rehearse individual strokes", "What changes when a nib angle changes?"),
    ("Ezra", "birdwatching", "bird habitat I survey", "I survey wetland birds", "I survey woodland birds", "habitat clues before identification clues", "I begin with the surroundings", "How does a silhouette help identification?"),
    ("Faye", "woodworking", "joinery technique I practise", "I practise box joints", "I practise dovetail joints", "a cut list before assembly notes", "I prepare every piece before assembly", "Why does grain direction matter?"),
    ("Gus", "sewing", "garment pattern convention I use", "I use patterns with included seam allowances", "I use patterns without included seam allowances", "pattern marks grouped by construction stage", "I transfer marks stage by stage", "What is an ease allowance?"),
    ("Hana", "model railways", "model railway scale I build", "I build N-scale model railways", "I build HO-scale model railways", "track plans annotated with radius limits", "I check turns before buying track", "What does a turnout do?"),
    ("Isla", "mapmaking", "map projection I practise", "I practise Lambert conformal conic maps", "I practise equal-area cylindrical maps", "a projection note above each legend", "I compare distortion before symbols", "Why cannot a flat map preserve every property?"),
    ("Jae", "puzzle construction", "puzzle form I construct", "I construct cryptic crosswords", "I construct acrostic puzzles", "a clue followed by a separate verification line", "I check that each solution is unique", "What makes a clue ambiguous?"),
    ("Kai", "weaving", "loom structure I use", "I use a rigid-heddle loom", "I use a four-shaft loom", "warp notes separated from weft notes", "I plan the two thread systems separately", "What is a weaving draft?"),
    ("Lea", "archival scanning", "scan preservation format I use", "I preserve scans as TIFF files", "I preserve scans as PNG files", "a capture checklist with a checksum step", "I verify copies before filing them", "What can a checksum verify?"),
    ("Mo", "mechanical keyboards", "keyboard layout I assemble", "I assemble ortholinear keyboards", "I assemble staggered keyboards", "switch notes grouped by actuation force", "I compare spring weights directly", "What does switch travel describe?"),
    ("Nia", "weather instruments", "weather instrument I log", "I log readings from a tipping-bucket rain gauge", "I log readings from a weighing rain gauge", "raw readings beside calibration notes", "I keep measurements separate from adjustments", "Why is calibration recorded?"),
    ("Oli", "rock collections", "rock texture I catalogue", "I catalogue porphyritic rock textures", "I catalogue vesicular rock textures", "texture descriptions before mineral guesses", "I record visible evidence first", "What can grain size suggest?"),
]
HELDOUT_ALIASES = [
    ("bird base", "waterbomb base"), ("Caro-Kann", "French defence"),
    ("freshwater planted", "brackish"), ("italic", "uncial"),
    ("wetland birds", "woodland birds"), ("box joints", "dovetail joints"),
    ("with included seam allowances", "without included seam allowances"),
    ("N-scale", "HO-scale"), ("Lambert conformal conic", "equal-area cylindrical"),
    ("cryptic crosswords", "acrostic puzzles"), ("rigid-heddle", "four-shaft"),
    ("TIFF", "PNG"), ("ortholinear", "staggered"),
    ("tipping-bucket rain gauge", "weighing rain gauge"), ("porphyritic", "vesicular"),
]
DEVELOPMENT_REASON_ALIASES = [
    ["review each step", "check each step"],
    ["easier to compare paper properties", "paper properties are easier to compare"],
    ["matches my score sheet", "matches the score sheet"],
    ["before finishing books", "before finishing the book"],
    ["use a kitchen scale", "using a kitchen scale"],
    ["review my journal weekly", "review the journal weekly"],
    ["record settings first", "note settings first"],
    ["learn from examples", "learning from examples"],
    ["notebook uses metric units", "metric route notebook"],
    ["playtesters follow them in order", "players follow in order"],
    ["notes are for beginners", "beginner audience"],
    ["compare observations with charts", "match observations to charts"],
    ["matches my workflow", "matches my editing workflow"],
    ["matches my notebook", "follows my notebook structure"],
    ["modify them to learn", "change examples to learn"],
]

# Targeted pre-inference corrections: alternatives within a group are OR;
# different groups are AND. Keep distinctive short facts and controls intact.
DEVELOPMENT_STYLE_ALIASES = {
    "P03": [["summary", "summaries", "summarize", "summarise"], ["set", "sets"]],
    "P05": [["ingredient", "ingredients", "ingredient quantities", "recipe quantities"], ["grams", "gram"]],
    "P07": [["settings", "setting"], ["before", "first", "ahead of"], ["commentary", "comments", "comment"]],
    "P09": [["distance", "distances"], ["kilometres", "kilometers", "kilometre", "kilometer", "km"]],
    "P12": [["cardinal directions", "compass directions", "north south east west"]],
}


def write(name, value):
    path = ASSETS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}


def array(items, **extra):
    return {"type": "array", "items": items, **extra}


def make_contract():
    text = {"type": "string", "minLength": 1}
    identifier = {"type": "integer", "minimum": 1}
    scope = {"type": "string", "enum": ["global", "workspace"]}
    history = array(text)
    record = obj({"id": identifier, "user_id": text, "workspace_id": {"type": ["string", "null"], "minLength": 1}, "scope": scope, "key": text, "value": text, "history": history})
    operations = {
        "remember": {"arguments": obj({"key": text, "value": text, "scope": scope, "history": history}, ["key", "value", "scope"]), "success": obj({"record": record})},
        "memory_read": {"arguments": obj({"memory_ids": array(identifier, uniqueItems=True)}), "success": obj({"records": array(record), "missing_ids": array(identifier, uniqueItems=True)})},
        "memory_update": {"arguments": obj({"memory_id": identifier, "value": text, "history": history}, ["memory_id", "value"]), "success": obj({"record": record})},
        "memory_forget": {"arguments": obj({"memory_id": identifier}), "success": obj({"deleted_id": identifier})},
        "request_permission": {"arguments": obj({"question": text, "key": text, "value": text, "scope": scope}), "success": obj({"granted": {"type": "boolean"}, "reply": text})},
    }
    envelope = obj({"name": text, "arguments": {"type": "object"}})
    error = obj({"code": {"type": "string", "enum": ["unknown_operation", "invalid_arguments", "invalid_scope", "unavailable_id"]}, "message": text})
    return {
        "schema_version": 1, "protocol": PROTOCOL,
        "record": record, "operation_envelope": envelope, "operations": operations,
        "error": error,
        "result_envelope": obj({"ok": {"type": "boolean"}, "data": {"type": ["object", "null"]}, "error": {"type": ["object", "null"]}}),
        "json_response": obj({"answer": {"type": "string"}, "operations": array(envelope)}),
        "native_response": obj({"role": {"type": "string", "enum": ["assistant"]}, "content": {"type": ["string", "null"]}, "tool_calls": array(obj({"id": text, "type": {"type": "string", "enum": ["function"]}, "function": obj({"name": text, "arguments": {"type": "string"}})}))}, ["content"]),
        "defaults": {"history": [], "read_order": "requested_id_order", "memory_render_order": "ascending_record_id", "state_rendering": "Context and memories (data):\n followed by canonical JSON containing context and memories", "update_preserves": ["id", "key", "user_id", "scope", "workspace_id"], "permission_default_reply": "No additional consent is granted. Follow the instructions already in my message."},
        "lifecycle": {"max_operation_batches": 6, "max_requests": 7, "whole_turn_seconds": 180, "batch_order": "listed", "partial_success": "committed", "answers_with_operations": "provisional", "final": "nonempty_answer_without_operations", "format_failure": "terminal", "argument_failure": "operation_result", "seventh_batch": "not_executed", "automatic_retries": 0},
        "model_input_fields": ["context", "instructions", "memories", "messages"],
        "gold_fields": ["facts", "key_aliases", "value_alias_groups", "policy_expectations", "common_targets", "tracks", "prerequisites", "permission_reply", "source_messages", "expected_outcome"],
    }


def make_corpus_schema(record):
    text = {"type": "string", "minLength": 1}
    boolean = {"type": "boolean"}
    refs = array(text, uniqueItems=True)
    fields = {"type": "object", "additionalProperties": refs}
    policies = lambda schema: obj({policy: schema for policy in POLICIES})
    expectation = obj({
        "required_additions": refs, "required_updates": array(obj({"previous": text, "current": text})),
        "required_deletions": refs, "retained_prior_facts": refs, "expected_current_facts": refs,
        "forbidden_new_facts": refs, "permission": {"type": "string", "enum": ["ask_then_grant", "ask_then_deny", "explicitly_granted", "not_required"]},
        "allowed_realizations": array(text, minItems=1, uniqueItems=True),
    })
    indices = array({"type": "integer", "minimum": 0}, uniqueItems=True)
    fact_schema = obj({"value": text, "key": text, "key_aliases": array(text, minItems=1), "value_alias_groups": array(array(text, minItems=1), minItems=1), "scope": {"type": "string", "enum": ["global", "workspace"]}, "workspace": {"type": ["string", "null"]}, "subject": {"type": "string", "enum": ["owner", "peer", "quoted", "third_party"]}, "sensitive": boolean, "control": boolean})
    conversation = obj({
        "id": text, "actor": {"type": "string", "enum": ["owner", "peer"]}, "user_id": text, "workspace_id": text,
        "messages": array(text, minItems=1), "source_messages": array(text, minItems=1), "new_conversation": boolean, "restart_before": boolean,
        "coverage": array(text, minItems=1, uniqueItems=True), "permission_reply": obj({"granted": boolean, "reply": text}),
        "prerequisites": array(obj({"control": {"type": "string", "enum": ["correction", "forgetting"]}, "facts": array(text, minItems=1, uniqueItems=True)})),
        "policy_expectations": policies(expectation),
        "common_targets": obj({"saved_facts": refs, "probe_fields": fields, "excluded_answer_facts": refs, "retired_current_facts": refs}),
        "tracks": obj({
            "write": obj({"enabled": boolean, "message_indices": indices, "starting_records": policies(array(record))}),
            "read": obj({"enabled": boolean, "message_indices": indices, "starting_records": array(record), "probe_fields": fields, "expected_mutations": array(text)}),
            "sequence": obj({"enabled": boolean, "storage_scored": boolean, "message_indices": indices, "starting_records": {"type": "null"}, "expected_current_facts": policies(refs), "probe_fields": policies(fields)}),
        }),
    })
    persona = obj({"id": text, "split": {"type": "string", "enum": ["development", "heldout"]}, "name": text, "topic": text, "context_subject": text, "namespaces": obj({"owner": text, "peer": text}), "workspaces": obj({"A": text, "B": text}), "facts": {"type": "object", "additionalProperties": fact_schema}, "sequence_start": obj({"owner_records": array(record), "peer_controls": array(record)}), "conversations": array(conversation, minItems=1)})
    return obj({"schema_version": {"type": "integer", "enum": [1]}, "protocol": {"type": "string", "enum": [PROTOCOL]}, "synthetic": {"type": "boolean", "enum": [True]}, "split": {"type": "string", "enum": ["development", "heldout"]}, "source": {"type": "object"}, "personas": array(persona, minItems=15, maxItems=15)})


def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def fact(value, key, groups=None, scope="global", workspace=None, subject="owner", sensitive=False, control=False):
    return {"value": value, "key": key, "key_aliases": list(dict.fromkeys([key, key.replace("_", " ")])), "value_alias_groups": groups or [[value]], "scope": scope, "workspace": workspace, "subject": subject, "sensitive": sensitive, "control": control}


def probe(subject, fields):
    descriptions = {"context": subject, "style": "my preferred answer format and its reason", "notebook": "my personal planning notebook label", "heading": "the heading for reports in this current workspace", "temporary_label": "the temporary label from a previous draft"}
    return "Use only retained memory for this user and workspace. Return one labelled line for each field:\n" + "\n".join(f"{field}: [{descriptions[field]}]" for field in fields) + "\nUse exactly UNKNOWN when the field is unavailable. Do not infer missing information.\n\n" + SHARED


def heldout_persona(index, row):
    name, topic, subject, original, corrected, style, reason, question = row
    pid = f"H{index:02d}"
    labels = {"A": f"Braid-{pid}", "B": f"Weave-{pid}", "notebook": f"Ledger-{pid}", "temporary": f"Fleeting-{pid}"}
    old_alias, new_alias = HELDOUT_ALIASES[index - 1]
    facts = {"original": {"value": original, "groups": [[original, old_alias]], "scope": "global"}, "corrected": {"value": corrected, "groups": [[corrected, new_alias]], "scope": "global"}, "style": {"value": style, "groups": [[style]], "scope": "global"}, "reason": {"value": reason, "groups": [[reason]], "scope": "global"}}
    facts.update({key: {"value": value, "groups": [[value]], "scope": "workspace" if key in ("A", "B") else "none" if key == "temporary" else "global"} for key, value in labels.items()})
    all_fields = ["context", "style", "notebook", "heading"]
    scripts = [
        ("owner", "A", [f"{original}. My preferred presentation is {style}, because {reason}. {question}", "Explain one edge case for that explanation."], {}),
        ("owner", "A", [f"{original}. Give me a practical example for my notes.", f"For this draft alone, title your next note {labels['temporary']}. Discard that title after this task."], {}),
        ("owner", "A", [probe(subject, ["context", "style", "temporary_label"])], {"context": "original", "style": "style", "temporary_label": "UNKNOWN"}),
        ("owner", "A", [f"Please retain for every future conversation: {original}, and my preferred format, {style}, because {reason}. Remember that my personal planning notebook is labelled {labels['notebook']}. Remember {labels['A']} as this workspace's report heading only."], {}),
        ("owner", "B", [probe(subject, all_fields), f"Remember {labels['B']} as the report heading for future work in this workspace only."], {"context": "original", "style": "style", "notebook": "notebook", "heading": "UNKNOWN"}),
        ("owner", "A", [probe(subject, all_fields)], {"context": "original", "style": "style", "notebook": "notebook", "heading": "A"}),
        ("peer", "A", [probe("my recurring activity context", all_fields)], {field: "PEER" for field in all_fields}),
        ("owner", "A", [f"Replace the context you retain for future conversations: {corrected}, rather than {original}. Erase my personal planning notebook label everywhere; keep none of its value."], {}),
        ("owner", "B", [probe(subject, all_fields + ["temporary_label"])], {"context": "corrected", "style": "style", "notebook": "UNKNOWN", "heading": "B", "temporary_label": "UNKNOWN"}),
        ("owner", "A", [probe(subject, all_fields + ["temporary_label"])], {"context": "corrected", "style": "style", "notebook": "UNKNOWN", "heading": "A", "temporary_label": "UNKNOWN"}),
    ]
    conversations = []
    for i, (actor, workspace, messages, expected) in enumerate(scripts, 1):
        conversations.append({"id": f"C{i}", "actor": actor, "workspace": workspace, "messages": [m if m.endswith(SHARED) else m + "\n\n" + SHARED for m in messages], "probe_expected": expected, "restart_before": i == 10})
    return {"id": pid, "name": name, "topic": topic, "context_subject": subject, "facts": facts, "conversations": conversations}


def adapt_persona(source, split):
    pid = source["id"]
    namespaces = {"owner": f"{pid}-owner", "peer": f"{pid}-peer"}
    workspaces = {"A": f"{pid}-A", "B": f"{pid}-B"}
    context_key = slug(source["context_subject"])
    facts = {}
    keys = {"original": context_key, "corrected": context_key, "style": "preferred_answer_format", "reason": "preferred_answer_reason", "A": "report_heading", "B": "report_heading", "notebook": "planning_notebook_label", "temporary": "draft_heading"}
    for fid, old in source["facts"].items():
        workspace = fid if fid in ("A", "B") else "A" if fid == "temporary" else None
        facts[fid] = fact(old["value"], keys[fid], old["groups"], "workspace" if workspace else "global", workspace, control=fid in ("A", "B", "notebook", "temporary"))
        if fid == "reason" and split == "development":
            facts[fid]["value_alias_groups"] = [[old["value"], *DEVELOPMENT_REASON_ALIASES[int(pid[1:]) - 1]]]
        if fid == "style" and split == "development" and pid in DEVELOPMENT_STYLE_ALIASES:
            facts[fid]["value_alias_groups"] = copy.deepcopy(DEVELOPMENT_STYLE_ALIASES[pid])
        if fid in ("original", "corrected"):
            facts[fid]["key_aliases"] += ["context", "user_context", "recurring_context"]
        elif fid == "style":
            facts[fid]["key_aliases"] += ["style", "answer_format", "preferred_format"]
        elif fid == "reason":
            facts[fid]["key_aliases"] += ["reason", "answer_reason", "format_reason"]
        elif fid in ("A", "B"):
            facts[fid]["key_aliases"] += ["heading", "workspace_heading"]
        elif fid == "notebook":
            facts[fid]["key_aliases"] += ["notebook", "notebook_label"]
    prefix = "Dev" if split == "development" else "Unseen"
    extras = {
        "sensitive_granted": (f"{prefix}-Health-{pid}", "private_health_reminder_label", "owner", True, "global", None),
        "sensitive_denied": (f"{prefix}-Finance-{pid}", "private_finance_reminder_label", "owner", True, "global", None),
        "sensitive_explicit": (f"{prefix}-Belief-{pid}", "private_belief_journal_label", "owner", True, "global", None),
        "quoted": (f"{prefix}-Quote-{pid}", "quoted_notebook_label", "quoted", False, "global", None),
        "third_person": (f"{prefix}-Colleague-{pid}", "colleague_notebook_label", "third_party", False, "global", None),
        "third_party_project": (f"{prefix}-Team-{pid}", "team_report_label", "third_party", False, "workspace", "A"),
    }
    for fid, (value, key, subject, sensitive, scope, workspace) in extras.items():
        facts[fid] = fact(value, key, scope=scope, workspace=workspace, subject=subject, sensitive=sensitive, control=True)
    for field in ("context", "style", "notebook", "heading"):
        scope = "workspace" if field == "heading" else "global"
        facts[f"peer_{field}"] = fact(f"{prefix}-Peer-{field}-{pid}", f"peer_{field}", scope=scope, workspace="A" if scope == "workspace" else None, subject="peer", control=True)
    order = list(facts)

    def record(fid, duplicate=False):
        f = facts[fid]
        return {"id": order.index(fid) + (100 if duplicate else 1), "user_id": namespaces["peer" if f["subject"] == "peer" else "owner"], "workspace_id": workspaces[f["workspace"]] if f["workspace"] else None, "scope": f["scope"], "key": f["key"], "value": f["value"], "history": []}

    peer_controls = [record(fid) for fid in facts if fid.startswith("peer_")]
    raw = copy.deepcopy(source["conversations"])
    extra_scripts = [
        ("C11", f"My private health reminder label is {facts['sensitive_granted']['value']}. It is stable context for all future chats about my health reminders.", ["consent_granted"]),
        ("C12", f"My private finance reminder label is {facts['sensitive_denied']['value']}. It is stable context for future chats, but I have not granted permission to save it.", ["consent_denied"]),
        ("C13", f"Remember for future chats that my private belief journal label is {facts['sensitive_explicit']['value']}. This is an explicit request to save that sensitive fact.", ["explicit_sensitive_consent"]),
        ("C14", f"Analyse this fictional quotation: 'I always label my notebook {facts['quoted']['value']}'. The speaker is not me. What does the sentence communicate?", ["quoted_information"]),
        ("C15", f"My colleague labels their personal notebook {facts['third_person']['value']}. What is a neutral way to acknowledge their statement?", ["third_person_information"]),
        ("C16", f"For this workspace only, remember that our colleague's team report label is {facts['third_party_project']['value']}. This is durable project information, not my personal notebook label.", ["authorized_third_party_project"]),
        ("C17", "Forget the report heading for this workspace everywhere it is retained, including any duplicate copies. Do not retain its value.", ["duplicate_forgetting"]),
        ("C18", f"For all future chats, my preferred answer format remains {facts['style']['value']}, because {facts['reason']['value']}. This repeats my established preference.", ["durable_preference", "unchanged_prior"]),
    ]
    for cid, text, coverage in extra_scripts:
        raw.append({"id": cid, "actor": "owner", "workspace": "A", "messages": [text + "\n\n" + SHARED], "probe_expected": {}, "restart_before": False, "coverage": coverage})
    states = {policy: [] for policy in POLICIES}
    ideal = []
    conversations = []
    for c in raw:
        cid = c["id"]
        i = int(cid[1:])
        before = copy.deepcopy(states)
        ideal_before = ideal[:]
        writes = {policy: [] for policy in POLICIES}
        deletes = []
        updates = []
        forbidden = ["temporary", "quoted", "third_person", "sensitive_denied"]
        coverage = c.get("coverage", [])
        if i == 1:
            writes["recurring"] = ["original", "style", "reason"]
            coverage = ["implicit_context", "preference_format", "preference_reason", "policy_difference"]
        elif i == 2:
            writes["recurring"] = ["original"]
            coverage = ["repetition", "temporary_detail"]
        elif i == 4:
            writes = {policy: ["original", "style", "reason", "notebook", "A"] for policy in POLICIES}
            coverage = ["explicit_remember", "global_scope", "workspace_scope"]
        elif i == 5:
            writes = {policy: ["B"] for policy in POLICIES}
            coverage = ["workspace_switch", "workspace_scope"]
        elif i == 8:
            writes = {policy: ["corrected"] for policy in POLICIES}
            deletes = ["original", "notebook"]
            updates = [{"previous": "original", "current": "corrected"}]
            coverage = ["correction", "forgetting", "history_retirement"]
        elif i in (11, 13, 16):
            target = {11: "sensitive_granted", 13: "sensitive_explicit", 16: "third_party_project"}[i]
            writes = {policy: [target] for policy in POLICIES}
        elif i == 17:
            deletes = ["A"]
        elif i == 18:
            writes = {policy: ["style", "reason"] for policy in POLICIES}
        # Quoted and third-person cases contain naturally durable information, but
        # neither policy may assign that information to the current user.
        if c.get("probe_expected"):
            coverage += ["blind_recall", "user_isolation" if i == 7 else "workspace_selection"]
        if i == 10:
            coverage += ["fresh_conversation"]
        for policy in POLICIES:
            states[policy] = [fid for fid in states[policy] if fid not in deletes]
            states[policy] += [fid for fid in writes[policy] if fid not in states[policy]]
        ideal = [fid for fid in ideal if fid not in deletes]
        ideal += [fid for fid in writes["recurring"] if fid not in ideal]
        probe_fields = {}
        for field, fid in c.get("probe_expected", {}).items():
            probe_fields[field] = [] if fid == "UNKNOWN" else [f"peer_{field}"] if fid == "PEER" else ["style", "reason"] if field == "style" else [fid]
        exclusions = {3: ["temporary"], 5: ["A"], 6: ["B"], 7: ["original", "corrected", "style", "reason", "notebook", "A", "B"], 9: ["notebook", "temporary", "A", "original"], 10: ["notebook", "temporary", "B", "original"]}.get(i, [])
        permission = {"granted": i == 11, "reply": "Yes, save that for future chats." if i == 11 else "No, do not save that." if i == 12 else "No additional consent is granted. Follow the instructions already in my message."}
        expectations = {}
        starting = {}
        for policy in POLICIES:
            starting[policy] = peer_controls + [record(fid) for fid in before[policy]]
            if i == 17:
                starting[policy].append(record("A", duplicate=True))
            required_updates = [update for update in updates if update["previous"] in before[policy]]
            additions = [fid for fid in writes[policy] if fid not in before[policy] and fid not in [update["current"] for update in required_updates]]
            expectations[policy] = {
                "required_additions": additions, "required_updates": required_updates,
                "required_deletions": [fid for fid in deletes if fid not in [update["previous"] for update in required_updates]],
                "retained_prior_facts": [fid for fid in before[policy] if fid not in deletes],
                "expected_current_facts": states[policy][:], "forbidden_new_facts": forbidden[:],
                "permission": "ask_then_grant" if i == 11 else "ask_then_deny" if i == 12 else "explicitly_granted" if i == 13 else "not_required",
                "allowed_realizations": ["update_existing", "forget_then_remember"] if required_updates else ["final_state_and_permission_requirements"],
            }
        prerequisites = ([{"control": "correction", "facts": ["original"]}, {"control": "forgetting", "facts": ["notebook"]}] if i == 8 else [{"control": "forgetting", "facts": ["A"]}] if i == 17 else [])
        pure_probe = bool(probe_fields) and len(c["messages"]) == 1
        conversations.append({
            "id": cid, "actor": c["actor"], "user_id": namespaces[c["actor"]], "workspace_id": workspaces[c["workspace"]],
            "messages": c["messages"], "source_messages": c["messages"][:], "new_conversation": True,
            "restart_before": c.get("restart_before", False), "coverage": coverage,
            "permission_reply": permission, "prerequisites": prerequisites,
            "policy_expectations": expectations,
            "common_targets": {"saved_facts": writes["recurring"], "probe_fields": probe_fields, "excluded_answer_facts": exclusions, "retired_current_facts": deletes},
            "tracks": {
                "write": {"enabled": not pure_probe, "message_indices": list(range(len(c["messages"]))), "starting_records": starting},
                "read": {"enabled": bool(probe_fields), "message_indices": [0] if probe_fields else [], "starting_records": peer_controls + [record(fid) for fid in ideal_before], "probe_fields": probe_fields, "expected_mutations": []},
                "sequence": {"enabled": True, "storage_scored": c["actor"] == "owner", "message_indices": list(range(len(c["messages"]))), "starting_records": None, "expected_current_facts": {policy: states[policy][:] for policy in POLICIES}, "probe_fields": {policy: {field: [fid for fid in required if fid.startswith('peer_') or fid in before[policy]] for field, required in probe_fields.items()} for policy in POLICIES}},
            },
        })
    return {"id": pid, "split": split, "name": source["name"], "topic": source["topic"], "context_subject": source["context_subject"], "namespaces": namespaces, "workspaces": workspaces, "facts": facts, "sequence_start": {"owner_records": [], "peer_controls": peer_controls}, "conversations": conversations}


def operation(name, **arguments):
    return {"name": name, "arguments": arguments}


def result(data=None, error=None):
    return {"ok": error is None, "data": data, "error": error}


def response(answer="", operations=None, results=None, elapsed=1):
    return {"elapsed_seconds": elapsed, "response": {"answer": answer, "operations": operations or []}, "results": results or []}


def fixtures(persona):
    facts = persona["facts"]
    user = persona["namespaces"]["owner"]
    workspace = persona["workspaces"]["A"]

    def rec(fid, rid=1, **changes):
        f = facts[fid]
        row = {"id": rid, "user_id": user, "workspace_id": persona["workspaces"][f["workspace"]] if f["workspace"] else None, "scope": f["scope"], "key": f["key"], "value": f["value"], "history": []}
        row.update(changes)
        return row

    good = rec("original")
    corrected = rec("corrected")
    metrics = lambda tp, fp, fn: {"tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None}
    score = []

    def add(name, expected, actual, counts, prior=None, **outcome):
        score.append({"id": name, "track": "sequence" if name.startswith("forget_") else "write", "expected_facts": expected, "starting_records": prior or [], "actual_records": actual, "expected_outcome": {**counts, **outcome}})

    add("positive_current_fact", ["original"], [good], metrics(1, 0, 0))
    add("empty_expected_and_actual", [], [], metrics(0, 0, 0), conformance=True)
    add("missing_required_save", ["original"], [], metrics(0, 0, 1))
    add("unnecessary_save", [], [good], metrics(0, 1, 0))
    add("duplicate_current_fact", ["original"], [good, rec("original", 2)], metrics(1, 1, 0), duplicates=1)
    add("wrong_key", ["original"], [rec("original", key="unrelated_free_form_key")], metrics(0, 1, 1))
    add("wrong_scope", ["original"], [rec("original", scope="workspace", workspace_id=workspace)], metrics(0, 1, 1))
    add("wrong_current_value", ["original"], [corrected], metrics(0, 1, 1))
    add("unchanged_prepared_fact", [], [good], metrics(0, 0, 0), prior=[good])
    add("unchanged_row_id_churn", [], [rec("original", 9)], metrics(0, 0, 0), prior=[good])
    add("duplicate_added_to_prepared_fact", [], [good, rec("original", 2)], metrics(0, 1, 0), prior=[good], duplicates=1)
    add("current_correction_with_history", ["corrected"], [rec("corrected", history=[facts['original']['value']])], metrics(1, 0, 0), prior=[good], current_correction=True, old_value_retired=False)
    add("complete_correction", ["corrected"], [corrected], metrics(1, 0, 0), prior=[good], current_correction=True, old_value_retired=True)
    add("forget_all_copies", [], [], metrics(0, 0, 0), prior=[rec("notebook"), rec("notebook", 2)], forgotten=True)
    add("forget_leaves_copy", [], [rec("notebook", 2)], metrics(0, 1, 0), prior=[rec("notebook"), rec("notebook", 2)], forgotten=False)
    add("scope_only_change", [], [rec("original", scope="workspace", workspace_id=workspace)], metrics(0, 1, 0), prior=[good], preserved_prior=False)
    add("destructive_prior_change", [], [rec("original", value="unrelated replacement")], metrics(0, 1, 0), prior=[good], preserved_prior=False)
    score += [
        {"id": "verbal_save_without_rows", "expected_facts": ["original"], "starting_records": [], "actual_records": [], "answer": "I saved it.", "expected_outcome": metrics(0, 0, 1)},
        {"id": "malformed_response", "raw_response": "{broken", "expected_outcome": {"error": "format_error"}},
        {"id": "missing_answer_field", "answer": "context: UNKNOWN", "required_fields": ["context", "style"], "expected_outcome": {"answer_format": False}},
        {"id": "duplicate_answer_field", "answer": "context: UNKNOWN\ncontext: UNKNOWN", "required_fields": ["context"], "expected_outcome": {"answer_format": False}},
        {"id": "valid_unknown", "answer": "notebook: UNKNOWN", "required_fields": ["notebook"], "expected_outcome": {"answer_format": True, "unknown": True}},
        {"id": "unknown_with_forgotten_control", "answer": f"notebook: UNKNOWN\nIt used to be {facts['notebook']['value']}.", "required_fields": ["notebook"], "excluded_facts": ["notebook"], "expected_outcome": {"unknown": False}},
        {"id": "correct_heading_with_wrong_workspace", "answer": f"heading: {facts['A']['value']}\nThe other label is {facts['B']['value']}.", "required_fields": ["heading"], "excluded_facts": ["B"], "expected_outcome": {"scope_correct": False}},
        {"id": "missing_sequence_prerequisite", "actual_records": [], "prerequisites": ["original"], "expected_outcome": {"current_correction": None, "exercised": False, "reason": "missing prerequisite"}},
    ]
    for fixture in score:
        fixture.setdefault("track", "sequence" if fixture["id"] == "missing_sequence_prerequisite" else "write" if fixture["id"] in ("verbal_save_without_rows", "malformed_response") else "read")
    write("fixtures/scoring.json", {"schema_version": 1, "protocol": PROTOCOL, "user_id": user, "workspace_id": workspace, "workspaces": persona["workspaces"], "facts": facts, "fixtures": score, "aggregate_fixture": {"members": ["positive_current_fact", "missing_required_save", "duplicate_current_fact"], "expected_outcome": metrics(2, 1, 1)}})
    save = operation("remember", key=good["key"], value=good["value"], scope="global")
    saved = {"name": "remember", "result": result({"record": good})}
    forget = operation("memory_forget", memory_id=999)
    failed = {"name": "memory_forget", "result": result(error={"code": "unavailable_id", "message": "ID is unavailable for this user"})}
    read = operation("memory_read", memory_ids=[1])
    read_result = {"name": "memory_read", "result": result({"records": [good], "missing_ids": []})}
    rounds = [response(f"provisional {i}", [read], [read_result], i) for i in range(1, 7)]
    protocol = [
        {"id": "final_answer", "requests": [response("Finished")], "expected": {"status": "complete", "batches": 0, "requests": 1, "final_answer": "Finished"}},
        {"id": "ordered_mixed_batch", "requests": [response("Provisional save claim", [save, forget, read], [saved, failed, read_result]), response(good["value"], elapsed=2)], "expected": {"status": "complete", "batches": 1, "requests": 2, "final_answer": good["value"]}, "required_committed_records": [good]},
        {"id": "read_before_final", "requests": [response("Not final", [read], [read_result]), response(good["value"], elapsed=2)], "expected": {"status": "complete", "batches": 1, "requests": 2, "final_answer": good["value"]}},
        {"id": "six_batches_then_final", "requests": rounds + [response("Final after results", elapsed=7)], "expected": {"status": "complete", "batches": 6, "requests": 7, "final_answer": "Final after results"}},
        {"id": "seventh_batch_not_executed", "requests": rounds + [response("Still provisional", [save], elapsed=7)], "expected": {"status": "round_exhaustion", "batches": 6, "requests": 7, "final_answer": None}},
        {"id": "malformed_envelope", "requests": [{"elapsed_seconds": 1, "response": {"operations": []}, "results": []}], "expected": {"status": "format_error", "batches": 0, "requests": 1, "final_answer": None}},
        {"id": "deadline", "requests": [response("Too late", elapsed=180)], "expected": {"status": "deadline", "batches": 0, "requests": 1, "final_answer": None}},
        {"id": "empty_final_answer", "requests": [response(" ")], "expected": {"status": "format_error", "batches": 0, "requests": 1, "final_answer": None}},
        {"id": "unknown_operation_feedback", "requests": [response("", [operation("unknown")], [{"name": "unknown", "result": result(error={"code": "unknown_operation", "message": "Unknown operation"})}]), response("Acknowledged", elapsed=2)], "expected": {"status": "complete", "batches": 1, "requests": 2, "final_answer": "Acknowledged"}},
        {"id": "invalid_argument_feedback", "requests": [response("", [operation("memory_forget", memory_id="bad")], [{"name": "memory_forget", "result": result(error={"code": "invalid_arguments", "message": "Expected integer ID"})}]), response("Acknowledged", elapsed=2)], "expected": {"status": "complete", "batches": 1, "requests": 2, "final_answer": "Acknowledged"}},
    ]
    write("fixtures/lifecycle.json", {"schema_version": 1, "protocol": PROTOCOL, "fixtures": protocol})
    write("fixtures/native.json", {"schema_version": 1, "protocol": PROTOCOL, "fixtures": [
        {"id": "native_batch", "response": {"content": "Provisional", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "remember", "arguments": json.dumps(save["arguments"])}}]}, "expected_error": None},
        {"id": "native_final", "response": {"role": "assistant", "content": "Finished"}, "expected_error": None},
        {"id": "native_malformed_arguments", "response": {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "remember", "arguments": "{broken"}}]}, "expected_error": "invalid_arguments"},
        {"id": "native_malformed_envelope", "response": {"tool_calls": []}, "expected_error": "format_error"},
    ]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-source", type=Path, required=True)
    args = parser.parse_args()
    source_bytes = args.development_source.read_bytes()
    source = json.loads(source_bytes)
    if source.get("protocol") != "hosted-memory-personas-v1" or [p["id"] for p in source["personas"]] != [f"P{i:02d}" for i in range(1, 16)]:
        raise ValueError("expected the original P01–P15 development source")
    frozen_contract = make_contract()
    write("contract.json", frozen_contract)
    write("corpus-schema.json", make_corpus_schema(frozen_contract["record"]))
    for split, originals in (("development", source["personas"]), ("heldout", [heldout_persona(i, row) for i, row in enumerate(HELDOUT, 1)])):
        personas = [adapt_persona(persona, split) for persona in originals]
        write(f"corpus/{split}.json", {"schema_version": 1, "protocol": PROTOCOL, "synthetic": True, "split": split, "source": {"protocol": source["protocol"], "sha256": hashlib.sha256(source_bytes).hexdigest()} if split == "development" else {"authored": "heldout-v1", "prompt_tuning": False}, "personas": personas})
        if split == "development":
            fixtures(personas[0])


if __name__ == "__main__":
    main()
