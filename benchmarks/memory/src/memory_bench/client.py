"""Direct, sequential local HTTP; no inherited credentials, retries or fallback."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import ipaddress
import time
from urllib.parse import urlsplit

import httpx

from .assets import strict_json

SETTINGS = {"temperature": 0, "reasoning_effort": "low", "max_tokens": 2048, "stream": False}
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))


class ClientError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def local_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ClientError("configuration_error", "invalid endpoint") from exc
    if (parts.scheme not in ("http", "https") or not parts.hostname or
            parts.username is not None or parts.password is not None or parts.query or parts.fragment):
        raise ClientError("configuration_error", "endpoint needs http(s), a local host and no credentials/query/fragment")
    host = parts.hostname.lower()
    if host != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ClientError("routing_error", "use a literal private/loopback IP or localhost") from exc
        if not (address.is_loopback or any(address in network for network in PRIVATE_NETWORKS)):
            raise ClientError("routing_error", "public and non-private endpoints are forbidden")
    if port is not None and not 1 <= port <= 65535:
        raise ClientError("configuration_error", "invalid endpoint port")
    path = parts.path.rstrip("/")
    # A direct OpenAI-compatible root, never an embedded provider/router path.
    if path not in ("", "/v1"):
        raise ClientError("routing_error", "endpoint path must be empty or /v1")
    return value.rstrip("/")


def validate_model_id(model: str) -> None:
    if (not isinstance(model, str) or not model.strip() or model != model.strip() or
            model.lower().startswith(("openrouter/", "openrouter:", "openai/", "openai:", "anthropic:", "provider:", "local:"))):
        raise ClientError("routing_error", "model must be an exact advertised ID, without a route alias")


class LocalClient:
    def __init__(self, base_url: str, *, transport=None, record=None):
        self.base_url = local_url(base_url)
        self.events: list[dict] = []
        self.catalog: dict | None = None
        self.models: set[str] = set()
        self._record = record or (lambda event: None)
        self._http = httpx.AsyncClient(
            trust_env=False, follow_redirects=False, auth=None,
            transport=transport if transport is not None else httpx.AsyncHTTPTransport(trust_env=False, retries=0),
            timeout=30, limits=httpx.Limits(max_connections=1, max_keepalive_connections=1))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._http.aclose()

    async def _request(self, kind: str, path: str, *, body=None, timeout=30) -> dict:
        event = {"index": len(self.events), "kind": kind, "url": self.base_url + path,
                 "model": body.get("model") if body else None, "request": deepcopy(body),
                 "started_at": time.time(), "duration_seconds": None, "status_code": None,
                 "response": None, "usage": None, "error": None}
        self.events.append(event)
        self._record({"type": "request_started", **deepcopy(event)})
        started = time.monotonic()
        try:
            if timeout <= 0:
                raise ClientError("deadline", "whole-turn deadline expired")
            request = (self._http.get(event["url"], timeout=timeout) if body is None else
                       self._http.post(event["url"], json=body, timeout=timeout))
            response = await asyncio.wait_for(request, timeout=timeout)
            event["status_code"] = response.status_code
            event["server"] = response.headers.get("server")
            event["request_id"] = response.headers.get("x-request-id")
            if 300 <= response.status_code < 400:
                event["response_text"] = response.text
                raise ClientError("routing_error", "redirect refused")
            try:
                data = strict_json(response.text)
            except ValueError as exc:
                event["response_text"] = response.text
                raise ClientError("api_error", "HTTP response is not JSON") from exc
            event["response"] = data
            if response.status_code >= 400:
                code = "unsupported_settings" if response.status_code in (400, 422) and any(
                    key in str(data).lower() for key in SETTINGS) else "api_error"
                raise ClientError(code, f"HTTP {response.status_code}: {data}")
            if not isinstance(data, dict):
                raise ClientError("api_error", "HTTP JSON envelope must be an object")
            event["usage"] = deepcopy(data.get("usage"))
            event["response_model"] = data.get("model")
            event["response_id"] = data.get("id")
            event["system_fingerprint"] = data.get("system_fingerprint")
            return data
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            event["error"] = {"code": "deadline", "message": str(exc) or "request exceeded remaining turn time"}
            raise ClientError("deadline", event["error"]["message"]) from exc
        except ClientError as exc:
            event["error"] = {"code": exc.code, "message": str(exc)}
            raise
        except httpx.HTTPError as exc:
            event["error"] = {"code": "api_error", "message": str(exc)}
            raise ClientError("api_error", str(exc)) from exc
        except BaseException as exc:
            event["error"] = {"code": "interrupted", "message": type(exc).__name__}
            raise
        finally:
            event["duration_seconds"] = time.monotonic() - started
            self._record({"type": "request_finished", **deepcopy(event)})

    async def verify_models(self, requested: list[str]) -> dict:
        if not requested or len(requested) != len(set(requested)):
            raise ClientError("configuration_error", "select unique model IDs")
        for model in requested:
            validate_model_id(model)
        self.catalog = await self._request("catalog", "/models")
        entries = self.catalog.get("data")
        if not isinstance(entries, list) or not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in entries):
            raise ClientError("catalog_error", "catalog needs data containing exact model IDs")
        self.models = {row["id"] for row in entries}
        missing = set(requested) - self.models
        if missing:
            raise ClientError("catalog_error", f"models not advertised: {sorted(missing)}")
        return deepcopy(self.catalog)

    async def completion(self, model: str, messages: list[dict], *, parameters: dict, timeout: float) -> dict:
        if model not in self.models:
            raise ClientError("catalog_error", "model was not verified before inference")
        if set(parameters) & ({"model", "messages"} | SETTINGS.keys()):
            raise ClientError("configuration_error", "adapter cannot replace model or fixed settings")
        body = {"model": model, "messages": deepcopy(messages), **SETTINGS, **deepcopy(parameters)}
        data = await self._request("inference", "/chat/completions", body=body, timeout=timeout)
        if data.get("model") is not None and data["model"] != model:
            error = ClientError("routing_error", "response model differs from exact requested model")
            self.events[-1]["error"] = {"code": error.code, "message": str(error)}
            self._record({"type": "request_rejected", **deepcopy(self.events[-1])})
            raise error
        return data
