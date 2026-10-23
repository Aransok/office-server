import pytest
from fastapi.testclient import TestClient

from app import config as C
from app.db import db
from app.main import app

from .conftest import login


def test_login_required():
    c = TestClient(app, follow_redirects=False)
    assert c.get("/files").status_code == 303
    assert c.get("/api/folders").status_code == 401
    assert c.get("/download?p=Pub/p.txt").status_code == 401


def test_login_bad_password_and_lockout():
    login("bob")
    c = TestClient(app, follow_redirects=False)
    for _ in range(5):
        assert c.post("/login", data={"username": "bob", "password": "x"}).status_code == 401
    assert c.post("/login", data={"username": "bob", "password": "pw"}).status_code == 429


def test_cookie_flags():
    from app.security import create_user
    create_user("z", "pw")
    r = TestClient(app, follow_redirects=False).post("/login", data={"username": "z", "password": "pw"})
    h = r.headers["set-cookie"].lower()
    assert "httponly" in h and "samesite=strict" in h


def test_security_headers(admin):
    r = admin.get("/files")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("p", ["../x", "Pub/../Acc", "/etc", "C:/Windows", "Pub/..", "\\\\srv\\share", "Pub/a:b", "Pub/CON", "_Корзина", ".tmp", "Pub/x.txt:s"])
def test_path_traversal_rejected(admin, p):
    assert admin.get("/files", params={"p": p}).status_code in (400, 404)
    assert admin.get("/download", params={"p": p}).status_code in (400, 404)


def test_permissions_listing_and_access(bob):
    assert "Pub" in bob.get("/files").text and ">Acc<" not in bob.get("/files").text
    assert bob.get("/files?p=Acc").status_code == 403
    assert bob.get("/download?p=Acc/a.txt").status_code == 403
    assert bob.get("/download?p=Pub/p.txt").status_code == 200


def test_search_does_not_leak(bob):
    assert "Acc/a.txt" not in bob.get("/files?q=a.txt").text


def test_read_only_user_cannot_write(reader):
    assert reader.post("/api/mkdir", json={"p": "Pub", "name": "n"}, headers=reader.csrf).status_code == 403
    assert reader.post("/api/delete", json={"paths": ["Pub/p.txt"]}, headers=reader.csrf).status_code == 403
    assert reader.put("/api/upload?p=Pub&name=n.txt", content=b"x", headers=reader.csrf).status_code == 403


def test_csrf_required(bob):
    assert bob.post("/api/mkdir", json={"p": "Pub", "name": "n"}).status_code == 403
    assert bob.post("/api/mkdir", json={"p": "Pub", "name": "n"}, headers={"X-CSRF": "bad"}).status_code == 403
    assert bob.post("/api/mkdir", json={"p": "Pub", "name": "n"}, headers=bob.csrf).status_code == 200


def test_user_cannot_touch_top_level_or_root(bob):
    assert bob.post("/api/delete", json={"paths": ["Pub"]}, headers=bob.csrf).status_code == 403
    assert bob.post("/api/rename", json={"p": "Pub", "name": "X"}, headers=bob.csrf).status_code == 403
    assert bob.post("/api/mkdir", json={"p": "", "name": "New"}, headers=bob.csrf).status_code == 403


def test_admin_creates_top_folder_and_user_perms(admin):
    assert admin.post("/api/mkdir", json={"p": "", "name": "Склад"}, headers=admin.csrf).status_code == 200
    assert (C.DATA_ROOT / "Склад").is_dir()


def test_mkdir_rename_bad_names(bob):
    for n in ["a/b", "..", "CON", "x.", "a:b", ""]:
        assert bob.post("/api/mkdir", json={"p": "Pub", "name": n}, headers=bob.csrf).status_code == 400


def test_upload_conflict_modes_and_limit(bob):
    u = "/api/upload?p=Pub&name=n.txt"
    assert bob.put(u, content=b"1", headers=bob.csrf).status_code == 200
    assert bob.put(u, content=b"2", headers=bob.csrf).status_code == 409
    assert bob.put(u + "&mode=replace", content=b"3", headers=bob.csrf).status_code == 200
    assert (C.DATA_ROOT / "Pub" / "n.txt").read_text() == "3"
    assert bob.put(u + "&mode=both", content=b"4", headers=bob.csrf).json()["name"] == "n (2).txt"
    assert bob.put(u + "&mode=skip", content=b"5", headers=bob.csrf).json()["skipped"]
    assert bob.put("/api/upload?p=Pub&name=big.bin", content=b"x" * (C.MAX_UPLOAD + 1), headers=bob.csrf).status_code == 413
    assert not (C.DATA_ROOT / "Pub" / "big.bin").exists()
    assert list(C.TMP.iterdir()) == []


def test_upload_into_root_rejected(admin):
    assert admin.put("/api/upload?p=&name=x.txt", content=b"x", headers=admin.csrf).status_code == 400


def test_delete_goes_to_trash_and_restore_admin_only(admin, bob):
    assert bob.post("/api/delete", json={"paths": ["Pub/p.txt"]}, headers=bob.csrf).status_code == 200
    assert not (C.DATA_ROOT / "Pub" / "p.txt").exists()
    rid = db("SELECT id FROM trash", fetch="one")["id"]
    assert bob.post("/api/trash/restore", json={"id": rid}, headers=bob.csrf).status_code == 403
    assert admin.post("/api/trash/restore", json={"id": rid}, headers=admin.csrf).status_code == 200
    assert (C.DATA_ROOT / "Pub" / "p.txt").read_text() == "public"


def test_move_and_copy_respect_permissions(bob):
    assert bob.post("/api/move", json={"paths": ["Pub/p.txt"], "dest": "Acc"}, headers=bob.csrf).status_code == 403
    assert bob.post("/api/copy", json={"paths": ["Acc/a.txt"], "dest": "Pub"}, headers=bob.csrf).status_code == 403
    bob.post("/api/mkdir", json={"p": "Pub", "name": "sub"}, headers=bob.csrf)
    assert bob.post("/api/move", json={"paths": ["Pub/p.txt"], "dest": "Pub/sub"}, headers=bob.csrf).status_code == 200
    assert (C.DATA_ROOT / "Pub" / "sub" / "p.txt").exists()
    assert bob.post("/api/move", json={"paths": ["Pub/sub"], "dest": "Pub/sub"}, headers=bob.csrf).status_code == 400


def test_zip_checks_permission_per_item(bob):
    assert bob.get("/zip?p=Pub/p.txt").status_code == 200
    assert bob.get("/zip?p=Pub/p.txt&p=Acc/a.txt").status_code == 403


def test_download_is_attachment_and_inline_sandboxed(bob):
    r = bob.get("/download?p=Pub/p.txt")
    assert "attachment" in r.headers["content-disposition"]
    (C.DATA_ROOT / "Pub" / "x.html").write_text("<script>alert(1)</script>")
    assert "attachment" in bob.get("/download?p=Pub/x.html&inline=1").headers["content-disposition"]


def test_admin_pages_forbidden_for_users(bob):
    for u in ("/admin/users", "/log", "/trash", "/status"):
        assert bob.get(u).status_code == 403


def test_admin_user_management(admin):
    r = admin.post("/admin/users/create", data={"username": "new", "csrf": admin.csrf["X-CSRF"]})
    assert "парола:" in r.text
    uid = db("SELECT id FROM users WHERE username='new'", fetch="one")["id"]
    admin.post(f"/admin/users/{uid}/perms", data={"csrf": admin.csrf["X-CSRF"], "f": ["Pub", "Evil"], "l": ["write", "write"]})
    assert db("SELECT folder FROM perms WHERE user_id=?", (uid,), "all")[0]["folder"] == "Pub"
    assert len(db("SELECT 1 FROM perms WHERE user_id=?", (uid,), "all")) == 1  # unknown folder ignored
    assert admin.post("/admin/users/create", data={"username": "x"}).status_code == 403  # no csrf


def test_disabled_user_loses_session(admin, bob):
    uid = db("SELECT id FROM users WHERE username='bob'", fetch="one")["id"]
    admin.post(f"/admin/users/{uid}/toggle", data={"csrf": admin.csrf["X-CSRF"]})
    assert bob.get("/files").status_code == 303


def test_activity_logged(bob, admin):
    bob.get("/download?p=Pub/p.txt")
    assert "download" in admin.get("/log?user=bob").text


def test_symlink_not_followed(admin):
    import os
    link = C.DATA_ROOT / "Pub" / "lnk"
    try:
        os.symlink(C.DATA_ROOT.parent, link, target_is_directory=True)
    except OSError:
        pytest.skip("no symlink privilege")
    assert admin.get("/files?p=Pub/lnk").status_code == 400
    assert "lnk" not in admin.get("/files?p=Pub").text


def test_rename_clash_and_top_rename_keeps_perms(admin, bob):
    admin.post("/api/mkdir", json={"p": "Pub", "name": "A"}, headers=admin.csrf)
    admin.post("/api/mkdir", json={"p": "Pub", "name": "B"}, headers=admin.csrf)
    assert admin.post("/api/rename", json={"p": "Pub/A", "name": "B"}, headers=admin.csrf).status_code == 409
    assert admin.post("/api/rename", json={"p": "Pub", "name": "Pub2"}, headers=admin.csrf).status_code == 200
    assert bob.get("/files?p=Pub2").status_code == 200  # bob's rights followed the rename


def test_zip_of_folder(bob):
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(bob.get("/zip?p=Pub").content))
    assert z.namelist() == ["Pub/p.txt"]


def test_client_files_need_login_and_whitelist(admin):
    (C.CLIENT_DIR).mkdir(exist_ok=True)
    (C.CLIENT_DIR / "setup.cmd").write_text("@echo off")
    anon = TestClient(app, follow_redirects=False)
    assert anon.get("/client/setup.cmd").status_code in (303, 401)
    assert admin.get("/client/setup.cmd").status_code == 200
    assert admin.get("/client/other.txt").status_code == 404
    assert admin.get("/client/root.crt").status_code == 404  # not generated yet in tests


def test_ntfs_sync_grants_by_level(monkeypatch):
    from app import ntfs
    calls = []
    monkeypatch.setattr(C, "NTFS_RIGHTS", True)
    monkeypatch.setattr(ntfs, "_icacls", lambda *a: calls.append(a) or a[-1].split(":")[0] != "ghost")
    login("w", perms={"Acc": "write"}); login("r", perms={"Acc": "read"}); login("n", perms={"Acc": "none"})
    login("ghost", perms={"Acc": "read"}); login("boss", role="admin")
    missing = ntfs.sync("Acc")
    grants = {a[-1] for a in calls if a[1] == "/grant"}
    assert grants == {"w:(OI)(CI)M", "r:(OI)(CI)RX", "ghost:(OI)(CI)RX", "boss:(OI)(CI)M"}
    assert missing == ["ghost"]


def test_user_pages_sync_windows_account(admin, monkeypatch):
    from app import winuser
    calls = []
    monkeypatch.setattr(C, "NTFS_RIGHTS", True)
    monkeypatch.setattr(winuser, "_net", lambda *a: calls.append(a) or True)
    r = admin.post("/admin/users/create", data={"username": "anna", "csrf": admin.csrf["X-CSRF"]})
    assert "Създаден: anna" in r.text and calls[0][:2] == ("user", "anna") and calls[0][-1] == "/add"
    bad = admin.post("/admin/users/create", data={"username": "../x /add", "csrf": admin.csrf["X-CSRF"]})
    assert "Невалидно" in bad.text
    uid = db("SELECT id FROM users WHERE username='anna'", fetch="all")[0]["id"]
    admin.post(f"/admin/users/{uid}/toggle", data={"csrf": admin.csrf["X-CSRF"]})
    assert ("user", "anna", "/active:no") in calls


def test_user_changes_own_password(bob, monkeypatch):
    from app import winuser
    calls = []
    monkeypatch.setattr(C, "NTFS_RIGHTS", True)
    monkeypatch.setattr(winuser, "_net", lambda *a: calls.append(a) or True)
    csrf = bob.csrf["X-CSRF"]
    other = TestClient(app, follow_redirects=False)
    other.post("/login", data={"username": "bob", "password": "pw"})  # a second session
    def change(**f):
        return bob.post("/account/password", data={"csrf": csrf, "old": "pw", "new": "newpass99", "again": "newpass99", **f})
    assert "не е вярна" in change(old="wrong").text
    assert "не съвпадат" in change(again="other999").text
    assert "между 8" in change(new="short", again="short").text
    assert not calls  # nothing reached Windows
    assert "е сменена" in change().text
    assert ("user", "bob", "newpass99", "/add") in calls
    assert bob.get("/files").status_code == 200  # this session survives
    assert other.get("/files").status_code == 303  # the other one is logged out
    assert TestClient(app).post("/login", data={"username": "bob", "password": "newpass99"}).status_code == 200


def test_windows_refusal_changes_nothing(bob, monkeypatch):
    from app import winuser
    monkeypatch.setattr(C, "NTFS_RIGHTS", True)
    monkeypatch.setattr(winuser, "_net", lambda *a: False)
    r = bob.post("/account/password", data={"csrf": bob.csrf["X-CSRF"], "old": "pw", "new": "newpass99", "again": "newpass99"})
    assert "Windows отказа" in r.text
    assert TestClient(app).post("/login", data={"username": "bob", "password": "pw"}).status_code == 200  # old one still works


def test_admin_sets_password(admin, bob):
    uid = db("SELECT id FROM users WHERE username='bob'", fetch="all")[0]["id"]
    csrf = admin.csrf["X-CSRF"]
    assert "между 8" in admin.post(f"/admin/users/{uid}/setpw", data={"csrf": csrf, "pw": "abc"}).text
    assert "е сменена" in admin.post(f"/admin/users/{uid}/setpw", data={"csrf": csrf, "pw": "chosen-pass1"}).text
    assert bob.get("/files").status_code == 303  # bob was logged out
    assert TestClient(app).post("/login", data={"username": "bob", "password": "chosen-pass1"}).status_code == 200
    assert bob.post(f"/admin/users/{uid}/setpw", data={"csrf": "x", "pw": "chosen-pass2"}).status_code in (303, 403)


def test_programs_page_lists_launchable_files_only(bob):
    from app.main import PROG
    (PROG / "Expecta").mkdir(parents=True, exist_ok=True)
    (PROG / "Expecta" / "Expecta.exe").write_text("x")
    (PROG / "Expecta" / "unins000.exe").write_text("x")
    (PROG / "Expecta" / "data.txt").write_text("x")
    (PROG / "_launcher").mkdir(exist_ok=True)
    (PROG / "_launcher" / "zzsecret.exe").write_text("x")
    t = bob.get("/programs").text
    assert "officeapp:///?p=Expecta%2FExpecta.exe" in t
    assert "unins000" not in t and "data.txt" not in t and "zzsecret" not in t
    import shutil
    shutil.rmtree(PROG)


def test_program_add_from_start_menu(admin, tmp_path, monkeypatch):
    from app import main
    root = tmp_path / "sm"
    (root / "Scan").mkdir(parents=True)
    (root / "Scan" / "Scanner.lnk").write_bytes(b"x")
    monkeypatch.setattr(main, "START_DIRS", [root])
    tok = admin.get("/programs").text.split('name="csrf" value="')[1].split('"')[0]
    for bad in ("0/../x.lnk", "0/Scan/Scanner.exe", "9/Scan/Scanner.lnk", "0/Missing.lnk"):
        assert admin.post("/api/programs/add", data={"csrf": tok, "rel": bad}, follow_redirects=False).status_code == 400
    r = admin.post("/api/programs/add", data={"csrf": tok, "rel": "0/Scan/Scanner.lnk"}, follow_redirects=False)
    assert r.status_code == 303 and (main.PROG / "Scanner.lnk").is_file()
