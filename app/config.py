"""Runtime configuration. Everything is read at call time so tests can change the environment."""
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent


def version() -> str:
    try:
        return (BASE_DIR.parent / "VERSION").read_text().strip()
    except OSError:
        return "dev"


def data_dir() -> Path:
    p = Path(os.environ.get("DATA_DIR", "./data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "mealkit.db"


def app_password() -> str:
    return os.environ.get("APP_PASSWORD", "")


def horizon_default() -> int:
    try:
        return max(1, min(52, int(os.environ.get("HORIZON_WEEKS", "12"))))
    except ValueError:
        return 12


def today() -> date:
    tz = ZoneInfo(os.environ.get("TZ", "America/Toronto"))
    return datetime.now(tz).date()
