from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_MARKET_SCOPES = {"a_share", "b_share", "bjse"}


@dataclass(slots=True)
class WorkspaceSettings:
    projectRoot: str = str(PROJECT_ROOT)
    annualReportDir: str = "annual_reports"
    textOutputDir: str = "txt_extract"
    stateDir: str = "."
    startYear: int = 2014
    endYear: int = 2024


@dataclass(slots=True)
class LinksSettings:
    seDate: str = ""
    pageSize: int = 30
    requestInterval: float = 0.2
    announcementConcurrency: int = 2
    marketScopes: list[str] = field(default_factory=lambda: ["a_share"])
    resetCheckpoint: bool = False
    deleteCheckpointOnSuccess: bool = False


@dataclass(slots=True)
class PdfSettings:
    downloadConcurrency: int = 2


@dataclass(slots=True)
class ExtractSettings:
    concurrency: int = 2
    resetCheckpoint: bool = False
    deleteCheckpointOnSuccess: bool = False


@dataclass(slots=True)
class AppSettings:
    workspace: WorkspaceSettings
    links: LinksSettings
    pdf: PdfSettings
    extract: ExtractSettings

    @classmethod
    def default(cls) -> "AppSettings":
        return cls(
            workspace=WorkspaceSettings(),
            links=LinksSettings(),
            pdf=PdfSettings(),
            extract=ExtractSettings(),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppSettings":
        defaults = cls.default()
        return cls(
            workspace=WorkspaceSettings(**{**asdict(defaults.workspace), **payload.get("workspace", {})}),
            links=LinksSettings(**{**asdict(defaults.links), **payload.get("links", {})}),
            pdf=PdfSettings(**{**asdict(defaults.pdf), **payload.get("pdf", {})}),
            extract=ExtractSettings(**{**asdict(defaults.extract), **payload.get("extract", {})}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if self.workspace.startYear > self.workspace.endYear:
            raise ValueError("workspace.startYear cannot be greater than workspace.endYear")
        if self.links.pageSize < 1:
            raise ValueError("links.pageSize must be >= 1")
        if self.links.requestInterval < 0:
            raise ValueError("links.requestInterval must be >= 0")
        if self.links.announcementConcurrency < 1:
            raise ValueError("links.announcementConcurrency must be >= 1")
        if not self.links.marketScopes:
            raise ValueError("links.marketScopes must not be empty")
        invalid_market_scopes = [item for item in self.links.marketScopes if item not in ALLOWED_MARKET_SCOPES]
        if invalid_market_scopes:
            raise ValueError(f"links.marketScopes contains invalid values: {invalid_market_scopes}")
        if self.pdf.downloadConcurrency < 1:
            raise ValueError("pdf.downloadConcurrency must be >= 1")
        if self.extract.concurrency < 1:
            raise ValueError("extract.concurrency must be >= 1")
