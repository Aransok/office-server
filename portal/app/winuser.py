"""Keep a Windows account in step with each portal user, same name and password, so one password covers O: and the portal."""
import re
import subprocess

from . import config as C

NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$")


def _net(*a):
    return subprocess.run(["net", *a], capture_output=True, text=True).returncode == 0


def create(name, pw):
    """Create the account, or just set the password if it exists. False when Windows refused. No-op unless NTFS_RIGHTS=1."""
    if not C.NTFS_RIGHTS:
        return True
    # shortcut: the password is briefly visible in the process list to local admins; fine on a one-purpose server
    ok = _net("user", name, pw, "/add") or _net("user", name, pw)
    _net("localgroup", "OfficeUsers", name, "/add")  # fails harmlessly when already a member
    return ok


def set_active(name, on):
    if C.NTFS_RIGHTS:
        _net("user", name, f"/active:{'yes' if on else 'no'}")
