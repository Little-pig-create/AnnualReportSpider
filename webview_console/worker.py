from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from extract_text import ExtractionCancelled
from spider import SpiderCancelled

from . import events
from .infra.cancellation import CancelToken
from .models import LogItem, Progress, RunState, STAGE_ORDER, STAGE_TITLES
from .services import ExtractService, LinksService, PdfService


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(slots=True)
class Reporter:
    runtime: Any
    run_state: RunState

    def log(self, level: str, stage: str, message: str) -> None:
        item = LogItem(time=now_text(), level=level, stage=stage, message=message)
        self.run_state.logs.append(item)
        if len(self.run_state.logs) > 1000:
            del self.run_state.logs[:-1000]
        self.runtime.emit(events.log_append(self.run_state.run_id, level, stage, message, item.time))

    def progress(
        self,
        stage: str,
        current: int,
        total: int,
        message: str = "",
        stats: dict[str, Any] | None = None,
    ) -> None:
        stage_state = self.run_state.stages[stage]
        total = max(int(total), 0)
        current = max(int(current), 0)
        if total > 0:
            current = min(current, total)
        percent = 1.0 if total == 0 and current > 0 else (current / total if total else 0.0)
        stage_state.progress = Progress(current=current, total=total, percent=percent)
        stage_state.hint = message
        if stats:
            stage_state.result = {
                **(stage_state.result or {}),
                **stats,
            }
        self.runtime.emit(
            events.stage_progress(
                self.run_state.run_id,
                stage,
                current,
                total,
                percent,
                message,
                stats,
            )
        )


class ExecutionWorker(threading.Thread):
    def __init__(self, runtime: Any, run_state: RunState, settings: Any, mode: str) -> None:
        super().__init__(daemon=True)
        self.runtime = runtime
        self.run_state = run_state
        self.settings = settings
        self.mode = mode
        self.cancel_token = CancelToken()
        self.reporter = Reporter(runtime=runtime, run_state=run_state)
        self.links_service = LinksService()
        self.pdf_service = PdfService()
        self.extract_service = ExtractService()

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def pause(self) -> None:
        self.cancel_token.pause()

    def resume(self) -> None:
        self.cancel_token.resume()

    def run(self) -> None:
        self.runtime.emit(events.run_started(self.run_state.run_id, self.mode, self.run_state.started_at))
        try:
            asyncio.run(self._run_mode())
        except (SpiderCancelled, ExtractionCancelled):
            self._mark_cancelled()
        except Exception as exc:
            self._mark_failed(str(exc))

    async def _run_mode(self) -> None:
        stage_sequence = {
            "links": ("links",),
            "pdf": ("pdf",),
            "extract": ("extract",),
            "pipeline": STAGE_ORDER,
        }[self.mode]

        for stage in stage_sequence:
            if self.cancel_token.cancel_requested():
                raise SpiderCancelled("cancelled")
            await self._run_stage(stage)

        self.run_state.status = "completed"
        self.run_state.finished_at = now_iso()
        self.runtime.emit(
            events.run_completed(
                self.run_state.run_id,
                self.run_state.finished_at,
                self.run_state.summary,
            )
        )
        self.runtime.persist_run_history(self.run_state.run_id)
        self.runtime.on_run_finished(self.run_state.run_id)

    async def _run_stage(self, stage: str) -> None:
        service = {
            "links": self.links_service,
            "pdf": self.pdf_service,
            "extract": self.extract_service,
        }[stage]
        stage_state = self.run_state.stages[stage]
        stage_state.title = STAGE_TITLES[stage]
        stage_state.status = "running"
        stage_state.hint = "执行中"
        self.run_state.current_stage = stage
        self.runtime.emit(events.stage_started(self.run_state.run_id, stage, STAGE_TITLES[stage]))

        result = await service.run(self.settings, self.reporter, self.cancel_token)
        stage_state.status = "completed"
        if stage_state.progress.total > 0:
            stage_state.progress = Progress(
                current=stage_state.progress.total,
                total=stage_state.progress.total,
                percent=1.0,
            )
        else:
            stage_state.progress = Progress(current=1, total=1, percent=1.0)
        stage_state.result = result
        stage_state.hint = "已完成"
        self.run_state.summary[stage] = result
        self.runtime.emit(events.stage_completed(self.run_state.run_id, stage, result))
        if stage == "links":
            self.runtime.visualization_index_service.update_links_from_result(self.settings, result)
        elif stage == "pdf":
            self.runtime.visualization_index_service.update_pdf_from_result(self.settings, result)
        elif stage == "extract":
            self.runtime.visualization_index_service.update_extract_from_result(self.settings, result)
        self.runtime.persist_run_history(self.run_state.run_id)

    def _mark_cancelled(self) -> None:
        self.run_state.status = "cancelled"
        self.run_state.finished_at = now_iso()
        current = self.run_state.current_stage
        if current and self.run_state.stages[current].status == "running":
            self.run_state.stages[current].status = "cancelled"
            self.run_state.stages[current].hint = "已终止"
        self.runtime.emit(events.run_cancelled(self.run_state.run_id, self.run_state.finished_at))
        self.runtime.persist_run_history(self.run_state.run_id)
        self.runtime.on_run_finished(self.run_state.run_id)

    def _mark_failed(self, error: str) -> None:
        self.run_state.status = "failed"
        self.run_state.error = error
        self.run_state.finished_at = now_iso()
        current = self.run_state.current_stage
        if current and self.run_state.stages[current].status == "running":
            self.run_state.stages[current].status = "failed"
            self.run_state.stages[current].hint = "执行失败"
        self.reporter.log("ERROR", current or "system", error)
        self.runtime.emit(events.run_failed(self.run_state.run_id, self.run_state.finished_at, error))
        self.runtime.persist_run_history(self.run_state.run_id)
        self.runtime.on_run_finished(self.run_state.run_id)
