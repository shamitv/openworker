"""Hosted product controls must never launch native UI on the server."""
import pytest
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app


@pytest.mark.parametrize("route,method", [
    ("/v1/skills/example/reveal", "reveal_skill"),
    ("/v1/mcp/config/reveal", "reveal_mcp_config"),
    ("/v1/workspaces/pick", "pick_native_folder"),
    ("/v1/sessions/example/artifacts/reveal", "reveal_artifact"),
])
def test_hosted_native_controls_refuse_before_calling_manager(tmp_path, monkeypatch, route, method):
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")

    def forbidden(*args, **kwargs):
        pytest.fail("hosted request attempted to launch native UI")

    monkeypatch.setattr(manager, method, forbidden)
    response = TestClient(create_app(manager)).post(route, json={})
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]


@pytest.mark.parametrize("route,method", [
    ("/v1/skills/example/reveal", "reveal_skill"),
    ("/v1/mcp/config/reveal", "reveal_mcp_config"),
])
def test_desktop_reveal_controls_still_dispatch(tmp_path, monkeypatch, route, method):
    monkeypatch.delenv("OPENWORKER_HOSTED_WEB", raising=False)
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    calls = []

    def reveal(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr(manager, method, reveal)
    response = TestClient(create_app(manager)).post(route, json={})
    assert response.json() == {"ok": True}
    assert len(calls) == 1
