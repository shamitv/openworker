import copy
import json
import sys

import pytest

from memory_bench import cli
from memory_bench.assets import asset_hashes, canonical_json, load_json, resource
from memory_bench.contract import ContractError
from memory_bench.validation import ValidationError, validate_fixture_header, validate_lifecycle_fixture, validate_native_fixture, validate_scoring_fixtures


@pytest.mark.parametrize("index", range(10))
def test_shared_lifecycle_examples(index):
    validate_lifecycle_fixture(load_json("fixtures/lifecycle.json")["fixtures"][index])


@pytest.mark.parametrize("index", range(4))
def test_native_schema_examples(index):
    validate_native_fixture(load_json("fixtures/native.json")["fixtures"][index])


@pytest.mark.parametrize("change", ["out_of_order", "provisional_final", "executed_seventh", "eighth_request", "after_final", "deadline_results", "bad_error_code", "lost_commit"])
def test_invalid_protocol_traces_rejected(change):
    fixtures = load_json("fixtures/lifecycle.json")["fixtures"]
    f = copy.deepcopy(fixtures[1])
    if change == "out_of_order":
        f["requests"][0]["results"].reverse()
    elif change == "provisional_final":
        f["expected"]["final_answer"] = "Provisional save claim"
    elif change == "executed_seventh":
        f = copy.deepcopy(fixtures[4])
        f["requests"][-1]["results"] = [fixtures[1]["requests"][0]["results"][0]]
    elif change == "eighth_request":
        f = copy.deepcopy(fixtures[4])
        f["requests"].append(copy.deepcopy(fixtures[0]["requests"][0]))
    elif change == "after_final":
        f["requests"].append(copy.deepcopy(fixtures[0]["requests"][0]))
    elif change == "deadline_results":
        f["requests"][0]["elapsed_seconds"] = 180
    elif change == "bad_error_code":
        f = copy.deepcopy(fixtures[9])
        f["requests"][0]["results"][0]["result"]["error"]["code"] = "unavailable_id"
    elif change == "lost_commit":
        f["required_committed_records"][0]["value"] = "missing committed value"
    with pytest.raises((ValidationError, ContractError)):
        validate_lifecycle_fixture(f)


def test_scoring_fixture_counts_and_nulls():
    data = load_json("fixtures/scoring.json")
    validate_scoring_fixtures(data)
    fixtures = {f["id"]: f for f in data["fixtures"]}
    assert fixtures["empty_expected_and_actual"]["expected_outcome"]["precision"] is None
    assert fixtures["missing_required_save"]["expected_outcome"]["recall"] == 0
    assert fixtures["unnecessary_save"]["expected_outcome"]["precision"] == 0
    assert fixtures["current_correction_with_history"]["expected_outcome"]["current_correction"] is True
    assert fixtures["current_correction_with_history"]["expected_outcome"]["old_value_retired"] is False
    assert fixtures["missing_sequence_prerequisite"]["expected_outcome"]["current_correction"] is None
    assert fixtures["forget_leaves_copy"]["track"] == "sequence"
    assert fixtures["unchanged_prepared_fact"]["track"] == "write"


@pytest.mark.parametrize("change", [{"schema_version": 2}, {"protocol": "hosted-memory-personas-v1"}])
def test_foreign_fixture_protocol_rejected(change):
    with pytest.raises(ValidationError):
        validate_fixture_header({"schema_version": 1, "protocol": "standalone-memory-benchmark-v1", **change})


@pytest.mark.parametrize("change", ["zero_denominator", "wrong_ratio", "wrong_aggregate", "negative_count", "missing_fixture"])
def test_invalid_scoring_fixture_declarations(change):
    data = load_json("fixtures/scoring.json")
    if change == "zero_denominator":
        data["fixtures"][1]["expected_outcome"]["precision"] = 1
    elif change == "wrong_ratio":
        data["fixtures"][0]["expected_outcome"]["recall"] = 0
    elif change == "wrong_aggregate":
        data["aggregate_fixture"]["expected_outcome"]["tp"] = 9
    elif change == "negative_count":
        data["fixtures"][0]["expected_outcome"]["fp"] = -1
    else:
        data["fixtures"].pop()
    with pytest.raises(ValidationError):
        validate_scoring_fixtures(data)


def test_hashes_are_stable_and_json_canonicalization_is_order_independent():
    assert asset_hashes() == asset_hashes()
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    assert len(asset_hashes()) == 11


@pytest.mark.parametrize("name", ["../corpus/development.json", "/contract.json", "corpus\\development.json", "corpus//development.json"])
def test_resource_paths_cannot_escape_bundle(name):
    with pytest.raises(ValueError):
        resource(name)


def test_cli_offline_from_unrelated_working_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["validate"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "valid"
    assert "coworker" not in sys.modules
    assert report["inference_requests"] == 0


def test_cli_validation_failure_is_nonzero(monkeypatch, capsys):
    def invalid():
        raise ValidationError("invalid bundled corpus")

    monkeypatch.setattr(cli, "validate_all", invalid)
    assert cli.main(["validate"]) == 1
    assert "invalid bundled corpus" in capsys.readouterr().err


def test_phase_one_does_not_offer_inference_commands():
    with pytest.raises(SystemExit) as caught:
        cli.main(["run"])
    assert caught.value.code == 2
