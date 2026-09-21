"""Filesystem locations: base dir, config file, bundled assets."""
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).parent
else:
    # dlp_gui/paths.py -> dlp_gui/ -> project root
    BASE = Path(__file__).resolve().parent.parent

CONFIG_FILE = BASE / "dlp-ui-config.json"


def resource_path(name: str) -> Path:
    """Locate a bundled asset, whether running from source or frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return BASE / name


QRCODE_IMAGE = resource_path("qrcode.png")


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)
