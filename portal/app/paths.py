import os
import stat

from fastapi import HTTPException

from .config import DATA_ROOT

RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
BAD = set('<>:"|?*\\/')


def check_name(n):
    """One path component, safe on NTFS."""
    if (
        not n
        or n in (".", "..")
        or n != n.rstrip(". ")
        or len(n) > 200
        or any(c in BAD or ord(c) < 32 for c in n)
        or n.split(".")[0].rstrip().upper() in RESERVED
    ):
        raise HTTPException(400, "Невалидно име")
    return n


def parts_of(rel):
    """Client path -> list of safe components. Rejects absolute, UNC, drive, '..', streams."""
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("/"):
        raise HTTPException(400, "Невалиден път")
    parts = [p for p in rel.split("/") if p]
    for p in parts:
        check_name(p)
    if parts and parts[0][0] in "_.":  # _Корзина, _Програми, .tmp are never reachable
        raise HTTPException(404, "Не е намерено")
    return parts


def is_link(p):
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)  # reparse point


def resolve(parts):
    cur = DATA_ROOT
    for p in parts:
        cur = cur / p
        if is_link(cur):
            raise HTTPException(400, "Невалиден път")
    full = cur.resolve()
    if full != DATA_ROOT and not full.is_relative_to(DATA_ROOT):
        raise HTTPException(400, "Невалиден път")
    return full


def unique(directory, name):
    """name (2).ext when name is taken."""
    if not (directory / name).exists():
        return directory / name
    stem, dot, ext = name.rpartition(".") if "." in name[1:] else (name, "", "")
    i = 2
    while True:
        cand = directory / (f"{stem} ({i}){dot}{ext}")
        if not cand.exists():
            return cand
        i += 1
