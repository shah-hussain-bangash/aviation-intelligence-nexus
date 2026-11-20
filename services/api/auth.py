"""Local account/session foundation. Requires HTTPS and external controls before deployment."""

from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
from threading import Lock
import time
import os
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

COOKIE = os.environ.get('AIN_SESSION_COOKIE','ain_session')
if COOKIE not in ('ain_session','ain_release_session'):
    raise RuntimeError('Unsupported session cookie namespace')
SESSION_SECONDS = 8 * 60 * 60
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def csrf_token(token):
    return hmac.new(token.encode(), b"ain-csrf-v1", hashlib.sha256).hexdigest()


class LoginDenied(ValueError):
    pass


class LoginLimited(ValueError):
    pass


class AuthStore:
    def __init__(self, database: Path):
        self.database = database
        self.lock = Lock()

    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def create_user(self, username, password, role):
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username) or role not in ("admin", "researcher", "viewer"):
            raise ValueError("Use a 3–32 character username and a valid role")
        if not 12 <= len(password) <= 128:
            raise ValueError("Password must contain 12–128 characters")
        encoded = HASHER.hash(password)
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() and role != "admin":
                raise ValueError("The first account must be an admin")
            db.execute("INSERT INTO auth_users(id,username,password_hash,role,active) VALUES(?,?,?,?,1)",
                       (str(uuid4()), username, encoded, role))

    def enrollment_required(self):
        with closing(self.connect()) as db:
            return not bool(db.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone())

    def login(self, username, password):
        username = username.lower()
        key = hashlib.sha256(username.encode()).hexdigest()
        current = time.time()
        denied = False
        with self.lock, closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM auth_limits WHERE window_start < ?", (current - 3600,))
            limit = db.execute("SELECT failures,window_start FROM auth_limits WHERE key=?", (key,)).fetchone()
            failures = limit["failures"] if limit and current - limit["window_start"] < 60 else 0
            started = limit["window_start"] if failures else current
            if failures >= 5:
                raise LoginLimited("Try again later")
            user = db.execute("SELECT * FROM auth_users WHERE username=?", (username,)).fetchone()
            try:
                HASHER.verify(user["password_hash"] if user else DUMMY_HASH, password)
                denied = not user or not user["active"]
            except (VerificationError, InvalidHashError):
                denied = True
            if denied:
                db.execute("INSERT INTO auth_limits(key,failures,window_start) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,window_start=excluded.window_start",
                    (key, failures + 1, started))
            else:
                if HASHER.check_needs_rehash(user["password_hash"]):
                    db.execute("UPDATE auth_users SET password_hash=? WHERE id=?", (HASHER.hash(password), user["id"]))
                db.execute("DELETE FROM auth_limits WHERE key=?", (key,))
                db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (current,))
                token = secrets.token_urlsafe(32)
                db.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(), user["id"], current + SESSION_SECONDS))
        if denied:
            raise LoginDenied("Invalid username or password")
        return token

    def session(self, token):
        if not token or len(token) > 128:
            return None
        with closing(self.connect()) as db:
            row = db.execute("SELECT u.id,u.username,u.role FROM auth_users u JOIN auth_sessions s ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
                (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def set_access(self, username, role=None, disable=False):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM auth_users WHERE username=?", (username.lower(),)).fetchone()
            if not row:
                raise ValueError("Account not found")
            if row["role"] == "admin" and row["active"] and (disable or role != "admin"):
                if db.execute("SELECT COUNT(*) FROM auth_users WHERE role='admin' AND active=1").fetchone()[0] <= 1:
                    raise ValueError("Keep at least one active administrator")
            db.execute("UPDATE auth_users SET role=?,active=? WHERE id=?",
                       (role or row["role"], 0 if disable else row["active"], row["id"]))
            db.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["id"],))
