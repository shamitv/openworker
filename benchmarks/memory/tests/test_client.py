import asyncio
import json

import httpx
import pytest

from memory_bench.client import ClientError, LocalClient, SETTINGS, local_url


@pytest.mark.parametrize("url", ["https://openrouter.ai/api/v1", "http://8.8.8.8/v1", "http://example.com/v1",
    "http://user:secret@127.0.0.1/v1", "http://10.0.0.1/v1?key=secret", "http://10.0.0.1/v1#x",
    "http://127.0.0.1/openrouter/v1", "http://169.254.1.1/v1", "ftp://127.0.0.1/v1"])
def test_refuse_nonlocal_and_embedded_routes(url):
    with pytest.raises(ClientError):
        local_url(url)


@pytest.mark.parametrize("url", ["http://10.42.0.202:8090/v1", "http://127.0.0.1/v1/", "http://localhost:8000", "http://[::1]/v1", "http://[fd00::1]/v1"])
def test_accept_explicit_local_endpoints(url):
    assert local_url(url) == url.rstrip("/")


def test_exact_routing_settings_and_no_environment_credentials(monkeypatch):
    for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(key, "secret-that-must-not-be-used")
    calls = []
    def handler(request):
        calls.append(request)
        assert "authorization" not in request.headers
        assert "proxy-authorization" not in request.headers
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        body = json.loads(request.content)
        assert body["model"] == "exact"
        assert all(body[k] == v for k, v in SETTINGS.items())
        return httpx.Response(200, json={"model": "exact", "choices": []})
    async def scenario():
        async with LocalClient("http://127.0.0.1/v1", transport=httpx.MockTransport(handler)) as client:
            assert client._http._trust_env is False
            await client.verify_models(["exact"])
            await client.completion("exact", [], parameters={}, timeout=1)
            assert client.events[-1]["usage"] is None
            assert client.events[-1]["duration_seconds"] >= 0
    asyncio.run(scenario())
    assert [str(r.url) for r in calls] == ["http://127.0.0.1/v1/models", "http://127.0.0.1/v1/chat/completions"]


@pytest.mark.parametrize("model", ["missing", "local:exact", "openrouter/exact"])
def test_unadvertised_or_aliased_models_never_infer(model):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"id": "exact"}]})
    async def scenario():
        async with LocalClient("http://localhost/v1", transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ClientError):
                await client.verify_models([model])
    asyncio.run(scenario())
    assert all(r.method == "GET" for r in calls)


@pytest.mark.parametrize("failure,code", [("redirect", "routing_error"), ("unsupported", "unsupported_settings"),
    ("disconnect", "api_error"), ("bad_json", "api_error"), ("wrong_model", "routing_error")])
def test_failed_inference_is_recorded_without_retry_or_repair(failure, code):
    calls, journal = [], []
    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://openrouter.ai"}, json={})
        if failure == "unsupported":
            return httpx.Response(400, json={"error": "reasoning_effort unsupported"})
        if failure == "disconnect":
            raise httpx.ConnectError("connection lost")
        if failure == "bad_json":
            return httpx.Response(200, text="not JSON")
        return httpx.Response(200, json={"model": "fallback"})
    async def scenario():
        async with LocalClient("http://localhost/v1", transport=httpx.MockTransport(handler), record=journal.append) as client:
            await client.verify_models(["exact"])
            with pytest.raises(ClientError) as caught:
                await client.completion("exact", [], parameters={}, timeout=1)
            assert caught.value.code == code
            assert client.events[-1]["error"]["code"] == code
    asyncio.run(scenario())
    assert len(calls) == 2
    assert len([e for e in journal if e["type"] == "request_started"]) == 2


def test_timeout_is_a_single_attempt():
    calls = []
    async def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "exact"}]})
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})
    async def scenario():
        async with LocalClient("http://localhost/v1", transport=httpx.MockTransport(handler)) as client:
            await client.verify_models(["exact"])
            with pytest.raises(ClientError, match="remaining turn time"):
                await client.completion("exact", [], parameters={}, timeout=0.01)
            assert client.events[-1]["error"]["code"] == "deadline"
    asyncio.run(scenario())
    assert len(calls) == 2
