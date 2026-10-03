"""One bounded response lifecycle for both interfaces."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import time

from .adapters import adapter_for
from .client import ClientError
from .contract import ContractError, contract


async def run_turn(client, model: str, interface: str, messages: list[dict], dispatcher, *,
                   clock=time.monotonic, record=None) -> dict:
    adapter = adapter_for(interface)
    limits = contract()["lifecycle"]
    started = clock()
    deadline = started + limits["whole_turn_seconds"]
    transcript = deepcopy(messages)
    batches, requests, provisional, errors = 0, 0, [], []
    status, answer = "complete", None
    record = record or (lambda event: None)
    event_offset = len(dispatcher.events)
    try:
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                raise ClientError("deadline", "whole-turn deadline expired")
            requests += 1
            response = await client.completion(model, transcript, parameters=adapter.parameters, timeout=remaining)
            if clock() >= deadline:
                raise ClientError("deadline", "response arrived after whole-turn deadline")
            batch = adapter.parse(response)
            transcript.append(batch["assistant"])
            if not batch["operations"]:
                if not batch["answer"].strip():
                    raise ContractError("format_error", "final answer must be nonempty")
                answer = batch["answer"]
                break
            provisional.append(batch["answer"])
            if batches >= limits["max_operation_batches"]:
                raise ClientError("round_exhaustion", "seventh operation batch was not executed")
            batches += 1
            results = []
            for operation in batch["operations"]:
                if clock() >= deadline:
                    raise ClientError("deadline", "deadline before operation")
                dispatcher.store.set_deadline(deadline, clock)
                try:
                    results.append(dispatcher.dispatch(operation))
                finally:
                    dispatcher.store.set_deadline(None)
                    if len(dispatcher.events) > event_offset:
                        record({"type": "operation", "event": dispatcher.events[-1]})
                if clock() >= deadline:
                    raise ClientError("deadline", "deadline during operation")
            transcript.extend(adapter.feedback(batch, results))
    except (ClientError, ContractError) as exc:
        status = exc.code
        errors.append({"code": exc.code, "message": str(exc)})
    except asyncio.CancelledError:
        status = "interrupted"
        errors.append({"code": status, "message": "collection interrupted"})
    except Exception as exc:
        status = "deadline" if clock() >= deadline else "infrastructure_error"
        errors.append({"code": status, "type": type(exc).__name__, "message": str(exc)})
    return {"answer": answer, "status": status, "operations": dispatcher.events[event_offset:],
            "errors": errors, "requests": requests, "operation_batches": batches,
            "provisional_answers": provisional, "duration_seconds": clock() - started,
            "messages": transcript}
