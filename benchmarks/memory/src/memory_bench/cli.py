"""Standalone validation, collection, replay and reporting CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from .validation import ValidationError, validate_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("validate", help="validate installed assets offline")
    for action in ("smoke", "run"):
        command = actions.add_parser(action, help="collect explicit local-model evidence")
        command.add_argument("--base-url", required=True)
        command.add_argument("--models", nargs="+", required=True)
        command.add_argument("--output", type=Path, required=True)
        if action == "run":
            command.add_argument("--dataset", choices=("development", "heldout"), required=True)
            command.add_argument("--policies", nargs="+", choices=("conservative", "recurring"), required=True)
            command.add_argument("--prompts", nargs="+", choices=("baseline", "rules", "examples"), required=True)
            command.add_argument("--interfaces", nargs="+", choices=("json", "native"), required=True)
            command.add_argument("--tracks", nargs="+", choices=("write", "read", "sequence"), required=True)
            command.add_argument("--runs", type=int, default=1)
    for action in ("replay", "report"):
        command = actions.add_parser(action, help="process captured evidence without inference")
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "smoke" and len(args.models) != 1:
        parser.error("smoke requires exactly one model")
    try:
        if args.action == "validate":
            result = validate_all()
        elif args.action in ("replay", "report"):
            from .reporting import replay, write_report
            result = replay(args.input, args.output) if args.action == "replay" else write_report(args.input, args.output)
            result = {"status": "complete", "collection_status": result["status"], "output": str(args.output.resolve()),
                      "scoring_sha256": result["scoring"]["sha256"], "inference_requests": 0}
        else:
            from .execution import collect
            from .experiments import schedule
            from .reporting import write_report
            smoke = args.action == "smoke"
            requested = {"dataset": "development" if smoke else args.dataset, "models": args.models,
                "policies": ["conservative", "recurring"] if smoke else args.policies,
                "prompts": ["baseline"] if smoke else args.prompts,
                "interfaces": ["json", "native"] if smoke else args.interfaces,
                "tracks": ["write", "read", "sequence"] if smoke else args.tracks,
                "runs": 1 if smoke else args.runs}
            planned = schedule(**requested, smoke=smoke)
            def progress(value):
                c = value["condition"]
                print(f"{c['model']} {c['policy']} {c['prompt']} {c['interface']} {value['track']} "
                      f"{c['persona_id']}/{value['conversation_id']}: {value['status']}", file=sys.stderr, flush=True)
            manifest = asyncio.run(collect(base_url=args.base_url, models=args.models, output=args.output,
                                           schedule=planned, requested=requested, smoke=smoke, progress=progress))
            report = write_report(args.output)
            result = {"status": manifest["status"], "gate_passed": report["gate_passed"],
                      "coverage": report["coverage"], "requests": report["requests"], "output": str(args.output.resolve())}
    except (ValidationError, ValueError, KeyError, TypeError, OSError) as exc:
        print(f"{args.action.capitalize()} failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if args.action not in ("smoke", "run") or result["status"] == "complete" and result["gate_passed"] else 1
