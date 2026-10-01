"""Database-backed accounts and browser sessions for hosted OpenWorker.

Only this store assigns an account to a home.  Engine state remains in that
home; the gateway must use the returned mapping instead of accepting a path or
user identity from the browser.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_DUMMY_HASH = _PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
_IDLE_SECONDS = 12 * 60 * 60
_ABSOLUTE_SECONDS = 7 * 24 * 60 * 60
_THROTTLE_WINDOW = 15 * 60
_ACCOUNT_FAILURE_LIMIT = 5
_IP_FAILURE_LIMIT = 20
_MAX_ENABLED_ACCOUNTS = 20

_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        home TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1,
        must_change INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_seen_at REAL NOT NULL,
        idle_expires_at REAL NOT NULL,
        absolute_expires_at REAL NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id)""",
    """CREATE TABLE IF NOT EXISTS login_failures (
        kind TEXT NOT NULL,
        subject TEXT NOT NULL,
        window_started_at REAL NOT NULL,
        failures INTEGER NOT NULL,
        PRIMARY KEY(kind, subject)
    )""",
    """CREATE TABLE IF NOT EXISTS account_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at REAL NOT NULL,
        event TEXT NOT NULL,
        user_id TEXT,
        username TEXT,
        client_ip TEXT
    )""",
)
_SCHEMA_VERSION = 1


def _schema_signature(db: sqlite3.Connection) -> dict:
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    result = {}
    for row in tables:
        name = row[0]
        quoted = '"' + name.replace('"', '""') + '"'
        columns = tuple(tuple(r) for r in db.execute(f"PRAGMA table_info({quoted})"))
        foreign_keys = tuple(tuple(r) for r in db.execute(f"PRAGMA foreign_key_list({quoted})"))
        indexes = []
        for index in db.execute(f"PRAGMA index_list({quoted})"):
            index_name = '"' + index[1].replace('"', '""') + '"'
            indexes.append((index[2], tuple(r[2] for r in db.execute(f"PRAGMA index_info({index_name})")), index[4]))
        result[name] = (columns, foreign_keys, tuple(sorted(indexes)))
    return result


def _validate_schema(db: sqlite3.Connection) -> None:
    with closing(sqlite3.connect(":memory:")) as expected:
        for statement in _SCHEMA_STATEMENTS:
            expected.execute(statement)
        if _schema_signature(db) != _schema_signature(expected):
            raise ValueError("incompatible account database schema")


def _migrate_v1(db: sqlite3.Connection) -> None:
    if db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
        _validate_schema(db)
    else:
        for statement in _SCHEMA_STATEMENTS:
            db.execute(statement)


_MIGRATIONS = (_migrate_v1,)


def _normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not _USERNAME.fullmatch(normalized):
        raise ValueError(
            "username must be 3–64 ASCII letters, digits, dots, underscores, or hyphens "
            "and start with a letter or digit"
        )
    return normalized


def _validate_password(password: str) -> None:
    if len(password) < 15:
        raise ValueError("password must contain at least 15 characters")
    if len(password.encode("utf-8")) > 1024:
        raise ValueError("password is too long")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AccountStore:
    """Central account database; each method opens its own SQLite connection.

    SQLite WAL and immediate write transactions permit independent gateway
    requests and admin commands to share this database safely.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.data_dir.chmod(0o700)
        self.homes_dir = self.data_dir / "homes"
        self.homes_dir.mkdir(exist_ok=True)
        if os.name != "nt":
            self.homes_dir.chmod(0o700)
        self.db_path = self.data_dir / "accounts.sqlite3"
        if self.db_path.is_symlink():
            raise ValueError("account database must not be a symlink")
        if not self.db_path.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(self.db_path, flags, 0o600)
            except FileExistsError:
                pass  # Another gateway or admin command created it.
            else:
                os.close(fd)
        if os.name != "nt":
            self.db_path.chmod(0o600)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version > _SCHEMA_VERSION:
                    raise ValueError("account database schema is newer than this application")
                for target in range(version + 1, _SCHEMA_VERSION + 1):
                    _MIGRATIONS[target - 1](db)
                    db.execute(f"PRAGMA user_version={target}")
                _validate_schema(db)
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=10000")
            # Concurrent first opens can race while SQLite changes journal mode;
            # that upgrade can return BUSY without honoring busy_timeout.
            deadline = time.monotonic() + 10
            while True:
                try:
                    if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                        db.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as exc:
                    # sqlite_errorcode is available starting with Python 3.11.
                    code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
                    busy = code in (5, 6) or str(exc) in (
                        "database is locked", "database table is locked",
                    )
                    if not busy or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.01)
            db.execute("PRAGMA foreign_keys=ON")
            yield db
        finally:
            db.close()

    @staticmethod
    def _audit(
        db: sqlite3.Connection,
        event: str,
        *,
        user_id: str | None = None,
        username: str | None = None,
        client_ip: str | None = None,
    ) -> None:
        db.execute(
            "INSERT INTO account_audit (occurred_at, event, user_id, username, client_ip) "
            "VALUES (?, ?, ?, ?, ?)",
            (time.time(), event, user_id, username, client_ip),
        )

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "home": row["home"],
            "enabled": bool(row["enabled"]),
            "must_change": bool(row["must_change"]),
        }

    def create(self, username: str, password: str) -> dict:
        normalized = _normalize_username(username)
        _validate_password(password)
        password_hash = _PASSWORD_HASHER.hash(password)
        user_id = uuid.uuid4().hex
        home = self.homes_dir / user_id
        now = time.time()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM users WHERE username=?", (normalized,)).fetchone():
                    raise ValueError("username already exists")
                enabled_count = db.execute(
                    "SELECT COUNT(*) FROM users WHERE enabled=1"
                ).fetchone()[0]
                if enabled_count >= _MAX_ENABLED_ACCOUNTS:
                    raise ValueError("a hosted deployment supports at most 20 enabled accounts")
                home.mkdir(mode=0o700)
                if os.name != "nt":
                    home.chmod(0o700)
                db.execute(
                    "INSERT INTO users "
                    "(id, username, password_hash, home, enabled, must_change, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 1, 1, ?, ?)",
                    (user_id, normalized, password_hash, str(home), now, now),
                )
                self._audit(db, "account_created", user_id=user_id, username=normalized)
                db.commit()
            except BaseException:
                db.rollback()
                # An unused empty directory can remain after a failed insert;
                # never remove a home containing user data.
                try:
                    home.rmdir()
                except OSError:
                    pass
                raise
        return {
            "id": user_id,
            "username": normalized,
            "home": str(home),
            "enabled": True,
            "must_change": True,
        }

    def list_users(self) -> list[dict]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT id, username, home, enabled, must_change FROM users ORDER BY username"
            ).fetchall()
        return [self._public_user(row) for row in rows]

    def disable(self, username: str) -> None:
        normalized = _normalize_username(username)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT id FROM users WHERE username=?", (normalized,)
                ).fetchone()
                if row is None:
                    raise KeyError(normalized)
                db.execute(
                    "UPDATE users SET enabled=0, updated_at=? WHERE id=?",
                    (time.time(), row["id"]),
                )
                db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
                self._audit(
                    db, "account_disabled", user_id=row["id"], username=normalized
                )
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def reset_password(self, username: str, password: str) -> None:
        normalized = _normalize_username(username)
        _validate_password(password)
        password_hash = _PASSWORD_HASHER.hash(password)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT id FROM users WHERE username=?", (normalized,)
                ).fetchone()
                if row is None:
                    raise KeyError(normalized)
                db.execute(
                    "UPDATE users SET password_hash=?, must_change=1, updated_at=? WHERE id=?",
                    (password_hash, time.time(), row["id"]),
                )
                db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
                self._audit(
                    db, "password_reset", user_id=row["id"], username=normalized
                )
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _throttled(db: sqlite3.Connection, kind: str, subject: str, limit: int, now: float) -> bool:
        row = db.execute(
            "SELECT window_started_at, failures FROM login_failures "
            "WHERE kind=? AND subject=?",
            (kind, subject),
        ).fetchone()
        return bool(
            row is not None
            and now - row["window_started_at"] < _THROTTLE_WINDOW
            and row["failures"] >= limit
        )

    @staticmethod
    def _record_failure(db: sqlite3.Connection, kind: str, subject: str, now: float) -> None:
        row = db.execute(
            "SELECT window_started_at, failures FROM login_failures "
            "WHERE kind=? AND subject=?",
            (kind, subject),
        ).fetchone()
        if row is None or now - row["window_started_at"] >= _THROTTLE_WINDOW:
            db.execute(
                "INSERT INTO login_failures (kind, subject, window_started_at, failures) "
                "VALUES (?, ?, ?, 1) "
                "ON CONFLICT(kind, subject) DO UPDATE SET "
                "window_started_at=excluded.window_started_at, failures=1",
                (kind, subject, now),
            )
        else:
            db.execute(
                "UPDATE login_failures SET failures=failures+1 WHERE kind=? AND subject=?",
                (kind, subject),
            )

    def authenticate(
        self, username: str, password: str, client_ip: str
    ) -> tuple[str, str, dict] | None:
        """Return opaque cookie, CSRF token, and account; all failures return None."""
        normalized = username.strip().lower()
        ip = client_ip[:255]
        # Invalid account names cannot match a provisioned account. Hash the
        # throttle subject so an attacker cannot grow the DB with long names.
        lookup = normalized if _USERNAME.fullmatch(normalized) else ""
        username_subject = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        now = time.time()
        # Already throttled attempts are audited without expensive password work
        # or changing the failure window. Recheck after verification for races.
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if self._throttled(db, "ip", ip, _IP_FAILURE_LIMIT, now) or self._throttled(
                    db, "username", username_subject, _ACCOUNT_FAILURE_LIMIT, now
                ):
                    row = db.execute("SELECT id FROM users WHERE username=?", (lookup,)).fetchone()
                    self._audit(
                        db, "login_throttled",
                        user_id=row["id"] if row is not None else None,
                        username=normalized[:64], client_ip=ip,
                    )
                    db.commit()
                    return None
                db.commit()
            except BaseException:
                db.rollback()
                raise
        # Unthrottled attempts always verify Argon2, including unknown names.
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username=?", (lookup,)
            ).fetchone()
        password_too_long = len(password.encode("utf-8")) > 1024
        candidate = row["password_hash"] if row is not None and not password_too_long else _DUMMY_HASH
        try:
            password_ok = _PASSWORD_HASHER.verify(candidate, password[:1024]) and not password_too_long
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            password_ok = False
        now = time.time()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                current = db.execute(
                    "SELECT * FROM users WHERE username=?", (lookup,)
                ).fetchone()
                throttled = self._throttled(
                    db, "username", username_subject, _ACCOUNT_FAILURE_LIMIT, now
                ) or self._throttled(db, "ip", ip, _IP_FAILURE_LIMIT, now)
                valid = bool(
                    not throttled
                    and password_ok
                    and current is not None
                    and current["enabled"]
                    and row is not None
                    and current["id"] == row["id"]
                    and current["password_hash"] == row["password_hash"]
                )
                if not valid:
                    self._record_failure(db, "username", username_subject, now)
                    self._record_failure(db, "ip", ip, now)
                    self._audit(
                        db,
                        "login_throttled" if throttled else "login_failed",
                        user_id=current["id"] if current is not None else None,
                        username=normalized[:64],
                        client_ip=ip,
                    )
                    db.commit()
                    return None

                db.execute(
                    "DELETE FROM login_failures WHERE "
                    "(kind='username' AND subject=?) OR (kind='ip' AND subject=?)",
                    (username_subject, ip),
                )
                token = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(32)
                db.execute(
                    "INSERT INTO sessions "
                    "(token_hash, user_id, csrf, created_at, last_seen_at, "
                    "idle_expires_at, absolute_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        _token_hash(token),
                        current["id"],
                        csrf,
                        now,
                        now,
                        now + _IDLE_SECONDS,
                        now + _ABSOLUTE_SECONDS,
                    ),
                )
                self._audit(
                    db,
                    "login_succeeded",
                    user_id=current["id"],
                    username=normalized,
                    client_ip=ip,
                )
                db.commit()
                result = self._public_user(current)
                result["csrf"] = csrf
                return token, csrf, result
            except BaseException:
                db.rollback()
                raise

    def get_session(self, token: str, *, touch: bool = True) -> dict | None:
        if not token or len(token) > 256:
            return None
        token_digest = _token_hash(token)
        now = time.time()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT u.id, u.username, u.home, u.enabled, u.must_change, "
                    "s.csrf, s.idle_expires_at, s.absolute_expires_at, s.last_seen_at "
                    "FROM sessions s JOIN users u ON u.id=s.user_id "
                    "WHERE s.token_hash=?",
                    (token_digest,),
                ).fetchone()
                if row is None:
                    db.commit()
                    return None
                if (
                    not row["enabled"]
                    or now >= row["idle_expires_at"]
                    or now >= row["absolute_expires_at"]
                ):
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest,))
                    self._audit(
                        db,
                        "session_expired",
                        user_id=row["id"],
                        username=row["username"],
                    )
                    db.commit()
                    return None
                if touch and now - row["last_seen_at"] >= 60:
                    db.execute(
                        "UPDATE sessions SET last_seen_at=?, idle_expires_at=? "
                        "WHERE token_hash=?",
                        (now, min(now + _IDLE_SECONDS, row["absolute_expires_at"]), token_digest),
                    )
                db.commit()
                result = self._public_user(row)
                result["csrf"] = row["csrf"]
                return result
            except BaseException:
                db.rollback()
                raise

    def revoke(self, token: str) -> None:
        if not token or len(token) > 256:
            return
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT u.id, u.username FROM sessions s "
                    "JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
                    (_token_hash(token),),
                ).fetchone()
                db.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
                if row is not None:
                    self._audit(
                        db,
                        "session_revoked",
                        user_id=row["id"],
                        username=row["username"],
                    )
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def change_password(self, token: str, current: str, new: str) -> bool:
        """Change a password and revoke all sessions; return False on bad auth."""
        _validate_password(new)
        if not token or len(token) > 256:
            return False
        digest = _token_hash(token)
        with self._connection() as db:
            row = db.execute(
                "SELECT u.id, u.username, u.password_hash, u.enabled, "
                "s.idle_expires_at, s.absolute_expires_at "
                "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
                (digest,),
            ).fetchone()
        candidate = row["password_hash"] if row is not None else _DUMMY_HASH
        try:
            password_ok = _PASSWORD_HASHER.verify(candidate, current)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            password_ok = False
        new_hash = _PASSWORD_HASHER.hash(new) if password_ok else None
        now = time.time()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                latest = db.execute(
                    "SELECT u.id, u.username, u.password_hash, u.enabled, "
                    "s.idle_expires_at, s.absolute_expires_at "
                    "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
                    (digest,),
                ).fetchone()
                valid = bool(
                    password_ok
                    and row is not None
                    and latest is not None
                    and latest["enabled"]
                    and now < latest["idle_expires_at"]
                    and now < latest["absolute_expires_at"]
                    and latest["password_hash"] == row["password_hash"]
                )
                if not valid:
                    self._audit(
                        db,
                        "password_change_failed",
                        user_id=latest["id"] if latest is not None else None,
                        username=latest["username"] if latest is not None else None,
                    )
                    db.commit()
                    return False
                db.execute(
                    "UPDATE users SET password_hash=?, must_change=0, updated_at=? WHERE id=?",
                    (new_hash, now, latest["id"]),
                )
                db.execute(
                    "DELETE FROM sessions WHERE user_id=?",
                    (latest["id"],),
                )
                self._audit(
                    db,
                    "password_changed",
                    user_id=latest["id"],
                    username=latest["username"],
                )
                db.commit()
                return True
            except BaseException:
                db.rollback()
                raise
