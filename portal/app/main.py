import asyncio
import json
import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import VERSION
from . import config as C
from . import ntfs, winuser
from .db import db, init
from .paths import check_name, is_link, parts_of, resolve, unique
from .security import (ph, check_login, clear_fails, create_user, current, end_session, locked, new_password,
                       new_session, register_fail)

C.LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=C.LOG_DIR / "portal.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
BASE = Path(__file__).resolve().parent
START = time.time()

init()
for d in (C.DATA_ROOT, C.TRASH, C.TMP):
    d.mkdir(parents=True, exist_ok=True)


def purge():
    cut = time.time() - C.TRASH_DAYS * 86400
    for r in db("SELECT * FROM trash WHERE ts<?", (cut,), "all"):
        _drop_trash(r)
    db("DELETE FROM log WHERE ts<?", (time.time() - C.LOG_DAYS * 86400,))
    db("DELETE FROM sessions WHERE expires<?", (time.time(),))
    for f in C.TMP.iterdir():  # leftovers of interrupted uploads
        f.unlink(missing_ok=True)


def _trash_file(r):
    return C.TRASH / f"{r['id']}_{r['name']}"


def _drop_trash(r):
    p = _trash_file(r)
    shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    db("DELETE FROM trash WHERE id=?", (r["id"],))


@asynccontextmanager
async def lifespan(app):
    async def daily():
        while True:
            await asyncio.to_thread(purge)
            await asyncio.sleep(86400)
    task = asyncio.create_task(daily())
    # PCs copy the launcher from the share during setup.cmd
    try:
        (C.DATA_ROOT / "_launcher").mkdir(parents=True, exist_ok=True)
        for f in ("officeapp.ps1", "OfficeLauncher.ps1"):
            shutil.copy2(C.CLIENT_DIR / f, C.DATA_ROOT / "_launcher" / f)
    except OSError:
        logging.warning("could not publish the launcher script")
    yield
    task.cancel()


PROG = C.DATA_ROOT / "_Програми"
APP_EXT = {".exe", ".lnk", ".bat", ".cmd", ".accdb", ".mdb"}

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["size"] = lambda n: (
    f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{n / 1024:.0f} KB" if n >= 1024 else f"{n} B"
)
# cache-buster: the browser refetches css/js whenever the files change
templates.env.globals["asset_v"] = lambda: int(max(p.stat().st_mtime for p in (BASE / "static").iterdir()))
templates.env.filters["dt"] = lambda t: datetime.fromtimestamp(t).strftime("%d.%m.%Y %H:%M")


class NotLoggedIn(Exception):
    pass


@app.exception_handler(NotLoggedIn)
async def _nli(request, exc):
    if request.url.path.startswith(("/api", "/download", "/zip")):
        return JSONResponse({"detail": "Не сте влезли"}, 401)
    return RedirectResponse("/login", 303)


@app.exception_handler(HTTPException)
async def _http(request, exc):
    if request.url.path.startswith(("/api", "/download", "/zip")) or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"detail": exc.detail}, exc.status_code)
    return templates.TemplateResponse(request, "error.html", {"user": current(request), "code": exc.status_code, "msg": exc.detail}, exc.status_code)


@app.exception_handler(Exception)
async def _boom(request, exc):
    logging.exception("unhandled %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Вътрешна грешка"}, 500)


@app.middleware("http")
async def headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'",
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


# ---------- helpers ----------

async def guard(request, admin=False):
    u = current(request)
    if not u:
        raise NotLoggedIn()
    if request.method not in ("GET", "HEAD"):
        tok = request.headers.get("x-csrf")
        if not tok and "form" in request.headers.get("content-type", ""):
            tok = (await request.form()).get("csrf")
        if not tok or not secrets.compare_digest(tok, u["csrf"]):
            raise HTTPException(403, "Невалидна заявка (CSRF)")
    if admin and u["role"] != "admin":
        raise HTTPException(403, "Само за администратор")
    return u


MIN_PW, MAX_PW = 8, 64
PW_LEN = f"Паролата трябва да е между {MIN_PW} и {MAX_PW} знака."
WIN_REFUSED = "Windows отказа паролата (твърде проста?). Нищо не е сменено."


async def set_password(uid, name, pw, keep=None):
    """Windows account first (it enforces the PC's password rules), then the portal, so O: and the portal never differ.
    Logs the user out everywhere except the session `keep`. False when Windows refused."""
    if not await asyncio.to_thread(winuser.create, name, pw):
        return False
    db("UPDATE users SET pw_hash=? WHERE id=?", (ph.hash(pw), uid))
    db("DELETE FROM sessions WHERE user_id=? AND token IS NOT ?", (uid, keep))
    return True


def ip(request):
    return request.client.host if request.client else ""


def log(u, action, request, path="", detail=""):
    db(
        "INSERT INTO log(ts,user,action,ip,path,detail) VALUES(?,?,?,?,?,?)",
        (time.time(), u["username"] if u else "-", action, ip(request), path, detail),
    )


def level(u, top):
    if u["role"] == "admin":
        return "write"
    r = db("SELECT level FROM perms WHERE user_id=? AND folder=?", (u["id"], top), "one")
    return r["level"] if r else "none"


def need(u, parts, write=False):
    if not parts:
        if write and u["role"] != "admin":
            raise HTTPException(403, "Нямате право")
        return
    lv = level(u, parts[0])
    if lv == "none" or (write and lv != "write"):
        raise HTTPException(403, "Нямате право")


def need_not_top(u, parts):
    """Top-level folders can only be renamed, moved or deleted by an admin."""
    if len(parts) == 1 and u["role"] != "admin":
        raise HTTPException(403, "Нямате право")


def tops(u):
    return sorted(
        e.name for e in os.scandir(C.DATA_ROOT)
        if e.is_dir() and e.name[0] not in "_." and not is_link(e.path) and level(u, e.name) != "none"
    )


def visible(u, parts, entry):
    if entry.name[0] in "_." and not parts:
        return False
    if is_link(entry.path):
        return False
    return not (not parts and level(u, entry.name) == "none")


def item(parts, e, shown=None):
    st = e.stat()
    rel = "/".join([*parts, e.name])
    last = db(
        "SELECT user FROM log WHERE path=? AND action IN ('upload','mkdir','rename','move','copy','restore') ORDER BY id DESC LIMIT 1",
        (rel,), "one",
    )
    return dict(name=shown or e.name, dir=e.is_dir(), size=st.st_size, mtime=st.st_mtime, path=rel, by=last["user"] if last else "")


def listing(u, parts):
    return [item(parts, e) for e in os.scandir(resolve(parts)) if visible(u, parts, e)]


def search(u, parts, q):
    q, out = q.lower(), []
    for root, dirs, files in os.walk(resolve(parts)):
        rp = Path(root).relative_to(C.DATA_ROOT).parts
        dirs[:] = [d for d in dirs if not (not rp and (d[0] in "_." or level(u, d) == "none")) and not is_link(Path(root) / d)]
        for e in os.scandir(root):
            if q in e.name.lower() and not is_link(e.path) and not (not rp and e.name[0] in "_."):
                out.append(item(list(rp), e, shown="/".join([*rp[len(parts):], e.name])))
                if len(out) >= 500:
                    return out
    return out


def render(request, name, u, status=200, **ctx):
    return templates.TemplateResponse(request, name, {"user": u, "version": VERSION, **ctx}, status)


# ---------- login ----------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return render(request, "login.html", None, error="")


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    name, pw = str(form.get("username", "")).strip(), str(form.get("password", ""))
    keys = (("u", name.lower()), ("i", ip(request)))
    if locked(*keys):
        log(None, "login_locked", request, detail=name)
        return render(request, "login.html", None, 429, error="Твърде много опити. Опитайте след 5 минути.")
    row = check_login(name, pw)
    if not row:
        register_fail(*keys)
        log(None, "login_failed", request, detail=name)
        return render(request, "login.html", None, 401, error="Грешно потребителско име или парола.")
    clear_fails(*keys)
    resp = RedirectResponse("/files", 303)
    resp.set_cookie("sid", new_session(row["id"]), httponly=True, samesite="strict", secure=C.COOKIE_SECURE, max_age=8 * 3600)
    log({"username": row["username"]}, "login", request)
    return resp


@app.post("/logout")
async def logout(request: Request):
    u = await guard(request)
    end_session(request.cookies.get("sid"))
    log(u, "logout", request)
    resp = RedirectResponse("/login", 303)
    resp.delete_cookie("sid")
    return resp


@app.get("/")
async def root():
    return RedirectResponse("/files", 303)


# ---------- file manager ----------

@app.get("/files", response_class=HTMLResponse)
async def files(request: Request, p: str = "", q: str = "", s: str = "name", d: str = "asc"):
    u = await guard(request)
    parts = parts_of(p)
    need(u, parts)
    if not resolve(parts).is_dir():
        raise HTTPException(404, "Папката не е намерена")
    items = search(u, parts, q) if q else listing(u, parts)
    key = {"size": lambda i: i["size"], "mtime": lambda i: i["mtime"]}.get(s, lambda i: i["name"].lower())
    items.sort(key=key, reverse=(d == "desc"))
    items.sort(key=lambda i: not i["dir"])
    crumbs = [(n, "/".join(parts[: i + 1])) for i, n in enumerate(parts)]
    can_write = u["role"] == "admin" if not parts else level(u, parts[0]) == "write"
    return render(
        request, "files.html", u, items=items, p="/".join(parts), parent="/".join(parts[:-1]), crumbs=crumbs,
        tops=tops(u), q=q, s=s, d=d, can_write=can_write, csrf=u["csrf"], max_mb=C.MAX_UPLOAD // 1048576,
    )


@app.get("/api/folders")
async def folders(request: Request):
    u = await guard(request)
    out = [""] if u["role"] == "admin" else []
    for t in tops(u):
        if level(u, t) != "write":
            continue
        for root, dirs, _ in os.walk(C.DATA_ROOT / t):
            dirs[:] = [x for x in dirs if not is_link(Path(root) / x)]
            rel = Path(root).relative_to(C.DATA_ROOT).as_posix()
            if rel.count("/") < 4:
                out.append(rel)
    return out


@app.post("/api/mkdir")
async def mkdir(request: Request):
    u = await guard(request)
    b = await request.json()
    parts = parts_of(b.get("p", ""))
    need(u, parts, True)
    name = check_name(str(b.get("name", "")).strip())
    target = resolve(parts) / name
    if target.exists():
        raise HTTPException(409, "Вече съществува")
    target.mkdir()
    log(u, "mkdir", request, "/".join([*parts, name]))
    return {"ok": True}


@app.post("/api/rename")
async def rename(request: Request):
    u = await guard(request)
    b = await request.json()
    parts = parts_of(b.get("p", ""))
    if not parts:
        raise HTTPException(400, "Невалиден път")
    need(u, parts, True)
    need_not_top(u, parts)
    name = check_name(str(b.get("name", "")).strip())
    src = resolve(parts)
    dst = src.parent / name
    if not src.exists():
        raise HTTPException(404, "Не е намерено")
    if dst.exists() and not os.path.samefile(src, dst):
        raise HTTPException(409, "Вече съществува")
    os.rename(src, dst)
    if len(parts) == 1:  # folder rights are keyed by top-folder name
        db("UPDATE perms SET folder=? WHERE folder=?", (name, parts[0]))
    log(u, "rename", request, "/".join([*parts[:-1], name]), "от " + "/".join(parts))
    return {"ok": True}


def _move_copy(u, request, b, copy):
    dest = parts_of(b.get("dest", ""))
    need(u, dest, True)
    dd = resolve(dest)
    if not dd.is_dir():
        raise HTTPException(404, "Целевата папка не е намерена")
    for rel in b.get("paths", []):
        parts = parts_of(rel)
        if not parts:
            raise HTTPException(400, "Невалиден път")
        need(u, parts, not copy)
        if not copy:
            need_not_top(u, parts)
            if len(parts) == 1:
                raise HTTPException(400, "Основните папки не се местят")
        src = resolve(parts)
        if not src.exists():
            raise HTTPException(404, "Не е намерено")
        if src.is_dir() and (dd == src or dd.is_relative_to(src)):
            raise HTTPException(400, "Не може да се премести папка в себе си")
        if not dest and not src.is_dir():
            raise HTTPException(400, "Файлове не могат да стоят в основата")
        target = unique(dd, src.name)
        if copy:
            shutil.copytree(src, target) if src.is_dir() else shutil.copy2(src, target)
        else:
            shutil.move(src, target)
        log(u, "copy" if copy else "move", request, "/".join([*dest, target.name]), "от " + "/".join(parts))
    return {"ok": True}


@app.post("/api/move")
async def move(request: Request):
    u = await guard(request)
    return await asyncio.to_thread(_move_copy, u, request, await request.json(), False)


@app.post("/api/copy")
async def copy(request: Request):
    u = await guard(request)
    return await asyncio.to_thread(_move_copy, u, request, await request.json(), True)


@app.post("/api/delete")
async def delete(request: Request):
    u = await guard(request)
    b = await request.json()
    for rel in b.get("paths", []):
        parts = parts_of(rel)
        if not parts:
            raise HTTPException(400, "Невалиден път")
        need(u, parts, True)
        need_not_top(u, parts)
        src = resolve(parts)
        if not src.exists():
            raise HTTPException(404, "Не е намерено")
        tid = db(
            "INSERT INTO trash(orig,name,user,ts,is_dir) VALUES(?,?,?,?,?)",
            ("/".join(parts), src.name, u["username"], time.time(), int(src.is_dir())),
        )
        shutil.move(src, C.TRASH / f"{tid}_{src.name}")
        if len(parts) == 1:
            db("DELETE FROM perms WHERE folder=?", (parts[0],))
        log(u, "delete", request, "/".join(parts))
    return {"ok": True}


@app.get("/api/exists")
async def exists(request: Request, p: str, name: str):
    u = await guard(request)
    parts = parts_of(p)
    need(u, parts)
    return {"exists": (resolve(parts) / check_name(name)).exists()}


@app.put("/api/upload")
async def upload(request: Request, p: str, name: str, mode: str = ""):
    u = await guard(request)
    parts = parts_of(p)
    if not parts:
        raise HTTPException(400, "Файлове не могат да стоят в основата")
    need(u, parts, True)
    check_name(name)
    try:
        too_big = int(request.headers.get("content-length", 0)) > C.MAX_UPLOAD
    except ValueError:
        raise HTTPException(400, "Невалидна заявка")
    if too_big:
        raise HTTPException(413, f"Файлът е по-голям от {C.MAX_UPLOAD // 1048576} MB")
    folder = resolve(parts)
    if not folder.is_dir():
        raise HTTPException(404, "Папката не е намерена")
    target = folder / name
    if target.exists():
        if mode == "skip":
            return {"skipped": True}
        if mode == "both":
            target = unique(folder, name)
        elif mode != "replace":
            raise HTTPException(409, "Вече съществува")
    tmp, size = C.TMP / secrets.token_hex(8), 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > C.MAX_UPLOAD:
                    raise HTTPException(413, f"Файлът е по-голям от {C.MAX_UPLOAD // 1048576} MB")
                f.write(chunk)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    log(u, "upload", request, "/".join([*parts, target.name]), f"{size} B")
    return {"ok": True, "name": target.name}


INLINE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
          ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8", ".csv": "text/plain; charset=utf-8"}


@app.get("/download")
async def download(request: Request, p: str, inline: int = 0):
    u = await guard(request)
    parts = parts_of(p)
    if not parts:
        raise HTTPException(400, "Невалиден път")
    need(u, parts)
    f = resolve(parts)
    if not f.is_file():
        raise HTTPException(404, "Не е намерено")
    log(u, "download", request, "/".join(parts))
    ext = f.suffix.lower()
    if inline and ext in INLINE:
        r = FileResponse(f, media_type=INLINE[ext], content_disposition_type="inline")
        r.headers["Content-Security-Policy"] = "sandbox"
        return r
    return FileResponse(f, media_type="application/octet-stream", filename=f.name, content_disposition_type="attachment")


@app.get("/zip")
async def zip_download(request: Request, p: list[str] = Query()):
    u = await guard(request)
    def build():
        tmp = tempfile.TemporaryFile()  # shortcut: built on disk, then streamed; fine for office-sized folders
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in p:
                parts = parts_of(rel)
                if not parts:
                    raise HTTPException(400, "Невалиден път")
                need(u, parts)
                src = resolve(parts)
                if src.is_file():
                    z.write(src, src.name)
                elif src.is_dir():
                    for root, dirs, fs in os.walk(src):
                        dirs[:] = [d for d in dirs if not is_link(Path(root) / d)]
                        for fn in fs:
                            fp = Path(root) / fn
                            if not is_link(fp):
                                z.write(fp, Path(src.name) / fp.relative_to(src))
                else:
                    raise HTTPException(404, "Не е намерено")
        return tmp

    tmp = await asyncio.to_thread(build)
    log(u, "download", request, ", ".join(p), "zip")
    tmp.seek(0)

    def chunks():
        try:
            while b := tmp.read(1 << 20):
                yield b
        finally:
            tmp.close()

    name = (Path(p[0]).name if len(p) == 1 else "files") + ".zip"
    return StreamingResponse(chunks(), media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ---------- admin ----------

@app.get("/trash", response_class=HTMLResponse)
async def trash_page(request: Request):
    u = await guard(request, True)
    return render(request, "trash.html", u, rows=db("SELECT * FROM trash ORDER BY ts DESC", fetch="all"), csrf=u["csrf"])


@app.post("/api/trash/restore")
async def trash_restore(request: Request):
    u = await guard(request, True)
    r = db("SELECT * FROM trash WHERE id=?", ((await request.json()).get("id"),), "one")
    if not r:
        raise HTTPException(404, "Не е намерено")
    parts = parts_of(r["orig"])
    parent = resolve(parts[:-1])
    parent.mkdir(parents=True, exist_ok=True)
    target = unique(parent, r["name"])
    shutil.move(_trash_file(r), target)
    db("DELETE FROM trash WHERE id=?", (r["id"],))
    log(u, "restore", request, "/".join([*parts[:-1], target.name]))
    return {"ok": True}


@app.post("/api/trash/empty")
async def trash_empty(request: Request):
    u = await guard(request, True)
    for r in db("SELECT * FROM trash", fetch="all"):
        _drop_trash(r)
    log(u, "empty_trash", request)
    return {"ok": True}


def users_page(request, u, msg=""):
    users = db("SELECT * FROM users ORDER BY username", fetch="all")
    perms = {(r["user_id"], r["folder"]): r["level"] for r in db("SELECT * FROM perms", fetch="all")}
    folders = sorted(e.name for e in os.scandir(C.DATA_ROOT) if e.is_dir() and e.name[0] not in "_.")
    return render(request, "users.html", u, users=users, perms=perms, folders=folders, msg=msg, csrf=u["csrf"])


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    return users_page(request, await guard(request, True))


@app.post("/admin/users/create", response_class=HTMLResponse)
async def admin_create(request: Request):
    u = await guard(request, True)
    form = await request.form()
    name = str(form.get("username", "")).strip()
    role = "admin" if form.get("role") == "admin" else "user"
    if not winuser.NAME_OK.match(name) or db("SELECT 1 FROM users WHERE username=?", (name,), "one"):
        return users_page(request, u, "Невалидно или заето име (латински букви, цифри, . _ -, до 20 знака).")
    pw = new_password()
    create_user(name, pw, role)
    log(u, "user_create", request, detail=f"{name} ({role})")
    ok = await asyncio.to_thread(winuser.create, name, pw)
    note = "" if ok else " ВНИМАНИЕ: Windows профилът не е създаден, диск O: няма да работи за него."
    return users_page(request, u, f"Създаден: {name}, парола: {pw} (за портала и за диск O:, показва се само сега).{note}")


@app.post("/admin/users/{uid}/toggle", response_class=HTMLResponse)
async def admin_toggle(request: Request, uid: int):
    u = await guard(request, True)
    if uid == u["id"]:
        return users_page(request, u, "Не можете да изключите себе си.")
    db("UPDATE users SET active=1-active WHERE id=?", (uid,))
    db("DELETE FROM sessions WHERE user_id=?", (uid,))
    row = db("SELECT username,active FROM users WHERE id=?", (uid,), "one")
    if row:
        await asyncio.to_thread(winuser.set_active, row["username"], bool(row["active"]))
    log(u, "user_toggle", request, detail=str(uid))
    return users_page(request, u, "Готово.")


@app.post("/admin/users/{uid}/reset", response_class=HTMLResponse)
async def admin_reset(request: Request, uid: int):
    u = await guard(request, True)
    row = db("SELECT username FROM users WHERE id=?", (uid,), "one")
    if not row:
        raise HTTPException(404, "Не е намерено")
    pw = new_password()
    if not await set_password(uid, row["username"], pw):
        return users_page(request, u, WIN_REFUSED)
    log(u, "password_reset", request, detail=row["username"])
    return users_page(request, u, f"Нова парола за {row['username']}: {pw} (за портала и за диск O:, показва се само сега).")


@app.post("/admin/users/{uid}/setpw", response_class=HTMLResponse)
async def admin_setpw(request: Request, uid: int):
    u = await guard(request, True)
    pw = str((await request.form()).get("pw", ""))
    row = db("SELECT username FROM users WHERE id=?", (uid,), "one")
    if not row:
        raise HTTPException(404, "Не е намерено")
    if not MIN_PW <= len(pw) <= MAX_PW:
        return users_page(request, u, PW_LEN)
    if not await set_password(uid, row["username"], pw, keep=request.cookies.get("sid") if uid == u["id"] else None):
        return users_page(request, u, WIN_REFUSED)
    log(u, "password_set", request, detail=row["username"])
    return users_page(request, u, f"Паролата на {row['username']} е сменена (за портала и за диск O:).")


# ---------- own password ----------

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    u = await guard(request)
    return render(request, "account.html", u, msg="", csrf=u["csrf"])


@app.post("/account/password", response_class=HTMLResponse)
async def account_password(request: Request):
    u = await guard(request)
    form = await request.form()
    old, new, again = (str(form.get(k, "")) for k in ("old", "new", "again"))
    keys = (("u", u["username"].lower()),)
    msg = ""
    if locked(*keys):
        msg = "Твърде много опити. Опитайте след 5 минути."
    elif not check_login(u["username"], old):
        register_fail(*keys)
        msg = "Сегашната парола не е вярна."
    elif new != again:
        msg = "Новите пароли не съвпадат."
    elif not MIN_PW <= len(new) <= MAX_PW:
        msg = PW_LEN
    elif new == old:
        msg = "Новата парола трябва да е различна."
    elif not await set_password(u["id"], u["username"], new, keep=request.cookies.get("sid")):
        msg = WIN_REFUSED
    else:
        clear_fails(*keys)
        log(u, "password_change", request)
        msg = "Паролата е сменена (за портала и за диск O:). На другите компютри влезте с новата."
    return render(request, "account.html", u, 400 if "сменена" not in msg else 200, msg=msg, csrf=u["csrf"])


@app.post("/admin/users/{uid}/perms", response_class=HTMLResponse)
async def admin_perms(request: Request, uid: int):
    u = await guard(request, True)
    form = await request.form()
    real = {e.name for e in os.scandir(C.DATA_ROOT) if e.is_dir() and e.name[0] not in "_."}
    changes = []
    for f, lv in zip(form.getlist("f"), form.getlist("l")):
        if f in real and lv in ("none", "read", "write"):
            db("INSERT OR REPLACE INTO perms VALUES(?,?,?)", (uid, f, lv))
            changes.append(f"{f}={lv}")
    log(u, "perms", request, detail=f"user {uid}: " + ", ".join(changes))
    missing = set()
    for c in changes:
        missing.update(await asyncio.to_thread(ntfs.sync, c.split("=")[0]))
    note = f" Няма Windows профил за: {', '.join(sorted(missing))}." if missing else ""
    return users_page(request, u, "Правата са запазени." + note)


@app.get("/log", response_class=HTMLResponse)
async def log_page(request: Request, user: str = "", action: str = "", frm: str = "", to: str = ""):
    u = await guard(request, True)
    sql, args = "SELECT * FROM log WHERE 1=1", []
    if user:
        sql += " AND user=?"; args.append(user)
    if action:
        sql += " AND action=?"; args.append(action)
    for val, op, add in ((frm, ">=", 0), (to, "<", 86400)):
        try:
            args.append(datetime.strptime(val, "%Y-%m-%d").timestamp() + add)
            sql += f" AND ts{op}?"
        except ValueError:
            pass  # empty or malformed date: no filter
    rows = db(sql + " ORDER BY id DESC LIMIT 500", args, "all")
    return render(request, "log.html", u, rows=rows, user_f=user, action_f=action, frm=frm, to=to,
                  actions=[r[0] for r in db("SELECT DISTINCT action FROM log", fetch="all")],
                  names=[r[0] for r in db("SELECT username FROM users", fetch="all")], ts=lambda t: datetime.fromtimestamp(t).strftime("%d.%m.%Y %H:%M:%S"))


@app.get("/status", response_class=HTMLResponse)
async def status(request: Request):
    u = await guard(request, True)

    def run(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except Exception:
            return ""

    total, _, free = shutil.disk_usage(C.DATA_ROOT)
    backup = {"ok": False, "msg": "Няма данни за архив"}
    try:
        b = json.loads(C.STATUS_FILE.read_text(encoding="utf-8"))
        age = (time.time() - b["time"]) / 3600
        backup = {"ok": bool(b["ok"]) and age < 36, "msg": f"{datetime.fromtimestamp(b['time']):%d.%m.%Y %H:%M} · {b.get('message', '')}"}
    except Exception:
        pass
    checks = [
        ("Свободно място", f"{free / 2**30:.0f} GB от {total / 2**30:.0f} GB", free / total > 0.15),
        ("SQL Server", "работи" if "RUNNING" in run("sc", "query", "MSSQL$SQLEXPRESS") else "не работи", "RUNNING" in run("sc", "query", "MSSQL$SQLEXPRESS")),
        ("Споделена папка", "има" if "Office" in run("net", "share") else "липсва", "Office" in run("net", "share")),
        ("Последен архив", backup["msg"], backup["ok"]),
        ("Портал", f"версия {VERSION}, работи {(time.time() - START) / 3600:.1f} ч", True),
    ]
    return render(request, "status.html", u, checks=checks)


# ---------- programs and client files ----------

def app_list():
    """Launchable files in _Програми: loose ones and those one folder down."""
    out = []
    if not PROG.is_dir():
        return out
    for e in sorted(os.scandir(PROG), key=lambda e: e.name.lower()):
        if e.name[0] in "_." or is_link(e.path):
            continue
        files = [(e, "")] if e.is_file() else [(f, e.name) for f in sorted(os.scandir(e.path), key=lambda f: f.name.lower())] if e.is_dir() else []
        for f, group in files:
            ext = os.path.splitext(f.name)[1].lower()
            if f.is_file() and ext in APP_EXT and "unins" not in f.name.lower():
                out.append({"name": os.path.splitext(f.name)[0], "group": group, "ext": ext[1:], "rel": (group + "/" if group else "") + f.name,
                            "link": "officeapp:///?p=" + quote((group + "/" if group else "") + f.name, safe="")})
    return out[:60]

START_DIRS = [Path(os.environ[k]) / "Microsoft/Windows/Start Menu/Programs" for k in ("ProgramData", "APPDATA") if os.environ.get(k)]


def start_menu():
    """Installed programs as Start Menu shortcuts: [{name, rel, target}] (rel = '<root index>/<path>')."""
    found = []
    for i, root in enumerate(START_DIRS):
        for f in root.rglob("*.lnk") if root.is_dir() else []:
            if "uninstall" not in f.name.lower() and "unins" not in f.name.lower():
                found.append({"name": f.stem, "rel": f"{i}/{f.relative_to(root).as_posix()}", "target": ""})
    found.sort(key=lambda a: a["name"].lower())
    for a, t in zip(found, lnk_targets([str(START_DIRS[int(a["rel"][0])] / a["rel"][2:]) for a in found])):
        a["target"] = t
    return found


def lnk_targets(paths):
    """Shortcut targets, one per path (one PowerShell call); [] when it fails."""
    ps = "$s=New-Object -ComObject WScript.Shell; $a=$env:LNKS|ConvertFrom-Json; foreach($l in $a){$s.CreateShortcut($l).TargetPath}"
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20,
                              env={**os.environ, "LNKS": json.dumps(paths)}).stdout.splitlines() if paths else []
    except Exception:
        return []


def start_src(rel):
    """The Start Menu .lnk for rel '<root index>/<path>', or 400."""
    idx, _, sub = rel.partition("/")
    if not idx.isdigit() or int(idx) >= len(START_DIRS) or not sub.lower().endswith(".lnk"):
        raise HTTPException(400, "Невалидна програма")
    root = START_DIRS[int(idx)].resolve()
    src = (root / sub).resolve()
    if not src.is_relative_to(root) or not src.is_file():
        raise HTTPException(400, "Невалидна програма")
    return src


@app.get("/programs", response_class=HTMLResponse)
async def programs(request: Request, msg: str = ""):
    u = await guard(request)
    return render(request, "programs.html", u, apps=app_list(), msg=msg, csrf=u["csrf"],
                  installed=start_menu() if u["role"] == "admin" else [])


@app.post("/api/programs/add")
async def programs_add(request: Request):
    u = await guard(request, True)
    src = start_src(str((await request.form()).get("rel", "")))
    PROG.mkdir(exist_ok=True)
    dst = unique(PROG, src.name)
    shutil.copy2(src, dst)
    log(u, "program.add", request, dst.name)
    return RedirectResponse("/programs?msg=" + quote(f"Добавена: {src.stem}"), 303)


COPY_MAX = 1536 * 1024 ** 2


def copy_app(folder, dest):
    """Copy folder to dest unless it is bigger than COPY_MAX; returns False when too big."""
    size = 0
    for f in folder.rglob("*"):
        size += f.stat().st_size if f.is_file() else 0
        if size > COPY_MAX:
            return False
    shutil.copytree(folder, dest)
    return True


@app.post("/api/programs/copy")
async def programs_copy(request: Request):
    """Copy the program's own folder to the server and add a tile that starts it from there (portable apps only)."""
    u = await guard(request, True)
    src = start_src(str((await request.form()).get("rel", "")))
    target = (lnk_targets([str(src)]) or [""])[0]
    exe = Path(target)
    folder = exe.parent
    # refuse Windows itself, drive roots and the Program Files folders: only an app's own folder
    if (not target.lower().endswith(".exe") or not exe.is_file() or folder == Path(folder.anchor)
            or folder.name.lower() in ("program files", "program files (x86)")
            or folder.resolve().is_relative_to(Path(os.environ.get("SystemRoot", "C:/Windows")).resolve())):
        raise HTTPException(400, "Тази програма не може да се копира")
    (PROG / "_files").mkdir(parents=True, exist_ok=True)
    dest = unique(PROG / "_files", src.stem)
    if not await asyncio.to_thread(copy_app, folder, dest):
        raise HTTPException(400, "Папката е твърде голяма (над 1,5 GB)")
    # %~dp0 keeps Cyrillic out of the file: it is the folder the launcher sits in
    launcher = unique(PROG, src.stem + ".cmd")
    launcher.write_bytes(f'@start "" /d "%~dp0_files\{dest.name}" "{exe.name}"\r\n'.encode("ascii", "replace"))
    log(u, "program.copy", request, dest.name)
    return RedirectResponse("/programs?msg=" + quote(f"Копирана на сървъра: {src.stem}"), 303)


@app.post("/api/programs/remove")
async def programs_remove(request: Request):
    u = await guard(request, True)
    rel = str((await request.form()).get("rel", ""))
    root = PROG.resolve()
    f = (root / rel).resolve()
    # only shortcuts: real files (portable apps) are never deleted from here
    if not rel.lower().endswith(".lnk") or not f.is_relative_to(root) or not f.is_file():
        raise HTTPException(400, "Невалидна програма")
    f.unlink()
    log(u, "program.remove", request, f.name)
    return RedirectResponse("/programs?msg=" + quote(f"Премахната: {f.stem}"), 303)


@app.get("/client/{name}")
async def client_file(request: Request, name: str):
    await guard(request)
    if name not in ("setup.cmd", "root.crt"):
        raise HTTPException(404, "Не е намерено")
    f = C.CLIENT_DIR / name
    if not f.is_file():
        raise HTTPException(404, "Файлът още не е готов")
    return FileResponse(f, filename=name, media_type="application/octet-stream")
