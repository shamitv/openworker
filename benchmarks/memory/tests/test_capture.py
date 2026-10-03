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
