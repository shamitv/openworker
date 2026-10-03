"""Phase 1 CLI: no network, credential loading, store or inference commands."""

from __future__ import annotations

import argparse
import json
import sys

from .validation import ValidationError, validate_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_subparsers(dest="action", required=True).add_parser("validate", help="validate installed assets offline")
    parser.parse_args(argv)
    try:
        report = validate_all()
    except (ValidationError, ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0
