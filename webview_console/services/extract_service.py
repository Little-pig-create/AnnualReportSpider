from __future__ import annotations

from pathlib import Path
from typing import Any

from ..text_engine import CHECKPOINT_NAME, ExtractTextConfig, ExtractionCancelled
from ..fast_engine import run_extraction_fast

from ..infra.file_ops import resolve_project_path


class ExtractService:
    stage = "extract"
    title = "文本提取"

    @staticmethod
    def build_progress_message(
        current: int,
        total: int,
        extracted: int,
        exists: int,
        failed: int,
        current_pdf: str = "",
    ) -> str:
        summary = (
            f"已完成 {current}/{total}，"
            f"新提取 {extracted}，已存在 {exists}，失败 {failed}"
        )
        return f"{summary}，当前：{current_pdf}" if current_pdf else summary

    @staticmethod
    def _extract_year_from_relative_path(relative_path: str) -> int | None:
        parts = Path(relative_path).parts
        if not parts:
            return None
        try:
            return int(parts[0])
        except ValueError:
            return None

    @staticmethod
    def _build_year_buckets(
        years: list[int],
        year_totals: dict[int, int],
        existing_by_year: dict[int, int],
        extracted_by_year: dict[int, int],
        failed_by_year: dict[int, int],
    ) -> list[dict[str, Any]]:
        buckets: list[dict[str, Any]] = []
        for year in years:
            total = int(year_totals.get(year, 0) or 0)
            exists = int(existing_by_year.get(year, 0) or 0)
            extracted = int(extracted_by_year.get(year, 0) or 0)
            failed = int(failed_by_year.get(year, 0) or 0)
            current = min(total, exists + extracted + failed)

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
                    "exists": exists,
                    "extracted": extracted,
                    "failed": failed,
                    "status": status,
                }
            )
        return buckets

    async def run(self, settings, reporter, cancel_token) -> dict[str, Any]:
        workspace = settings.workspace
        extract = settings.extract
        input_dir = resolve_project_path(workspace.projectRoot, workspace.annualReportDir)
        output_dir = resolve_project_path(workspace.projectRoot, workspace.textOutputDir)
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)
        checkpoint_path = state_dir / CHECKPOINT_NAME

        reporter.log("INFO", self.stage, "快速文本提取任务已启动，正在初始化任务")

        if extract.resetCheckpoint and checkpoint_path.exists():
            checkpoint_path.unlink()
            reporter.log("INFO", self.stage, f"已重置 checkpoint：{checkpoint_path}")

        config = ExtractTextConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            state_dir=state_dir,
            start_year=workspace.startYear,
            end_year=workspace.endYear,
            concurrency=extract.concurrency,
        )

        years = list(range(workspace.startYear, workspace.endYear + 1))
        year_totals = {year: 0 for year in years}
        existing_by_year = {year: 0 for year in years}
        extracted_by_year = {year: 0 for year in years}
        failed_by_year = {year: 0 for year in years}
        last_extracted = 0
        last_failed = 0
        last_exists = 0

        reporter.progress(
            self.stage,
            0,
            1,
            "正在初始化文本提取任务",
            {
                "pdfTotal": 0,
                "extracted": 0,
                "exists": 0,
                "failed": 0,
                "yearBuckets": self._build_year_buckets(
                    years,
                    year_totals,
                    existing_by_year,
                    extracted_by_year,
                    failed_by_year,
                ),
                "speedPerMinute": 0,
                "etaSeconds": 0,
            },
        )

        def build_year_buckets() -> list[dict[str, Any]]:
            return self._build_year_buckets(
                years,
                year_totals,
                existing_by_year,
                extracted_by_year,
                failed_by_year,
            )

        def distribute_total(total: int) -> None:
            base = total // max(len(years), 1)
            remainder = total % max(len(years), 1)
            for index, year in enumerate(years):
                year_totals[year] = base + (1 if index < remainder else 0)

        def on_log(level: str, message: str) -> None:
            reporter.log(level.upper(), self.stage, message)

        def on_progress(payload: dict[str, Any]) -> None:
            nonlocal last_extracted, last_failed, last_exists

            phase = str(payload.get("phase") or "")
            pdf_total = int(payload.get("pdf_total", 0) or 0)
            extracted = int(payload.get("extracted", 0) or 0)
            exists = int(payload.get("existing", payload.get("exists", 0)) or 0)
            failed = int(payload.get("failed", 0) or 0)
            pending_total = int(payload.get("total", 0) or 0)
            speed_per_minute = float(payload.get("speed_per_minute", 0) or 0)
            eta_seconds = int(payload.get("eta_seconds", 0) or 0)
            current_year_payload = int(payload.get("current_year", 0) or 0)
            year_buckets = payload.get("year_buckets")

            if phase == "prepare":
                total = pdf_total or pending_total
                current = exists
                distribute_total(total)
                message = f"总计 {total} 份 PDF，已存在 {exists} 份，待提取 {pending_total} 份"
            elif phase == "extract":
                current_pdf = str(payload.get("current_pdf") or "")
                current_year = self._extract_year_from_relative_path(current_pdf)
                extracted_delta = max(0, extracted - last_extracted)
                failed_delta = max(0, failed - last_failed)
                exists_delta = max(0, exists - last_exists)

                if current_year in year_totals:
                    year_totals[current_year] = max(
                        year_totals[current_year],
                        int(existing_by_year.get(current_year, 0) or 0)
                        + int(extracted_by_year.get(current_year, 0) or 0)
                        + int(failed_by_year.get(current_year, 0) or 0)
                        + extracted_delta
                        + failed_delta
                        + exists_delta,
                    )
                if current_year in existing_by_year and exists_delta:
                    existing_by_year[current_year] += exists_delta
                if current_year in extracted_by_year and extracted_delta:
                    extracted_by_year[current_year] += extracted_delta
                if current_year in failed_by_year and failed_delta:
                    failed_by_year[current_year] += failed_delta

                total = pdf_total or pending_total
                current = extracted + exists + failed
                message = self.build_progress_message(
                    current,
                    total,
                    extracted,
                    exists,
                    failed,
                    current_pdf,
                )
            elif phase == "done":
                total = pdf_total or pending_total
                current = pdf_total or total
                if total > 0 and all(value == 0 for value in year_totals.values()):
                    distribute_total(total)
                message = self.build_progress_message(
                    current or total,
                    total or max(extracted + exists + failed, 1),
                    extracted,
                    exists,
                    failed,
                )
            else:
                return

            last_extracted = extracted
            last_failed = failed
            last_exists = exists

            reporter.progress(
                self.stage,
                current,
                total,
                message,
                {
                    "pdfTotal": pdf_total,
                    "extracted": extracted,
                    "exists": exists,
                    "failed": failed,
                    "yearBuckets": year_buckets if isinstance(year_buckets, list) else build_year_buckets(),
                    "speedPerMinute": speed_per_minute,
                    "etaSeconds": eta_seconds,
                    "currentYear": current_year_payload or None,
                    "currentPdf": str(payload.get("current_pdf") or ""),
                },
            )

        try:
            result = await run_extraction_fast(
                config,
                log_callback=on_log,
                progress_callback=on_progress,
                cancel_requested=cancel_token.cancel_requested,
            )
        except ExtractionCancelled:
            raise

        payload = {
            "pdfTotal": result.pdf_total,
            "pendingTotal": result.pending_total,
            "extracted": result.stats.get("extracted", 0),
            "exists": result.stats.get("exists", 0),
            "failed": result.stats.get("failed", 0),
            "outputDir": str(output_dir),
            "summaryPath": str(result.summary_path),
            "checkpointPath": str(result.checkpoint_path),
            "summary": result.summary,
            "yearBuckets": build_year_buckets(),
            "speedPerMinute": 0,
            "etaSeconds": 0,
        }

        if extract.deleteCheckpointOnSuccess and checkpoint_path.exists():
            checkpoint_path.unlink()
            reporter.log("INFO", self.stage, f"已删除 checkpoint：{checkpoint_path}")

        reporter.progress(
            self.stage,
            result.pdf_total,
            result.pdf_total or 1,
            self.build_progress_message(
                result.pdf_total,
                result.pdf_total or 1,
                result.stats.get("extracted", 0),
                result.stats.get("exists", 0),
                result.stats.get("failed", 0),
            ),
            payload,
        )
        return payload
