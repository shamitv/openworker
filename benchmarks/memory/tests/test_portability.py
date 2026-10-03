import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def verifier(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools" / "verify_portability.py"
    spec = importlib.util.spec_from_file_location("review_portability_verifier", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "package"
    root.mkdir()
    (root / "README.md").write_text("Test package", encoding="utf-8")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(sys, "argv", [str(path), "--wheelhouse", str(wheelhouse)])
    return module


@pytest.mark.parametrize("failure", ["command", "copy", "cleanup"])
def test_failure_preserves_diagnostics_and_only_cleans_owned_directory(verifier, monkeypatch, capsys, failure):
    build = verifier.ROOT / "build"
    previous = build / "portability-previous"
    previous.mkdir(parents=True)
    (previous / "report.json").write_text("previous evidence", encoding="utf-8")

    def failed_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "partial environment output", "creation failed")

    monkeypatch.setattr(verifier.subprocess, "run", failed_run)
    if failure == "copy":
        def failed_copy(*args, **kwargs):
            raise OSError("copy failed")
        monkeypatch.setattr(verifier.shutil, "copytree", failed_copy)
    if failure == "cleanup":
        def failed_cleanup(*args, **kwargs):
            raise PermissionError("directory locked")
        monkeypatch.setattr(verifier.shutil, "rmtree", failed_cleanup)
    with pytest.raises(OSError if failure == "copy" else RuntimeError,
                       match="copy failed" if failure == "copy" else "verification command failed"):
        verifier.main()
    report_path, = (build / "portability-reports").glob("*.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    work = Path(report["work_directory"])
    assert work.parent == build.resolve()
    assert report["status"] == "failed"
    assert report["inference_requests"] == 0
    if failure != "copy":
        assert report["commands"][0]["stdout"] == "partial environment output"
        assert report["commands"][0]["stderr"] == "creation failed"
        assert report["commands"][0]["returncode"] == 1
    assert (previous / "report.json").read_text(encoding="utf-8") == "previous evidence"
    if failure == "cleanup":
        assert work.exists()
        assert report["cleanup"] == "failed"
        assert "directory locked" in report["cleanup_error"]
        assert "cleanup failed" in capsys.readouterr().err
    else:
        assert report["cleanup"] == "removed"
        assert not work.exists()


def test_cleanup_refuses_target_outside_build(verifier, tmp_path):
    build = verifier.ROOT / "build"
    build.mkdir()
    unrelated = tmp_path / "portability-unrelated"
    unrelated.mkdir()
    (unrelated / "marker").write_text("preserve", encoding="utf-8")
    verifier.preserve_failure_and_cleanup(build, unrelated, [], RuntimeError("primary failure"))
    report = json.loads((build / "portability-reports" / (unrelated.name + ".json")).read_text(encoding="utf-8"))
    assert report["error"] == "primary failure"
    assert report["cleanup"] == "failed"
    assert (unrelated / "marker").exists()


def test_diagnostic_write_failure_retains_work_and_primary_error(verifier, monkeypatch, capsys):
    original = Path.write_text

    def fail_report(path, *args, **kwargs):
        if path.parent.name == "portability-reports":
            raise PermissionError("report locked")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report)
    monkeypatch.setattr(verifier.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 1, "", "primary command failure"))
    with pytest.raises(RuntimeError, match="verification command failed"):
        verifier.main()
    work, = [p for p in (verifier.ROOT / "build").glob("portability-*") if p.name != "portability-reports"]
    assert work.exists()
    assert "Could not preserve failure report" in capsys.readouterr().err
