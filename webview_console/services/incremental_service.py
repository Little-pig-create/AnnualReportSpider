from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..text_engine import (
    SUMMARY_NAME as TEXT_SUMMARY_NAME,
    build_job_key,
    build_output_path,
    collect_pdf_paths,
    is_output_complete,
)
from ..link_engine import (
    build_pdf_locator_cache_for_items,
    download_failures_path,
    find_existing_pdf_path,
    load_replaced_reports_from_output_dir,
    load_target_reports_from_output_dir,
)

from ..infra.file_ops import resolve_project_path


FILTERED_FILENAME = "filtered_announcements.jsonl"
TEXT_CHECKPOINT_NAME = "text_extract_checkpoint.json"
LINKS_CHECKPOINT_NAME = "checkpoint.json"
PDF_SUMMARY_NAME = "summary.json"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _count_non_empty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _count_permanent_failures(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("permanent"):
                count += 1
    return count


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _match_extract_job(jobs: Any, input_dir: Path, output_dir: Path) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(jobs, dict):
        return None, None

    expected_key = build_job_key(input_dir, output_dir)
    job = jobs.get(expected_key)
    if isinstance(job, dict):
        return expected_key, job

    input_value = str(input_dir.resolve())
    output_value = str(output_dir.resolve())
    for job_key, candidate in jobs.items():
        if not isinstance(candidate, dict):
            continue
        if candidate.get("input_dir") == input_value and candidate.get("output_dir") == output_value:
            return str(job_key), candidate

    return None, None


class IncrementalStatusService:
    def scan(self, settings, *, lightweight: bool = False) -> dict[str, Any]:
        workspace = settings.workspace
        years = list(range(workspace.startYear, workspace.endYear + 1))
        annual_report_dir = resolve_project_path(workspace.projectRoot, workspace.annualReportDir)
        text_output_dir = resolve_project_path(workspace.projectRoot, workspace.textOutputDir)
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)

        return {
            "mode": "incremental",
            "enabled": True,
            "description": "默认启用增量更新：自动扫描状态文件与结果目录，识别已抓取年份、已下载 PDF 和已提取文本，只补新增部分。",
            "range": {
                "startYear": workspace.startYear,
                "endYear": workspace.endYear,
                "yearTotal": len(years),
            },
            "workspace": {
                "projectRoot": str(Path(workspace.projectRoot).resolve()),
                "annualReportDir": str(annual_report_dir),
                "textOutputDir": str(text_output_dir),
                "stateDir": str(state_dir),
            },
            "links": self._scan_links(years, annual_report_dir, state_dir),
            "pdf": self._scan_pdf(years, annual_report_dir, lightweight=lightweight),
            "extract": self._scan_extract(years, annual_report_dir, text_output_dir, state_dir, lightweight=lightweight),
        }

    def _scan_links(self, years: list[int], annual_report_dir: Path, state_dir: Path) -> dict[str, Any]:
        checkpoint_path = state_dir / LINKS_CHECKPOINT_NAME
        checkpoint = _read_json(checkpoint_path)
        cache_dir = state_dir / "cache"

        buckets: list[dict[str, Any]] = []
        completed_years = 0
        partial_years = 0
        total_rows = 0
        checkpoint_years = 0

        for year in years:
            filtered_path = annual_report_dir / str(year) / FILTERED_FILENAME
            cache_path = cache_dir / f"{year}.jsonl"

            filtered_rows = _count_non_empty_lines(filtered_path)
            cache_rows = _count_non_empty_lines(cache_path)
            total_rows += filtered_rows

            year_checkpoint = checkpoint.get(str(year)) if isinstance(checkpoint, dict) else None
            if isinstance(year_checkpoint, dict):
                checkpoint_years += 1

            query_ranges = year_checkpoint.get("query_ranges") if isinstance(year_checkpoint, dict) else None
            range_states = year_checkpoint.get("ranges") if isinstance(year_checkpoint, dict) else None
            query_ranges = query_ranges if isinstance(query_ranges, list) else []
            range_states = range_states if isinstance(range_states, dict) else {}

            known_ranges = query_ranges or list(range_states.keys())
            range_total = len(known_ranges)
            range_completed = sum(
                1
                for range_key in known_ranges
                if isinstance(range_states.get(range_key), dict) and bool(range_states.get(range_key, {}).get("completed"))
            )
            if not known_ranges and range_states:
                range_total = len(range_states)
                range_completed = sum(
                    1 for state in range_states.values() if isinstance(state, dict) and bool(state.get("completed"))
                )

            manifest_ready = filtered_path.exists()
            result_ready = filtered_path.exists()
            has_partial_state = bool(range_total or cache_rows or range_states)

            if result_ready or (range_total > 0 and range_completed >= range_total):
                status = "completed"
                completed_years += 1
            elif has_partial_state:
                status = "partial"
                partial_years += 1
            else:
                status = "pending"

            buckets.append(
                {
                    "year": year,
                    "exists": result_ready,
                    "rows": filtered_rows,
                    "cacheRows": cache_rows,
                    "manifestReady": manifest_ready,
                    "checkpointTracked": bool(year_checkpoint),
                    "rangeTotal": range_total,
                    "rangeCompleted": range_completed,
                    "updatedAt": year_checkpoint.get("updated_at") if isinstance(year_checkpoint, dict) else None,
                    "status": status,
                }
            )

        return {
            "completedYears": completed_years,
            "partialYears": partial_years,
            "pendingYears": len(years) - completed_years - partial_years,
            "totalRows": total_rows,
            "checkpointPath": str(checkpoint_path),
            "checkpointExists": checkpoint_path.exists(),
            "checkpointTrackedYears": checkpoint_years,
            "yearBuckets": buckets,
        }

    def _scan_pdf(self, years: list[int], annual_report_dir: Path, *, lightweight: bool = False) -> dict[str, Any]:
        summary_path = annual_report_dir / PDF_SUMMARY_NAME
        summary_payload = _read_json(summary_path)
        summary_by_year: dict[int, dict[str, Any]] = {}
        if isinstance(summary_payload, list):
            for item in summary_payload:
                if not isinstance(item, dict):
                    continue
                year = _safe_int(item.get("year"))
                if year:
                    summary_by_year[year] = item

        items_by_year: dict[int, list[Any]] = {year: [] for year in years}
        locator_cache: dict[Any, Any] = {}
        if not lightweight:
            try:
                target_items = load_target_reports_from_output_dir(annual_report_dir)
            except FileNotFoundError:
                target_items = []
            replaced_items = load_replaced_reports_from_output_dir(annual_report_dir)

            all_items: list[Any] = []
            for item in [*target_items, *replaced_items]:
                if item.report_year in items_by_year:
                    items_by_year[item.report_year].append(item)
                    all_items.append(item)
            locator_cache = build_pdf_locator_cache_for_items(annual_report_dir, all_items) if all_items else {}

        buckets: list[dict[str, Any]] = []
        target_total = 0
        existing_total = 0
        skipped_total = 0
        summary_years = 0

        for year in years:
            manifest_ready = (annual_report_dir / str(year) / FILTERED_FILENAME).exists()
            items = items_by_year[year]
            summary_item = summary_by_year.get(year) or {}
            if summary_item:
                summary_years += 1

            manifest_total = len(items)
            summary_total = _safe_int(summary_item.get("filtered_total")) + _safe_int(summary_item.get("replaced_total"))
            total = manifest_total if manifest_total > 0 else summary_total

            existing = 0
            if not lightweight:
                for item in items:
                    if find_existing_pdf_path(annual_report_dir, item, locator_cache) is not None:
                        existing += 1

            if existing == 0:
                existing = _safe_int(summary_item.get("downloaded")) + _safe_int(summary_item.get("exists"))
                existing += _safe_int(summary_item.get("replaced_downloaded")) + _safe_int(summary_item.get("replaced_exists"))

            skipped = _count_permanent_failures(download_failures_path(annual_report_dir, year))
            if skipped == 0 and summary_item:
                skipped = _safe_int(summary_item.get("skipped")) + _safe_int(summary_item.get("replaced_skipped"))

            failed = _safe_int(summary_item.get("failed")) + _safe_int(summary_item.get("replaced_failed"))
            pending = max(total - existing - skipped, 0)

            target_total += total
            existing_total += existing
            skipped_total += skipped

            if total > 0 and pending == 0:
                status = "completed"
            elif existing > 0 or skipped > 0 or failed > 0:
                status = "partial"
            elif manifest_ready or summary_item:
                status = "pending"
            else:
                status = "waiting"

            buckets.append(
                {
                    "year": year,
                    "manifestReady": manifest_ready,
                    "summaryTracked": bool(summary_item),
                    "total": total,
                    "existing": existing,
                    "skipped": skipped,
                    "failed": failed,
                    "pending": pending,
                    "status": status,
                }
            )

        return {
            "targetTotal": target_total,
            "existingTotal": existing_total,
            "skippedTotal": skipped_total,
            "pendingTotal": max(target_total - existing_total - skipped_total, 0),
            "summaryPath": str(summary_path),
            "summaryExists": summary_path.exists(),
            "summaryTrackedYears": summary_years,
            "lightweight": lightweight,
            "yearBuckets": buckets,
        }

    def _scan_extract(
        self,
        years: list[int],
        annual_report_dir: Path,
        text_output_dir: Path,
        state_dir: Path,
        *,
        lightweight: bool = False,
    ) -> dict[str, Any]:
        checkpoint_path = state_dir / TEXT_CHECKPOINT_NAME
        checkpoint = _read_json(checkpoint_path)
        checkpoint_jobs = checkpoint.get("jobs") if isinstance(checkpoint, dict) else None
        job_key, job = _match_extract_job(checkpoint_jobs, annual_report_dir, text_output_dir)
        files = job.get("files") if isinstance(job, dict) else None
        files = files if isinstance(files, dict) else {}

        summary_path = text_output_dir / TEXT_SUMMARY_NAME
        summary = _read_json(summary_path)

        pdf_paths_by_year: dict[int, list[Path]] = {year: [] for year in years}
        if not lightweight:
            try:
                pdf_paths = collect_pdf_paths(annual_report_dir, years[0], years[-1])
            except FileNotFoundError:
                pdf_paths = []

            for pdf_path in pdf_paths:
                try:
                    year = int(pdf_path.relative_to(annual_report_dir).parts[0])
                except (ValueError, IndexError):
                    continue
                if year in pdf_paths_by_year:
                    pdf_paths_by_year[year].append(pdf_path)

        checkpoint_by_year: dict[int, dict[str, int]] = {
            year: {"tracked": 0, "completed": 0, "failed": 0} for year in years
        }
        for rel_pdf, state in files.items():
            if not isinstance(rel_pdf, str) or not isinstance(state, dict):
                continue
            try:
                year = int(Path(rel_pdf).parts[0])
            except (ValueError, IndexError):
                continue
            if year not in checkpoint_by_year:
                continue
            checkpoint_by_year[year]["tracked"] += 1
            status = str(state.get("status", "")).lower()
            if status == "completed":
                checkpoint_by_year[year]["completed"] += 1
            elif status == "failed":
                checkpoint_by_year[year]["failed"] += 1

        buckets: list[dict[str, Any]] = []
        pdf_total = 0
        existing_total = 0
        checkpoint_completed_total = 0
        checkpoint_failed_total = 0

        for year in years:
            year_pdf_paths = pdf_paths_by_year[year]
            total = len(year_pdf_paths)
            existing = 0
            if not lightweight:
                for pdf_path in year_pdf_paths:
                    output_path = build_output_path(annual_report_dir, text_output_dir, pdf_path)
                    if is_output_complete(output_path):
                        existing += 1

            tracked = checkpoint_by_year[year]["tracked"]
            checkpoint_completed = checkpoint_by_year[year]["completed"]
            checkpoint_failed = checkpoint_by_year[year]["failed"]
            if lightweight and total == 0:
                total = tracked
            if lightweight and existing == 0:
                existing = checkpoint_completed
            pending = max(total - existing, 0)

            pdf_total += total
            existing_total += existing
            checkpoint_completed_total += checkpoint_completed
            checkpoint_failed_total += checkpoint_failed

            if total > 0 and pending == 0:
                status = "completed"
            elif existing > 0 or checkpoint_completed > 0 or checkpoint_failed > 0:
                status = "partial"
            elif tracked > 0:
                status = "pending"
            else:
                status = "waiting"

            buckets.append(
                {
                    "year": year,
                    "total": total,
                    "existing": existing,
                    "pending": pending,
                    "checkpointTracked": tracked,
                    "checkpointCompleted": checkpoint_completed,
                    "checkpointFailed": checkpoint_failed,
                    "status": status,
                }
            )

        return {
            "pdfTotal": pdf_total,
            "existingTotal": existing_total,
            "pendingTotal": max(pdf_total - existing_total, 0),
            "checkpointCompletedTotal": checkpoint_completed_total,
            "checkpointFailedTotal": checkpoint_failed_total,
            "checkpointPath": str(checkpoint_path),
            "checkpointExists": checkpoint_path.exists(),
            "checkpointJobKey": job_key,
            "summaryPath": str(summary_path),
            "summaryExists": summary_path.exists(),
            "summaryStats": summary if isinstance(summary, dict) else None,
            "lightweight": lightweight,
            "yearBuckets": buckets,
        }
