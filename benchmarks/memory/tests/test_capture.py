import json

import pytest

from memory_bench.capture import Capture, read_checkpoints


def test_capture_requires_new_output_and_retains_latest_partial_checkpoint(tmp_path):
    path = tmp_path / "capture"
    capture = Capture(path, {"status": "running"})
    capture.record({"type": "request_started", "request": {"model": "exact"}})
    capture.checkpoint({"checkpoint_id": "one", "status": "running"})
    capture.checkpoint({"checkpoint_id": "one", "status": "failed"})
    capture.close()
    assert read_checkpoints(path) == [{"checkpoint_id": "one", "status": "failed"}]
    assert json.loads((path / "diagnostics.jsonl").read_text())["type"] == "request_started"
    with pytest.raises(FileExistsError):
        Capture(path, {})


def test_only_interrupted_trailing_write_is_ignored(tmp_path):
    path = tmp_path / "checkpoints.jsonl"
    path.write_text('{"checkpoint_id":"one"}\n{"interrupted":', encoding="utf-8")
    assert read_checkpoints(tmp_path) == [{"checkpoint_id": "one"}]
    path.write_text('BROKEN\n{"checkpoint_id":"one"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        read_checkpoints(tmp_path)
@pytest.mark.parametrize("failures", [1, 3])
def test_atomic_json_publication_retries_transient_windows_sharing_only(tmp_path, monkeypatch, failures):
    from memory_bench.capture import write_json
    path = tmp_path / "manifest.json"
    path.write_text('{"old":true}', encoding="utf-8")
    original = type(path).replace
    calls, delays = [], []
    def replace(source, target):
        calls.append(target)
        if len(calls) <= failures:
            assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        return original(source, target)
    monkeypatch.setattr(type(path), "replace", replace)
    monkeypatch.setattr("memory_bench.capture.time.sleep", delays.append)
    write_json(path, {"new": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert len(calls) == failures + 1
    assert sum(delays) <= 0.176
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("winerror,expected_calls", [(None, 1), (32, 4)])
def test_atomic_publication_does_not_hide_persistent_or_non_windows_errors(tmp_path, monkeypatch, winerror, expected_calls):
    from memory_bench.capture import write_json
    path = tmp_path / "manifest.json"
    path.write_text('{"old":true}', encoding="utf-8")
    calls = []
    def failed(source, target):
        calls.append(target)
        error = PermissionError("access denied")
        error.winerror = winerror
        raise error
    monkeypatch.setattr(type(path), "replace", failed)
    monkeypatch.setattr("memory_bench.capture.time.sleep", lambda _: None)
    with pytest.raises(PermissionError):
        write_json(path, {"new": True})
    assert len(calls) == expected_calls
    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
