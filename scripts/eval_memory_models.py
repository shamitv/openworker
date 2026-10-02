#!/usr/bin/env python3
"""Compare model memory saves and fresh-chat recall through OpenRouter or a local endpoint.

Every model/run/scenario gets an empty, temporary SQLite store. Each scenario consists
of one save chat and one genuinely fresh recall chat that receives only the persisted
memory block (never the first chat transcript). The harness uses OpenWorker's existing
memory tools, guidance, and provider router; it does not change memory policy.

Example:
    python scripts/eval_memory_models.py
    python scripts/eval_memory_models.py --models openai/gpt-6-luna --runs 1
    python scripts/eval_memory_models.py --base-url http://localhost:8090/v1 \
        --models Ornith-1.5-35B-Uncensored-Q6_K --runs 1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODELS = [
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-sol",
    "openai/gpt-6-luna",
    "openai/gpt-6-sol",
    "openai/gpt-6.1-sol",
]
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MAX_TOOL_ROUNDS = 6
MAX_COMPLETION_TOKENS = 768
MANGLED_PREVIEW_CHARS = 200


@dataclass(frozen=True)
class Scenario:
    name: str
    category: str
    save_prompt: str
    recall_prompt: str
    target_in_memory: Callable[[str], bool]
    target_in_answer: Callable[[str], bool]


@dataclass
class UsageTotals:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        for name in ("input", "output", "cache_read", "cache_write"):
            setattr(self, name, getattr(self, name) + int(getattr(usage, name, 0) or 0))


@dataclass
class RunMetrics:
    model: str
    run: int
    scenario: str
    category: str
    stored_target: bool = False
    fresh_chat_recall: bool = False
    unnecessary_saves: int = 0
    explicit_request_save: bool = False
    permission_requests: int = 0
    memory_tool_calls: dict[str, int] = field(default_factory=dict)
    fresh_chat_received_memories: int = 0
    prior_chat_messages_injected: int = 0
    errors: list[str] = field(default_factory=list)
    usage: UsageTotals = field(default_factory=UsageTotals)
    latency_seconds: float = 0.0
    cost_usd_estimate: float | None = None


SCENARIOS = [
    Scenario(
        name="grade8_cbse",
        category="automatic",
        save_prompt=(
            "I will be asking for study help throughout this school year. I am a student "
            "in Grade 8 following the CBSE curriculum. Can you suggest a good sequence "
            "for studying physics?"
        ),
        recall_prompt="Which grade and school curriculum did I tell you I follow?",
        target_in_memory=lambda text: "grade 8" in text.lower() and "cbse" in text.lower(),
        target_in_answer=lambda text: "grade 8" in text.lower() and "cbse" in text.lower(),
    ),
    Scenario(
        name="lasting_preference",
        category="automatic",
        save_prompt=(
            "From now on, across our chats, please keep explanations concise and direct. "
            "For this question, briefly explain why the sky looks blue."
        ),
        recall_prompt="What response style do I prefer?",
        target_in_memory=lambda text: (
            "concise" in text.lower() and "direct" in text.lower()
        ),
        target_in_answer=lambda text: any(
            word in text.lower() for word in ("concise", "brief", "short")
        )
        and any(word in text.lower() for word in ("direct", "to the point", "clear")),
    ),
    Scenario(
        name="temporary_detail",
        category="temporary",
        save_prompt=(
            "For dinner tonight only, I ordered mushroom pizza. Do you think a green "
            "salad would go well with it?"
        ),
        recall_prompt="What did I say I ordered for dinner?",
        target_in_memory=lambda text: "mushroom pizza" in text.lower(),
        target_in_answer=lambda text: "mushroom pizza" in text.lower(),
    ),
    Scenario(
        name="explicit_remember",
        category="explicit",
        save_prompt=(
            "Please remember for future chats: this synthetic test project is called "
            "Redwood. What is a useful way to organize its notes?"
        ),
        recall_prompt="What did I ask you to remember about this test project?",
        target_in_memory=lambda text: "redwood" in text.lower(),
        target_in_answer=lambda text: "redwood" in text.lower(),
    ),
]


def _load_dotenv_key(path: Path) -> str | None:
    """Read only OPENROUTER_API_KEY; never echo or persist the value."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        name, separator, value = stripped.partition("=")
        if not separator or name.strip() != "OPENROUTER_API_KEY":
            continue
        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = re.search(rf"(?<!\\){re.escape(quote)}", value[1:])
            if end:
                value = value[1 : end.start() + 1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        return value or None
    return None


def resolve_api_key(env: dict[str, str] | None = None, env_file: Path | None = None) -> str | None:
    values = os.environ if env is None else env
    key = values.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    return _load_dotenv_key(env_file or Path(__file__).resolve().parents[1] / ".env")


def _parse_models(raw_models: list[str], *, local_endpoint: bool = False) -> list[str]:
    models: list[str] = []
    for raw in raw_models:
        models.extend(part.strip() for part in raw.split(",") if part.strip())
    if not models:
        raise ValueError("provide at least one model")
    model_pattern = r"[^\s,]+" if local_endpoint else r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.:/-]+"
    invalid = [model for model in models if not re.fullmatch(model_pattern, model)]
    if invalid:
        expected = "non-empty local model IDs" if local_endpoint else "OpenRouter's provider/model format"
        raise ValueError(f"model IDs must use {expected}")
    return list(dict.fromkeys(models))


def _sanitize_error(message: object, secret: str) -> str:
    safe = str(message or "unknown error")
    if secret:
        safe = safe.replace(secret, "[redacted]")
    safe = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [redacted]", safe)
    safe = re.sub(r"sk-or-v1-[A-Za-z0-9]+", "[redacted]", safe)
    safe = re.sub(r"sk-or-[A-Za-z0-9_-]+", "[redacted]", safe)
    return safe[:1200]


def _load_prices(api_key: str, models: list[str]) -> dict[str, dict[str, Decimal]]:
    """Fetch the listed token rates once; completion traffic still uses ProviderRouter."""
    import httpx

    response = httpx.get(
        f"{OPENROUTER_BASE}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    catalog = response.json().get("data", [])
    requested = set(models)
    prices: dict[str, dict[str, Decimal]] = {}
    for entry in catalog:
        if entry.get("id") not in requested:
            continue
        raw = entry.get("pricing") or {}
        parsed: dict[str, Decimal] = {}
        for key, value in raw.items():
            try:
                parsed[key] = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                continue
        prices[str(entry["id"])] = parsed
    return prices


def _estimate_cost(usage: UsageTotals, prices: dict[str, Decimal]) -> float | None:
    if "prompt" not in prices or "completion" not in prices:
        return None
    # OpenWorker separates uncached prompt tokens from cache reads/writes. When an
    # endpoint does not publish cache-specific rates, estimate those at prompt rate.
    cache_read_price = prices.get("input_cache_read", prices["prompt"])
    cache_write_price = prices.get("input_cache_write", prices["prompt"])
    total = (
        Decimal(usage.input) * prices["prompt"]
        + Decimal(usage.output) * prices["completion"]
        + Decimal(usage.cache_read) * cache_read_price
        + Decimal(usage.cache_write) * cache_write_price
    )
    return float(total)


def _system_prompt(memory_items: list[Any]) -> str:
    from coworker.agent import _MEMORY_GUIDANCE
    from coworker.memory import render_memory_block

    base = (
        "You are a helpful assistant. Answer the user's request directly. "
        "Use the provided memory tools when the memory guidance calls for them."
    )
    parts = [base, _MEMORY_GUIDANCE]
    memory_block = render_memory_block(memory_items)
    if memory_block:
        parts.append(memory_block)
    return "\n\n".join(parts)


def _record_usage(metrics: RunMetrics, turn: Any) -> None:
    metrics.usage.add(getattr(turn, "usage", None))


def _run_conversation(
    *,
    provider: Any,
    provider_model: str,
    messages: list[dict[str, Any]],
    registry: Any,
    metrics: RunMetrics,
    secret: str,
) -> str:
    """Run one isolated tool loop; failures are captured and are never retried here."""
    started = time.perf_counter()
    latest_text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            turn = provider.complete(
                model=provider_model,
                messages=messages,
                tools=registry.schemas(),
                reasoning_effort="low",
                max_tokens=MAX_COMPLETION_TOKENS,
                temperature=0,
            )
        except Exception as exc:  # provider errors are an evaluation result
            metrics.errors.append(_sanitize_error(exc, secret))
            break
        _record_usage(metrics, turn)
        latest_text = str(getattr(turn, "text", None) or "")
        calls = list(getattr(turn, "tool_calls", None) or [])
        if not calls:
            break

        assistant_calls = []
        for call in calls:
            if set(call.arguments or {}) == {"_raw"}:
                raw = str(call.arguments.get("_raw") or "")
                if len(raw) > MANGLED_PREVIEW_CHARS:
                    call.arguments = {
                        "_raw": raw[:MANGLED_PREVIEW_CHARS]
                        + f"… [unparsed tool-call text, {len(raw)} chars, truncated in history]"
                    }
            args_text = json.dumps(call.arguments or {}, ensure_ascii=False, separators=(",", ":"))
            assistant_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": args_text},
                }
            )
        messages.append(
            {"role": "assistant", "content": latest_text or None, "tool_calls": assistant_calls}
        )
        for call in calls:
            metrics.memory_tool_calls[call.name] = metrics.memory_tool_calls.get(call.name, 0) + 1
            if call.name == "ask_user":
                metrics.permission_requests += 1
            if set(call.arguments or {}) == {"_raw"}:
                if getattr(turn, "finish_reason", None) == "length":
                    reason = (
                        "tool-call arguments were cut off by the output-token limit; "
                        "reissue the content in smaller pieces"
                    )
                else:
                    reason = (
                        "tool-call arguments did not parse as a JSON object; _raw is not "
                        "a parameter, so reissue the call using declared parameters"
                    )
                result = {"error": "tool call not executed", "reason": reason}
                metrics.errors.append(f"tool {call.name}: malformed JSON arguments")
            else:
                try:
                    result = registry.execute(call.name, call.arguments)
                except Exception as exc:
                    result = {"error": _sanitize_error(exc, secret)}
                    metrics.errors.append(f"tool {call.name}: {_sanitize_error(exc, secret)}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    else:
        metrics.errors.append(f"tool loop exceeded {MAX_TOOL_ROUNDS} completion rounds")
    metrics.latency_seconds += time.perf_counter() - started
    return latest_text


def _run_case(
    provider: Any,
    model: str,
    run: int,
    scenario: Scenario,
    prices: dict[str, Decimal],
    secret: str,
    *,
    provider_model: str,
) -> RunMetrics:
    from coworker.memory import Scope, memory_tools
    from coworker.memory.sqlite_store import SQLiteMemoryStore
    from coworker.tools import ToolRegistry
    from coworker.tools.ask import ask_user_tool

    metrics = RunMetrics(model=model, run=run, scenario=scenario.name, category=scenario.category)
    with tempfile.TemporaryDirectory(prefix="openworker-memory-eval-") as tmp:
        store = SQLiteMemoryStore(Path(tmp) / "memory.sqlite3")
        # Give workspace-scoped facts the same visibility they have in an actual
        # workspace-bound OpenWorker session. Every case still owns a unique path/store.
        workspace = str(Path(tmp) / "synthetic-workspace")
        try:
            first_registry = ToolRegistry()
            first_registry.register_all(memory_tools(store, workspace=workspace))
            first_registry.register(ask_user_tool())
            save_messages = [
                {"role": "system", "content": _system_prompt([])},
                {"role": "user", "content": scenario.save_prompt},
            ]
            _run_conversation(
                provider=provider,
                provider_model=provider_model,
                messages=save_messages,
                registry=first_registry,
                metrics=metrics,
                secret=secret,
            )

            saved = store.list(scope=Scope.GLOBAL) + store.list(
                scope=Scope.WORKSPACE, workspace=workspace
            )
            saved_text = "\n".join(item.content for item in saved)
            metrics.stored_target = scenario.target_in_memory(saved_text)
            if scenario.category == "temporary":
                metrics.unnecessary_saves = len(saved)
            if scenario.category == "explicit":
                metrics.explicit_request_save = metrics.stored_target

            # New registry and only system + new user message: there is no transcript
            # carry-over. The system's memory block is re-rendered from this store.
            fresh_registry = ToolRegistry()
            fresh_registry.register_all(memory_tools(store, workspace=workspace))
            fresh_registry.register(ask_user_tool())
            fresh_prompt = _system_prompt(saved)
            metrics.fresh_chat_received_memories = len(saved)
            recall_messages = [
                {"role": "system", "content": fresh_prompt},
                {"role": "user", "content": scenario.recall_prompt},
            ]
            metrics.prior_chat_messages_injected = 0
            answer = _run_conversation(
                provider=provider,
                provider_model=provider_model,
                messages=recall_messages,
                registry=fresh_registry,
                metrics=metrics,
                secret=secret,
            )
            metrics.fresh_chat_recall = scenario.target_in_answer(answer)
            metrics.cost_usd_estimate = _estimate_cost(metrics.usage, prices)
            return metrics
        finally:
            store.close()


def _summarize(
    results: list[RunMetrics],
    models: list[str],
    runs: int,
    *,
    cost_note: str,
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for model in models:
        selected = [item for item in results if item.model == model]
        by_scenario: dict[str, dict[str, Any]] = {}
        for scenario in SCENARIOS:
            cases = [item for item in selected if item.scenario == scenario.name]
            by_scenario[scenario.name] = {
                "target_saved": sum(item.stored_target for item in cases),
                "fresh_chat_recalled": sum(item.fresh_chat_recall for item in cases),
                "runs": len(cases),
                "unnecessary_saves": sum(item.unnecessary_saves for item in cases),
                "permission_requests": sum(item.permission_requests for item in cases),
            }
        usage = UsageTotals()
        for item in selected:
            usage.input += item.usage.input
            usage.output += item.usage.output
            usage.cache_read += item.usage.cache_read
            usage.cache_write += item.usage.cache_write
        costs = [item.cost_usd_estimate for item in selected if item.cost_usd_estimate is not None]
        summaries.append(
            {
                "model": model,
                "runs_per_scenario": runs,
                "scenarios": by_scenario,
                "automatic_target_saves": sum(
                    item.stored_target for item in selected if item.category == "automatic"
                ),
                "automatic_fresh_chat_recalls": sum(
                    item.fresh_chat_recall for item in selected if item.category == "automatic"
                ),
                "permission_requests": sum(item.permission_requests for item in selected),
                "unnecessary_saves": sum(item.unnecessary_saves for item in selected),
                "errors": sum(len(item.errors) for item in selected),
                "input_tokens": usage.input,
                "output_tokens": usage.output,
                "cache_read_tokens": usage.cache_read,
                "cache_write_tokens": usage.cache_write,
                "estimated_cost_usd": round(sum(costs), 8) if costs else None,
                "average_latency_seconds_per_scenario": round(
                    sum(item.latency_seconds for item in selected) / len(selected), 3
                )
                if selected
                else 0,
            }
        )
    return {
        "models": summaries,
        "runs_per_scenario": runs,
        "scenario_count": len(SCENARIOS),
        "total_scenario_runs": len(results),
        "cost_note": cost_note,
        "results": [asdict(item) for item in results],
    }


def _print_summary(report: dict[str, Any]) -> None:
    print("OpenWorker memory model comparison")
    print(f"Runs per scenario: {report['runs_per_scenario']}  |  Scenarios: {report['scenario_count']}")
    print()
    header = (
        f"{'Model':<31} {'Auto save':>10} {'Fresh recall':>13} "
        f"{'Explicit':>9} {'Noise':>7} {'Ask user':>9} {'Errors':>7} "
        f"{'Tokens in/out':>15} {'Cost est.':>12} {'Avg sec':>8}"
    )
    print(header)
    print("-" * len(header))
    for item in report["models"]:
        explicit = item["scenarios"]["explicit_remember"]
        auto_total = 2 * report["runs_per_scenario"]
        cost = "n/a" if item["estimated_cost_usd"] is None else f"${item['estimated_cost_usd']:.6f}"
        print(
            f"{item['model']:<31} "
            f"{item['automatic_target_saves']:>4}/{auto_total:<5} "
            f"{item['automatic_fresh_chat_recalls']:>5}/{auto_total:<7} "
            f"{explicit['target_saved']:>3}/{explicit['runs']:<5} "
            f"{item['unnecessary_saves']:>7} "
            f"{item['permission_requests']:>9} "
            f"{item['errors']:>7} "
            f"{item['input_tokens']:>7}/{item['output_tokens']:<7} "
            f"{cost:>12} "
            f"{item['average_latency_seconds_per_scenario']:>8.2f}"
        )
    print("\nPer-scenario saves and fresh-chat recalls:")
    for item in report["models"]:
        print(f"  {item['model']}")
        for name, values in item["scenarios"].items():
            print(
                f"    {name}: saved {values['target_saved']}/{values['runs']}, "
                f"recalled {values['fresh_chat_recalled']}/{values['runs']}, "
                f"unnecessary saves {values['unnecessary_saves']}, "
                f"permission requests {values['permission_requests']}"
            )
    errors = [
        (item["model"], item["run"], item["scenario"], error)
        for item in report["results"]
        for error in item["errors"]
    ]
    if errors:
        print("\nErrors (no benchmark-level retry was made):")
        for model, run, scenario, error in errors:
            print(f"  {model} run {run} / {scenario}: {error}")


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        metavar="MODEL",
        help="model IDs (space-separated or comma-separated; defaults to the five verified OpenRouter models; required with --base-url)",
    )
    parser.add_argument("--runs", type=_positive_int, default=3, help="isolated repetitions per scenario (default: 3)")
    parser.add_argument("--output", type=Path, help="also write the full, credential-free report as JSON")
    parser.add_argument(
        "--base-url",
        help="use an OpenAI-compatible endpoint directly (for example http://localhost:8090/v1); skips OpenRouter auth/pricing",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env",
        help="key file to read when OPENROUTER_API_KEY is not set (default: repository .env)",
    )
    args = parser.parse_args(argv)

    raw_models = args.models or ([] if args.base_url else DEFAULT_MODELS)
    if args.base_url and not args.models:
        parser.error("--models is required when --base-url is used")
    try:
        models = _parse_models(raw_models, local_endpoint=bool(args.base_url))
    except ValueError as exc:
        parser.error(str(exc))

    if args.base_url:
        from coworker.providers import OpenAIProvider

        # OpenAI's SDK requires an API key argument even for unauthenticated local
        # servers; this placeholder is local-only and is never sent to OpenRouter.
        api_key = "openworker-local-endpoint"
        prices: dict[str, dict[str, Decimal]] = {model: {} for model in models}
        provider = OpenAIProvider(api_key=api_key, base_url=args.base_url.rstrip("/"))
        provider_models = {model: model for model in models}
        secret_for_errors = api_key
        cost_note = "Local endpoint pricing is unavailable; cost is reported as n/a."
    else:
        api_key = resolve_api_key(env_file=args.env_file)
        if not api_key:
            print(
                f"Error: OPENROUTER_API_KEY is not set and was not found in {args.env_file}.",
                file=sys.stderr,
            )
            return 2
        # ProviderRouter resolves provider credentials from environment; keep the .env value
        # in this process only and never write it to a config, database, or output report.
        os.environ["OPENROUTER_API_KEY"] = api_key
        try:
            prices = _load_prices(api_key, models)
        except Exception as exc:
            safe_error = _sanitize_error(exc, api_key)
            print(f"Error: unable to load OpenRouter model pricing: {safe_error}", file=sys.stderr)
            return 2
        missing = [model for model in models if model not in prices]
        if missing:
            print(
                "Error: these model IDs were not present in the current OpenRouter catalog: "
                + ", ".join(missing),
                file=sys.stderr,
            )
            return 2

        from coworker.providers import ProviderRouter
        from coworker.secrets import EphemeralSecretStore

        # Do not let a previously configured GUI profile override the key read from this
        # process's environment/.env file, and never touch the user's persistent secrets.
        provider = ProviderRouter(EphemeralSecretStore())
        provider_models = {model: f"openrouter:{model}" for model in models}
        secret_for_errors = api_key
        cost_note = (
            "Estimated from OpenRouter's current model catalog token rates; provider routing, "
            "credits, and cache discounts can make the billed amount differ."
        )
    results: list[RunMetrics] = []
    total_runs = len(models) * len(SCENARIOS) * args.runs
    completed = 0
    for model in models:
        model_prices = prices.get(model, {})
        for run in range(1, args.runs + 1):
            for scenario in SCENARIOS:
                completed += 1
                print(f"[{completed}/{total_runs}] {model} run {run}: {scenario.name}", flush=True)
                try:
                    metrics = _run_case(
                        provider,
                        model,
                        run,
                        scenario,
                        model_prices,
                        secret_for_errors,
                        provider_model=provider_models[model],
                    )
                except Exception as exc:
                    metrics = RunMetrics(model=model, run=run, scenario=scenario.name, category=scenario.category)
                    metrics.errors.append(_sanitize_error(exc, secret_for_errors))
                results.append(metrics)

    report = _summarize(results, models, args.runs, cost_note=cost_note)
    _print_summary(report)
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Error: could not write JSON report: {_sanitize_error(exc, api_key)}", file=sys.stderr)
            return 2
        print(f"\nJSON report written to {args.output}")
    return 1 if any(item.errors for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
