import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from memory_bench import cli
from memory_bench.execution import collect
from memory_bench.experiments import schedule
from memory_bench.reporting import load_capture, replay, request_summary, sanitized, write_report


@pytest.fixture
def evidence(tmp_path):
    rows = schedule(dataset="development", models=["exact"], policies=["conservative"], prompts=["baseline"],
                    interfaces=["json"], tracks=["read"], runs=1)
    rows = rows[:1]
    rows[0]["checkpoints"] = rows[0]["checkpoints"][:1]
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "exact"}]} if request.method == "GET" else
            {"choices": [{"message": {"content": '{"answer":"UNKNOWN","operations":[]}'}}]})
    path = tmp_path / "collected"
    asyncio.run(collect(base_url="http://localhost/v1", models=["exact"], output=path,
                       schedule=rows, requested={}, transport=httpx.MockTransport(handler)))
    return path


def test_replay_and_report_never_infer_and_preserve_provenance(evidence, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline action constructed an inference client")
    monkeypatch.setattr("memory_bench.execution.LocalClient", forbidden)
    original, _ = load_capture(evidence)
    report = write_report(evidence, tmp_path / "report")
    rescored = replay(evidence, tmp_path / "replay")
    assert rescored["conditions"] == report["conditions"]
    assert rescored["collection"] == original["collection"]
    assert rescored["collection_scoring"] == original["collection_scoring"]
    assert rescored["scoring_history"][0] == original["collection_scoring"]
    assert rescored["offline_inference_requests"] == 0
    assert (tmp_path / "report" / "report.md").is_file()
    assert "base_url" not in json.dumps(report)
    assert "provisional_answers" not in json.dumps(report)
    assert "messages" not in json.dumps(report)
    assert "Context and memories" not in json.dumps(report)


def test_replay_records_new_scorer_without_changing_collection(evidence, tmp_path, monkeypatch):
    original, _ = load_capture(evidence)
    changed = deepcopy(original["collection_scoring"])
    changed["revision"] = "new-scoring-revision"
    monkeypatch.setattr("memory_bench.reporting.scorer_provenance", lambda: changed)
    result = replay(evidence, tmp_path / "rescored")
    assert result["collection"] == original["collection"]
    assert result["scoring_history"] == [original["collection_scoring"], changed]


def test_replay_refuses_incompatible_corpus(evidence, monkeypatch):
    from memory_bench.assets import asset_hashes
    changed = asset_hashes()
    changed["corpus/development.json"] = "changed"
    monkeypatch.setattr("memory_bench.reporting.asset_hashes", lambda: changed)
    with pytest.raises(ValueError, match="differs"):
        load_capture(evidence)


def test_missing_usage_is_null_and_partial_totals_have_reported_counts():
    rows = [{"kind": "inference", "usage": None, "error": None, "duration_seconds": 1}]
    summary = request_summary(rows)
    assert summary["usage"]["prompt_tokens"] is None
    assert summary["missing_usage_requests"] == 1
    rows.append({"kind": "inference", "usage": {"prompt_tokens": 12}, "error": None, "duration_seconds": 1})
    summary = request_summary(rows)
    assert summary["usage"]["prompt_tokens"] == 12
    assert summary["usage"]["prompt_tokens_reported_requests"] == 1
    assert summary["usage"]["completion_tokens"] is None
    assert summary["cost"] is None


def test_sanitization_removes_headers_paths_and_raw_error_messages():
    result = sanitized({"headers": {"Authorization": "secret"}, "base_url": "private", "output": "C:/private",
                        "error": {"code": "api_error", "message": "raw secret response"}})
    assert result == {"error": {"code": "api_error"}}


def test_offline_cli_actions_work_from_unrelated_directory(evidence, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for action in ("report", "replay"):
        assert cli.main([action, "--input", str(evidence), "--output", str(tmp_path / action)]) == 0
        assert json.loads(capsys.readouterr().out)["inference_requests"] == 0


@pytest.mark.parametrize("args", [["run"], ["smoke"], ["smoke", "--base-url", "http://localhost", "--models", "one", "two", "--output", "unused"],
    ["smoke", "--base-url", "http://localhost", "--models", "one", "--output", "unused", "--dataset", "heldout"],
    ["run", "--base-url", "http://localhost", "--models", "one", "--output", "unused", "--dataset", "development"]])
def test_live_cli_requires_explicit_selections_and_fixed_smoke(args):
    with pytest.raises(SystemExit) as caught:
        cli.main(args)
    assert caught.value.code == 2


def test_existing_output_directory_is_not_overwritten(evidence):
    with pytest.raises(FileExistsError):
        replay(evidence, evidence)


def test_complete_fixed_smoke_cli_uses_mock_http_only(tmp_path, monkeypatch, capsys):
    from memory_bench.client import LocalClient
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"id": "exact"}]} if request.method == "GET" else
            {"choices": [{"message": {"content": '{"answer":"UNKNOWN","operations":[]}'}}]})
    monkeypatch.setattr("memory_bench.execution.LocalClient", lambda url, **kwargs:
        LocalClient(url, transport=httpx.MockTransport(handler), record=kwargs["record"]))
    path = tmp_path / "full-smoke"
    assert cli.main(["smoke", "--base-url", "http://localhost/v1", "--models", "exact", "--output", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["coverage"] == {"track_runs": 12, "checkpoints": 148, "completed": 148, "failed": 0, "unexecuted": 0}
    assert len(calls) == 173
    assert result["requests"]["usage"]["prompt_tokens"] is None
    assert (path / "results.json").is_file()


def test_phase5_report_metadata_turn_accounting_and_read_scoring(evidence, tmp_path):
    report = write_report(evidence, tmp_path / "phase5-report")
    assert report["turn_coverage"] == {"scheduled": 1, "executed": 1, "completed": 1, "failed": 0, "unexecuted": 0}
    assert report["model_metadata"]["advertised"][0]["id"] == "exact"
    assert report["model_metadata"]["missing_response_model_requests"] == 1
    assert report["reporting"]["source_hashes"].keys() == {"reporting.py", "comparison.py"}
    assert report["comparison_limits"]["one_repetition"]
    assert report["comparisons"]["model"] == []
    text = (tmp_path / "phase5-report" / "report.md").read_text(encoding="utf-8")
    for phrase in ("Preference reason", "Historical wording retired", "Controls exercised/unexercised",
                   "Prepared reads earn no save credit", "one repetition", "No matched comparison", "Server-effective settings: `null`"):
        assert phrase in text
    assert "Phase 5 remains a separate" not in text  # full run, not smoke


def test_latency_denominators_and_nearest_rank_percentile():
    rows = [{"kind": "inference", "usage": None, "duration_seconds": value} for value in (1, 2, 3, 4, None)]
    summary = request_summary(rows)
    assert summary["latency_seconds"] == {"reported_requests": 4, "missing_requests": 1,
        "min": 1, "median": 2.5, "p90": 4, "max": 4, "p90_method": "nearest rank"}
    assert request_summary([])["latency_seconds"]["median"] is None


def test_sanitization_excludes_reasoning_text():
    assert sanitized({"reasoning_content": "private text", "answer": "synthetic final"}) == {"answer": "synthetic final"}
