from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, path: Path, max_items: int = 200) -> None:
        self.path = path
        self.max_items = max_items

    def list(self) -> list[dict[str, Any]]:
        items = self._read_items()
        return sorted(items, key=lambda item: str(item.get("startedAt") or ""), reverse=True)

    def upsert(self, item: dict[str, Any]) -> None:
        run_id = str(item.get("runId") or "").strip()
        if not run_id:
            return

        items = [row for row in self._read_items() if str(row.get("runId") or "") != run_id]
        items.append(item)
        items = sorted(items, key=lambda row: str(row.get("startedAt") or ""), reverse=True)[: self.max_items]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_items(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]
