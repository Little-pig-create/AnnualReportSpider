import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import spider
from spider import (
    ReportItem,
    append_permanent_download_failure,
    download_pdf_sync,
    is_download_complete,
    load_permanent_download_failures,
    sync_year_outputs_with_replaced,
    write_jsonl,
)


def build_report_item(
    announcement_id: str,
    title: str,
    announcement_time: int,
    report_year: int = 2024,
    sec_code: str = "000001",
) -> ReportItem:
    return ReportItem(
        report_year=report_year,
        sec_code=sec_code,
        sec_name="测试公司",
        announcement_id=announcement_id,
        announcement_title=title,
        announcement_time=announcement_time,
        adjunct_url=f"finalpage/{announcement_id}.PDF",
    )


class FakeResponse:
    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield from self._chunks


class SpiderTests(unittest.TestCase):
    def test_is_download_complete_rejects_non_pdf_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"<html>" + b"x" * 2048)

            self.assertFalse(is_download_complete(pdf_path))

    def test_download_pdf_sync_rejects_non_pdf_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "download.pdf"
            fake_response = FakeResponse(200, [b"<html>" + b"x" * 4096])

            with mock.patch("spider.requests.get", return_value=fake_response):
                ok, message = download_pdf_sync("https://example.com/file.pdf", pdf_path, retries=1)

            self.assertFalse(ok)
            self.assertEqual(message, "invalid pdf header")
            self.assertFalse(pdf_path.exists())
            self.assertFalse(pdf_path.with_suffix(".pdf.part").exists())

    def test_download_pdf_sync_does_not_retry_permanent_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "download.pdf"
            fake_response = FakeResponse(404, [])

            with mock.patch("spider.requests.get", return_value=fake_response) as get_mock:
                ok, message = download_pdf_sync("https://example.com/missing.pdf", pdf_path, retries=6)

            self.assertFalse(ok)
            self.assertEqual(message, "permanent HTTP 404")
            self.assertEqual(get_mock.call_count, 1)
            self.assertFalse(pdf_path.exists())
            self.assertFalse(pdf_path.with_suffix(".pdf.part").exists())

    def test_permanent_download_failures_are_loaded_by_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            item = build_report_item("123", "2024年年度报告", 1)
            keys: set[tuple[str, str, str]] = set()

            append_permanent_download_failure(
                output_dir,
                "replaced",
                item,
                output_dir / "2024" / "replaced_pdfs" / item.filename,
                "permanent HTTP 404",
                keys,
            )

            self.assertEqual(
                load_permanent_download_failures(output_dir, {2024}),
                {("replaced", "123", item.adjunct_url)},
            )

    def test_sync_year_outputs_backfills_existing_replaced_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            year_dir = output_dir / "2024"
            year_dir.mkdir(parents=True, exist_ok=True)

            existing_replaced = build_report_item("1", "2024年年度报告", 1)
            current_primary = build_report_item("2", "2024年年度报告（修订版）", 2)

            write_jsonl(year_dir / "filtered_announcements.jsonl", [current_primary])
            write_jsonl(year_dir / "filtered_out_announcements.jsonl", [])
            write_jsonl(year_dir / spider.REPLACED_REPORTS_MANIFEST_NAME, [existing_replaced])

            artifacts = sync_year_outputs_with_replaced(
                output_dir=output_dir,
                reports=[current_primary],
                filtered_out=[],
                replaced_reports=[],
            )

            self.assertIn(2024, artifacts.active_replaced_reports)
            self.assertEqual(
                [item.announcement_id for item in artifacts.active_replaced_reports[2024]],
                ["1"],
            )

    def test_async_main_uses_default_tls_verification(self) -> None:
        connector_calls: list[dict] = []

        class FakeAiohttp:
            class ClientTimeout:
                def __init__(self, **kwargs) -> None:
                    self.kwargs = kwargs

            class TCPConnector:
                def __init__(self, **kwargs) -> None:
                    connector_calls.append(kwargs)

            class ClientSession:
                def __init__(self, **kwargs) -> None:
                    self.kwargs = kwargs

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

        async def fake_process_year_with_replaced(**kwargs):
            del kwargs
            return {
                "year": 2024,
                "raw_total": 0,
                "filtered_total": 0,
                "replaced_total": 0,
                "filtered_out_total": 0,
                "downloaded": 0,
                "exists": 0,
                "failed": 0,
                "filtered_paths": [],
                "filtered_out_paths": [],
                "replaced_paths": [],
                "metadata_csv_paths": [],
                "replaced_metadata_csv_paths": [],
            }

        args = SimpleNamespace(
            output_dir="annual_reports_test",
            state_dir="state_test",
            start_year=2024,
            end_year=2024,
            se_date=None,
            request_interval=0,
            download_pdf=True,
            metadata_only=False,
            page_size=30,
            announcement_concurrency=2,
            download_concurrency=3,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            args.output_dir = str(Path(tmp_dir) / "annual_reports")
            args.state_dir = str(Path(tmp_dir) / "state")
            with mock.patch.object(spider, "aiohttp", FakeAiohttp):
                with mock.patch.object(spider.CninfoClient, "warmup", return_value=None):
                    with mock.patch.object(spider, "process_year_with_replaced", side_effect=fake_process_year_with_replaced):
                        with mock.patch.object(spider, "log"):
                            asyncio.run(spider.async_main(args))

        self.assertEqual(len(connector_calls), 2)
        for kwargs in connector_calls:
            self.assertNotIn("ssl", kwargs)


if __name__ == "__main__":
    unittest.main()
