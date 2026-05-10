import json
import unittest
from pathlib import Path

from app_metadata import APP_FILE_VERSION, APP_VERSION, build_release_download_url


class ReleaseMetadataTests(unittest.TestCase):
    def test_app_file_version_matches_windows_format(self) -> None:
        self.assertEqual(APP_FILE_VERSION, f"{APP_VERSION}.0")

    def test_update_manifests_match_app_version(self) -> None:
        for manifest_name in ("update.json", "update.json.example"):
            with self.subTest(manifest_name=manifest_name):
                payload = json.loads(Path(manifest_name).read_text(encoding="utf-8"))
                self.assertEqual(payload["version"], APP_VERSION)
                self.assertEqual(payload["url"], build_release_download_url(APP_VERSION))


if __name__ == "__main__":
    unittest.main()
