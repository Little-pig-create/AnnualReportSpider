from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


STAGE_ORDER = ("links", "pdf", "extract")
STAGE_TITLES = {
    "links": "公告链接抓取",
    "pdf": "PDF 下载",
    "extract": "文本提取",
}


@dataclass(slots=True)
class Progress:
    current: int = 0
    total: int = 0
    percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StageState:
    name: str
    title: str
    status: str = "pending"
    progress: Progress = field(default_factory=Progress)
    result: dict[str, Any] | None = None
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "status": self.status,
            "progress": self.progress.to_dict(),
            "result": self.result,
            "hint": self.hint,
        }


@dataclass(slots=True)
class LogItem:
    time: str
    level: str
    stage: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunState:
    run_id: str
    mode: str
    status: str
    current_stage: str | None
    started_at: str
    finished_at: str | None = None
    stages: dict[str, StageState] = field(default_factory=dict)
    logs: list[LogItem] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=lambda: {"links": None, "pdf": None, "extract": None})
    error: str | None = None
    settings_snapshot: dict[str, Any] | None = None
    outputs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        run_id: str,
        mode: str,
        started_at: str,
        *,
        settings_snapshot: dict[str, Any] | None = None,
        outputs: dict[str, str] | None = None,
    ) -> "RunState":
        stages = {
            name: StageState(name=name, title=STAGE_TITLES[name])
            for name in STAGE_ORDER
        }
        return cls(
            run_id=run_id,
            mode=mode,
            status="running",
            current_stage=None,
            started_at=started_at,
            stages=stages,
            settings_snapshot=settings_snapshot,
            outputs=outputs or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "mode": self.mode,
            "status": self.status,
            "currentStage": self.current_stage,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "summary": self.summary,
            "error": self.error,
            "outputs": self.outputs,
        }

    def stages_payload(self) -> dict[str, Any]:
        return {
            "items": [self.stages[name].to_dict() for name in STAGE_ORDER]
        }

    def logs_payload(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.logs]
        }
