"""Make the real Windows (NTFS) rights of a top folder match the portal rights, so drive O: obeys them too."""
import os
import subprocess

from . import config as C
from .db import db

SYSTEM, ADMINS = "*S-1-5-18", "*S-1-5-32-544"


def _icacls(*a):
    return subprocess.run(["icacls", *a], capture_output=True, text=True).returncode == 0


def sync(folder):
    """Returns the users whose Windows account was not found (they stay without access). No-op unless NTFS_RIGHTS=1."""
    if not C.NTFS_RIGHTS:
        return []
    p = str(C.DATA_ROOT / folder)
    _icacls(p, "/reset")  # back to inherited rights, so removed users lose their entries
    _icacls(p, "/inheritance:r", "/grant:r", f"{SYSTEM}:(OI)(CI)F", f"{ADMINS}:(OI)(CI)F")
    missing = []
    for r in db("SELECT id,username,role FROM users WHERE active=1", fetch="all"):
        lv = "write" if r["role"] == "admin" else (db("SELECT level FROM perms WHERE user_id=? AND folder=?", (r["id"], folder), "one") or {"level": "none"})["level"]
        if lv != "none" and not _icacls(p, "/grant", f"{r['username']}:(OI)(CI){'M' if lv == 'write' else 'RX'}"):
            missing.append(r["username"])
    return missing


def sync_all():
    out = {}
    for e in os.scandir(C.DATA_ROOT):
        if e.is_dir() and e.name[0] not in "_.":
            out[e.name] = sync(e.name)
    return out
