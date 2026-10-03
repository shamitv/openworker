"""One ordered dispatcher for both future model interfaces."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass

from .contract import ContractError, contract, validate_operation, validate_result, validate_schema
from .store import MemoryStore


@dataclass(frozen=True)
class OperationContext:
    user_id: str
    workspace_id: str
    conversation_id: str

    def __post_init__(self):
        for value in asdict(self).values():
            if not isinstance(value, str) or not value.strip():
                raise ValueError("operation context IDs must be nonempty strings")


class OperationDispatcher:
    def __init__(self, store: MemoryStore, context: OperationContext | dict, permission_reply: dict | None = None):
        self.store = store
        self.context = context if isinstance(context, OperationContext) else OperationContext(**context)
        reply = permission_reply if permission_reply is not None else {
            "granted": False, "reply": contract()["defaults"]["permission_default_reply"]}
        validate_schema(reply, contract()["operations"]["request_permission"]["success"])
        self._permission_reply = deepcopy(reply)
        self._events: list[dict] = []

    @property
    def events(self) -> list[dict]:
        return deepcopy(self._events)

    def dispatch(self, operation: dict) -> dict:
        event = {"index": len(self._events), "context": asdict(self.context), "operation": deepcopy(operation)}
        try:
            validate_operation(operation)
            name, args = operation["name"], operation["arguments"]
            if name == "remember":
                data = {"record": self.store.remember(self.context.user_id, self.context.workspace_id, **args)}
            elif name == "memory_read":
                data = self.store.read(self.context.user_id, args["memory_ids"])
            elif name == "memory_update":
                data = {"record": self.store.update(self.context.user_id, **args)}
            elif name == "memory_forget":
                data = {"deleted_id": self.store.forget(self.context.user_id, **args)}
            else:
                event["proposal"] = {key: args[key] for key in ("key", "value", "scope")}
                data = deepcopy(self._permission_reply)
            result = {"ok": True, "data": data, "error": None}
        except ContractError as exc:
            result = {"ok": False, "data": None, "error": {"code": exc.code, "message": str(exc)}}
        except Exception as exc:
            event["result"] = None
            event["infrastructure_error"] = {"type": type(exc).__name__, "message": str(exc)}
            self._events.append(event)
            raise
        validate_result(operation.get("name", "") if isinstance(operation, dict) else "", result)
        event["result"] = deepcopy(result)
        self._events.append(event)
        return result

    def dispatch_batch(self, operations: list[dict]) -> list[dict]:
        return [self.dispatch(operation) for operation in operations]
