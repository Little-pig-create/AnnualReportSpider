from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .file_ops import resolve_project_path


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


FILTERED_FILENAME = "filtered_announcements.jsonl"


class VisualizationIndexService:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _index_dir(self, state_dir: Path) -> Path:
        return state_dir / "visualization"

    def _pdf_path(self, state_dir: Path) -> Path:
        return self._index_dir(state_dir) / "pdf_years.json"

    def _txt_path(self, state_dir: Path) -> Path:
        return self._index_dir(state_dir) / "txt_years.json"

    def _links_path(self, state_dir: Path) -> Path:
        return self._index_dir(state_dir) / "links_years.json"

    def _meta_path(self, state_dir: Path) -> Path:
        return self._index_dir(state_dir) / "meta.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _count_jsonl_rows(self, path: Path) -> int:
        if not path.exists():
            return 0
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
        return count

    def _count_links_by_year(self, annual_report_dir: Path, years: list[int]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        year_total = len(years)
        completed_years = 0
        total_announcements = 0

        for index, year in enumerate(years, start=1):
            filtered_path = annual_report_dir / str(year) / FILTERED_FILENAME
            count = self._count_jsonl_rows(filtered_path)
            if filtered_path.exists():
                completed_years += 1
            total_announcements += count
            result[str(year)] = {
                "year": year,
                "count": count,
                "status": "completed" if filtered_path.exists() else "pending",
                "active": False,
                "updatedAt": _now_text(),
            }

        overall_percent = (completed_years / year_total) if year_total > 0 else 0.0
        return {
            "_snapshot": {
                "yearTotal": year_total,
                "currentYearIndex": completed_years if completed_years > 0 else 0,
                "currentYear": years[-1] if completed_years == year_total and year_total > 0 else None,
                "rangeCurrent": 0,
                "rangeTotal": 0,
                "recordsFound": 0,
                "rawRecordsFound": 0,
                "currentWindow": "",
                "overallPercent": overall_percent,
                "totalAnnouncements": total_announcements,
                "countBasis": f"counts come from {FILTERED_FILENAME}",
                "yearBuckets": [result[str(year)] for year in years],
            },
            "_years": result,
        }

    def _count_top_level_pdf_by_year(self, annual_report_dir: Path, years: list[int]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for year in years:
            year_dir = annual_report_dir / str(year)
            total = 0
            if year_dir.exists():
                total = sum(1 for item in year_dir.glob("*.pdf") if item.is_file())
            result[str(year)] = {
                "year": year,
                "total": total,
                "downloaded": 0,
                "exists": total,
                "failed": 0,
                "skipped": 0,
                "completed": total,
                "percent": 1.0 if total > 0 else 0.0,
                "status": "completed" if total > 0 else "pending",
                "active": False,
                "updatedAt": _now_text(),
            }
        return result

    def _count_top_level_txt_by_year(self, text_output_dir: Path, years: list[int]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for year in years:
            year_dir = text_output_dir / str(year)
            total = 0
            if year_dir.exists():
                total = sum(1 for item in year_dir.glob("*.txt") if item.is_file())
            result[str(year)] = {
                "year": year,
                "total": total,
                "extracted": total,
                "exists": 0,
                "failed": 0,
                "completed": total,
                "percent": 1.0 if total > 0 else 0.0,
                "status": "completed" if total > 0 else "pending",
                "active": False,
                "updatedAt": _now_text(),
            }
        return result

    def build_snapshot(self, settings) -> dict[str, Any]:
        workspace = settings.workspace
        project_root = workspace.projectRoot
        annual_report_dir = resolve_project_path(project_root, workspace.annualReportDir)
        text_output_dir = resolve_project_path(project_root, workspace.textOutputDir)
        state_dir = resolve_project_path(project_root, workspace.stateDir)
        years = list(range(workspace.startYear, workspace.endYear + 1))

        with self._lock:
            links_years = self._read_json(self._links_path(state_dir), {})
            pdf_years = self._read_json(self._pdf_path(state_dir), {})
            txt_years = self._read_json(self._txt_path(state_dir), {})

            if not links_years:
                links_payload = self._count_links_by_year(annual_report_dir, years)
                links_years = links_payload["_years"]
                self._write_json(self._links_path(state_dir), links_years)
            if not pdf_years:
                pdf_years = self._count_top_level_pdf_by_year(annual_report_dir, years)
                self._write_json(self._pdf_path(state_dir), pdf_years)
            if not txt_years:
                txt_years = self._count_top_level_txt_by_year(text_output_dir, years)
                self._write_json(self._txt_path(state_dir), txt_years)

            meta = {
                "generatedAt": _now_text(),
                "projectRoot": str(Path(project_root).resolve()),
                "annualReportDir": str(annual_report_dir),
                "textOutputDir": str(text_output_dir),
                "stateDir": str(state_dir),
                "startYear": workspace.startYear,
                "endYear": workspace.endYear,
            }
            self._write_json(self._meta_path(state_dir), meta)

        links_items = [links_years.get(str(year), {"year": year, "count": 0, "status": "pending", "active": False}) for year in years]
        pdf_items = [pdf_years.get(str(year), {"year": year}) for year in years]
        txt_items = [txt_years.get(str(year), {"year": year}) for year in years]
        completed_link_years = sum(1 for item in links_items if item.get("status") == "completed")
        total_link_announcements = sum(int(item.get("count", 0) or 0) for item in links_items)
        return {
            "links": {
                "yearTotal": len(years),
                "currentYearIndex": completed_link_years if completed_link_years > 0 else 0,
                "currentYear": years[-1] if completed_link_years == len(years) and years else None,
                "rangeCurrent": 0,
                "rangeTotal": 0,
                "recordsFound": 0,
                "rawRecordsFound": 0,
                "currentWindow": "",
                "overallPercent": (completed_link_years / len(years)) if years else 0.0,
                "totalAnnouncements": total_link_announcements,
                "countBasis": f"counts come from {FILTERED_FILENAME}",
                "yearBuckets": links_items,
            },
            "pdf": {
                "yearBuckets": pdf_items,
                "total": sum(int(item.get("total", 0) or 0) for item in pdf_items),
                "completed": sum(int(item.get("completed", 0) or 0) for item in pdf_items),
            },
            "extract": {
                "yearBuckets": txt_items,
                "total": sum(int(item.get("total", 0) or 0) for item in txt_items),
                "completed": sum(int(item.get("completed", 0) or 0) for item in txt_items),
            },
            "meta": meta,
        }

    def update_links_from_result(self, settings, result: dict[str, Any]) -> None:
        workspace = settings.workspace
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)
        live = result.get("live") if isinstance(result.get("live"), dict) else None
        source_buckets = None
        if live and isinstance(live.get("yearBuckets"), list):
            source_buckets = live.get("yearBuckets")
        elif isinstance(result.get("yearBuckets"), list):
            source_buckets = result.get("yearBuckets")
        if not isinstance(source_buckets, list):
            return

        with self._lock:
            payload = {}
            for item in source_buckets:
                year = item.get("year")
                if year is None:
                    continue
                count = int(item.get("count", 0) or 0)
                payload[str(int(year))] = {
                    "year": int(year),
                    "count": count,
                    "status": item.get("status") or "completed",
                    "active": False,
                    "updatedAt": _now_text(),
                }
            self._write_json(self._links_path(state_dir), payload)

    def update_pdf_from_result(self, settings, result: dict[str, Any]) -> None:
        workspace = settings.workspace
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)
        year_buckets = result.get("yearBuckets")
        if not isinstance(year_buckets, list):
            return
        with self._lock:
            payload = {
                str(int(item.get("year"))): {
                    **item,
                    "updatedAt": _now_text(),
                }
                for item in year_buckets
                if item.get("year") is not None
            }
            self._write_json(self._pdf_path(state_dir), payload)

    def update_extract_from_result(self, settings, result: dict[str, Any]) -> None:
        workspace = settings.workspace
        state_dir = resolve_project_path(workspace.projectRoot, workspace.stateDir)
        year_buckets = result.get("yearBuckets")
        if not isinstance(year_buckets, list):
            return
        with self._lock:
            payload = {
                str(int(item.get("year"))): {
                    **item,
                    "updatedAt": _now_text(),
                }
                for item in year_buckets
                if item.get("year") is not None
            }
            self._write_json(self._txt_path(state_dir), payload)
