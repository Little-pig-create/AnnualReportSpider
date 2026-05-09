from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import spider as spider_module
from spider import SpiderCancelled, SpiderConfig, run_spider_service

from ..infra.file_ops import resolve_project_path


FILTERED_OUT_FILENAME = "filtered_out_announcements.jsonl"
MARKET_SCOPE_TO_PLATES = {
    "a_share": ["sz", "szmb", "szcy", "sh", "shmb", "shkcp"],
    "b_share": ["szb", "shb"],
    "bjse": ["bj"],
}


class LinksService:
    stage = "links"
    title = "公告链接抓取"

    async def run(self, settings, reporter, cancel_token) -> dict[str, Any]:
        workspace = settings.workspace
        links = settings.links
        output_dir = resolve_project_path(workspace.projectRoot, workspace.annualReportDir)
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)
        checkpoint_path = state_dir / "checkpoint.json"

        if links.resetCheckpoint and checkpoint_path.exists():
            checkpoint_path.unlink()
            reporter.log("INFO", self.stage, f"已重置 checkpoint: {checkpoint_path}")

        selected_market_scopes = links.marketScopes or ["a_share"]
        selected_plates: list[str] = []
        for scope in selected_market_scopes:
            for plate in MARKET_SCOPE_TO_PLATES.get(scope, []):
                if plate not in selected_plates:
                    selected_plates.append(plate)

        plate_value = ";".join(selected_plates)
        original_all_plates = spider_module.ALL_PLATES
        spider_module.ALL_PLATES = plate_value
        reporter.log("INFO", self.stage, f"selected plates: {plate_value}")

        config = SpiderConfig(
            start_year=workspace.startYear,
            end_year=workspace.endYear,
            se_date=links.seDate.strip() or None,
            page_size=links.pageSize,
            request_interval=links.requestInterval,
            announcement_concurrency=links.announcementConcurrency,
            download_concurrency=max(1, settings.pdf.downloadConcurrency),
            output_dir=str(output_dir),
            state_dir=str(state_dir),
            download_pdf=False,
            metadata_only=True,
            audit_pdf=False,
            cleanup_orphan_pdf=False,
        )

        years = list(range(workspace.startYear, workspace.endYear + 1))
        year_total = max(1, len(years))
        year_counts = {year: 0 for year in years}
        year_live_counts = {year: 0 for year in years}
        year_status = {year: "pending" for year in years}
        touched_years: set[int] = set()

        live_stats: dict[str, Any] = {
            "yearTotal": year_total,
            "currentYearIndex": 0,
            "currentYear": workspace.startYear,
            "rangeCurrent": 0,
            "rangeTotal": 0,
            "recordsFound": 0,
            "rawRecordsFound": 0,
            "currentWindow": "",
            "overallPercent": 0.0,
            "totalAnnouncements": 0,
            "countBasis": f"counts come from {FILTERED_OUT_FILENAME}, active year may temporarily use live crawl count",
            "yearBuckets": [],
        }
        last_emit_at = 0.0
        last_emit_message = ""
        min_emit_interval = 0.35

        range_progress_re = re.compile(r"\[(?P<current>\d+)/(?P<total>\d+)\]")
        page_progress_re = re.compile(r"page\s+(?P<page>\d+)/(?P<total>\d+)", re.IGNORECASE)
        count_re = re.compile(r"(?P<count>\d+)\s*条公告")

        year_banner_re = re.compile(r"^\s*=+\s*(?P<year>\d{4})\s*年年报")
        year_breakpoint_re = re.compile(r"^\s*(?P<year>\d{4})\s*年检测到断点")
        year_cache_re = re.compile(r"^\s*(?P<year>\d{4})\s*年\s*从缓存加载")
        year_done_re = re.compile(r"^\s*(?P<year>\d{4})\s*年.*(?:仅抓取公告|已完成|完成)$")

        def filtered_out_path(year: int) -> Path:
            return output_dir / str(year) / FILTERED_OUT_FILENAME

        def count_jsonl_rows(path: Path) -> int:
            if not path.exists():
                return 0
            count = 0
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        count += 1
            return count

        def active_year() -> int:
            current = int(live_stats.get("currentYear") or workspace.startYear)
            return current if current in year_counts else workspace.startYear

        def sync_year_count(year: int) -> None:
            touched_years.add(year)
            current_rows = count_jsonl_rows(filtered_out_path(year))
            year_counts[year] = max(year_counts[year], current_rows)
            if year_status[year] != "running":
                year_live_counts[year] = year_counts[year]
            if active_year() == year:
                live_stats["recordsFound"] = year_counts[year]

        def seed_previous_years(current_year: int) -> None:
            for year in years:
                if year >= current_year:
                    break
                if year_status[year] == "pending":
                    sync_year_count(year)
                    year_status[year] = "completed"

        def refresh_year_buckets() -> None:
            buckets: list[dict[str, Any]] = []
            total = 0
            current_year = active_year()
            for year in years:
                is_active = year == current_year and year_status[year] == "running"
                display_count = year_counts[year]
                if is_active:
                    display_count = max(display_count, year_live_counts[year])
                total += display_count
                buckets.append(
                    {
                        "year": year,
                        "count": display_count,
                        "status": year_status[year],
                        "active": is_active,
                    }
                )
            live_stats["totalAnnouncements"] = total
            live_stats["yearBuckets"] = buckets

        def detect_year(message: str) -> int | None:
            for pattern in (year_banner_re, year_breakpoint_re, year_cache_re, year_done_re):
                match = pattern.search(message)
                if not match:
                    continue
                year = int(match.group("year"))
                if year in year_counts:
                    return year
            return None

        def infer_year(message: str) -> int | None:
            explicit = detect_year(message)
            if explicit is not None:
                return explicit
            if (
                page_progress_re.search(message)
                or "累计公告" in message
                or "条公告" in message
                or "~" in message
            ):
                return active_year()
            return None

        def mark_year_running(year: int) -> None:
            touched_years.add(year)
            seed_previous_years(year)
            for other in years:
                if other != year and year_status[other] == "running":
                    year_status[other] = "pending"
            year_status[year] = "running"
            live_stats["currentYear"] = year
            live_stats["currentYearIndex"] = max(0, year - workspace.startYear + 1)
            live_stats["recordsFound"] = year_counts[year]
            live_stats["rawRecordsFound"] = year_live_counts[year]

        def mark_year_completed(year: int) -> None:
            sync_year_count(year)
            year_status[year] = "completed"
            year_live_counts[year] = year_counts[year]
            if active_year() == year:
                live_stats["rawRecordsFound"] = year_counts[year]

        def emit_live(message: str) -> None:
            nonlocal last_emit_at, last_emit_message
            now = time.perf_counter()
            force_emit = any(
                keyword in message
                for keyword in ("开始抓取", "检测到断点", "仅抓取公告", "已完成", "完成")
            )
            if not force_emit and message == last_emit_message and (now - last_emit_at) < min_emit_interval:
                return
            if not force_emit and (now - last_emit_at) < min_emit_interval:
                return

            completed_count = sum(1 for year in years if year_status[year] == "completed")
            fraction = 0.0
            if int(live_stats["rangeTotal"] or 0) > 0:
                fraction = min(
                    max(int(live_stats["rangeCurrent"]) / max(int(live_stats["rangeTotal"]), 1), 0.0),
                    1.0,
                )
            running_bonus = 0.0
            current_year = active_year()
            if year_status[current_year] == "running":
                running_bonus = fraction

            live_stats["overallPercent"] = min((completed_count + running_bonus) / year_total, 0.99)
            refresh_year_buckets()
            reporter.progress(
                self.stage,
                int(live_stats["overallPercent"] * 100),
                100,
                message,
                dict(live_stats),
            )
            last_emit_at = now
            last_emit_message = message

        def on_log(level: str, message: str) -> None:
            reporter.log(level.upper(), self.stage, message)
            year = infer_year(message)
            if year is None:
                return

            mark_year_running(year)

            range_match = range_progress_re.search(message)
            if range_match:
                live_stats["rangeCurrent"] = int(range_match.group("current"))
                live_stats["rangeTotal"] = int(range_match.group("total"))

            count_match = count_re.search(message)
            if count_match:
                year_live_counts[year] = max(year_live_counts[year], int(count_match.group("count")))
                live_stats["rawRecordsFound"] = year_live_counts[year]

            if "~" in message:
                live_stats["currentWindow"] = message.strip()

            if "开始抓取" in message:
                live_stats["currentWindow"] = "开始抓取"

            if "检测到断点" in message:
                live_stats["currentWindow"] = "断点恢复"

            if "累计公告" in message:
                page_match = page_progress_re.search(message)
                if page_match:
                    live_stats["currentWindow"] = f"page {page_match.group('page')}/{page_match.group('total')}"

            if "过滤" in message or "被过滤公告" in message or "仅抓取公告" in message or "完成" in message:
                sync_year_count(year)

            if "仅抓取公告" in message or year_done_re.search(message):
                mark_year_completed(year)

            emit_live(message.strip()[:120])

        def on_progress(payload: dict[str, Any]) -> None:
            if payload.get("phase") == "log":
                return
            if payload.get("phase") == "done":
                for year in touched_years:
                    mark_year_completed(year)
                live_stats["overallPercent"] = 1.0
                refresh_year_buckets()
                reporter.progress(
                    self.stage,
                    100,
                    100,
                    "links completed, summarizing results",
                    {
                        **live_stats,
                        "elapsedSeconds": payload.get("elapsed_seconds", 0),
                    },
                )

        refresh_year_buckets()
        reporter.progress(
            self.stage,
            0,
            100,
            "waiting for first crawl signal",
            dict(live_stats),
        )

        try:
            try:
                result = await run_spider_service(
                    config,
                    log_callback=on_log,
                    progress_callback=on_progress,
                    cancel_requested=cancel_token.cancel_requested,
                    console_log=False,
                )
            finally:
                spider_module.ALL_PLATES = original_all_plates
        except SpiderCancelled:
            raise

        for year in touched_years:
            sync_year_count(year)

        year_buckets = [{"year": year, "count": year_counts[year]} for year in years]
        payload = {
            "rows": sum(year_counts.values()),
            "years": [item["year"] for item in year_buckets if item["count"] > 0],
            "yearBuckets": year_buckets,
            "preview": [],
            "outputDir": str(result.output_dir),
            "summaryPath": str(result.summary_path) if result.summary_path else "",
            "elapsedSeconds": result.elapsed_seconds,
            "checkpointPath": str(checkpoint_path),
            "live": dict(live_stats),
        }

        if links.deleteCheckpointOnSuccess and checkpoint_path.exists():
            checkpoint_path.unlink()
            reporter.log("INFO", self.stage, f"deleted checkpoint: {checkpoint_path}")

        reporter.progress(
            self.stage,
            100,
            100,
            f"links completed, current run delta = {sum(year_counts.values())}",
            payload,
        )
        return payload
