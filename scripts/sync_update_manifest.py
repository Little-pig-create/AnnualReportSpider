from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_metadata import (
    APP_VERSION,
    UPDATE_PRIMARY_CHANNEL,
    build_primary_download_url,
    build_release_download_urls,
)

APP_METADATA_PATH = PROJECT_ROOT / "app_metadata.py"
UPDATE_MANIFEST_PATHS = (
    PROJECT_ROOT / "update.json",
    PROJECT_ROOT / "config" / "update.json.example",
)
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync app version into update manifests."
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Optional version like 4.3.0. When omitted, syncs current APP_VERSION only.",
    )
    return parser.parse_args()


def validate_version(version: str) -> str:
    value = version.strip()
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError("version must use major.minor.patch format, for example 4.3.0")
    return value


def file_version_from_app_version(version: str) -> str:
    return f"{version}.0"


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(content)


def update_app_metadata(version: str) -> bool:
    file_version = file_version_from_app_version(version)
    content = APP_METADATA_PATH.read_text(encoding="utf-8")

    updated = re.sub(
        r'^APP_VERSION = ".*"$',
        f'APP_VERSION = "{version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    updated = re.sub(
        r'^APP_FILE_VERSION = ".*"$',
        f'APP_FILE_VERSION = "{file_version}"',
        updated,
        count=1,
        flags=re.MULTILINE,
    )

    if updated == content:
        return False

    write_text(APP_METADATA_PATH, updated)
    return True


def sync_update_manifest(path: Path, version: str) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_url = build_primary_download_url(version)
    expected_downloads = build_release_download_urls(version)
    changed = False

    if payload.get("version") != version:
        payload["version"] = version
        changed = True

    if payload.get("url") != expected_url:
        payload["url"] = expected_url
        changed = True

    if payload.get("downloadUrl") != expected_url:
        payload["downloadUrl"] = expected_url
        changed = True

    if payload.get("primaryChannel") != UPDATE_PRIMARY_CHANNEL:
        payload["primaryChannel"] = UPDATE_PRIMARY_CHANNEL
        changed = True

    if payload.get("downloads") != expected_downloads:
        payload["downloads"] = expected_downloads
        changed = True

    if not changed:
        return False

    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_text(path, serialized)
    return True


def main() -> int:
    args = parse_args()
    version = validate_version(args.version) if args.version else APP_VERSION

    updated_paths: list[Path] = []
    if args.version and update_app_metadata(version):
        updated_paths.append(APP_METADATA_PATH)

    for path in UPDATE_MANIFEST_PATHS:
        if sync_update_manifest(path, version):
            updated_paths.append(path)

    if updated_paths:
        print("Synced files:")
        for path in updated_paths:
            print(f"- {path.name}")
    else:
        print(f"Already in sync: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
