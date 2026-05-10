from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import aiohttp
except ModuleNotFoundError:
    aiohttp = None

from .text_engine import (
    CHECKPOINT_NAME as TEXT_CHECKPOINT_NAME,
    SUMMARY_NAME as TEXT_SUMMARY_NAME,
    ExtractTextConfig,
    ExtractTextResult,
    ExtractionCancelled,
    build_job_key,
    build_output_path,
    build_summary as build_text_summary,
    collect_pdf_paths,
    extract_text_to_file,
    is_output_complete,
    read_json as read_text_json,
    write_json as write_text_json,
)
from .link_engine import (
    DEFAULT_HEADERS,
    REPLACED_PDF_DIRNAME,
    REPLACED_REPORTS_MANIFEST_NAME,
    REPLACED_REPORTS_METADATA_NAME,
    CninfoClient,
    PdfDownloadResult,
    ReportItem,
    SpiderCancelled,
    SpiderConfig,
    append_permanent_download_failure,
    classify_reports_with_replaced,
    dedupe_report_items,
    download_failure_key,
    download_pdf_async,
    fetch_announcements_for_year,
    format_report_year_range,
    get_pdf_target_path,
    get_replaced_pdf_target_path,
    is_permanent_download_message,
    load_permanent_download_failures,
    load_report_items,
    log,
    sync_year_outputs_with_replaced,
)

FAILED_SAMPLE_LIMIT = 50
PER_YEAR_INDEX_DIRS = ("", "pdf", REPLACED_PDF_DIRNAME)
PDF_PROGRESS_EMIT_INTERVAL = 0.25
PDF_PROGRESS_EMIT_EVERY = 8
PDF_LOG_EMIT_INTERVAL = 1.5
PDF_LOG_EMIT_EVERY = 20
EXTRACT_PROGRESS_EMIT_INTERVAL = 0.35
EXTRACT_PROGRESS_EMIT_EVERY = 6
EXTRACT_LOG_EMIT_INTERVAL = 1.5
EXTRACT_LOG_EMIT_EVERY = 20
MIN_PDF_BYTES = 1024

LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[dict[str, Any]], None]
CancelCallback = Callable[[], bool]


def emit_log(log_callback: LogCallback | None, level: str, message: str) -> None:
    if log_callback is None:
        log(level, message)
        return
    log_callback(level, message)


def emit_progress(progress_callback: ProgressCallback | None, **payload: Any) -> None:
    if progress_callback is None:
        return
    progress_callback(payload)


def raise_if_cancelled(cancel_requested: CancelCallback | None) -> None:
    if cancel_requested is not None and cancel_requested():
        raise SpiderCancelled("fast spider cancelled")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def iter_year_manifest_paths(output_dir: Path, filename: str) -> list[Path]:
    return sorted(
        path
        for path in output_dir.glob(f"*/{filename}")
        if path.parent.is_dir() and path.parent.name.isdigit()
    )


def _report_preference_key_local(item: ReportItem) -> tuple[int, int, int, int]:
    try:
        announcement_rank = int((item.announcement_id or "").strip())
    except Exception:
        announcement_rank = -1
    title = item.announcement_title or ""
    title_rank = 2 if str(item.report_year) in title else 1
    revision_rank = 1 if any(token in title for token in ("修订", "更正", "更新")) else 0
    return (announcement_rank, title_rank, revision_rank, int(item.announcement_time or 0))


def _choose_best_reports_local(items: list[ReportItem]) -> tuple[list[ReportItem], list[ReportItem]]:
    latest: dict[tuple[str, int], ReportItem] = {}
    replaced: list[ReportItem] = []
    for item in items:
        key = (item.sec_code, item.report_year)
        old = latest.get(key)
        if old is None:
            latest[key] = item
            continue
        if _report_preference_key_local(item) > _report_preference_key_local(old):
            replaced.append(old)
            latest[key] = item
        else:
            replaced.append(item)
    kept = sorted(latest.values(), key=lambda row: (row.report_year, row.sec_code, row.announcement_time, row.announcement_id))
    return kept, replaced


def load_target_reports_by_year(output_dir: Path) -> dict[int, list[ReportItem]]:
    result: dict[int, list[ReportItem]] = {}
    for manifest_path in iter_year_manifest_paths(output_dir, "filtered_announcements.jsonl"):
        year = int(manifest_path.parent.name)
        kept, _ = _choose_best_reports_local(load_report_items(manifest_path))
        result[year] = kept
    return result


def load_replaced_reports_by_year(output_dir: Path) -> dict[int, list[ReportItem]]:
    result: dict[int, list[ReportItem]] = {}
    for manifest_path in iter_year_manifest_paths(output_dir, REPLACED_REPORTS_MANIFEST_NAME):
        year = int(manifest_path.parent.name)
        result[year] = dedupe_report_items(load_report_items(manifest_path))
    return result


@dataclass(slots=True)
class FastYearPdfIndex:
    by_name: dict[str, list[Path]]
    by_announcement_id: dict[str, list[Path]]


def is_complete_pdf(path: Path, *, verify_header: bool = True) -> bool:
    try:
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size < MIN_PDF_BYTES:
            return False
        if not verify_header:
            return True
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def _extract_announcement_id_from_name(filename: str) -> str:
    stem = Path(filename).stem
    parts = stem.rsplit("_", 1)
    if len(parts) != 2:
        return ""
    suffix = parts[1].strip()
    return suffix if suffix.isdigit() else ""


def build_fast_year_pdf_index(output_dir: Path, report_year: int) -> FastYearPdfIndex:
    by_name: dict[str, list[Path]] = {}
    by_announcement_id: dict[str, list[Path]] = {}
    year_dir = output_dir / str(report_year)
    for relative_dir in PER_YEAR_INDEX_DIRS:
        base_dir = year_dir / relative_dir if relative_dir else year_dir
        if not base_dir.exists():
            continue
        for pdf_path in base_dir.glob("*.pdf"):
            if not is_complete_pdf(pdf_path, verify_header=False):
                continue
            by_name.setdefault(pdf_path.name, []).append(pdf_path)
            announcement_id = _extract_announcement_id_from_name(pdf_path.name)
            if announcement_id:
                by_announcement_id.setdefault(announcement_id, []).append(pdf_path)
    return FastYearPdfIndex(by_name=by_name, by_announcement_id=by_announcement_id)


def find_existing_pdf_fast(item: ReportItem, target_path: Path, year_index: FastYearPdfIndex) -> Path | None:
    if is_complete_pdf(target_path, verify_header=False):
        return target_path
    candidates: list[Path] = []
    candidates.extend(year_index.by_name.get(item.filename, []))
    candidates.extend(year_index.by_name.get(item.legacy_filename, []))
    if item.announcement_id:
        candidates.extend(year_index.by_announcement_id.get(item.announcement_id, []))
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if is_complete_pdf(candidate, verify_header=False):
            return candidate
    return None


def relocate_if_needed(existing_path: Path, target_path: Path) -> Path:
    resolved_existing = existing_path.resolve()
    resolved_target = target_path.resolve()
    if resolved_existing == resolved_target:
        return resolved_target
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if is_complete_pdf(target_path, verify_header=False):
        if resolved_existing != resolved_target:
            existing_path.unlink(missing_ok=True)
        return resolved_target
    existing_path.replace(target_path)
    return target_path.resolve()


def refresh_index_with_path(index: FastYearPdfIndex, path: Path) -> None:
    name_list = index.by_name.setdefault(path.name, [])
    if path not in name_list:
        name_list.append(path)
    announcement_id = _extract_announcement_id_from_name(path.name)
    if announcement_id:
        id_list = index.by_announcement_id.setdefault(announcement_id, [])
        if path not in id_list:
            id_list.append(path)


def _safe_speed_per_minute(completed: int, elapsed_seconds: float) -> float:
    if completed <= 0 or elapsed_seconds <= 0:
        return 0.0
    return round((completed / elapsed_seconds) * 60.0, 2)


def _safe_eta_seconds(total: int, completed: int, elapsed_seconds: float) -> int:
    remaining = max(0, int(total) - int(completed))
    if remaining <= 0 or completed <= 0 or elapsed_seconds <= 0:
        return 0
    per_second = completed / elapsed_seconds
    if per_second <= 0:
        return 0
    return int(round(remaining / per_second))


def build_pdf_year_buckets(
    years: list[int],
    target_by_year: dict[int, list[ReportItem]],
    replaced_by_year: dict[int, list[ReportItem]],
    stats_by_year: dict[int, dict[str, int]],
    *,
    current_year: int | None = None,
) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for year in years:
        total = len(target_by_year.get(year, [])) + len(replaced_by_year.get(year, []))
        stats = stats_by_year.get(year, {})
        downloaded = int(stats.get("downloaded", 0)) + int(stats.get("replaced_downloaded", 0))
        exists = int(stats.get("exists", 0)) + int(stats.get("replaced_exists", 0))
        failed = int(stats.get("failed", 0)) + int(stats.get("replaced_failed", 0))
        skipped = int(stats.get("skipped", 0)) + int(stats.get("replaced_skipped", 0))
        completed = min(total, downloaded + exists + failed + skipped)
        if total == 0:
            status = "pending"
        elif completed >= total:
            status = "completed"
        elif completed > 0:
            status = "running"
        else:
            status = "pending"
        buckets.append(
            {
                "year": year,
                "total": total,
                "downloaded": downloaded,
                "exists": exists,
                "failed": failed,
                "skipped": skipped,
                "completed": completed,
                "percent": round(completed / total, 6) if total > 0 else 0,
                "status": status,
                "active": current_year == year,
            }
        )
    return buckets


def build_extract_year_buckets(
    years: list[int],
    totals_by_year: dict[int, int],
    stats_by_year: dict[int, dict[str, int]],
    *,
    current_year: int | None = None,
) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for year in years:
        total = int(totals_by_year.get(year, 0) or 0)
        stats = stats_by_year.get(year, {})
        extracted = int(stats.get("extracted", 0))
        exists = int(stats.get("exists", 0))
        failed = int(stats.get("failed", 0))
        completed = min(total, extracted + exists + failed)
        if total == 0:
            status = "pending"
        elif completed >= total:
            status = "completed"
        elif completed > 0:
            status = "running"
        else:
            status = "pending"
        buckets.append(
            {
                "year": year,
                "total": total,
                "extracted": extracted,
                "exists": exists,
                "failed": failed,
                "completed": completed,
                "percent": round(completed / total, 6) if total > 0 else 0,
                "status": status,
                "active": current_year == year,
            }
        )
    return buckets


def collect_pdf_paths_fast(
    input_dir: Path,
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")

    year_dirs = sorted(
        path for path in input_dir.iterdir() if path.is_dir() and path.name.isdigit()
    )
    if not year_dirs:
        return collect_pdf_paths(input_dir, start_year, end_year)

    pdf_paths: list[Path] = []
    for year_dir in year_dirs:
        year = int(year_dir.name)
        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue
        pdf_paths.extend(
            sorted(
                path
                for path in year_dir.glob("*.pdf")
                if path.is_file()
            )
        )
    return pdf_paths


def update_summary_json_fast(
    output_dir: Path,
    target_by_year: dict[int, list[ReportItem]],
    replaced_by_year: dict[int, list[ReportItem]],
    stats_by_year: dict[int, dict[str, int]],
) -> list[dict[str, Any]]:
    summary_path = output_dir / "summary.json"
    existing_payload = read_json(summary_path)
    existing_by_year: dict[int, dict[str, Any]] = {}
    if isinstance(existing_payload, list):
        for item in existing_payload:
            if not isinstance(item, dict):
                continue
            try:
                existing_by_year[int(item.get("year"))] = dict(item)
            except Exception:
                continue

    merged: list[dict[str, Any]] = []
    touched_years = sorted(set(existing_by_year.keys()) | set(target_by_year.keys()) | set(replaced_by_year.keys()) | set(stats_by_year.keys()))
    for year in touched_years:
        base = existing_by_year.get(year, {})
        stats = stats_by_year.get(year, {})
        merged.append(
            {
                **base,
                "year": year,
                "filtered_total": len(target_by_year.get(year, [])),
                "replaced_total": len(replaced_by_year.get(year, [])),
                "downloaded": int(stats.get("downloaded", 0)),
                "exists": int(stats.get("exists", 0)),
                "failed": int(stats.get("failed", 0)),
                "skipped": int(stats.get("skipped", 0)),
                "replaced_downloaded": int(stats.get("replaced_downloaded", 0)),
                "replaced_exists": int(stats.get("replaced_exists", 0)),
                "replaced_failed": int(stats.get("replaced_failed", 0)),
                "replaced_skipped": int(stats.get("replaced_skipped", 0)),
            }
        )
    merged.sort(key=lambda row: int(row["year"]))
    write_json(summary_path, merged)
    return merged


def write_metadata_fast(csv_path: Path, reports: list[ReportItem], path_map: dict[str, Path]) -> None:
    import csv

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report_year", "sec_code", "sec_name", "announcement_id", "announcement_title", "pdf_url", "local_path"])
        for item in reports:
            writer.writerow([
                item.report_year,
                item.sec_code,
                item.sec_name,
                item.announcement_id,
                item.announcement_title,
                item.pdf_url,
                str(path_map.get(item.announcement_id, "")),
            ])


def write_replaced_metadata_fast(
    csv_path: Path,
    replaced_reports: list[ReportItem],
    replaced_path_map: dict[str, Path],
    primary_reports: list[ReportItem],
    primary_path_map: dict[str, Path],
) -> None:
    import csv

    primary_by_key = {(item.report_year, item.sec_code): item for item in primary_reports}
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "report_year",
            "sec_code",
            "sec_name",
            "announcement_id",
            "announcement_title",
            "pdf_url",
            "local_path",
            "replacement_announcement_id",
            "replacement_announcement_title",
            "replacement_pdf_url",
            "replacement_local_path",
        ])
        for item in replaced_reports:
            replacement = primary_by_key.get((item.report_year, item.sec_code))
            writer.writerow([
                item.report_year,
                item.sec_code,
                item.sec_name,
                item.announcement_id,
                item.announcement_title,
                item.pdf_url,
                str(replaced_path_map.get(item.announcement_id, "")),
                replacement.announcement_id if replacement else "",
                replacement.announcement_title if replacement else "",
                replacement.pdf_url if replacement else "",
                str(primary_path_map.get(replacement.announcement_id, "")) if replacement else "",
            ])


async def run_pdf_download_service_fast(
    config: SpiderConfig,
    *,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
) -> PdfDownloadResult:
    start_time = time.perf_counter()
    output_dir = Path(config.output_dir)
    state_dir = Path(config.state_dir)
    if not output_dir.exists():
        raise FileNotFoundError(f"输出目录不存在：{output_dir}")

    target_by_year = load_target_reports_by_year(output_dir)
    replaced_by_year = load_replaced_reports_by_year(output_dir)
    years = sorted(set(target_by_year.keys()) | set(replaced_by_year.keys()))
    if not years:
        raise FileNotFoundError(f"未找到可下载清单：{output_dir}")

    permanent_failure_keys = load_permanent_download_failures(output_dir, set(years))
    year_indexes = {year: build_fast_year_pdf_index(output_dir, year) for year in years}
    path_maps_main = {year: {} for year in years}
    path_maps_replaced = {year: {} for year in years}
    stats_by_year = {
        year: {
            "downloaded": 0,
            "exists": 0,
            "failed": 0,
            "skipped": 0,
            "replaced_downloaded": 0,
            "replaced_exists": 0,
            "replaced_failed": 0,
            "replaced_skipped": 0,
        }
        for year in years
    }

    pending_downloads: list[tuple[str, ReportItem, Path]] = []
    for year in years:
        index = year_indexes[year]
        for role, items, target_fn, path_map, exists_key, skipped_key in (
            ("main", target_by_year.get(year, []), get_pdf_target_path, path_maps_main[year], "exists", "skipped"),
            ("replaced", replaced_by_year.get(year, []), get_replaced_pdf_target_path, path_maps_replaced[year], "replaced_exists", "replaced_skipped"),
        ):
            for item in items:
                raise_if_cancelled(cancel_requested)
                target_path = target_fn(output_dir, item)
                existing_path = find_existing_pdf_fast(item, target_path, index)
                if existing_path is not None:
                    final_path = relocate_if_needed(existing_path, target_path)
                    refresh_index_with_path(index, final_path)
                    path_map[item.announcement_id] = final_path
                    stats_by_year[year][exists_key] += 1
                    continue
                if download_failure_key(role, item) in permanent_failure_keys:
                    stats_by_year[year][skipped_key] += 1
                    continue
                pending_downloads.append((role, item, target_path))

    pdf_total = sum(len(rows) for rows in target_by_year.values()) + sum(len(rows) for rows in replaced_by_year.values())
    emit_log(log_callback, "INFO", f"快速 PDF 下载启动：总任务 {pdf_total}，待下载 {len(pending_downloads)}")
    emit_progress(
        progress_callback,
        phase="prepare",
        pdf_total=pdf_total,
        total=len(pending_downloads),
        completed=0,
        downloaded=0,
        exists=sum(v["exists"] + v["replaced_exists"] for v in stats_by_year.values()),
        failed=0,
        skipped=sum(v["skipped"] + v["replaced_skipped"] for v in stats_by_year.values()),
        year_buckets=build_pdf_year_buckets(years, target_by_year, replaced_by_year, stats_by_year),
        speed_per_minute=0.0,
        eta_seconds=0,
    )

    download_sem = asyncio.Semaphore(max(1, int(config.download_concurrency)))
    finished = 0
    downloaded_total = 0
    failed_total = 0
    last_progress_emit_at = 0.0
    last_success_log_at = 0.0

    async def run_one(session: aiohttp.ClientSession | None, role: str, item: ReportItem, target_path: Path):
        ok, message = await download_pdf_async(session, item.pdf_url, target_path, download_sem)
        return role, item, target_path, ok, message

    async def run_all(session: aiohttp.ClientSession | None) -> None:
        nonlocal finished, downloaded_total, failed_total, last_progress_emit_at, last_success_log_at
        max_inflight = max(4, int(config.download_concurrency) * 2)
        active: dict[asyncio.Task, tuple[str, ReportItem, Path]] = {}
        pending_iter = iter(pending_downloads)

        def submit_more() -> None:
            while len(active) < max_inflight:
                try:
                    role, item, target_path = next(pending_iter)
                except StopIteration:
                    break
                task = asyncio.create_task(run_one(session, role, item, target_path))
                active[task] = (role, item, target_path)

        def emit_progress_if_needed(force: bool = False, current_title: str = "", current_code: str = "", current_year: int | None = None) -> None:
            nonlocal last_progress_emit_at
            now = time.perf_counter()
            if not force and finished > 0 and (finished % PDF_PROGRESS_EMIT_EVERY) != 0 and (now - last_progress_emit_at) < PDF_PROGRESS_EMIT_INTERVAL:
                return
            elapsed = max(0.001, now - start_time)
            emit_progress(
                progress_callback,
                phase="download",
                pdf_total=pdf_total,
                total=len(pending_downloads),
                completed=finished,
                downloaded=downloaded_total,
                exists=sum(v["exists"] + v["replaced_exists"] for v in stats_by_year.values()),
                failed=failed_total,
                skipped=sum(v["skipped"] + v["replaced_skipped"] for v in stats_by_year.values()),
                current_title=current_title,
                current_code=current_code,
                current_year=current_year,
                speed_per_minute=_safe_speed_per_minute(finished, elapsed),
                eta_seconds=_safe_eta_seconds(len(pending_downloads), finished, elapsed),
                year_buckets=build_pdf_year_buckets(
                    years,
                    target_by_year,
                    replaced_by_year,
                    stats_by_year,
                    current_year=current_year,
                ),
            )
            last_progress_emit_at = now

        submit_more()
        try:
            while active:
                raise_if_cancelled(cancel_requested)
                done, _ = await asyncio.wait(set(active.keys()), timeout=0.2, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                for task in done:
                    active.pop(task, None)
                    role, item, target_path, ok, message = await task
                    finished += 1
                    year = item.report_year
                    if ok and is_complete_pdf(target_path, verify_header=False):
                        refresh_index_with_path(year_indexes[year], target_path)

                    if ok and message == "downloaded":
                        downloaded_total += 1
                        if role == "main":
                            stats_by_year[year]["downloaded"] += 1
                            path_maps_main[year][item.announcement_id] = target_path
                        else:
                            stats_by_year[year]["replaced_downloaded"] += 1
                            path_maps_replaced[year][item.announcement_id] = target_path
                        now = time.perf_counter()
                        if finished == len(pending_downloads) or (finished % PDF_LOG_EMIT_EVERY) == 0 or (now - last_success_log_at) >= PDF_LOG_EMIT_INTERVAL:
                            emit_log(
                                log_callback,
                                "INFO",
                                f"PDF 下载进度 [{finished}/{len(pending_downloads)}]：新增 {downloaded_total}，已存在 {sum(v['exists'] + v['replaced_exists'] for v in stats_by_year.values())}",
                            )
                            last_success_log_at = now
                    elif ok and message == "exists":
                        if role == "main":
                            stats_by_year[year]["exists"] += 1
                            path_maps_main[year][item.announcement_id] = target_path
                        else:
                            stats_by_year[year]["replaced_exists"] += 1
                            path_maps_replaced[year][item.announcement_id] = target_path
                    elif is_permanent_download_message(message):
                        if role == "main":
                            stats_by_year[year]["skipped"] += 1
                        else:
                            stats_by_year[year]["replaced_skipped"] += 1
                        append_permanent_download_failure(output_dir, role, item, target_path, message, permanent_failure_keys)
                        emit_log(log_callback, "WARN", f"{year}年远端 PDF 不可用 [{finished}/{len(pending_downloads)}] [{role}]：{item.sec_code} {item.sec_name}")
                    else:
                        failed_total += 1
                        if role == "main":
                            stats_by_year[year]["failed"] += 1
                        else:
                            stats_by_year[year]["replaced_failed"] += 1
                        emit_log(log_callback, "ERROR", f"{year}年下载失败 [{finished}/{len(pending_downloads)}] [{role}]：{item.sec_code} {item.sec_name} | {message}")

                    emit_progress_if_needed(
                        force=finished == len(pending_downloads) or not ok,
                        current_title=item.announcement_title,
                        current_code=item.sec_code,
                        current_year=year,
                    )
                submit_more()
        finally:
            for task in active:
                if not task.done():
                    task.cancel()
            if active:
                await asyncio.gather(*active.keys(), return_exceptions=True)

    if pending_downloads:
        if aiohttp is None:
            emit_log(log_callback, "WARN", "未安装 aiohttp，快速模式退化为同步下载逻辑")
            await run_all(None)
        else:
            timeout = aiohttp.ClientTimeout(total=120)
            connector = aiohttp.TCPConnector(limit=max(32, int(config.download_concurrency) * 4))
            async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=DEFAULT_HEADERS) as session:
                await run_all(session)

    for year in years:
        year_dir = output_dir / str(year)
        write_metadata_fast(year_dir / "metadata.csv", target_by_year.get(year, []), path_maps_main[year])
        write_replaced_metadata_fast(
            year_dir / REPLACED_REPORTS_METADATA_NAME,
            replaced_by_year.get(year, []),
            path_maps_replaced[year],
            target_by_year.get(year, []),
            path_maps_main[year],
        )

    merged_summary = update_summary_json_fast(output_dir, target_by_year, replaced_by_year, stats_by_year)
    elapsed = time.perf_counter() - start_time
    exists_total = sum(v["exists"] + v["replaced_exists"] for v in stats_by_year.values())
    skipped_total = sum(v["skipped"] + v["replaced_skipped"] for v in stats_by_year.values())
    emit_progress(
        progress_callback,
        phase="done",
        elapsed_seconds=elapsed,
        pdf_total=pdf_total,
        downloaded=downloaded_total,
        exists=exists_total,
        failed=failed_total,
        skipped=skipped_total,
        speed_per_minute=_safe_speed_per_minute(len(pending_downloads), elapsed),
        eta_seconds=0,
        year_buckets=build_pdf_year_buckets(years, target_by_year, replaced_by_year, stats_by_year),
    )
    emit_log(log_callback, "INFO", f"快速 PDF 下载完成：总量 {pdf_total}，新下载 {downloaded_total}，已存在 {exists_total}，跳过 {skipped_total}，失败 {failed_total}")
    return PdfDownloadResult(
        output_dir=output_dir,
        state_dir=state_dir,
        summary_path=output_dir / "summary.json",
        summary=merged_summary if isinstance(merged_summary, list) else None,
        elapsed_seconds=elapsed,
        pdf_total=pdf_total,
        downloaded=downloaded_total,
        exists=exists_total,
        failed=failed_total,
        skipped=skipped_total,
    )


def _run_extract_worker(pdf_path: Path, output_path: Path) -> tuple[Path, Path, bool, str, int, int]:
    try:
        page_count, char_count = extract_text_to_file(pdf_path, output_path)
        return pdf_path, output_path, True, "", page_count, char_count
    except Exception as exc:
        return pdf_path, output_path, False, str(exc), 0, 0


async def run_extraction_fast(
    config: ExtractTextConfig,
    *,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: Optional[Callable[[], bool]] = None,
    checkpoint_every: int = 120,
    checkpoint_interval: float = 8.0,
) -> ExtractTextResult:
    start_time = time.perf_counter()
    input_dir = config.input_dir
    output_dir = config.output_dir
    state_dir = config.state_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = collect_pdf_paths_fast(input_dir, config.start_year, config.end_year)
    years = list(range(config.start_year or 0, (config.end_year or 0) + 1)) if config.start_year is not None and config.end_year is not None else sorted({int(path.parent.name) for path in pdf_paths if path.parent.name.isdigit()})
    checkpoint_path = state_dir / TEXT_CHECKPOINT_NAME
    checkpoint = read_text_json(checkpoint_path) or {}
    jobs = checkpoint.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}
        checkpoint["jobs"] = jobs

    job_key = build_job_key(input_dir, output_dir)
    job = jobs.get(job_key)
    if not isinstance(job, dict):
        job = {}
        jobs[job_key] = job

    files = job.get("files")
    if not isinstance(files, dict):
        files = {}
        job["files"] = files

    job["input_dir"] = str(input_dir.resolve())
    job["output_dir"] = str(output_dir.resolve())
    job["updated_at"] = datetime.now().isoformat(timespec="seconds")
    stats = {"extracted": 0, "exists": 0, "failed": 0}
    stats_by_year: dict[int, dict[str, int]] = {year: {"extracted": 0, "exists": 0, "failed": 0} for year in years}
    totals_by_year: dict[int, int] = {year: 0 for year in years}
    failed_samples: list[dict[str, str]] = []
    work_items: list[tuple[Path, Path]] = []

    for pdf_path in pdf_paths:
        rel_pdf = pdf_path.relative_to(input_dir).as_posix()
        year = int(Path(rel_pdf).parts[0]) if Path(rel_pdf).parts and Path(rel_pdf).parts[0].isdigit() else None
        if year is not None:
            totals_by_year[year] = totals_by_year.get(year, 0) + 1
        output_path = build_output_path(input_dir, output_dir, pdf_path)
        rel_txt = output_path.relative_to(output_dir).as_posix()
        state = files.get(rel_pdf, {})
        if state.get("status") == "completed" and is_output_complete(output_path):
            stats["exists"] += 1
            if year is not None:
                stats_by_year.setdefault(year, {"extracted": 0, "exists": 0, "failed": 0})["exists"] += 1
            continue
        if is_output_complete(output_path):
            stats["exists"] += 1
            if year is not None:
                stats_by_year.setdefault(year, {"extracted": 0, "exists": 0, "failed": 0})["exists"] += 1
            files[rel_pdf] = {
                "status": "completed",
                "output": rel_txt,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            continue
        work_items.append((pdf_path, output_path))

    write_text_json(checkpoint_path, checkpoint)
    emit_log(log_callback, "INFO", f"快速文本提取启动：PDF 总数 {len(pdf_paths)}，已存在 {stats['exists']}，待处理 {len(work_items)}，进程数 {max(1, config.concurrency)}")
    emit_progress(
        progress_callback,
        phase="prepare",
        total=len(work_items),
        completed=0,
        existing=stats["exists"],
        failed=0,
        extracted=0,
        pdf_total=len(pdf_paths),
        year_buckets=build_extract_year_buckets(years, totals_by_year, stats_by_year),
        speed_per_minute=0.0,
        eta_seconds=0,
    )

    worker_count = max(1, config.concurrency)
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(max_workers=worker_count)
    pending: dict[asyncio.Future, tuple[Path, Path]] = {}
    pending_iter = iter(work_items)
    finished = 0
    dirty_count = 0
    last_checkpoint_at = time.perf_counter()
    last_progress_emit_at = 0.0
    last_success_log_at = 0.0

    def flush_checkpoint(force: bool = False) -> None:
        nonlocal dirty_count, last_checkpoint_at
        now = time.perf_counter()
        if not force and dirty_count < checkpoint_every and (now - last_checkpoint_at) < checkpoint_interval:
            return
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")
        write_text_json(checkpoint_path, checkpoint)
        dirty_count = 0
        last_checkpoint_at = now

    def submit_more() -> None:
        while len(pending) < worker_count * 2:
            try:
                pdf_path, output_path = next(pending_iter)
            except StopIteration:
                break
            future = loop.run_in_executor(executor, _run_extract_worker, pdf_path, output_path)
            pending[future] = (pdf_path, output_path)

    try:
        submit_more()
        while pending:
            if cancel_requested is not None and cancel_requested():
                raise ExtractionCancelled("fast extraction cancelled")
            done, _ = await asyncio.wait(set(pending.keys()), timeout=0.2, return_when=FIRST_COMPLETED)
            if not done:
                continue
            for future in done:
                pending.pop(future, None)
                pdf_path, output_path, ok, err, page_count, char_count = await future
                finished += 1
                rel_pdf = pdf_path.relative_to(input_dir).as_posix()
                rel_txt = output_path.relative_to(output_dir).as_posix()
                current_year = int(Path(rel_pdf).parts[0]) if Path(rel_pdf).parts and Path(rel_pdf).parts[0].isdigit() else None

                if ok:
                    stats["extracted"] += 1
                    if current_year is not None:
                        stats_by_year.setdefault(current_year, {"extracted": 0, "exists": 0, "failed": 0})["extracted"] += 1
                    files[rel_pdf] = {
                        "status": "completed",
                        "output": rel_txt,
                        "pages": page_count,
                        "chars": char_count,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    now = time.perf_counter()
                    if finished == len(work_items) or (finished % EXTRACT_LOG_EMIT_EVERY) == 0 or (now - last_success_log_at) >= EXTRACT_LOG_EMIT_INTERVAL:
                        emit_log(log_callback, "INFO", f"文本提取进度 [{finished}/{len(work_items)}]：新增 {stats['extracted']}，失败 {stats['failed']}")
                        last_success_log_at = now
                else:
                    stats["failed"] += 1
                    if current_year is not None:
                        stats_by_year.setdefault(current_year, {"extracted": 0, "exists": 0, "failed": 0})["failed"] += 1
                    files[rel_pdf] = {
                        "status": "failed",
                        "output": rel_txt,
                        "error": err,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    if len(failed_samples) < FAILED_SAMPLE_LIMIT:
                        failed_samples.append({"pdf": rel_pdf, "error": err})
                    emit_log(log_callback, "ERROR", f"文本提取失败 [{finished}/{len(work_items)}]：{rel_pdf} | {err}")

                dirty_count += 1
                flush_checkpoint()
                now = time.perf_counter()
                if (
                    finished == len(work_items)
                    or not ok
                    or (finished % EXTRACT_PROGRESS_EMIT_EVERY) == 0
                    or (now - last_progress_emit_at) >= EXTRACT_PROGRESS_EMIT_INTERVAL
                ):
                    elapsed = max(0.001, now - last_checkpoint_at + (last_checkpoint_at - start_time if 'start_time' in globals() else 0))
                    elapsed = max(0.001, now - start_time)
                    emit_progress(
                        progress_callback,
                        phase="extract",
                        total=len(work_items),
                        completed=finished,
                        existing=stats["exists"],
                        failed=stats["failed"],
                        extracted=stats["extracted"],
                        current_pdf=rel_pdf,
                        current_output=rel_txt,
                        pdf_total=len(pdf_paths),
                        current_year=current_year,
                        speed_per_minute=_safe_speed_per_minute(finished, elapsed),
                        eta_seconds=_safe_eta_seconds(len(work_items), finished, elapsed),
                        year_buckets=build_extract_year_buckets(
                            years,
                            totals_by_year,
                            stats_by_year,
                            current_year=current_year,
                        ),
                    )
                    last_progress_emit_at = now
            submit_more()
    finally:
        flush_checkpoint(force=True)
        executor.shutdown(wait=False, cancel_futures=True)

    summary = build_text_summary(input_dir, output_dir, pdf_paths, stats, config.start_year, config.end_year, failed_samples)
    summary_path = output_dir / TEXT_SUMMARY_NAME
    write_text_json(summary_path, summary)
    emit_log(log_callback, "INFO", f"快速文本提取完成：提取 {stats['extracted']}，已存在 {stats['exists']}，失败 {stats['failed']}")
    emit_progress(
        progress_callback,
        phase="done",
        total=len(work_items),
        completed=len(work_items),
        existing=stats["exists"],
        failed=stats["failed"],
        extracted=stats["extracted"],
        summary_path=str(summary_path),
        checkpoint_path=str(checkpoint_path),
        pdf_total=len(pdf_paths),
        current_year=None,
        speed_per_minute=_safe_speed_per_minute(len(work_items), max(0.001, time.perf_counter() - start_time)),
        eta_seconds=0,
        year_buckets=build_extract_year_buckets(years, totals_by_year, stats_by_year),
    )
    return ExtractTextResult(
        summary=summary,
        summary_path=summary_path,
        checkpoint_path=checkpoint_path,
        stats=dict(stats),
        pdf_total=len(pdf_paths),
        pending_total=len(work_items),
    )


async def run_links_fast(
    config: SpiderConfig,
    *,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
) -> list[dict[str, Any]]:
    output_dir = Path(config.output_dir)
    state_dir = Path(config.state_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    client = CninfoClient(timeout=40.0, request_interval=config.request_interval)
    await asyncio.to_thread(client.warmup)

    summary: list[dict[str, Any]] = []
    years = list(range(config.start_year, config.end_year + 1))
    emit_log(log_callback, "INFO", "快速公告抓取已启动")

    async def run_years(announcement_session):
        for index, year in enumerate(years, start=1):
            raise_if_cancelled(cancel_requested)
            se_date = config.se_date or f"{year + 1}-01-01~{year + 2}-06-30"
            emit_log(log_callback, "INFO", f"开始抓取 {year} 年公告，窗口 {se_date}")
            announcements = await fetch_announcements_for_year(
                client,
                announcement_session,
                year,
                se_date,
                config.page_size,
                state_dir,
                config.announcement_concurrency,
            )
            reports, filtered_out, replaced_reports = classify_reports_with_replaced(announcements, year)
            artifacts = sync_year_outputs_with_replaced(output_dir, reports, filtered_out, replaced_reports)
            summary.append(
                {
                    "year": year,
                    "raw_total": len(announcements),
                    "filtered_total": len(reports),
                    "replaced_total": len(replaced_reports),
                    "filtered_out_total": len(filtered_out),
                    "filtered_paths": artifacts.filtered_paths,
                    "filtered_out_paths": artifacts.filtered_out_paths,
                    "replaced_paths": artifacts.replaced_paths,
                    "metadata_csv_paths": artifacts.metadata_paths,
                    "replaced_metadata_csv_paths": artifacts.replaced_metadata_paths,
                    "report_year_range": format_report_year_range(config.start_year, config.end_year),
                    "effective_se_date": se_date,
                    "se_date_mode": "custom" if config.se_date else "default_per_year",
                }
            )
            emit_progress(
                progress_callback,
                phase="links",
                current=index,
                total=len(years),
                year=year,
                raw_total=len(announcements),
                filtered_total=len(reports),
                filtered_out_total=len(filtered_out),
            )

    if aiohttp is None:
        await run_years(None)
    else:
        timeout = aiohttp.ClientTimeout(total=120)
        connector = aiohttp.TCPConnector(limit=max(32, config.announcement_concurrency * 4))
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=DEFAULT_HEADERS,
            cookies=client.session.cookies.get_dict(),
        ) as announcement_session:
            await run_years(announcement_session)

    write_json(output_dir / "summary.json", summary)
    emit_log(log_callback, "INFO", f"快速公告抓取完成，共处理 {len(years)} 个年份")
    return summary


async def run_pipeline_fast(
    config: SpiderConfig,
    *,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
    extract_concurrency: int = 2,
) -> dict[str, Any]:
    links_summary = await run_links_fast(config, log_callback=log_callback, progress_callback=progress_callback, cancel_requested=cancel_requested)
    pdf_result = await run_pdf_download_service_fast(config, log_callback=log_callback, progress_callback=progress_callback, cancel_requested=cancel_requested)
    extract_result = await run_extraction_fast(
        ExtractTextConfig(
            input_dir=Path(config.output_dir),
            output_dir=Path(config.output_dir).parent / "txt_extract",
            state_dir=Path(config.state_dir),
            start_year=config.start_year,
            end_year=config.end_year,
            concurrency=extract_concurrency,
        ),
        log_callback=log_callback,
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
    )
    return {"links": links_summary, "pdf": pdf_result, "extract": extract_result}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AnnualReportSpider 快速版：保持原目录兼容，优化 PDF/TXT 性能")
    parser.add_argument("--mode", choices=["links", "pdf", "extract", "pipeline"], default="pdf")
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--se-date", default=None)
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--request-interval", type=float, default=0.2)
    parser.add_argument("--announcement-concurrency", type=int, default=8)
    parser.add_argument("--download-concurrency", type=int, default=12)
    parser.add_argument("--extract-concurrency", type=int, default=2)
    parser.add_argument("--output-dir", default="annual_reports")
    parser.add_argument("--text-output-dir", default="txt_extract")
    parser.add_argument("--state-dir", default=".")
    return parser


async def main_async(args: argparse.Namespace) -> None:
    if args.mode in {"links", "pdf", "pipeline"}:
        config = SpiderConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            se_date=args.se_date,
            page_size=args.page_size,
            request_interval=args.request_interval,
            announcement_concurrency=args.announcement_concurrency,
            download_concurrency=args.download_concurrency,
            output_dir=args.output_dir,
            state_dir=args.state_dir,
            download_pdf=args.mode in {"pdf", "pipeline"},
            metadata_only=args.mode == "links",
        )
    else:
        config = None

    if args.mode == "links":
        await run_links_fast(config)
        return
    if args.mode == "pdf":
        await run_pdf_download_service_fast(config)
        return
    if args.mode == "extract":
        await run_extraction_fast(
            ExtractTextConfig(
                input_dir=Path(args.output_dir),
                output_dir=Path(args.text_output_dir),
                state_dir=Path(args.state_dir),
                start_year=args.start_year,
                end_year=args.end_year,
                concurrency=args.extract_concurrency,
            )
        )
        return
    await run_pipeline_fast(config, extract_concurrency=args.extract_concurrency)


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
