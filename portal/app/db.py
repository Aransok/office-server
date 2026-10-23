import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE,
  pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS perms(
  user_id INTEGER NOT NULL, folder TEXT NOT NULL, level TEXT NOT NULL,
  PRIMARY KEY(user_id, folder));
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS log(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, user TEXT, action TEXT, ip TEXT, path TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS log_path ON log(path);
CREATE TABLE IF NOT EXISTS trash(
  id INTEGER PRIMARY KEY, orig TEXT NOT NULL, name TEXT NOT NULL, user TEXT, ts REAL NOT NULL, is_dir INTEGER NOT NULL);
"""


def db(sql, args=(), fetch=None):
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, args)
        c.commit()
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()
        return cur.lastrowid
    finally:
        c.close()


def init():
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    c.close()
