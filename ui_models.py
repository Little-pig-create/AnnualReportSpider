from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldSpec:
    key: str
    label: str
    value_type: str = "str"
    default: Any = ""
    optional: bool = False
    browse: str | None = None
    choices: tuple[str, ...] = ()


@dataclass
class FieldGroup:
    title: str
    fields: list[FieldSpec] = field(default_factory=list)


@dataclass
class CommandSpec:
    title: str
    args: list[str] | None = None
    action: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceTaskResult:
    status: str
    detail: str
    stats: dict[str, Any] = field(default_factory=dict)
