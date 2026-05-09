from __future__ import annotations

import os
import webbrowser
from pathlib import Path


def resolve_project_path(project_root: str, raw: str) -> Path:
    path = Path((raw or "").strip()).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path(project_root) / path).resolve()


def open_path(path: Path) -> None:
    target = path
    if not target.exists():
        target = target.parent
    if os.name == "nt":
        os.startfile(str(target))
        return
    webbrowser.open(target.as_uri())
