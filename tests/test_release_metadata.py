import json
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_metadata import (
    APP_FILE_VERSION,
    APP_VERSION,
    UPDATE_PRIMARY_CHANNEL,
    build_primary_download_url,
    build_release_download_urls,
)


class ReleaseMetadataTests(unittest.TestCase):
    def test_app_file_version_matches_windows_format(self) -> None:
        self.assertEqual(APP_FILE_VERSION, f"{APP_VERSION}.0")

    def test_update_manifests_match_app_version(self) -> None:
        for manifest_name in ("update.json", "config/update.json.example"):
            with self.subTest(manifest_name=manifest_name):
                payload = json.loads((PROJECT_ROOT / manifest_name).read_text(encoding="utf-8"))
                self.assertEqual(payload["version"], APP_VERSION)
                self.assertEqual(payload["url"], build_primary_download_url(APP_VERSION))
                self.assertEqual(payload["downloadUrl"], build_primary_download_url(APP_VERSION))
                self.assertEqual(payload["primaryChannel"], UPDATE_PRIMARY_CHANNEL)
                self.assertEqual(payload["downloads"], build_release_download_urls(APP_VERSION))


if __name__ == "__main__":
    unittest.main()
