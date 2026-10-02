"""Exercise the local model fixture through the real provider SDK, without a sandbox."""
import pytest

from coworker.providers.openai_provider import OpenAIProvider
from test_hosted_web import _serve
from hosted_acceptance import ORIGIN, WS_ORIGIN, model_app


def test_acceptance_websocket_sends_secure_cookie_to_gateway_origin():
    from fastapi import FastAPI, Response, WebSocket
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/login")
    def login(response: Response):
        response.set_cookie("__Host-test-session", "test-only-cookie", secure=True, httponly=True, path="/")
        return {"ok": True}

    @app.websocket("/ws/session/probe")
    async def websocket(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({"cookie": websocket.cookies.get("__Host-test-session")})

    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/login")
        with client.websocket_connect(f"{WS_ORIGIN}/ws/session/probe") as websocket:
            assert websocket.receive_json() == {"cookie": "test-only-cookie"}


@pytest.mark.parametrize("stream", [False, True])
def test_local_acceptance_model_requests_one_write_then_finishes(stream):
    port, server, thread = _serve(model_app())
    try:
        provider = OpenAIProvider(api_key="local-test", base_url=f"http://127.0.0.1:{port}/v1")
        messages = [{"role": "user", "content": "Write marker.txt"}]
        tools = [{"type": "function", "function": {"name": "write_file", "description": "Write a file",
                   "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                                  "required": ["path", "content"]}}}]
        def complete():
            if not stream:
                return provider.complete(model="phase2", messages=messages, tools=tools)
            chunks = list(provider.stream(model="phase2", messages=messages, tools=tools))
            return next(chunk.turn for chunk in reversed(chunks) if chunk.turn is not None)
        turn = complete()
        assert len(turn.tool_calls) == 1 and turn.tool_calls[0].name == "write_file"
        assert turn.tool_calls[0].arguments == {"path": "marker.txt", "content": "scheduled work ran"}
        messages.extend([{"role": "assistant", "content": None, "tool_calls": [{"id": "phase2-write", "type": "function",
                         "function": {"name": "write_file", "arguments": '{"path":"marker.txt","content":"scheduled work ran"}'}}]},
                         {"role": "tool", "tool_call_id": "phase2-write", "content": "written"}])
        turn = complete()
        assert not turn.tool_calls and turn.text == "Done"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
