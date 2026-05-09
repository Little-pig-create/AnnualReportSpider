from __future__ import annotations

from time import time
from typing import Any


def _base(event: str, run_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": event,
        "runId": run_id,
        "timestamp": int(time()),
        "data": data,
    }


def run_started(run_id: str, mode: str, started_at: str) -> dict[str, Any]:
    return _base("run.started", run_id, {
        "mode": mode,
        "status": "running",
        "startedAt": started_at,
    })


def run_paused(run_id: str) -> dict[str, Any]:
    return _base("run.paused", run_id, {
        "status": "paused",
    })


def run_resumed(run_id: str) -> dict[str, Any]:
    return _base("run.resumed", run_id, {
        "status": "running",
    })


def run_completed(run_id: str, finished_at: str, summary: dict[str, Any]) -> dict[str, Any]:
    return _base("run.completed", run_id, {
        "status": "completed",
        "finishedAt": finished_at,
        "summary": summary,
    })


def run_failed(run_id: str, finished_at: str, error: str) -> dict[str, Any]:
    return _base("run.failed", run_id, {
        "status": "failed",
        "finishedAt": finished_at,
        "error": error,
    })


def run_cancelled(run_id: str, finished_at: str) -> dict[str, Any]:
    return _base("run.cancelled", run_id, {
        "status": "cancelled",
        "finishedAt": finished_at,
    })


def stage_started(run_id: str, stage: str, title: str) -> dict[str, Any]:
    return _base("stage.started", run_id, {
        "stage": stage,
        "title": title,
        "status": "running",
    })


def stage_progress(
    run_id: str,
    stage: str,
    current: int,
    total: int,
    percent: float,
    message: str = "",
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _base("stage.progress", run_id, {
        "stage": stage,
        "current": current,
        "total": total,
        "percent": percent,
        "message": message,
        "stats": stats or {},
    })


def stage_completed(run_id: str, stage: str, result: dict[str, Any]) -> dict[str, Any]:
    return _base("stage.completed", run_id, {
        "stage": stage,
        "status": "completed",
        "result": result,
    })


def log_append(run_id: str, level: str, stage: str, message: str, time_text: str) -> dict[str, Any]:
    return _base("log.append", run_id, {
        "time": time_text,
        "level": level,
        "stage": stage,
        "message": message,
    })


def app_close_requested(run_id: str | None, status: str | None = None) -> dict[str, Any]:
    return {
        "event": "app.close_requested",
        "runId": run_id,
        "timestamp": int(time()),
        "data": {
            "runId": run_id,
            "status": status,
        },
    }
