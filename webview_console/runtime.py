from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import events
from .about import build_about_payload
from .error_codes import (
    INCREMENTAL_STATUS_FAILED,
    INTERNAL_ERROR,
    INVALID_MODE,
    INVALID_PAYLOAD,
    RUN_ALREADY_ACTIVE,
    RUN_NOT_CANCELLABLE,
    RUN_NOT_FOUND,
    RUN_NOT_PAUSABLE,
    RUN_NOT_RESUMABLE,
    SETTINGS_VALIDATION_FAILED,
    VISUALIZATION_INDEX_FAILED,
)
from .infra.file_ops import open_path as open_fs_path
from .infra.history_store import HistoryStore
from .infra.visualization_index import VisualizationIndexService
from .models import Progress, RunState, STAGE_ORDER
from .paths import history_path
from .settings import AppSettings
from .services import IncrementalStatusService
from .services import UpdateService
from .worker import ExecutionWorker


class Runtime:
    def __init__(self, config_store, event_pusher) -> None:
        self.config_store = config_store
        self.event_pusher = event_pusher
        self._window = None
        self.settings = config_store.load()
        self._lock = threading.Lock()
        self._runs: dict[str, RunState] = {}
        self._active_run_id: str | None = None
        self._worker: ExecutionWorker | None = None
        self.history_store = HistoryStore(history_path())
        self.incremental_status_service = IncrementalStatusService()
        self.update_service = UpdateService()
        self.visualization_index_service = VisualizationIndexService()
        self._allow_window_close = False
        self._close_request_pending = False

    def has_active_run(self) -> bool:
        with self._lock:
            if self._active_run_id is None:
                return False
            run_state = self._runs.get(self._active_run_id)
            if run_state is None:
                return False
            return run_state.status in {"running", "paused", "cancelling"}

    def attach_window(self, window: Any) -> None:
        self._window = window
        self.event_pusher.attach_window(window)

    def _ok(self, data: Any) -> dict[str, Any]:
        return {"ok": True, "data": data}

    def _error(self, code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message}}

    def get_settings(self) -> dict[str, Any]:
        return self._ok(self.settings.to_dict())

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            settings = AppSettings.from_dict(payload)
            settings.validate()
        except Exception as exc:
            return self._error(SETTINGS_VALIDATION_FAILED, str(exc))
        with self._lock:
            if self._active_run_id is not None:
                return self._error(RUN_ALREADY_ACTIVE, "Stop the current run before changing settings.")
            self.settings = settings
            self.config_store.save(settings)
        return self._ok({"message": "settings updated"})

    def get_runtime(self) -> dict[str, Any]:
        with self._lock:
            active = self._active_run_id
            status = self._runs[active].status if active else "idle"
        return self._ok({
            "activeRunId": active,
            "status": status,
            "windowReady": True,
        })

    def get_pending_events(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raw_limit = (payload or {}).get("limit", 200)
        try:
            limit = max(1, min(int(raw_limit), 1000))
        except Exception:
            limit = 200
        return self._ok({"items": self.event_pusher.drain(limit)})

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = payload.get("mode")
        if mode not in {"links", "pdf", "extract", "pipeline"}:
            return self._error(INVALID_MODE, "mode must be one of links, pdf, extract, pipeline")

        with self._lock:
            if self._active_run_id is not None:
                return self._error(RUN_ALREADY_ACTIVE, "A run is already active.")
            run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            run_state = RunState.create(
                run_id,
                mode,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                settings_snapshot=self.settings.to_dict(),
                outputs=self._resolve_output_paths(self.settings),
            )
            self._seed_run_stages_from_visualization(run_state)
            self._prepare_stages_for_mode(run_state, mode)
            worker = ExecutionWorker(self, run_state, self.settings, mode)
            self._runs[run_id] = run_state
            self._active_run_id = run_id
            self._worker = worker
            self.persist_run_history(run_id)
            worker.start()
        return self._ok(run_state.to_dict())

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_state = self._runs.get(run_id)
        if run_state is None:
            return self._error(RUN_NOT_FOUND, "Run not found.")
        return self._ok(run_state.to_dict())

    def pause_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            if self._active_run_id != run_id or self._worker is None:
                return self._error(RUN_NOT_PAUSABLE, "Run is not active.")
            if self._runs[run_id].status != "running":
                return self._error(RUN_NOT_PAUSABLE, "Run is not in running state.")
            self._runs[run_id].status = "paused"
            current_stage = self._runs[run_id].current_stage
            if current_stage and current_stage in self._runs[run_id].stages:
                self._runs[run_id].stages[current_stage].hint = "暂停中"
            self._worker.pause()
        self.emit(events.run_paused(run_id))
        self._persist_run_history_async(run_id)
        return self._ok({"runId": run_id, "status": "paused"})

    def resume_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            if self._active_run_id != run_id or self._worker is None:
                return self._error(RUN_NOT_RESUMABLE, "Run is not active.")
            if self._runs[run_id].status != "paused":
                return self._error(RUN_NOT_RESUMABLE, "Run is not paused.")
            self._runs[run_id].status = "running"
            current_stage = self._runs[run_id].current_stage
            if current_stage and current_stage in self._runs[run_id].stages:
                self._runs[run_id].stages[current_stage].hint = "执行中"
            self._worker.resume()
        self.emit(events.run_resumed(run_id))
        self._persist_run_history_async(run_id)
        return self._ok({"runId": run_id, "status": "running"})

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            if self._active_run_id != run_id or self._worker is None:
                return self._error(RUN_NOT_CANCELLABLE, "Run is not active.")
            self._runs[run_id].status = "cancelling"
            current_stage = self._runs[run_id].current_stage
            if current_stage and current_stage in self._runs[run_id].stages:
                self._runs[run_id].stages[current_stage].hint = "终止中"
            self._worker.cancel()
        self._persist_run_history_async(run_id)
        return self._ok({"runId": run_id, "status": "cancelling"})

    def get_run_stages(self, run_id: str) -> dict[str, Any]:
        run_state = self._runs.get(run_id)
        if run_state is None:
            return self._error(RUN_NOT_FOUND, "Run not found.")
        return self._ok(run_state.stages_payload())

    def get_run_logs(self, run_id: str) -> dict[str, Any]:
        run_state = self._runs.get(run_id)
        if run_state is None:
            return self._error(RUN_NOT_FOUND, "Run not found.")
        return self._ok(run_state.logs_payload())

    def open_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = str(payload.get("path", "")).strip()
        if not raw:
            return self._error(INVALID_PAYLOAD, "path is required")
        path = Path(raw)
        try:
            open_fs_path(path)
        except Exception as exc:
            return self._error(INTERNAL_ERROR, str(exc))
        return self._ok({"path": str(path)})

    def select_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._window is None:
            return self._error(INTERNAL_ERROR, "window is not ready")
        initial_dir = str(payload.get("path", "")).strip()
        try:
            import webview

            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                directory=initial_dir,
            )
        except Exception as exc:
            return self._error(INTERNAL_ERROR, str(exc))

        if not result:
            return self._ok({"path": ""})
        return self._ok({"path": str(result[0])})

    def get_about(self) -> dict[str, Any]:
        return self._ok(build_about_payload())

    def check_update(self) -> dict[str, Any]:
        try:
            return self._ok(self.update_service.check())
        except Exception as exc:
            return self._error(INTERNAL_ERROR, str(exc))

    def get_incremental_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            settings = self.settings if not payload else AppSettings.from_dict(payload)
            settings.validate()
            return self._ok(self.incremental_status_service.scan(settings, lightweight=self.has_active_run()))
        except Exception as exc:
            return self._error(INCREMENTAL_STATUS_FAILED, str(exc))

    def get_visualization_index(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            settings = self.settings if not payload else AppSettings.from_dict(payload)
            settings.validate()
            return self._ok(self.visualization_index_service.build_snapshot(settings))
        except Exception as exc:
            return self._error(VISUALIZATION_INDEX_FAILED, str(exc))

    def get_run_history(self) -> dict[str, Any]:
        return self._ok({"items": self.history_store.list()})

    def export_run_history(self) -> dict[str, Any]:
        export_path = history_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)
        items = self.history_store.list()
        export_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._ok({"path": str(export_path), "count": len(items)})

    def request_window_close(self) -> bool:
        with self._lock:
            active = self._active_run_id
            status = self._runs[active].status if active and active in self._runs else "idle"
            if self._allow_window_close:
                return True
            if status not in {"running", "paused", "cancelling"}:
                return True
            if self._close_request_pending:
                return False
            self._close_request_pending = True

        def _emit_close_request() -> None:
            self.emit(events.app_close_requested(active, status))

        threading.Thread(target=_emit_close_request, daemon=True).start()
        return False

    def confirm_close_window(self) -> dict[str, Any]:
        self._finalize_active_run_for_window_close()
        with self._lock:
            self._allow_window_close = True
            self._close_request_pending = False
            window = self._window

        def _destroy_window_async() -> None:
            try:
                if window is not None:
                    window.destroy()
            except Exception:
                with self._lock:
                    self._allow_window_close = False
                    self._close_request_pending = False

        threading.Thread(target=_destroy_window_async, daemon=True).start()
        return self._ok({"closing": True})

    def cancel_close_window_request(self) -> dict[str, Any]:
        with self._lock:
            self._close_request_pending = False
        return self._ok({"cancelled": True})

    def _finalize_active_run_for_window_close(self) -> None:
        with self._lock:
            active = self._active_run_id
            if not active:
                return
            run_state = self._runs.get(active)
            worker = self._worker
            if run_state is None:
                return
            if run_state.status not in {"running", "paused", "cancelling"}:
                return

            run_state.status = "cancelled"
            run_state.error = "窗口关闭导致任务中断"
            run_state.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            current_stage = run_state.current_stage
            if current_stage and current_stage in run_state.stages:
                stage_state = run_state.stages[current_stage]
                if stage_state.status == "running":
                    stage_state.status = "cancelled"
                stage_state.hint = "窗口关闭，任务中断"
            self._active_run_id = None
            self._worker = None

        try:
            if worker is not None:
                worker.cancel()
        except Exception:
            pass

        self.persist_run_history(active)

    def emit(self, event: dict[str, Any]) -> None:
        self.event_pusher.push(event)

    def persist_run_history(self, run_id: str) -> None:
        run_state = self._runs.get(run_id)
        if run_state is None:
            return
        self.history_store.upsert(self._build_history_entry(run_state))

    def _persist_run_history_async(self, run_id: str) -> None:
        threading.Thread(
            target=self.persist_run_history,
            args=(run_id,),
            daemon=True,
        ).start()

    def on_run_finished(self, run_id: str) -> None:
        with self._lock:
            self.persist_run_history(run_id)
            if self._active_run_id == run_id:
                self._active_run_id = None
                self._worker = None

    def _resolve_output_paths(self, settings: AppSettings) -> dict[str, str]:
        workspace = settings.workspace
        project_root = Path(workspace.projectRoot).resolve()
        annual_report_dir = Path(workspace.annualReportDir)
        text_output_dir = Path(workspace.textOutputDir)
        state_dir = Path(workspace.stateDir)

        return {
            "projectRoot": str(project_root),
            "annualReportDir": str((project_root / annual_report_dir).resolve() if not annual_report_dir.is_absolute() else annual_report_dir.resolve()),
            "textOutputDir": str((project_root / text_output_dir).resolve() if not text_output_dir.is_absolute() else text_output_dir.resolve()),
            "stateDir": str((project_root / state_dir).resolve() if not state_dir.is_absolute() else state_dir.resolve()),
        }

    def _build_history_entry(self, run_state: RunState) -> dict[str, Any]:
        outputs = dict(run_state.outputs or {})
        primary_output_dir = outputs.get(
            "textOutputDir" if run_state.mode in {"extract", "pipeline"} else "annualReportDir",
            "",
        )
        return {
            "runId": run_state.run_id,
            "mode": run_state.mode,
            "status": run_state.status,
            "startedAt": run_state.started_at,
            "finishedAt": run_state.finished_at,
            "error": run_state.error,
            "outputDir": primary_output_dir,
            "outputDirectories": outputs,
            "settingsSnapshot": run_state.settings_snapshot,
            "summary": run_state.summary,
            "stages": [run_state.stages[name].to_dict() for name in run_state.stages],
        }

    def _reset_stage_state(self, run_state: RunState, stage_name: str) -> None:
        stage_state = run_state.stages[stage_name]
        stage_state.status = "pending"
        stage_state.progress = Progress()
        stage_state.result = None
        stage_state.hint = ""
        run_state.summary[stage_name] = None

    def _prepare_stages_for_mode(self, run_state: RunState, mode: str) -> None:
        reset_map = {
            "links": ("links", "pdf", "extract"),
            "pdf": ("pdf", "extract"),
            "extract": ("extract",),
            "pipeline": STAGE_ORDER,
        }
        for stage_name in reset_map[mode]:
            self._reset_stage_state(run_state, stage_name)

    def _seed_run_stages_from_visualization(self, run_state: RunState) -> None:
        history_stages = self._load_latest_stage_map(run_state)
        if history_stages:
            self._seed_run_stages_from_history(run_state, history_stages)

        try:
            snapshot = self.visualization_index_service.build_snapshot(self.settings)
        except Exception:
            return

        links = snapshot.get("links") or {}
        links_buckets = links.get("yearBuckets") if isinstance(links.get("yearBuckets"), list) else []
        links_year_total = int(links.get("yearTotal", len(links_buckets)) or len(links_buckets) or 0)
        links_completed = sum(
            1 for item in links_buckets
            if str((item or {}).get("status", "")).lower() == "completed"
        )
        if links_year_total > 0 and run_state.stages["links"].status == "pending":
            links_stage = run_state.stages["links"]
            links_percent = min(links_completed / links_year_total, 1.0)
            links_stage.progress = Progress(
                current=min(links_completed, links_year_total),
                total=links_year_total,
                percent=links_percent,
            )
            links_stage.result = {
                "rows": int(links.get("totalAnnouncements", 0) or 0),
                "yearBuckets": links_buckets,
                "live": links,
            }
            if links_completed >= links_year_total:
                links_stage.status = "completed"
                links_stage.hint = "已完成"
                run_state.summary["links"] = links_stage.result
            elif links_completed > 0:
                links_stage.hint = "检测到历史结果"

        pdf = snapshot.get("pdf") or {}
        pdf_buckets = pdf.get("yearBuckets") if isinstance(pdf.get("yearBuckets"), list) else []
        pdf_total = int(pdf.get("total", 0) or 0)
        pdf_completed = int(pdf.get("completed", 0) or 0)
        if pdf_total > 0 and run_state.stages["pdf"].status == "pending":
            pdf_stage = run_state.stages["pdf"]
            pdf_percent = min(pdf_completed / pdf_total, 1.0)
            pdf_stage.progress = Progress(
                current=min(pdf_completed, pdf_total),
                total=pdf_total,
                percent=pdf_percent,
            )
            pdf_stage.result = {
                "pdfTotal": pdf_total,
                "downloaded": 0,
                "exists": pdf_completed,
                "failed": 0,
                "skipped": 0,
                "yearBuckets": pdf_buckets,
                "speedPerMinute": 0,
                "etaSeconds": 0,
            }
            if pdf_completed >= pdf_total:
                pdf_stage.status = "completed"
                pdf_stage.hint = "已完成"
                run_state.summary["pdf"] = pdf_stage.result
            elif pdf_completed > 0:
                pdf_stage.hint = "检测到历史结果"

        extract = snapshot.get("extract") or {}
        extract_buckets = extract.get("yearBuckets") if isinstance(extract.get("yearBuckets"), list) else []
        extract_total = int(extract.get("total", 0) or 0)
        extract_completed = int(extract.get("completed", 0) or 0)
        if extract_total > 0 and run_state.stages["extract"].status == "pending":
            extract_stage = run_state.stages["extract"]
            extract_percent = min(extract_completed / extract_total, 1.0)
            extract_stage.progress = Progress(
                current=min(extract_completed, extract_total),
                total=extract_total,
                percent=extract_percent,
            )
            extract_stage.result = {
                "pdfTotal": extract_total,
                "extracted": extract_completed,
                "exists": 0,
                "failed": 0,
                "yearBuckets": extract_buckets,
                "speedPerMinute": 0,
                "etaSeconds": 0,
            }
            if extract_completed >= extract_total:
                extract_stage.status = "completed"
                extract_stage.hint = "已完成"
                run_state.summary["extract"] = extract_stage.result
            elif extract_completed > 0:
                extract_stage.hint = "检测到历史结果"

    def _load_latest_stage_map(self, run_state: RunState) -> dict[str, dict[str, Any]]:
        items = self.history_store.list()
        current_outputs = dict(run_state.outputs or {})
        current_project_root = str(current_outputs.get("projectRoot") or "")
        current_annual_dir = str(current_outputs.get("annualReportDir") or "")
        current_text_dir = str(current_outputs.get("textOutputDir") or "")
        for item in items:
            output_dirs = item.get("outputDirectories") or {}
            if not isinstance(output_dirs, dict):
                continue
            project_root = str(output_dirs.get("projectRoot") or "")
            annual_dir = str(output_dirs.get("annualReportDir") or "")
            text_dir = str(output_dirs.get("textOutputDir") or "")
            if (
                project_root != current_project_root
                or annual_dir != current_annual_dir
                or text_dir != current_text_dir
            ):
                continue
            stages = item.get("stages")
            if not isinstance(stages, list):
                continue
            mapped: dict[str, dict[str, Any]] = {}
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                name = str(stage.get("name") or "").strip()
                if name in STAGE_ORDER:
                    mapped[name] = stage
            if mapped:
                return mapped
        return {}

    def _seed_run_stages_from_history(self, run_state: RunState, history_stages: dict[str, dict[str, Any]]) -> None:
        for stage_name in STAGE_ORDER:
            payload = history_stages.get(stage_name)
            if not payload:
                continue

            status = str(payload.get("status") or "pending")
            progress_payload = payload.get("progress") or {}
            progress = Progress(
                current=int(progress_payload.get("current", 0) or 0),
                total=int(progress_payload.get("total", 0) or 0),
                percent=float(progress_payload.get("percent", 0) or 0),
            )
            result = payload.get("result") if isinstance(payload.get("result"), dict) else None
            hint = str(payload.get("hint") or "")

            stage_state = run_state.stages[stage_name]
            stage_state.status = status
            stage_state.progress = progress
            stage_state.result = result
            stage_state.hint = hint
            run_state.summary[stage_name] = result
