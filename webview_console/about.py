from __future__ import annotations

from pathlib import Path

from app_metadata import APP_NAME, APP_VERSION, GITHUB_URL, GITEE_URL, UPDATE_SOURCE_URLS


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def build_about_payload() -> dict[str, str]:
    return {
        "appName": f"{APP_NAME} Webview Console",
        "version": APP_VERSION,
        "githubUrl": GITHUB_URL,
        "giteeUrl": GITEE_URL,
        "updateSourceUrls": list(UPDATE_SOURCE_URLS),
        "readme": _read_text(PROJECT_ROOT / "README.md"),
        "guiReadme": _read_text(PROJECT_ROOT / "GUI_README.md"),
    }
