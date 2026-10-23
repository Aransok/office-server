import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

_env = BASE / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DATA_ROOT = Path(os.environ.get("DATA_ROOT", r"C:\OfficeData")).resolve()
DB_PATH = Path(os.environ.get("DB_PATH", BASE / "portal.db"))
MAX_UPLOAD = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
NTFS_RIGHTS = os.environ.get("NTFS_RIGHTS", "0") == "1"  # server .env sets 1; tests and laptops leave it off
LOG_DIR = Path(os.environ.get("LOG_DIR", r"C:\OfficeServer\logs"))
STATUS_FILE = Path(os.environ.get("STATUS_FILE", r"C:\OfficeServer\logs\backup-status.json"))
CLIENT_DIR = Path(os.environ.get("CLIENT_DIR", r"C:\OfficeServer\client"))

TRASH = DATA_ROOT / "_Корзина"
TMP = DATA_ROOT / ".tmp"
TRASH_DAYS = 30
LOG_DAYS = 365
