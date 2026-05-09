from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any

from app_metadata import APP_VERSION, GITHUB_URL
from extract_text import (
    CHECKPOINT_NAME as EXTRACT_CHECKPOINT_NAME,
    ExtractTextConfig,
    ExtractionCancelled,
    run_extraction,
)
from spider import (
    SpiderCancelled,
    SpiderConfig,
    run_pdf_download_service,
    run_spider_service,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPIDER_CHECKPOINT_NAME = "checkpoint.json"
CONFIG_PATH = PROJECT_ROOT / "enterprise_console" / "console_config.json"


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def load_text_file(path: Path) -> str:
    if not path.exists():
        return f"文件不存在: {path}"
    for encoding in ("utf-8", "utf-8-sig", "gbk", "cp936"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


@dataclass(slots=True)
class WorkspaceSettings:
    project_root: str = str(PROJECT_ROOT)
    annual_report_dir: str = "annual_reports"
    text_output_dir: str = "txt_extract"
    state_dir: str = "."
    start_year: int = 2014
    end_year: int = 2024


@dataclass(slots=True)
class SpiderStageSettings:
    se_date: str = ""
    page_size: int = 30
    request_interval: float = 0.2
    announcement_concurrency: int = 2
    download_concurrency: int = 2
    download_pdf: bool = True
    metadata_only: bool = False
    audit_pdf: bool = False
    cleanup_orphan_pdf: bool = False
    reset_checkpoint: bool = False
    delete_checkpoint_on_success: bool = False


@dataclass(slots=True)
class ExtractStageSettings:
    concurrency: int = 2
    reset_checkpoint: bool = False
    delete_checkpoint_on_success: bool = False


@dataclass(slots=True)
class ConsoleSettings:
    workspace: WorkspaceSettings
    spider: SpiderStageSettings
    extract: ExtractStageSettings


def default_settings() -> ConsoleSettings:
    return ConsoleSettings(
        workspace=WorkspaceSettings(),
        spider=SpiderStageSettings(),
        extract=ExtractStageSettings(),
    )


def load_settings() -> ConsoleSettings:
    settings = default_settings()
    if not CONFIG_PATH.exists():
        return settings
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return settings
    return ConsoleSettings(
        workspace=WorkspaceSettings(**payload.get("workspace", {})),
        spider=SpiderStageSettings(**payload.get("spider", {})),
        extract=ExtractStageSettings(**payload.get("extract", {})),
    )


def save_settings(settings: ConsoleSettings) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_path(project_root: str, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (Path(project_root) / path).resolve()


def delete_file_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def summarize_spider_output(summary_path: Path | None) -> dict[str, Any]:
    if summary_path is None or not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, list):
        years = sorted(
            {
                row.get("report_year", row.get("year"))
                for row in payload
                if isinstance(row, dict) and row.get("report_year", row.get("year")) is not None
            }
        )
        return {
            "rows": len(payload),
            "years": years,
            "preview": payload[:100],
        }
    if isinstance(payload, dict):
        return payload
    return {}


def summarize_extract_output(summary_path: Path | None) -> dict[str, Any]:
    if summary_path is None or not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_about_payload() -> dict[str, str]:
    readme = load_text_file(PROJECT_ROOT / "README.md")
    gui_readme = load_text_file(PROJECT_ROOT / "GUI_README.md")
    return {
        "app_version": APP_VERSION,
        "github_url": GITHUB_URL,
        "readme": readme,
        "gui_readme": gui_readme,
    }


class ExecutionWorker(threading.Thread):
    def __init__(
        self,
        *,
        queue: Queue[dict[str, Any]],
        mode: str,
        settings: ConsoleSettings,
    ) -> None:
        super().__init__(daemon=True)
        self.queue = queue
        self.mode = mode
        self.settings = settings
        self._cancel_event = threading.Event()
        self._run_started_at = 0.0

    def cancel(self) -> None:
        self._cancel_event.set()

    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def emit(self, event: str, **payload: Any) -> None:
        self.queue.put({"event": event, "timestamp": now_text(), **payload})

    def log(self, level: str, message: str) -> None:
        self.emit("log", level=level.upper(), message=message)

    def run(self) -> None:
        self._run_started_at = time.perf_counter()
        self.emit("run_started", mode=self.mode, project_root=self.settings.workspace.project_root)
        try:
            asyncio.run(self._run_async())
        except (SpiderCancelled, ExtractionCancelled):
            self.emit("run_stopped", elapsed_seconds=time.perf_counter() - self._run_started_at)
        except Exception as exc:
            self.emit(
                "run_error",
                error=str(exc),
                elapsed_seconds=time.perf_counter() - self._run_started_at,
            )

    async def _run_async(self) -> None:
        links_payload: dict[str, Any] | None = None
        pdf_payload: dict[str, Any] | None = None
        extract_payload: dict[str, Any] | None = None

        if self.mode in {"links", "pipeline"}:
            links_payload = await self._run_links_stage()
        if self.cancel_requested():
            raise SpiderCancelled("cancelled")

        if self.mode in {"pdf", "pipeline"}:
            pdf_payload = await self._run_pdf_stage()
        if self.cancel_requested():
            raise SpiderCancelled("cancelled")

        if self.mode in {"extract", "pipeline"}:
            extract_payload = await self._run_extract_stage()
        if self.cancel_requested():
            raise ExtractionCancelled("cancelled")

        self.emit(
            "run_completed",
            mode=self.mode,
            elapsed_seconds=time.perf_counter() - self._run_started_at,
            links=links_payload or {},
            pdf=pdf_payload or {},
            extract=extract_payload or {},
        )

    async def _run_links_stage(self) -> dict[str, Any]:
        workspace = self.settings.workspace
        spider_settings = self.settings.spider
        state_dir = resolve_path(workspace.project_root, workspace.state_dir)
        checkpoint_path = state_dir / SPIDER_CHECKPOINT_NAME

        if spider_settings.reset_checkpoint:
            delete_file_if_exists(checkpoint_path)
            self.emit("stage_notice", stage="links", message=f"已重置 {checkpoint_path}")

        config = SpiderConfig(
            start_year=safe_int(workspace.start_year, 2014),
            end_year=safe_int(workspace.end_year, 2024),
            se_date=spider_settings.se_date.strip() or None,
            page_size=safe_int(spider_settings.page_size, 30),
            request_interval=safe_float(spider_settings.request_interval, 0.2),
            announcement_concurrency=max(1, safe_int(spider_settings.announcement_concurrency, 2)),
            download_concurrency=max(1, safe_int(spider_settings.download_concurrency, 2)),
            output_dir=str(resolve_path(workspace.project_root, workspace.annual_report_dir)),
            state_dir=str(state_dir),
            download_pdf=False,
            metadata_only=True,
            audit_pdf=False,
            cleanup_orphan_pdf=False,
        )

        self.emit("stage_started", stage="links", title="公告链接抓取", checkpoint=str(checkpoint_path))
        result = await run_spider_service(
            config,
            log_callback=self.log,
            progress_callback=lambda payload: self.emit("link_progress", payload=payload),
            cancel_requested=self.cancel_requested,
            console_log=False,
        )

        if spider_settings.delete_checkpoint_on_success:
            delete_file_if_exists(checkpoint_path)
            self.emit("stage_notice", stage="links", message=f"已删除 {checkpoint_path}")

        summary = summarize_spider_output(result.summary_path)
        payload = {
            "summary_path": str(result.summary_path) if result.summary_path else "",
            "output_dir": str(result.output_dir),
            "elapsed_seconds": result.elapsed_seconds,
            "mode": result.mode,
            "rows": summary.get("rows", 0),
            "years": summary.get("years", []),
            "preview": summary.get("preview", []),
        }
        self.emit("stage_completed", stage="links", payload=payload)
        return payload

    async def _run_pdf_stage(self) -> dict[str, Any]:
        workspace = self.settings.workspace
        spider_settings = self.settings.spider
        state_dir = resolve_path(workspace.project_root, workspace.state_dir)
        output_dir = resolve_path(workspace.project_root, workspace.annual_report_dir)

        config = SpiderConfig(
            start_year=safe_int(workspace.start_year, 2014),
            end_year=safe_int(workspace.end_year, 2024),
            se_date=spider_settings.se_date.strip() or None,
            page_size=safe_int(spider_settings.page_size, 30),
            request_interval=safe_float(spider_settings.request_interval, 0.2),
            announcement_concurrency=max(1, safe_int(spider_settings.announcement_concurrency, 2)),
            download_concurrency=max(1, safe_int(spider_settings.download_concurrency, 2)),
            output_dir=str(output_dir),
            state_dir=str(state_dir),
            download_pdf=True,
            metadata_only=False,
            audit_pdf=False,
            cleanup_orphan_pdf=False,
        )

        self.emit("stage_started", stage="pdf", title="PDF 文件爬取")
        result = await run_pdf_download_service(
            config,
            log_callback=self.log,
            progress_callback=lambda payload: self.emit("pdf_progress", payload=payload),
            cancel_requested=self.cancel_requested,
            console_log=False,
        )

        payload = {
            "summary_path": str(result.summary_path) if result.summary_path else "",
            "output_dir": str(result.output_dir),
            "elapsed_seconds": result.elapsed_seconds,
            "pdf_total": result.pdf_total,
            "downloaded": result.downloaded,
            "exists": result.exists,
            "failed": result.failed,
            "skipped": result.skipped,
        }
        self.emit("stage_completed", stage="pdf", payload=payload)
        return payload

    async def _run_extract_stage(self) -> dict[str, Any]:
        workspace = self.settings.workspace
        extract_settings = self.settings.extract
        state_dir = resolve_path(workspace.project_root, workspace.state_dir)
        checkpoint_path = state_dir / EXTRACT_CHECKPOINT_NAME

        if extract_settings.reset_checkpoint:
            delete_file_if_exists(checkpoint_path)
            self.emit("stage_notice", stage="extract", message=f"已重置 {checkpoint_path}")

        config = ExtractTextConfig(
            input_dir=resolve_path(workspace.project_root, workspace.annual_report_dir),
            output_dir=resolve_path(workspace.project_root, workspace.text_output_dir),
            state_dir=state_dir,
            start_year=safe_int(workspace.start_year, 2014),
            end_year=safe_int(workspace.end_year, 2024),
            concurrency=max(1, safe_int(extract_settings.concurrency, 2)),
        )

        self.emit("stage_started", stage="extract", title="文本提取", checkpoint=str(checkpoint_path))
        result = await run_extraction(
            config,
            log_callback=self.log,
            progress_callback=lambda payload: self.emit("extract_progress", payload=payload),
            cancel_requested=self.cancel_requested,
        )

        if extract_settings.delete_checkpoint_on_success:
            delete_file_if_exists(checkpoint_path)
            self.emit("stage_notice", stage="extract", message=f"已删除 {checkpoint_path}")

        summary = summarize_extract_output(result.summary_path)
        payload = {
            "summary_path": str(result.summary_path),
            "checkpoint_path": str(result.checkpoint_path),
            "output_dir": str(config.output_dir),
            "pdf_total": result.pdf_total,
            "pending_total": result.pending_total,
            "extracted": result.stats.get("extracted", 0),
            "exists": result.stats.get("exists", 0),
            "failed": result.stats.get("failed", 0),
            "elapsed_seconds": time.perf_counter() - self._run_started_at,
            "summary": summary,
        }
        self.emit("stage_completed", stage="extract", payload=payload)
        return payload
