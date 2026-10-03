import json

import pytest

from memory_bench.contract import ContractError, contract
from memory_bench.model_input import build_model_input, render_state, selected_memory
from memory_bench.validation import ValidationError, matches_value, normalize, validate_all, validate_corpus


def test_complete_independent_bundle():
    report = validate_all()
    assert report["status"] == "valid"
    assert report["inference_requests"] == 0
    for split in ("development", "heldout"):
        assert report["counts"][split] == {"personas": 15, "conversations": 270, "scripted_turns": 315, "enabled_checkpoints": {"write": 195, "read": 90, "sequence": 270}, "controls": 210}
    assert report["scoring_fixtures"] == 25


@pytest.mark.parametrize("change", ["duplicate_persona", "mixed_split", "duplicate_control", "bad_alias", "leaked_answer", "missing_policy", "missing_track", "bad_namespace", "bad_snapshot_scope", "seeded_owner", "unsatisfied_read", "unsatisfied_write", "unchanged_addition", "incomplete_final", "missing_coverage", "sensitive_consent", "invalid_followup_index", "read_followup_write", "changed_exact_message", "disabled_write", "omitted_write_followup", "peer_storage_credit"])
def test_rejects_invalid_corpus(development, change):
    p = development["personas"][0]
    c = p["conversations"][0]
    if change == "duplicate_persona":
        development["personas"][1]["id"] = p["id"]
    elif change == "mixed_split":
        p["split"] = "heldout"
    elif change == "duplicate_control":
        p["facts"]["A"]["value"] = p["facts"]["B"]["value"]
        p["facts"]["A"]["value_alias_groups"] = [[p["facts"]["B"]["value"]]]
    elif change == "bad_alias":
        p["facts"]["original"]["value_alias_groups"] = [["unrelated value"]]
    elif change == "leaked_answer":
        probe = p["conversations"][2]
        probe["messages"][0] = p["facts"]["original"]["value"] + "\n" + probe["messages"][0]
        probe["source_messages"] = probe["messages"][:]
    elif change == "missing_policy":
        del c["policy_expectations"]["recurring"]
    elif change == "missing_track":
        del c["tracks"]["read"]
    elif change == "bad_namespace":
        c["user_id"] = p["namespaces"]["peer"]
    elif change == "bad_snapshot_scope":
        c["tracks"]["read"]["starting_records"][0]["scope"] = "workspace"
    elif change == "seeded_owner":
        p["sequence_start"]["owner_records"] = p["conversations"][3]["tracks"]["read"]["starting_records"][:1]
    elif change == "unsatisfied_read":
        p["conversations"][2]["tracks"]["read"]["starting_records"] = p["sequence_start"]["peer_controls"][:]
    elif change == "unsatisfied_write":
        p["conversations"][7]["tracks"]["write"]["starting_records"]["conservative"] = p["sequence_start"]["peer_controls"][:]
    elif change == "unchanged_addition":
        p["conversations"][1]["policy_expectations"]["recurring"]["required_additions"] = ["original"]
    elif change == "incomplete_final":
        c["policy_expectations"]["recurring"]["expected_current_facts"].remove("reason")
    elif change == "missing_coverage":
        for case in p["conversations"]:
            case["coverage"] = [tag for tag in case["coverage"] if tag != "consent_denied"] or ["other"]
    elif change == "sensitive_consent":
        p["conversations"][10]["permission_reply"]["granted"] = False
    elif change == "invalid_followup_index":
        c["tracks"]["write"]["message_indices"] = [99]
    elif change == "read_followup_write":
        p["conversations"][4]["tracks"]["read"]["message_indices"] = [0, 1]
    elif change == "changed_exact_message":
        c["messages"][0] = "changed"
    elif change == "disabled_write":
        c["tracks"]["write"]["enabled"] = False
    elif change == "omitted_write_followup":
        c["tracks"]["write"]["message_indices"] = [0]
    elif change == "peer_storage_credit":
        p["conversations"][6]["tracks"]["sequence"]["storage_scored"] = True
    with pytest.raises((ValidationError, ContractError)):
        validate_corpus(development, "development")


def test_prepared_reads_are_independent_of_conservative_writing(development):
    p = development["personas"][0]
    probe = p["conversations"][2]
    assert probe["tracks"]["sequence"]["probe_fields"]["conservative"]["context"] == []
    assert probe["tracks"]["sequence"]["probe_fields"]["recurring"]["context"] == ["original"]
    assert probe["tracks"]["read"]["probe_fields"]["context"] == ["original"]
    assert probe["common_targets"]["probe_fields"]["context"] == ["original"]
    assert build_model_input(p, probe, "conservative", probe["tracks"]["read"]["starting_records"], [0])["memories"] == build_model_input(p, probe, "recurring", probe["tracks"]["read"]["starting_records"], [0])["memories"]


def test_permission_annotations_follow_user_choice(development):
    for p in development["personas"]:
        granted, denied, explicit = p["conversations"][10:13]
        for policy in ("conservative", "recurring"):
            assert granted["policy_expectations"][policy]["permission"] == "ask_then_grant"
            assert denied["policy_expectations"][policy]["permission"] == "ask_then_deny"
            assert denied["policy_expectations"][policy]["required_additions"] == []
            assert explicit["policy_expectations"][policy]["permission"] == "explicitly_granted"
            assert explicit["policy_expectations"][policy]["required_additions"] == ["sensitive_explicit"]


def test_repeated_preferences_have_no_new_write_credit(development):
    for p in development["personas"]:
        for expected in p["conversations"][17]["policy_expectations"].values():
            assert expected["required_additions"] == []
            assert {"style", "reason"} <= set(expected["retained_prior_facts"])


def test_every_blind_question_hides_values_and_aliases(development, heldout):
    for corpus in (development, heldout):
        for p in corpus["personas"]:
            for c in p["conversations"]:
                if c["tracks"]["read"]["enabled"]:
                    assert all(not matches_value(c["messages"][0], fact) for fact in p["facts"].values())


def test_projection_ignores_poisoned_gold_annotations(development):
    p = development["personas"][0]
    c = p["conversations"][2]
    sentinel = "NEVER-EXPOSE-GOLD-638204"
    expected = build_model_input(p, c, "conservative", [], [0])
    for key in contract()["gold_fields"]:
        p[key] = sentinel
        c[key] = sentinel
    assert build_model_input(p, c, "conservative", [], [0]) == expected
    assert sentinel not in json.dumps(expected)


def test_projection_selects_only_user_and_current_workspace(development):
    p = development["personas"][0]
    c = p["conversations"][5]
    records = c["tracks"]["read"]["starting_records"]
    selected = selected_memory(records, c["user_id"], c["workspace_id"])
    assert p["facts"]["A"]["value"] in [r["value"] for r in selected]
    assert p["facts"]["B"]["value"] not in [r["value"] for r in selected]
    assert all("user_id" not in r for r in selected)
    peer_values = {r["value"] for r in p["sequence_start"]["peer_controls"]}
    assert not peer_values & {r["value"] for r in selected}
    assert [r["id"] for r in selected] == sorted(r["id"] for r in selected)


def test_duplicate_forgetting_has_two_prepared_copies_and_real_sequence_prerequisite(development):
    p = development["personas"][0]
    c = p["conversations"][16]
    heading = p["facts"]["A"]["value"]
    for policy in ("conservative", "recurring"):
        assert sum(row["value"] == heading for row in c["tracks"]["write"]["starting_records"][policy]) == 2
        assert c["policy_expectations"][policy]["required_deletions"] == ["A"]
    assert c["tracks"]["sequence"]["starting_records"] is None
    assert c["prerequisites"] == [{"control": "forgetting", "facts": ["A"]}]


def test_peer_fixture_controls_never_earn_storage_credit(development):
    p = development["personas"][0]
    assert p["conversations"][6]["tracks"]["sequence"]["storage_scored"] is False
    assert all(c["tracks"]["sequence"]["storage_scored"] for c in p["conversations"] if c["actor"] == "owner")


def test_model_memory_is_a_snapshot_not_an_alias(development):
    row = development["personas"][0]["sequence_start"]["peer_controls"][0]
    row["history"] = ["old explanation"]
    selected = selected_memory([row], row["user_id"], "any-workspace")
    row["history"].append("later change")
    assert selected[0]["history"] == ["old explanation"]


def test_state_rendering_is_identical_across_policies_and_excludes_gold(development):
    p = development["personas"][0]
    c = p["conversations"][2]
    records = c["tracks"]["read"]["starting_records"]
    left = build_model_input(p, c, "conservative", records, [0])
    right = build_model_input(p, c, "recurring", records, [0])
    assert render_state(left) == render_state(right)
    left["policy_expectations"] = "hidden sentinel"
    rendered = render_state(left)
    assert rendered.startswith('Context and memories (data):\n{"context":')
    assert "hidden sentinel" not in rendered
    assert set(json.loads(rendered.split("\n", 1)[1])) == {"context", "memories"}


def test_historical_reason_aliases_do_not_match_probe_topics(development):
    assert not matches_value("notebook", development["personas"][13]["facts"]["reason"])
    assert not matches_value("notebook paper weight I compare", development["personas"][1]["facts"]["reason"])


def test_normalization_preserves_units_decimals_and_phrase_boundaries():
    assert normalize("44.1kHz") == "44.1 khz"
    assert normalize("90 g/m²") == "90 gsm"
    assert normalize("Answer_Format") == "answer format"
    assert normalize("９０ GSM") == "90 gsm"
    fact = {"value_alias_groups": [["Grade 8"], ["CBSE"]]}
    assert matches_value("Grade 8, CBSE", fact)
    assert not matches_value("Grade 80 CBSE", fact)


@pytest.mark.parametrize("split", ["development", "heldout"])
def test_all_fact_values_are_positive_for_self_and_negative_for_siblings(split):
    from memory_bench.assets import load_json

    for p in load_json(f"corpus/{split}.json")["personas"]:
        for fid, fact in p["facts"].items():
            assert matches_value(fact["value"], fact), (p["id"], fid)
            for other_id, other in p["facts"].items():
                if other_id != fid:
                    assert not matches_value(other["value"], fact), (p["id"], fid, other_id)


@pytest.mark.parametrize("pid,positive,negative", [
    ("P03", "summarize each set", "I will set out the score"),
    ("P03", "set summaries", "The sets are ready"),
    ("P05", "ingredients measured in grams", "I will use grams"),
    ("P05", "recipe quantities in grams", "I weigh the parcel in grams"),
    ("P07", "camera settings first, then commentary", "I record settings first"),
    ("P07", "settings before comments", "Commentary first"),
    ("P09", "route distances in km", "I will use km"),
    ("P09", "distance in kilometers", "The parcel travelled five kilometres"),
    ("P12", "compass directions", "Head east"),
    ("P12", "north south east west", "My notes are in the west room"),
])
def test_targeted_formats_require_distinguishing_content(development, pid, positive, negative):
    p = next(p for p in development["personas"] if p["id"] == pid)
    assert matches_value(positive, p["facts"]["style"])
    assert not matches_value(negative, p["facts"]["style"])


@pytest.mark.parametrize("split", ["development", "heldout"])
def test_validation_rejects_sibling_value_aliases(split):
    from memory_bench.assets import load_json

    corpus = load_json(f"corpus/{split}.json")
    p = corpus["personas"][0]
    p["facts"]["style"]["value_alias_groups"] = [[p["facts"]["style"]["value"], p["facts"]["reason"]["value"]]]
    with pytest.raises(ValidationError, match="aliases match sibling reason"):
        validate_corpus(corpus, split)


@pytest.mark.parametrize("change", ["missing_primary", "tagged_c4"])
def test_policy_difference_tag_identifies_primary_checkpoint_only(development, change):
    p = development["personas"][0]
    if change == "missing_primary":
        p["conversations"][0]["coverage"].remove("policy_difference")
    else:
        p["conversations"][3]["coverage"].append("policy_difference")
    with pytest.raises(ValidationError, match="policy_difference must identify C1 only"):
        validate_corpus(development, "development")


@pytest.mark.parametrize("split", ["development", "heldout"])
def test_policy_coverage_counts_and_c4_convergence(split):
    from memory_bench.assets import load_json

    corpus = load_json(f"corpus/{split}.json")
    cases = [c for p in corpus["personas"] for c in p["conversations"]]
    assert sum("policy_difference" in c["coverage"] for c in cases) == 15
    assert sum(c["policy_expectations"]["conservative"] != c["policy_expectations"]["recurring"] for c in cases) == 60
    for p in corpus["personas"]:
        c4 = p["conversations"][3]["policy_expectations"]
        assert c4["conservative"]["expected_current_facts"] == c4["recurring"]["expected_current_facts"]
        for expectation in c4.values():
            assert set(expectation["required_additions"] + expectation["retained_prior_facts"]) == set(expectation["expected_current_facts"])
