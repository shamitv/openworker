"""Acceptance checks for hosted accounts, migrations, sessions and administration."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import sqlite3
import threading

import pytest

from coworker.hosted import accounts, run
from coworker.hosted.accounts import AccountStore

PASSWORD = "initial secure password long enough"
NEW_PASSWORD = "replacement secure password long enough"


# Frozen schema from the pre-versioning hosted account implementation.
LEGACY_SCHEMA = """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    home TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    must_change INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    idle_expires_at REAL NOT NULL,
                    absolute_expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS login_failures (
                    kind TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    window_started_at REAL NOT NULL,
                    failures INTEGER NOT NULL,
                    PRIMARY KEY(kind, subject)
                );
                CREATE TABLE IF NOT EXISTS account_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at REAL NOT NULL,
                    event TEXT NOT NULL,
                    user_id TEXT,
                    username TEXT,
                    client_ip TEXT
                );
                """


@pytest.fixture
def clock(monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr(accounts.time, "time", lambda: now[0])
    return now


@pytest.fixture
def store(tmp_path):
    return AccountStore(tmp_path)


def login(store, name="alice", password=PASSWORD, ip="192.0.2.1"):
    result = store.authenticate(name, password, ip)
    assert result is not None
    return result[0]


def rows(store, table):
    with sqlite3.connect(store.db_path) as db:
        return db.execute(f"SELECT * FROM {table}").fetchall()


def test_fresh_and_repeated_initialization(store):
    with sqlite3.connect(store.db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    user = store.create("Alice", PASSWORD)
    token = login(store)
    reopened = AccountStore(store.data_dir)
    assert reopened.list_users() == [user]
    assert reopened.get_session(token)["id"] == user["id"]


@pytest.mark.parametrize("kind", ["fresh", "legacy", "versioned"])
@pytest.mark.parametrize("attempt", range(3))
def test_concurrent_initialization(tmp_path, kind, attempt):
    if kind == "legacy":
        with sqlite3.connect(tmp_path / "accounts.sqlite3") as db:
            db.executescript(LEGACY_SCHEMA)
    elif kind == "versioned":
        AccountStore(tmp_path)
    barrier = threading.Barrier(4)
    def initialize():
        barrier.wait(timeout=10)
        return AccountStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        stores = list(pool.map(lambda _: initialize(), range(4)))
    with sqlite3.connect(stores[0].db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


@pytest.mark.parametrize("kind", ["future", "partial", "wrong_constraint", "corrupt"])
def test_reject_invalid_database(tmp_path, kind):
    path = tmp_path / "accounts.sqlite3"
    if kind == "corrupt":
        path.write_bytes(b"not a SQLite database")
        with pytest.raises(sqlite3.DatabaseError):
            AccountStore(tmp_path)
        return
    with sqlite3.connect(path) as db:
        if kind == "future":
            db.execute("PRAGMA user_version=2")
        else:
            db.execute("CREATE TABLE users (id TEXT, username TEXT)")
            if kind == "wrong_constraint":
                db.execute("PRAGMA user_version=1")
    with pytest.raises(ValueError, match="newer|incompatible"):
        AccountStore(tmp_path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == (2 if kind == "future" else 1 if kind == "wrong_constraint" else 0)


def test_migration_failure_rolls_back(tmp_path, monkeypatch):
    original = accounts._MIGRATIONS[0]
    def fail(db):
        original(db)
        db.execute("INSERT INTO account_audit (occurred_at,event) VALUES (0,'partial')")
        raise RuntimeError("injected failure")
    monkeypatch.setattr(accounts, "_MIGRATIONS", (fail,))
    with pytest.raises(RuntimeError, match="injected"):
        AccountStore(tmp_path)
    with sqlite3.connect(tmp_path / "accounts.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    monkeypatch.setattr(accounts, "_MIGRATIONS", (original,))
    AccountStore(tmp_path)


@pytest.mark.parametrize("expiry", ["idle", "absolute"])
def test_session_expiry_exact_boundary(store, clock, expiry):
    store.create("alice", PASSWORD)
    token = login(store)
    created = clock[0]
    boundary = accounts._IDLE_SECONDS if expiry == "idle" else accounts._ABSOLUTE_SECONDS
    if expiry == "absolute":
        # Keep the idle deadline alive until the absolute deadline.
        for hours in range(6, 168, 6):
            clock[0] = created + hours * 3600
            assert store.get_session(token)
        assert rows(store, "sessions")[0][5] == created + accounts._ABSOLUTE_SECONDS
    clock[0] = created + boundary - 1
    assert store.get_session(token, touch=False)
    clock[0] += 1
    assert store.get_session(token) is None
    assert rows(store, "sessions") == []
    assert rows(store, "account_audit")[-1][2] == "session_expired"


def test_touch_and_token_storage(store, clock):
    user = store.create("alice", PASSWORD)
    token = login(store)
    with sqlite3.connect(store.db_path) as db:
        session = db.execute("SELECT * FROM sessions").fetchone()
    assert session[0] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(session)
    assert user["id"] == session[1]
    created = clock[0]
    clock[0] += 59
    assert store.get_session(token)
    assert rows(store, "sessions")[0][4] == created
    clock[0] += 1
    assert store.get_session(token, touch=False)
    assert rows(store, "sessions")[0][4] == created
    assert store.get_session(token)
    session = rows(store, "sessions")[0]
    assert session[4] == clock[0]
    assert session[5] == clock[0] + accounts._IDLE_SECONDS
    assert session[6] == created + accounts._ABSOLUTE_SECONDS
    assert store.get_session("") is None
    assert store.get_session("x" * 257) is None
    assert store.get_session("unknown") is None


@pytest.mark.parametrize("action", ["reset", "disable", "change", "logout"])
def test_revocation_scope(store, action):
    store.create("alice", PASSWORD)
    store.create("bob", PASSWORD)
    first, second, bob = login(store), login(store), login(store, "bob")
    if action == "reset":
        store.reset_password("alice", NEW_PASSWORD)
        token = login(store, password=NEW_PASSWORD)
        assert store.get_session(token)["must_change"]
        store.revoke(token)
    elif action == "disable":
        store.disable("alice")
        assert store.authenticate("alice", PASSWORD, "192.0.2.1") is None
    elif action == "change":
        assert store.change_password(first, PASSWORD, NEW_PASSWORD)
        assert not store.get_session(login(store, password=NEW_PASSWORD))["must_change"]
    else:
        store.revoke(first)
    assert store.get_session(first) is None
    assert bool(store.get_session(second)) == (action == "logout")
    assert store.get_session(bob)["username"] == "bob"


def test_account_throttle_and_recovery(store, clock):
    store.create("alice", PASSWORD)
    for i in range(5):
        assert store.authenticate(" Alice ", "incorrect password", f"192.0.2.{i+1}") is None
    assert store.authenticate("alice", PASSWORD, "192.0.2.99") is None
    assert rows(store, "account_audit")[-1][2] == "login_throttled"
    clock[0] += 899
    assert store.authenticate("alice", PASSWORD, "192.0.2.99") is None
    clock[0] += 1
    assert login(store)
    failures = rows(store, "login_failures")
    assert not any(row[0] == "username" or row[1] == "192.0.2.1" for row in failures)
    assert any(row[1] == "192.0.2.2" for row in failures)


def test_ip_throttle_across_accounts(store, clock):
    store.create("alice", PASSWORD)
    for i in range(20):
        assert store.authenticate(f"missing{i}", PASSWORD, "192.0.2.1") is None
    assert store.authenticate("alice", PASSWORD, "192.0.2.1") is None
    assert rows(store, "account_audit")[-1][2] == "login_throttled"
    assert login(store, ip="192.0.2.2")
    clock[0] += 900
    assert login(store)


@contextmanager
def paused_verification(monkeypatch, workers=1):
    """Pause successful Argon2 verification before the store's write recheck."""
    original = accounts._PASSWORD_HASHER
    reached = threading.Barrier(workers + 1)
    release = threading.Event()
    class Hasher:
        def verify(self, candidate, password):
            result = original.verify(candidate, password)
            reached.wait(timeout=15)
            assert release.wait(timeout=15)
            return result
        def hash(self, password):
            return original.hash(password)
    monkeypatch.setattr(accounts, "_PASSWORD_HASHER", Hasher())
    try:
        yield reached, release
    finally:
        release.set()
        monkeypatch.setattr(accounts, "_PASSWORD_HASHER", original)


def test_simultaneous_logins(store, monkeypatch):
    store.create("alice", PASSWORD)
    with paused_verification(monkeypatch, 2) as (reached, release):
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(store.authenticate, "alice", PASSWORD, "192.0.2.1") for _ in range(2)]
            reached.wait(timeout=15)
            release.set()
            results = [future.result(timeout=15) for future in pending]
    assert len({r[0] for r in results}) == 2
    assert all(store.get_session(r[0]) for r in results)


@pytest.mark.parametrize("action", ["reset", "disable"])
def test_login_racing_account_change(store, monkeypatch, action):
    store.create("alice", PASSWORD)
    with paused_verification(monkeypatch) as (reached, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(store.authenticate, "alice", PASSWORD, "192.0.2.1")
            reached.wait(timeout=15)
            if action == "reset":
                store.reset_password("alice", NEW_PASSWORD)
            else:
                store.disable("alice")
            release.set()
            assert pending.result(timeout=15) is None
    assert rows(store, "sessions") == []


def test_competing_password_changes(store, monkeypatch):
    store.create("alice", PASSWORD)
    tokens = [login(store), login(store)]
    with paused_verification(monkeypatch, 2) as (reached, release):
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(store.change_password, token, PASSWORD, NEW_PASSWORD + str(i)) for i, token in enumerate(tokens)]
            reached.wait(timeout=15)
            release.set()
            results = [future.result(timeout=15) for future in pending]
    assert sorted(results) == [False, True]
    assert all(store.get_session(token) is None for token in tokens)
    winner = results.index(True)
    assert login(store, password=NEW_PASSWORD + str(winner))
    assert store.authenticate("alice", NEW_PASSWORD + str(1-winner), "192.0.2.1") is None


@pytest.mark.parametrize("invalid", ["short", "x" * 1025, "ab", "bad name"])
def test_account_input_validation(store, invalid):
    with pytest.raises(ValueError):
        if invalid in ("ab", "bad name"):
            store.create(invalid, PASSWORD)
        else:
            store.create("alice", invalid)
    assert store.list_users() == []


def cli(tmp_path, *args):
    run.main(["--data-dir", str(tmp_path), "user", *args])


def prompts(monkeypatch, values):
    replies = iter(values)
    seen = []
    def getpass(prompt):
        seen.append(prompt)
        return next(replies)
    monkeypatch.setattr(run.getpass, "getpass", getpass)
    return seen


def test_cli_lifecycle(tmp_path, monkeypatch, capsys):
    seen = prompts(monkeypatch, [PASSWORD, PASSWORD, NEW_PASSWORD, NEW_PASSWORD])
    cli(tmp_path, "create", " Alice ")
    store = AccountStore(tmp_path)
    token = login(store)
    cli(tmp_path, "list")
    cli(tmp_path, "reset-password", "ALICE")
    assert store.get_session(token) is None
    assert store.get_session(login(store, password=NEW_PASSWORD))["must_change"]
    cli(tmp_path, "disable", "alice")
    cli(tmp_path, "list")
    output = capsys.readouterr()
    assert "alice\tenabled" in output.out and "alice\tdisabled" in output.out
    assert seen == ["Password: ", "Confirm password: "] * 2
    assert PASSWORD not in output.out + output.err
    assert NEW_PASSWORD not in output.out + output.err


@pytest.mark.parametrize("kind", ["duplicate", "mismatch", "short", "missing", "missing_reset", "capacity", "database", "newer"])
def test_cli_errors(tmp_path, monkeypatch, capsys, kind):
    store = AccountStore(tmp_path)
    values = [PASSWORD, PASSWORD]
    command = ("create", "alice")
    if kind == "duplicate":
        store.create("alice", PASSWORD)
        command = ("create", "ALICE")
    elif kind == "mismatch":
        values = [PASSWORD, NEW_PASSWORD]
    elif kind == "short":
        values = ["short", "short"]
    elif kind in ("missing", "missing_reset"):
        command = ("disable" if kind == "missing" else "reset-password", "missing")
    elif kind == "capacity":
        for i in range(20):
            store.create(f"user{i}", PASSWORD)
    elif kind == "database":
        store.db_path.write_bytes(b"not SQLite")
        command = ("list",)
    elif kind == "newer":
        with sqlite3.connect(store.db_path) as db:
            db.execute("PRAGMA user_version=2")
        command = ("list",)
    prompts(monkeypatch, values)
    with pytest.raises(SystemExit) as exc:
        cli(tmp_path, *command)
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "error:" in output.err
    assert "Traceback" not in output.err
    assert PASSWORD not in output.out + output.err
    assert NEW_PASSWORD not in output.out + output.err


def test_cli_rejects_password_argument(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli(tmp_path, "create", "alice", "--password")
    assert exc.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_populated_unversioned_upgrade(tmp_path, clock):
    home = tmp_path / "homes" / ("a" * 32)
    home.mkdir(parents=True)
    (home / "workspace.txt").write_text("existing user data")
    path = tmp_path / "accounts.sqlite3"
    token = "existing opaque browser token"
    with sqlite3.connect(path) as db:
        db.executescript(LEGACY_SCHEMA)
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)", ("a" * 32, "alice", accounts._PASSWORD_HASHER.hash(PASSWORD), str(home), 1, 0, clock[0], clock[0]))
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", (accounts._token_hash(token), "a" * 32, "existing-csrf", clock[0], clock[0], clock[0] + 43200, clock[0] + 604800))
        db.execute("INSERT INTO login_failures VALUES ('ip','192.0.2.1',?,2)", (clock[0],))
        db.execute("INSERT INTO account_audit (occurred_at,event,user_id) VALUES (?,'account_created',?)", (clock[0], "a" * 32))
        before = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in ("users", "sessions", "login_failures", "account_audit")}
    store = AccountStore(tmp_path)
    assert {table: rows(store, table) for table in before} == before
    assert store.get_session(token)["csrf"] == "existing-csrf"
    assert (home / "workspace.txt").read_text() == "existing user data"
    assert login(store)
    assert AccountStore(tmp_path).list_users()[0]["home"] == str(home)


def test_reject_legacy_without_unique_constraint(tmp_path):
    path = tmp_path / "accounts.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(LEGACY_SCHEMA.replace("username TEXT NOT NULL UNIQUE", "username TEXT NOT NULL"))
    with pytest.raises(ValueError, match="incompatible"):
        AccountStore(tmp_path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0


@pytest.mark.parametrize("action", ["reset", "disable", "logout"])
def test_password_change_racing_revocation(store, monkeypatch, action):
    store.create("alice", PASSWORD)
    token = login(store)
    with paused_verification(monkeypatch) as (reached, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(store.change_password, token, PASSWORD, NEW_PASSWORD)
            reached.wait(timeout=15)
            if action == "reset":
                store.reset_password("alice", NEW_PASSWORD + " reset")
            elif action == "disable":
                store.disable("alice")
            else:
                store.revoke(token)
            release.set()
            assert pending.result(timeout=15) is False
    assert store.get_session(token) is None


@pytest.mark.parametrize("invalid_session", ["expired", "revoked", "unknown"])
def test_password_change_rejects_invalid_session(store, clock, invalid_session):
    store.create("alice", PASSWORD)
    token = login(store)
    if invalid_session == "expired":
        clock[0] += accounts._IDLE_SECONDS
    elif invalid_session == "revoked":
        store.revoke(token)
    else:
        token = "unknown"
    assert not store.change_password(token, PASSWORD, NEW_PASSWORD)
    assert login(store)


@pytest.mark.parametrize("failures", [4, 5])
def test_account_throttle_limit_boundary(store, failures):
    store.create("alice", PASSWORD)
    for _ in range(failures):
        assert store.authenticate("alice", "wrong", "192.0.2.1") is None
    assert bool(store.authenticate("alice", PASSWORD, "192.0.2.1")) == (failures < 5)


@pytest.mark.parametrize("failures", [19, 20])
def test_ip_throttle_limit_boundary(store, failures):
    store.create("alice", PASSWORD)
    for i in range(failures):
        assert store.authenticate(f"unknown{i}", "wrong", "192.0.2.1") is None
    assert bool(store.authenticate("alice", PASSWORD, "192.0.2.1")) == (failures < 20)


def test_failed_password_change_preserves_sessions(store):
    store.create("alice", PASSWORD)
    token = login(store)
    assert not store.change_password(token, "wrong", NEW_PASSWORD)
    with pytest.raises(ValueError):
        store.change_password(token, PASSWORD, "short")
    assert store.get_session(token)["must_change"]
    assert login(store)
    assert rows(store, "users")[0][2].startswith("$argon2id$")


def test_account_capacity_counts_enabled_accounts(store):
    for i in range(20):
        store.create(f"user{i}", PASSWORD)
    with pytest.raises(ValueError, match="20 enabled"):
        store.create("overflow", PASSWORD)
    store.disable("user0")
    assert store.create("replacement", PASSWORD)["enabled"]
    assert sum(user["enabled"] for user in store.list_users()) == 20


def test_post_migration_validation_rolls_back_version_and_schema(tmp_path, monkeypatch):
    original = accounts._MIGRATIONS[0]
    def incompatible(db):
        original(db)
        db.execute("ALTER TABLE users ADD COLUMN unexpected TEXT")
    monkeypatch.setattr(accounts, "_MIGRATIONS", (incompatible,))
    with pytest.raises(ValueError, match="incompatible"):
        AccountStore(tmp_path)
    with sqlite3.connect(tmp_path / "accounts.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
