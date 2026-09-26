"""Runtime paths. Inside the HA add-on everything lives under /data (persistent)."""

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("REPAGG_DATA", Path(__file__).resolve().parents[3] / "data"))
DB_PATH = DATA_DIR / "repagg.db"
PHOTO_DIR = DATA_DIR / "photos"
RAW_DIR = DATA_DIR / "raw"
STATIC_DIR = Path(os.environ.get("REPAGG_STATIC", Path(__file__).resolve().parents[3] / "web" / "dist"))


def addon_options() -> dict:
    """Options set in the HA add-on UI (written by the Supervisor)."""
    path = Path("/data/options.json")
    return json.loads(path.read_text()) if path.exists() else {}
