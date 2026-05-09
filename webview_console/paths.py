from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return bundle_root()


def frontend_dist_dir() -> Path:
    return project_root() / "webui" / "dist"


def app_storage_dir() -> Path:
    app_name = "AnnualReportSpiderGUI"
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / app_name
    return Path.home() / f".{app_name}"


def config_path() -> Path:
    return app_storage_dir() / "webview_config.json"


def history_path() -> Path:
    return app_storage_dir() / "run_history.json"
