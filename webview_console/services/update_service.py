from __future__ import annotations

import re
from typing import Any

import requests

from app_metadata import APP_VERSION, UPDATE_PRIMARY_CHANNEL, UPDATE_SOURCE_URLS


def _split_version(value: str) -> list[int]:
    parts = re.findall(r"\d+", value or "")
    return [int(part) for part in parts] if parts else [0]


def _compare_versions(left: str, right: str) -> int:
    left_parts = _split_version(left)
    right_parts = _split_version(right)
    max_length = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_length - len(left_parts)))
    right_parts.extend([0] * (max_length - len(right_parts)))
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part != right_part:
            return 1 if left_part > right_part else -1
    return 0


class UpdateService:
    def __init__(self, source_urls: list[str] | None = None, timeout: float = 5.0) -> None:
        self.source_urls = source_urls or list(UPDATE_SOURCE_URLS)
        self.timeout = timeout

    def check(self, current_version: str = APP_VERSION) -> dict[str, Any]:
        attempts: list[dict[str, str]] = []
        for source_url in self.source_urls:
            try:
                response = requests.get(
                    source_url,
                    timeout=self.timeout,
                    headers={
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("update payload must be a JSON object")

                latest_version = str(payload.get("version") or "").strip()
                if not latest_version:
                    raise ValueError("missing version")

                channel = self._channel_for_source(source_url)
                download_url, download_file_name = self._resolve_download(payload, channel)
                notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
                has_update = _compare_versions(latest_version, current_version) > 0

                return {
                    "status": "available" if has_update else "current",
                    "currentVersion": current_version,
                    "latestVersion": latest_version,
                    "downloadUrl": download_url,
                    "downloadFileName": download_file_name,
                    "downloadChannel": channel,
                    "notes": [str(item) for item in notes if str(item).strip()],
                    "force": bool(payload.get("force", False)),
                    "sha256": str(payload.get("sha256") or ""),
                    "sourceUrl": source_url,
                    "raw": payload,
                }
            except Exception as exc:
                attempts.append({"url": source_url, "error": str(exc)})

        return {
            "status": "error",
            "currentVersion": current_version,
            "latestVersion": current_version,
            "downloadUrl": "",
            "downloadFileName": "",
            "downloadChannel": "",
            "notes": [],
            "force": False,
            "sha256": "",
            "sourceUrl": "",
            "attempts": attempts,
            "message": "未能获取更新信息",
        }

    @staticmethod
    def _channel_for_source(source_url: str) -> str:
        value = source_url.lower()
        if "gitee.com" in value:
            return "gitee"
        if "github.com" in value or "githubusercontent.com" in value:
            return "github"
        return UPDATE_PRIMARY_CHANNEL

    @staticmethod
    def _resolve_download(payload: dict[str, Any], channel: str) -> tuple[str, str]:
        downloads = payload.get("downloads")
        if isinstance(downloads, dict):
            installer = downloads.get("installer")
            if isinstance(installer, dict):
                file_name = str(installer.get("fileName") or "").strip()
                download_url = str(installer.get(channel) or installer.get(UPDATE_PRIMARY_CHANNEL) or "").strip()
                if download_url:
                    return download_url, file_name

        legacy_url = str(payload.get("downloadUrl") or payload.get("url") or "").strip()
        return legacy_url, ""
