from __future__ import annotations

from typing import Any


class Bridge:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def get_settings(self) -> dict[str, Any]:
        return self._runtime.get_settings()

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.update_settings(payload)

    def get_runtime(self) -> dict[str, Any]:
        return self._runtime.get_runtime()

    def get_pending_events(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._runtime.get_pending_events(payload or {})

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.create_run(payload)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._runtime.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        return self._runtime.cancel_run(run_id)

    def pause_run(self, run_id: str) -> dict[str, Any]:
        return self._runtime.pause_run(run_id)

    def resume_run(self, run_id: str) -> dict[str, Any]:
        return self._runtime.resume_run(run_id)

    def get_run_stages(self, run_id: str) -> dict[str, Any]:
        return self._runtime.get_run_stages(run_id)

    def get_run_logs(self, run_id: str) -> dict[str, Any]:
        return self._runtime.get_run_logs(run_id)

    def open_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.open_path(payload)

    def select_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.select_directory(payload)

    def get_about(self) -> dict[str, Any]:
        return self._runtime.get_about()

    def check_update(self) -> dict[str, Any]:
        return self._runtime.check_update()

    def get_incremental_status(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._runtime.get_incremental_status(payload or {})

    def get_visualization_index(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._runtime.get_visualization_index(payload or {})

    def get_run_history(self) -> dict[str, Any]:
        return self._runtime.get_run_history()

    def export_run_history(self) -> dict[str, Any]:
        return self._runtime.export_run_history()

    def confirm_close_window(self) -> dict[str, Any]:
        return self._runtime.confirm_close_window()

    def cancel_close_window_request(self) -> dict[str, Any]:
        return self._runtime.cancel_close_window_request()
