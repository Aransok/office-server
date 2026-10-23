import os
import sys
import tempfile
from pathlib import Path

_t = Path(tempfile.mkdtemp())
os.environ.update(
    DATA_ROOT=str(_t / "data"), DB_PATH=str(_t / "t.db"), LOG_DIR=str(_t / "logs"),
    STATUS_FILE=str(_t / "none.json"), CLIENT_DIR=str(_t / "client"), MAX_UPLOAD_MB="1",
    NTFS_RIGHTS="0",  # never run icacls from tests
    COOKIE_SECURE="0",  # tests use http; a server .env with 1 would block the cookie
)
(_t / "data").mkdir()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config as C  # noqa: E402
from app.db import db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import _fails, create_user  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    for t in ("users", "perms", "sessions", "log", "trash"):
        db(f"DELETE FROM {t}")
    _fails.clear()
    import shutil
    for e in C.DATA_ROOT.iterdir():
        if e.name not in (C.TRASH.name, C.TMP.name):
            shutil.rmtree(e, ignore_errors=True) if e.is_dir() else e.unlink()
    for e in C.TRASH.iterdir():
        shutil.rmtree(e, ignore_errors=True) if e.is_dir() else e.unlink()
    (C.DATA_ROOT / "Acc").mkdir()
    (C.DATA_ROOT / "Acc" / "a.txt").write_text("secret-acc")
    (C.DATA_ROOT / "Pub").mkdir()
    (C.DATA_ROOT / "Pub" / "p.txt").write_text("public")


def login(name, pw="pw", role="user", perms=None):
    uid = create_user(name, pw, role)
    for f, lv in (perms or {}).items():
        db("INSERT INTO perms VALUES(?,?,?)", (uid, f, lv))
    c = TestClient(app, follow_redirects=False)
    r = c.post("/login", data={"username": name, "password": pw})
    assert r.status_code == 303
    c.csrf = {"X-CSRF": db("SELECT csrf FROM sessions", fetch="all")[-1]["csrf"]}
    return c


@pytest.fixture
def admin():
    return login("admin", role="admin")


@pytest.fixture
def bob():
    return login("bob", perms={"Pub": "write", "Acc": "none"})


@pytest.fixture
def reader():
    return login("rita", perms={"Pub": "read"})
