"""Copy, build, install and verify from a clean venv, using an offline wheelhouse.

The owned verification directory stays under this package's ignored build folder.
Successful artifacts and existing directories are retained. Failed invocations
preserve diagnostics outside their disposable directory before cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def preserve_failure_and_cleanup(build, work, commands, error):
    """Keep failure evidence; never delete a sibling or mask the primary error."""
    report = {"status": "failed", "error_type": type(error).__name__, "error": str(error),
              "commands": commands, "work_directory": str(work), "cleanup": "pending",
              "installation_network": False, "inference_requests": 0}
    output = build / "portability-reports" / (work.name + ".json")
    try:
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as diagnostic_error:
        print(f"Could not preserve failure report: {diagnostic_error}; retained {work}", file=sys.stderr)
        return
    try:
        resolved_build, resolved_work = build.resolve(), work.resolve()
        if resolved_work.parent != resolved_build or not resolved_work.name.startswith("portability-"):
            raise ValueError("cleanup target is not this invocation's directory inside build")
        shutil.rmtree(resolved_work)
        report["cleanup"] = "removed"
    except Exception as cleanup_error:
        report["cleanup"] = "failed"
        report["cleanup_error"] = str(cleanup_error)
        print(f"Verification cleanup failed for {work}: {cleanup_error}", file=sys.stderr)
    try:
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as diagnostic_error:
        print(f"Could not update failure report: {diagnostic_error}", file=sys.stderr)
    print(f"Verification failure report: {output}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    args = parser.parse_args()
    wheelhouse = args.wheelhouse.resolve()
    if not wheelhouse.is_dir():
        parser.error("wheelhouse must be an existing directory")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="portability-", dir=build)).resolve()
    work.relative_to(build.resolve())
    commands = []
    try:
        copied = work / "copied-package"
        shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns("build", "dist", ".venv", "__pycache__", ".pytest_cache", "*.egg-info"))
        unrelated = work / "unrelated-cwd"
        unrelated.mkdir()
        scratch = work / "scratch"
        scratch.mkdir()
        environment = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME"):
            environment.pop(key, None)
        environment.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "TEMP": str(scratch), "TMP": str(scratch), "PIP_DISABLE_PIP_VERSION_CHECK": "1"})

        def run(command, cwd=unrelated):
            entry = {"command": [str(item) for item in command], "cwd": str(cwd),
                     "returncode": None, "stdout": "", "stderr": ""}
            commands.append(entry)
            completed = subprocess.run([str(item) for item in command], cwd=cwd, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
            entry.update(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
            if completed.returncode:
                print(completed.stdout + completed.stderr, file=sys.stderr)
                raise RuntimeError(f"verification command failed: {command[1:]}")
            return completed.stdout

        env_dir = work / "env"
        run([sys.executable, "-m", "venv", env_dir])
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        pip = [python, "-m", "pip", "--isolated", "--cache-dir", work / "pip-cache"]
        run(pip + ["install", "--no-index", "--find-links", wheelhouse, "setuptools>=68", "wheel"])
        wheels = work / "wheels"
        run(pip + ["wheel", "--no-index", "--no-build-isolation", "--find-links", wheelhouse, "--no-deps", "--wheel-dir", wheels, copied])
        run(pip + ["install", "--no-index", "--find-links", wheelhouse, "--find-links", wheels, "standalone-memory-bench[test]==0.1.0"])
        check = """import importlib.metadata as m, importlib.util, json, sys
import memory_bench
assert importlib.util.find_spec('coworker') is None, 'OpenWorker is installed'
assert 'site-packages' in memory_bench.__file__, 'using source tree rather than wheel'
print(json.dumps({'python':sys.version, 'module':memory_bench.__file__, 'distributions':{d.metadata['Name']:d.version for d in m.distributions()}, 'requires_python':m.metadata('standalone-memory-bench')['Requires-Python'], 'requirements':m.requires('standalone-memory-bench'), 'openworker_available':False}))
"""
        metadata = json.loads(run([python, "-I", "-c", check]))
        # Network guards in-process also cover validation launched from an unrelated cwd.
        offline = """import socket, sys
def forbidden(*args, **kwargs):
    raise AssertionError('validation attempted network access')
socket.create_connection = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
from memory_bench.cli import main
assert main(['validate']) == 0
assert 'coworker' not in sys.modules
"""
        validation = json.loads(run([python, "-I", "-c", offline]))
        cli_validation = json.loads(run([python, "-I", "-m", "memory_bench", "validate"]))
        if cli_validation != validation:
            raise RuntimeError("module CLI validation differs from guarded validation")
        scorer = json.loads(run([python, "-I", "-c", "import json; from memory_bench.provenance import scorer_provenance; print(json.dumps(scorer_provenance()))"]))
        tests = run([python, "-m", "pytest", copied / "tests", "-c", copied / "pyproject.toml", "--confcutdir", copied / "tests", "-o", "pythonpath=", "--basetemp", work / "test-temp", "-q"])
        versions = metadata["distributions"]
        unexpected = set(versions) - {"pip", "setuptools", "wheel", "standalone-memory-bench", "httpx", "httpcore", "anyio", "certifi", "idna", "h11", "typing_extensions", "pytest", "colorama", "iniconfig", "packaging", "pluggy", "Pygments", "pygments", "exceptiongroup", "tomli"}
        if unexpected:
            raise RuntimeError(f"unexpected isolated distributions: {sorted(unexpected)}")
        wheel = next(wheels.glob("standalone_memory_bench-*.whl"))
        report = {"status": "passed", "metadata": metadata, "validation": validation, "scorer": scorer, "pytest": tests.strip(), "commands": commands, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "work_directory": str(work), "installation_network": False, "inference_requests": 0}
        output = work / "report.json"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(output), "pytest": report["pytest"], "bundle_hash": validation["bundle_hash"], "scorer_sha256": scorer["sha256"], "wheel_sha256": report["wheel_sha256"], "openworker_available": False, "installation_network": False}, indent=2))
    except BaseException as error:
        preserve_failure_and_cleanup(build, work, commands, error)
        raise


if __name__ == "__main__":
    main()
