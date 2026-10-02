"""Controller unit coverage with native launch mocked; live checks are separate."""
import json
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows controller")


@pytest.fixture
def providers(tmp_path, monkeypatch):
    from coworker.sandbox import winsec
    from coworker.sandbox.providers import windows, windows_setup

    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross")
    monkeypatch.setenv("COWORKER_API_TOKEN", "engine-secret")
    monkeypatch.setattr(windows, "preflight", lambda: None)
    monkeypatch.setattr(windows_setup, "account", lambda kind: ("account", "S-1-5-21-1-2-3-1000", "unused"))
    monkeypatch.setattr(windows_setup, "SANDBOXES", tmp_path / "boxes")
    monkeypatch.setattr(windows_setup, "reap_private_folders", lambda: [])
    monkeypatch.setattr(winsec, "protect_directory", lambda path: None)
    monkeypatch.setattr(winsec, "protect_owner_rights", lambda path: None)
    acl = {}
    for kind in ("write", "read", "traverse"):
        monkeypatch.setattr(winsec, "grant_" + kind, lambda path, sid, kind=kind: acl.__setitem__((path, sid), kind))
    monkeypatch.setattr(winsec, "revoke", lambda path, sid: acl.pop((path, sid), None))

    class Desktop:
        name = "private-desktop"
        def __init__(self, sid):
            pass
        def close(self):
            pass

    class Process:
        returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = 0
        def wait(self, timeout=None):
            return self.returncode
        def close(self):
            pass

    launched = []
    def launch(argv, **kwargs):
        assert "restricted-serve" in argv
        assert kwargs["environment"].get("OPENAI_API_KEY") is None
        assert kwargs["environment"].get("COWORKER_API_TOKEN") is None
        kwargs["before_resume"](f"S-1-5-5-0-{100 + len(launched)}")
        assert kwargs.get("stderr_path") is None
        config = json.loads(__import__("pathlib").Path(argv[argv.index("--config") + 1]).read_text())
        launched.append(config)
        return Process()

    monkeypatch.setattr(winsec, "Desktop", Desktop)
    monkeypatch.setattr(winsec, "spawn_as_account", launch)
    monkeypatch.setattr(windows, "wait_for_runner", lambda *args: None)
    bundle = tmp_path / "runner.pyz"
    bundle.write_bytes(b"trusted-bundle")
    made = []
    def make(name):
        project = tmp_path / name
        project.mkdir()
        provider = windows.WindowsProvider(roots=[{"path": str(project), "writable": True}], cwd=project, network=False, runner_path=bundle)
        made.append(provider)
        return provider
    yield make, acl, launched
    for provider in made:
        provider.destroy()


def test_concurrent_grants_and_private_profiles_do_not_accumulate(providers):
    make, acl, launched = providers
    alice, bob = make("alice"), make("bob")
    alice.create()
    bob.create()
    assert alice.session_sid != bob.session_sid
    assert launched[0]["env"]["USERPROFILE"] != launched[1]["env"]["USERPROFILE"]
    for provider, config in zip((alice, bob), launched):
        assert config["sid"] == provider.session_sid
        assert config["argv"].count(provider.session_sid) == 1
        assert "S-1-5-21-1-2-3-1000" not in config["argv"]
    alice.destroy()
    assert not any(sid == alice.session_sid for _, sid in acl)
    assert any(sid == bob.session_sid for _, sid in acl)
    assert os.path.isdir(bob._dir)


def test_restart_uses_new_logon_grants_and_no_shared_profile(providers):
    make, acl, launched = providers
    provider = make("alice")
    provider.create()
    old = provider.session_sid
    provider.restart_daemon()
    assert provider.session_sid != old
    assert not any(sid == old for _, sid in acl)
    assert launched[-1]["env"]["HOME"].startswith(provider._dir)


def test_wrong_runner_home_refuses_credential_provisioning(providers):
    from coworker.sandbox.providers.windows import WindowsUnavailable

    make, _, _ = providers
    provider = make("alice")
    client = type("Client", (), {"hello": {"home": "C:/Users/shared-account"}})()
    with pytest.raises(WindowsUnavailable, match="private home"):
        provider.provision(client)


def test_regrant_revalidates_paths_before_native_acl_changes(providers, monkeypatch, tmp_path):
    from coworker.basedir import OutsideBaseDir

    make, acl, _ = providers
    provider = make("alice")
    provider.create()
    monkeypatch.setenv("OPENWORKER_BASE_DIR", str(tmp_path / "alice"))
    before = dict(acl)
    with pytest.raises(OutsideBaseDir):
        provider.regrant([{"path": str(tmp_path / "bob"), "writable": True}])
    assert acl == before


def test_private_directory_failure_closes_lease_and_removes_runtime(providers, monkeypatch, tmp_path):
    from coworker.sandbox import winsec

    def blocked(path):
        raise OSError("ACL denied")
    monkeypatch.setattr(winsec, "protect_directory", blocked)
    with pytest.raises(OSError, match="ACL denied"):
        providers[0]("alice")
    assert list((tmp_path / "boxes").iterdir()) == []
