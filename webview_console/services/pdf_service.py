from __future__ import annotations

from typing import Any

from ..link_engine import PdfDownloadResult, SpiderCancelled, SpiderConfig
from ..fast_engine import run_pdf_download_service_fast

from ..infra.file_ops import resolve_project_path


class PdfService:
    stage = "pdf"
    title = "PDF 下载"

    @staticmethod
    def build_progress_message(
        current: int,
        total: int,
        downloaded: int,
        exists: int,
        failed: int,
        skipped: int,
        current_title: str = "",
    ) -> str:
        summary = (
            f"已完成 {current}/{total}，"
            f"新下载 {downloaded}，已存在 {exists}，失败 {failed}，跳过 {skipped}"
        )
        return f"{summary}，当前：{current_title}" if current_title else summary

    @staticmethod
    def _build_cached_year_buckets(
        years: list[int],
        year_totals: dict[int, int],
        year_downloaded: dict[int, int],
        year_failed: dict[int, int],
        year_skipped: dict[int, int],
    ) -> list[dict[str, Any]]:
        buckets: list[dict[str, Any]] = []
        for year in years:
            total = int(year_totals.get(year, 0) or 0)
            downloaded = int(year_downloaded.get(year, 0) or 0)
            failed = int(year_failed.get(year, 0) or 0)
            skipped = int(year_skipped.get(year, 0) or 0)
            current = min(total, downloaded + failed + skipped)

            if total == 0:
                status = "pending"
            elif current >= total:
                status = "completed"
            elif current > 0:
                status = "running"
            else:
                status = "pending"

            buckets.append(
                {
                    "year": year,
                    "total": total,
                    "current": current,
                    "percent": round(current / total, 6) if total > 0 else 0,
                    "count": total,
                    "present": downloaded,
                    "failed": failed,
                    "skipped": skipped,
                    "status": status,
                }
            )
        return buckets

    async def run(self, settings, reporter, cancel_token) -> dict[str, Any]:
        workspace = settings.workspace
        links = settings.links
        pdf = settings.pdf
        output_dir = resolve_project_path(workspace.projectRoot, workspace.annualReportDir)
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)

        reporter.log("INFO", self.stage, "快速 PDF 下载任务已启动，正在读取年份任务清单")

        config = SpiderConfig(
            start_year=workspace.startYear,
            end_year=workspace.endYear,
            se_date=links.seDate.strip() or None,
            page_size=links.pageSize,
            request_interval=links.requestInterval,
            announcement_concurrency=links.announcementConcurrency,
            download_concurrency=pdf.downloadConcurrency,
            output_dir=str(output_dir),
            state_dir=str(state_dir),
            download_pdf=True,
            metadata_only=False,
            audit_pdf=False,
            cleanup_orphan_pdf=False,
        )

        years = list(range(workspace.startYear, workspace.endYear + 1))
        runtime_failed_by_year = {year: 0 for year in years}
        runtime_downloaded_by_year = {year: 0 for year in years}
        year_totals = {year: 0 for year in years}
        year_skipped = {year: 0 for year in years}

        reporter.progress(
            self.stage,
            0,
            1,
            "正在初始化 PDF 下载任务",
            {
                "pdfTotal": 0,
                "downloaded": 0,
                "exists": 0,
                "failed": 0,
                "skipped": 0,
                "yearBuckets": self._build_cached_year_buckets(
                    years,
                    year_totals,
                    runtime_downloaded_by_year,
                    runtime_failed_by_year,
                    year_skipped,
                ),
                "speedPerMinute": 0,
                "etaSeconds": 0,
            },
        )

        def refresh_year_buckets() -> list[dict[str, Any]]:
            return self._build_cached_year_buckets(
                years,
                year_totals,
                runtime_downloaded_by_year,
                runtime_failed_by_year,
                year_skipped,
            )

        def distribute_total(total: int) -> None:
            base = total // max(len(years), 1)
            remainder = total % max(len(years), 1)
            for index, year in enumerate(years):
                year_totals[year] = base + (1 if index < remainder else 0)

        def on_log(level: str, message: str) -> None:
            reporter.log(level.upper(), self.stage, message)

        def on_progress(payload: dict[str, Any]) -> None:
            phase = str(payload.get("phase", "") or "")
            if phase == "log":
                return

            pdf_total = int(payload.get("pdf_total", 0) or 0)
            pending_total = int(payload.get("total", pdf_total) or 0)
            downloaded = int(payload.get("downloaded", 0) or 0)
            exists = int(payload.get("exists", 0) or 0)
            failed = int(payload.get("failed", 0) or 0)
            skipped = int(payload.get("skipped", 0) or 0)
            total = pdf_total or pending_total
            current = downloaded + exists + failed + skipped
            current_title = str(payload.get("current_title") or "")
            speed_per_minute = float(payload.get("speed_per_minute", 0) or 0)
            eta_seconds = int(payload.get("eta_seconds", 0) or 0)
            current_year = int(payload.get("current_year", 0) or 0)
            year_buckets = payload.get("year_buckets")

            if phase == "prepare":
                distribute_total(max(total, current))
            elif phase in {"download", "done"} and total > 0 and all(value == 0 for value in year_totals.values()):
                distribute_total(total)

            message = self.build_progress_message(
                current if phase != "done" else (current or total),
                total or max(current, 1),
                downloaded,
                exists,
                failed,
                skipped,
                "" if phase == "done" else current_title,
            )

            reporter.progress(
                self.stage,
                current if phase != "done" else (current or total),
                total or max(current, 1),
                message,
                {
                    "pdfTotal": pdf_total,
                    "downloaded": downloaded,
                    "exists": exists,
                    "failed": failed,
                    "skipped": skipped,
                    "yearBuckets": year_buckets if isinstance(year_buckets, list) else refresh_year_buckets(),
                    "speedPerMinute": speed_per_minute,
                    "etaSeconds": eta_seconds,
                    "currentYear": current_year or None,
                    "currentTitle": current_title,
                },
            )

        try:
            result: PdfDownloadResult = await run_pdf_download_service_fast(
                config,
                log_callback=on_log,
                progress_callback=on_progress,
                cancel_requested=cancel_token.cancel_requested,
            )
        except SpiderCancelled:
            raise

        payload = {
            "pdfTotal": result.pdf_total,
            "downloaded": result.downloaded,
            "exists": result.exists,
            "failed": result.failed,
            "skipped": result.skipped,
            "outputDir": str(result.output_dir),
            "summaryPath": str(result.summary_path) if result.summary_path else "",
            "elapsedSeconds": result.elapsed_seconds,
            "summary": result.summary,
            "yearBuckets": refresh_year_buckets(),
            "speedPerMinute": 0,
            "etaSeconds": 0,
        }
        reporter.progress(
            self.stage,
            result.pdf_total,
            result.pdf_total or 1,
            self.build_progress_message(
                result.pdf_total,
                result.pdf_total or 1,
                result.downloaded,
                result.exists,
                result.failed,
                result.skipped,
            ),
            payload,
        )
        return payload
