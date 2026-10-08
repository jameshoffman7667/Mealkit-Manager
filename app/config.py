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


def secret_key() -> str:
    """Operator-supplied key that protects stored service logins. Empty means linking is disabled."""
    return os.environ.get("SECRET_KEY", "")


def automation_enabled() -> bool:
    return os.environ.get("AUTOMATION", "on").strip().lower() != "off"


def sync_hours() -> float:
    try:
        return max(0.0, float(os.environ.get("SYNC_HOURS", "6")))
    except ValueError:
        return 6.0


def debug_capture() -> bool:
    """When on, connectors save the text of each page they read to DATA_DIR/debug (contains personal data)."""
    return os.environ.get("CONNECTOR_DEBUG", "").strip().lower() in ("1", "true", "on", "yes")
