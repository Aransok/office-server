"""python -m app.cli create-admin|reset-password [username] | sync-rights"""
import sys

from . import ntfs
from .db import db, init
from .security import create_user, new_password, ph


def main():
    init()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sync-rights":
        for folder, missing in ntfs.sync_all().items():
            print(f"{folder}: done" + (f", no Windows account for: {', '.join(missing)}" if missing else ""))
        return
    if cmd not in ("create-admin", "reset-password"):
        sys.exit("usage: python -m app.cli create-admin|reset-password [username] | sync-rights")
    name = sys.argv[2] if len(sys.argv) > 2 else "admin"
    row = db("SELECT id FROM users WHERE username=?", (name,), "one")
    pw = new_password()
    if cmd == "reset-password":
        if not row:
            sys.exit(f"User {name} not found.")
        db("UPDATE users SET pw_hash=? WHERE id=?", (ph.hash(pw), row["id"]))
        db("DELETE FROM sessions WHERE user_id=?", (row["id"],))
    else:
        if row:
            sys.exit(f"User {name} already exists.")
        create_user(name, pw, "admin")
    print(f"Done.\n  user: {name}\n  password: {pw}\nWrite it down now, it is not shown again.")


main()
