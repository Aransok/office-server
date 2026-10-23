import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .db import db

ph = PasswordHasher()
SESSION_SECONDS = 8 * 3600
LOCK_AFTER, LOCK_SECONDS = 5, 300
_fails = {}  # key -> [count, locked_until]; shortcut: in memory, resets on restart


def new_password():
    return secrets.token_urlsafe(9)


def create_user(username, password, role="user"):
    return db("INSERT INTO users(username,pw_hash,role) VALUES(?,?,?)", (username, ph.hash(password), role))


def check_login(username, password):
    row = db("SELECT * FROM users WHERE username=? AND active=1", (username,), "one")
    if not row:
        ph.hash("x")  # keep timing similar
        return None
    try:
        ph.verify(row["pw_hash"], password)
    except VerifyMismatchError:
        return None
    return row


def locked(*keys):
    now = time.time()
    return any(_fails.get(k, [0, 0])[1] > now for k in keys)


def register_fail(*keys):
    for k in keys:
        c, _ = _fails.get(k, [0, 0])
        c += 1
        _fails[k] = [0, time.time() + LOCK_SECONDS] if c >= LOCK_AFTER else [c, 0]


def clear_fails(*keys):
    for k in keys:
        _fails.pop(k, None)


def new_session(uid):
    tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    db("INSERT INTO sessions VALUES(?,?,?,?)", (tok, uid, csrf, time.time() + SESSION_SECONDS))
    return tok


def current(request):
    tok = request.cookies.get("sid")
    if not tok:
        return None
    row = db(
        "SELECT u.id,u.username,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token=? AND s.expires>? AND u.active=1",
        (tok, time.time()),
        "one",
    )
    return dict(row) if row else None


def end_session(tok):
    db("DELETE FROM sessions WHERE token=?", (tok,))
