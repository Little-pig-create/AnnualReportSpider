from __future__ import annotations

import json
import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
import asyncio
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import customtkinter as ctk
import ttkbootstrap as ttk

from ui_models import CommandSpec, FieldGroup, FieldSpec, ServiceTaskResult

try:
    import pywinstyles
except ImportError:  # pragma: no cover - optional window polish
    pywinstyles = None

try:
    from tkinterdnd2 import COPY as DND_COPY, DND_FILES, TkinterDnD
except ImportError:  # pragma: no cover - optional drag and drop
    DND_COPY = None
    DND_FILES = None
    TkinterDnD = None

try:
    from tksheet import Sheet
except ImportError:  # pragma: no cover - optional result grid
    Sheet = None

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

from app_metadata import (
    APP_ICON_DIRNAME,
    APP_ICON_ICO_FILENAME,
    APP_ICON_PNG_FILENAME,
    APP_NAME,
    APP_TITLE,
    APP_VERSION,
    COMPANY_NAME,
    GITHUB_URL,
)
SOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR)).resolve()
ROOT_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_DIR).resolve()
CONFIG_DIR = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
    if getattr(sys, "frozen", False)
    else ROOT_DIR
)
CONFIG_PATH = CONFIG_DIR / "gui_config.json"
README_PATH = RESOURCE_DIR / "README.md"
GUI_README_PATH = RESOURCE_DIR / "GUI_README.md"
APP_ICON_ICO_PATH = RESOURCE_DIR / APP_ICON_DIRNAME / APP_ICON_ICO_FILENAME
APP_ICON_PNG_PATH = RESOURCE_DIR / APP_ICON_DIRNAME / APP_ICON_PNG_FILENAME
SPIDER_CHECKPOINT_NAME = "checkpoint.json"
SPIDER_SUMMARY_NAME = "summary.json"
EXTRACT_CHECKPOINT_NAME = "text_extract_checkpoint.json"
EXTRACT_SUMMARY_NAME = "text_extract_summary.json"
MAX_EVENTS_PER_POLL = 80
MAX_POLL_SECONDS = 0.03
UI_FONT = "Microsoft YaHei UI"
APP_BG = "#f5efe6"
SURFACE_BG = "#fffdfa"
SURFACE_SOFT = "#f8f2ea"
SURFACE_PANEL = "#fcf7f0"
SURFACE_ELEVATED = "#fff8ef"
SURFACE_TINT = "#f2e6d6"
BORDER_SOFT = "#e8dccf"
BORDER_COLOR = "#dbcbb8"
TEXT_PRIMARY = "#223042"
TEXT_MUTED = "#6f7a86"
ACCENT = "#1f3a5f"
ACCENT_ALT = "#2d537f"
ACCENT_SOFT = "#e7eef7"
ACCENT_LINE = "#88a8d3"
GOLD = "#b98a43"
GOLD_SOFT = "#f5e8cc"
DANGER = "#b94b56"
DANGER_SOFT = "#f8e7ea"
SUCCESS = "#2f7a52"
CONSOLE_BG = "#fffdfa"
CONSOLE_FG = "#111111"
CONSOLE_ACCENT = "#ff4d4f"
CONSOLE_MUTED = "#8a8f98"
WIN11_BUILD = 22000
STAGE_SEQUENCE = ("spider", "extract")
STAGE_LABELS = {
    "spider": "抓取状态",
    "extract": "提取状态",
}
STAGE_TYPE_ICONS = {
    "spider": "PDF",
    "extract": "TXT",
}
TAB_DESCRIPTIONS = {
    "spider": ("年报抓取", "面向公告和 PDF 年报抓取，适合单独补数据、续跑和整理原始产物。"),
    "extract": ("文本提取", "从已下载 PDF 中批量提取文本，适合独立重跑文本阶段。"),
    "pipeline": ("一键全流程", "把抓取与提取串成一次任务，完成后可直接查看整合汇总。"),
}
TAB_HINTS = {
    "spider": "支持并发抓取、checkpoint 管理和结果目录快速打开。",
    "extract": "支持断点续跑、结果覆盖控制和输出目录独立配置。",
    "pipeline": "适合日常批量执行，完成后会自动汇总抓取与提取结果。",
}
STAGE_VISUALS = {
    "未开始": {
        "bg": "#f4ede4",
        "border": "#d6c6b4",
        "title": "#6d6258",
        "text": "#6d6258",
        "badge_bg": "#e9dfd1",
        "badge_fg": "#6d6258",
        "accent": "#d6c6b4",
        "icon": "○",
    },
    "准备中": {
        "bg": "#fff2df",
        "border": "#d0a15a",
        "title": "#8c611b",
        "text": "#7b5a28",
        "badge_bg": "#f3dfba",
        "badge_fg": "#8c611b",
        "accent": "#e4b569",
        "icon": "◔",
    },
    "进行中": {
        "bg": "#e8eef8",
        "border": "#6789ba",
        "title": "#23496f",
        "text": "#355578",
        "badge_bg": "#d5e2f5",
        "badge_fg": "#23496f",
        "accent": "#6f97cf",
        "icon": "◕",
    },
    "已完成": {
        "bg": "#ebf7ef",
        "border": "#5ca27a",
        "title": "#1f6a42",
        "text": "#325f44",
        "badge_bg": "#5ca27a",
        "badge_fg": "#ffffff",
        "accent": "#7bcca0",
        "icon": "✓",
    },
    "已停止": {
        "bg": "#fbefde",
        "border": "#cf9854",
        "title": "#99611d",
        "text": "#785723",
        "badge_bg": "#f0d7ad",
        "badge_fg": "#99611d",
        "accent": "#e0af67",
        "icon": "■",
    },
    "失败": {
        "bg": "#f9e8eb",
        "border": "#d2717a",
        "title": "#9d3340",
        "text": "#812d37",
        "badge_bg": "#d2717a",
        "badge_fg": "#ffffff",
        "accent": "#e58f98",
        "icon": "✕",
    },
}

def resolve_path(value: str | None) -> Path:
    raw = (value or "").strip()
    if not raw:
        return ROOT_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def open_path(value: str | None) -> None:
    target = resolve_path(value)
    if target.is_file():
        open_target = target
    elif target.exists():
        open_target = target
    else:
        open_target = target.parent

    if sys.platform.startswith("win"):
        os.startfile(str(open_target))
        return

    webbrowser.open(open_target.as_uri())


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def get_github_url() -> str:
    return GITHUB_URL


def load_extract_text_module():
    import extract_text

    return extract_text


def load_spider_module():
    import spider

    return spider


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        if path.exists():
            path.unlink()


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            total_lines = sum(1 for _ in handle)
    except OSError:
        return 0
    return max(total_lines - 1, 0)


def make_delete_file_command(title: str, path: Path) -> CommandSpec:
    return CommandSpec(title=title, action="delete_file", payload={"path": str(path)})


def wrap_with_checkpoint_actions(
    commands: list[CommandSpec],
    *,
    checkpoint_path: Path,
    reset_checkpoint: bool,
    delete_checkpoint_on_success: bool,
) -> list[CommandSpec]:
    wrapped: list[CommandSpec] = []
    if reset_checkpoint:
        wrapped.append(make_delete_file_command("重置旧 checkpoint", checkpoint_path))
    wrapped.extend(commands)
    if delete_checkpoint_on_success:
        wrapped.append(make_delete_file_command("成功后删除 checkpoint", checkpoint_path))
    return wrapped


class TaskWorker(threading.Thread):
    def __init__(
        self,
        commands: list[CommandSpec],
        event_queue: queue.Queue[tuple[str, Any]],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self.commands = commands
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.current_process: subprocess.Popen[str] | None = None

    def run(self) -> None:
        try:
            total = len(self.commands)
            for index, command in enumerate(self.commands, start=1):
                if self.stop_event.is_set():
                    self.event_queue.put(("stopped", "任务已取消"))
                    return

                title = f"[{index}/{total}] {command.title}"
                self.event_queue.put(
                    (
                        "status",
                        {
                            "message": f"正在执行：{title}",
                            "step": index,
                            "total": total,
                            "title": command.title,
                            "action": command.action or "",
                        },
                    )
                )

                if command.action == "delete_file":
                    return_code = self._delete_file(Path(str(command.payload["path"])))
                elif command.action == "extract_service":
                    result = self._run_extract_service(command.payload)
                    return_code = 0 if result.status == "completed" else 1
                    if result.status == "cancelled":
                        self.event_queue.put(("stopped", result.detail))
                        return
                    if result.status == "completed":
                        self.event_queue.put(
                            (
                                "service_result",
                                {
                                    "action": command.action,
                                    "title": command.title,
                                    **result.stats,
                                },
                            )
                        )
                    else:
                        self.event_queue.put(("error", result.detail))
                        return
                elif command.action == "spider_service":
                    result = self._run_spider_service(command.payload)
                    return_code = 0 if result.status == "completed" else 1
                    if result.status == "cancelled":
                        self.event_queue.put(("stopped", result.detail))
                        return
                    if result.status == "completed":
                        self.event_queue.put(
                            (
                                "service_result",
                                {
                                    "action": command.action,
                                    "title": command.title,
                                    **result.stats,
                                },
                            )
                        )
                    else:
                        self.event_queue.put(("error", result.detail))
                        return
                else:
                    assert command.args is not None
                    self.event_queue.put(("log", f"$ {subprocess.list2cmdline(command.args)}"))
                    return_code = self._run_command(command.args)

                if self.stop_event.is_set():
                    self.event_queue.put(("stopped", "任务已取消"))
                    return

                if return_code != 0:
                    self.event_queue.put(("error", f"{title} 执行失败，退出码 {return_code}"))
                    return

                self.event_queue.put(("log", f"{title} 已完成"))
                self.event_queue.put(
                    (
                        "command_done",
                        {
                            "step": index,
                            "total": total,
                            "title": command.title,
                            "action": command.action or "",
                        },
                    )
                )

            self.event_queue.put(("done", "全部任务执行完成"))
        except Exception as exc:  # pragma: no cover - GUI runtime safety
            self.event_queue.put(("error", f"运行任务时出现异常：{exc}"))

    def _run_command(self, args: list[str]) -> int:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        self.current_process = subprocess.Popen(
            args,
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=1,
            creationflags=creationflags,
            env=env,
        )

        assert self.current_process.stdout is not None
        for raw_line in self.current_process.stdout:
            if self.stop_event.is_set():
                self._terminate_current_process()
                break
            self.event_queue.put(("log", self._decode_output(raw_line).rstrip()))

        return_code = self.current_process.wait()
        self.current_process = None
        return return_code

    def _terminate_current_process(self) -> None:
        if self.current_process is None:
            return

        process = self.current_process
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                check=False,
            )
            return

        process.terminate()

    def _delete_file(self, path: Path) -> int:
        try:
            if path.exists():
                safe_unlink(path)
                self.event_queue.put(("log", f"已删除文件：{path}"))
            else:
                self.event_queue.put(("log", f"文件不存在，跳过删除：{path}"))
            return 0
        except OSError as exc:
            self.event_queue.put(("log", f"删除文件失败：{path} | {exc}"))
            return 1

    def _run_extract_service(self, payload: dict[str, Any]) -> ServiceTaskResult:
        extract_text_module = load_extract_text_module()

        config = extract_text_module.ExtractTextConfig(
            input_dir=Path(str(payload["input_dir"])),
            output_dir=Path(str(payload["output_dir"])),
            state_dir=Path(str(payload["state_dir"])),
            start_year=payload.get("start_year"),
            end_year=payload.get("end_year"),
            concurrency=int(payload.get("concurrency", 2)),
        )

        def log_callback(level: str, message: str) -> None:
            self.event_queue.put(("log", f"[{level}] {message}"))

        def progress_callback(progress: dict[str, Any]) -> None:
            self.event_queue.put(("extract_progress", progress))

        try:
            result = asyncio.run(
                extract_text_module.run_extraction(
                    config,
                    log_callback=log_callback,
                    progress_callback=progress_callback,
                    cancel_requested=self.stop_event.is_set,
                )
            )
            return ServiceTaskResult(
                status="completed",
                detail="文本提取完成",
                stats={
                    "summary_path": str(result.summary_path),
                    "checkpoint_path": str(result.checkpoint_path),
                    "pdf_total": result.pdf_total,
                    "pending_total": result.pending_total,
                    **result.stats,
                },
            )
        except extract_text_module.ExtractionCancelled:
            return ServiceTaskResult(status="cancelled", detail="文本提取已取消")
        except Exception as exc:
            return ServiceTaskResult(status="error", detail=f"文本提取失败：{exc}")

    def _run_spider_service(self, payload: dict[str, Any]) -> ServiceTaskResult:
        spider_module = load_spider_module()

        config = spider_module.SpiderConfig(
            start_year=int(payload["start_year"]),
            end_year=int(payload["end_year"]),
            se_date=payload.get("se_date") or None,
            page_size=int(payload["page_size"]),
            request_interval=float(payload["request_interval"]),
            announcement_concurrency=int(payload["announcement_concurrency"]),
            download_concurrency=int(payload["download_concurrency"]),
            output_dir=str(payload["output_dir"]),
            state_dir=str(payload["state_dir"]),
            download_pdf=bool(payload.get("download_pdf")),
            metadata_only=bool(payload.get("metadata_only")),
            audit_pdf=bool(payload.get("audit_pdf")),
            cleanup_orphan_pdf=bool(payload.get("cleanup_orphan_pdf")),
        )

        def log_callback(level: str, message: str) -> None:
            self.event_queue.put(("log", f"[{level}] {message}"))

        def progress_callback(progress: dict[str, Any]) -> None:
            self.event_queue.put(("spider_progress", progress))

        try:
            result = asyncio.run(
                spider_module.run_spider_service(
                    config,
                    log_callback=log_callback,
                    progress_callback=progress_callback,
                    cancel_requested=self.stop_event.is_set,
                )
            )
            summary = result.summary or []
            total_raw = sum(int(item.get("raw_total", 0)) for item in summary if isinstance(item, dict))
            total_filtered = sum(int(item.get("filtered_total", 0)) for item in summary if isinstance(item, dict))
            total_failed = sum(int(item.get("failed", 0)) for item in summary if isinstance(item, dict))
            return ServiceTaskResult(
                status="completed",
                detail="年报抓取完成",
                stats={
                    "mode": result.mode,
                    "output_dir": str(result.output_dir),
                    "state_dir": str(result.state_dir),
                    "summary_path": str(result.summary_path) if result.summary_path else "",
                    "elapsed_seconds": result.elapsed_seconds,
                    "summary_count": len(summary),
                    "raw_total": total_raw,
                    "filtered_total": total_filtered,
                    "failed_total": total_failed,
                },
            )
        except spider_module.SpiderCancelled:
            return ServiceTaskResult(status="cancelled", detail="年报抓取已取消")
        except Exception as exc:
            return ServiceTaskResult(status="error", detail=f"年报抓取失败：{exc}")

    @staticmethod
    def _decode_output(raw_line: bytes) -> str:
        for encoding in ("utf-8", "gb18030"):
            try:
                return raw_line.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw_line.decode("utf-8", errors="replace")


class TaskTab(ttk.Frame):
    def __init__(
        self,
        master: ttk.Notebook,
        app: "DesktopApp",
        tab_key: str,
        title: str,
        groups: list[FieldGroup],
        command_builder: Callable[[dict[str, Any]], list[CommandSpec]],
        output_key: str,
    ) -> None:
        super().__init__(master, padding=16, style="Surface.TFrame")
        self.app = app
        self.tab_key = tab_key
        self.title = title
        self.groups = groups
        self.command_builder = command_builder
        self.output_key = output_key
        self.variables: dict[str, tk.Variable] = {}
        self.path_widgets: dict[str, ttk.Entry] = {}
        self.path_hints: dict[str, ttk.Label] = {}
        self.start_button: ttk.Button | None = None
        self.stop_button: ttk.Button | None = None
        self.form_frame: ttk.Frame | None = None
        self.canvas: tk.Canvas | None = None
        self.scroll_enabled = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, style="Surface.TFrame", padding=(4, 4, 4, 4))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, highlightthickness=0, bg=SURFACE_BG)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="Surface.TFrame", padding=(8, 6, 8, 8))

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.columnconfigure(0, weight=1)

        def sync_scrollregion(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            self._update_scroll_state(scrollbar)

        def sync_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)
            self._update_scroll_state(scrollbar)

        def on_mousewheel(event: tk.Event) -> str:
            if not self.scroll_enabled:
                return "break"
            if getattr(event, "delta", 0):
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            return "break"

        def on_arrow_scroll(event: tk.Event) -> str:
            if not self.scroll_enabled:
                return "break"
            key = getattr(event, "keysym", "")
            if key == "Down":
                canvas.yview_scroll(1, "units")
            elif key == "Up":
                canvas.yview_scroll(-1, "units")
            elif key == "Next":
                canvas.yview_scroll(1, "pages")
            elif key == "Prior":
                canvas.yview_scroll(-1, "pages")
            else:
                return ""
            return "break"

        content.bind("<Configure>", sync_scrollregion)
        canvas.bind("<Configure>", sync_content_width)
        canvas.bind("<MouseWheel>", on_mousewheel)
        content.bind("<MouseWheel>", on_mousewheel)

        self.form_frame = content
        self.canvas = canvas
        self._bind_scroll_events(content, on_mousewheel)
        self._bind_key_scroll_events(content, on_arrow_scroll)
        self._bind_key_scroll_events(canvas, on_arrow_scroll)
        self.after(120, lambda: self._update_scroll_state(scrollbar))

        intro_title, intro_body = TAB_DESCRIPTIONS.get(self.tab_key, (self.title, ""))
        intro_card = ttk.Frame(content, style="TabIntro.TFrame", padding=(16, 14, 16, 12))
        intro_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        intro_card.columnconfigure(0, weight=1)
        ttk.Label(intro_card, text=intro_title, style="TabIntroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            intro_card,
            text=intro_body,
            style="TabIntroBody.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(
            intro_card,
            text=TAB_HINTS.get(self.tab_key, ""),
            style="TabIntroHint.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        for group_index, group in enumerate(self.groups):
            frame = ttk.Labelframe(
                content,
                text=group.title,
                padding=18,
                style="SoftCard.TLabelframe",
                bootstyle="secondary",
            )
            frame.grid(row=group_index + 1, column=0, sticky="ew", pady=(0, 14))
            frame.columnconfigure(0, minsize=132)
            frame.columnconfigure(1, weight=1)

            current_row = 0
            for field in group.fields:
                if field.value_type == "bool":
                    variable = tk.BooleanVar(value=bool(field.default))
                    self.variables[field.key] = variable
                    checkbox = ttk.Checkbutton(frame, text=field.label, variable=variable, bootstyle="round-toggle")
                    checkbox.grid(
                        row=current_row,
                        column=0,
                        columnspan=3,
                        sticky="w",
                        pady=6,
                    )
                    self._bind_scroll_events(checkbox, on_mousewheel)
                    self._bind_key_scroll_events(checkbox, on_arrow_scroll)
                    current_row += 1
                    continue

                label = ttk.Label(frame, text=field.label, style="FieldLabel.TLabel")
                label.grid(
                    row=current_row,
                    column=0,
                    sticky="w",
                    padx=(0, 12),
                    pady=6,
                )
                self._bind_scroll_events(label, on_mousewheel)
                self._bind_key_scroll_events(label, on_arrow_scroll)

                if field.choices:
                    variable = tk.StringVar(value=str(field.default))
                    widget: ttk.Widget = ttk.Combobox(
                        frame,
                        textvariable=variable,
                        values=field.choices,
                        state="readonly",
                        font=(UI_FONT, 10),
                    )
                else:
                    variable = tk.StringVar(value="" if field.default is None else str(field.default))
                    widget = ttk.Entry(frame, textvariable=variable, font=(UI_FONT, 10))

                self.variables[field.key] = variable
                widget.grid(row=current_row, column=1, sticky="ew", pady=6)
                self._bind_scroll_events(widget, on_mousewheel)
                self._bind_key_scroll_events(widget, on_arrow_scroll)
                if isinstance(widget, ttk.Entry):
                    self.path_widgets[field.key] = widget

                if field.browse:
                    browse_button = ttk.Button(
                        frame,
                        text="浏览",
                        command=lambda key=field.key, mode=field.browse: self._browse_value(key, mode),
                        style="Subtle.TButton",
                        bootstyle="secondary",
                    )
                    browse_button.grid(row=current_row, column=2, sticky="w", padx=(10, 0), pady=6)
                    self._bind_scroll_events(browse_button, on_mousewheel)
                    self._bind_key_scroll_events(browse_button, on_arrow_scroll)
                    self._register_drop_target(field.key, field.browse)
                    hint = ttk.Label(frame, text=self._drop_hint_text(field.browse), style="DropHint.TLabel")
                    hint.grid(row=current_row + 1, column=1, columnspan=2, sticky="w", pady=(0, 6))
                    self.path_hints[field.key] = hint
                    self._bind_scroll_events(hint, on_mousewheel)
                    self._bind_key_scroll_events(hint, on_arrow_scroll)
                    current_row += 1

                current_row += 1

            self._bind_scroll_events(frame, on_mousewheel)
            self._bind_key_scroll_events(frame, on_arrow_scroll)

        actions_card = ttk.Labelframe(
            content,
            text="任务操作",
            padding=16,
            style="SoftCard.TLabelframe",
            bootstyle="info",
        )
        actions_card.grid(row=len(self.groups) + 1, column=0, sticky="ew", pady=(4, 0))
        actions = ttk.Frame(actions_card, style="Panel.TFrame", padding=(2, 4, 2, 2))
        actions.grid(row=0, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)

        primary_actions = ttk.Frame(actions, style="Panel.TFrame")
        primary_actions.grid(row=0, column=0, sticky="w")
        secondary_actions = ttk.Frame(actions, style="Panel.TFrame")
        secondary_actions.grid(row=0, column=1, sticky="e")

        self.start_button = ttk.Button(
            primary_actions,
            text="开始运行",
            command=self.start_task,
            style="Primary.TButton",
            bootstyle="primary",
        )
        self.start_button.grid(row=0, column=0, padx=(0, 10))

        self.stop_button = ttk.Button(
            primary_actions,
            text="停止任务",
            command=self.app.stop_running_task,
            state="disabled",
            style="Danger.TButton",
            bootstyle="danger",
        )
        self.stop_button.grid(row=0, column=1, padx=(0, 10))

        open_button = ttk.Button(
            secondary_actions,
            text="打开结果位置",
            command=self.open_output,
            style="Subtle.TButton",
            bootstyle="secondary",
        )
        open_button.grid(row=0, column=0, padx=(0, 10))
        save_button = ttk.Button(
            secondary_actions,
            text="保存当前配置",
            command=self.app.save_config,
            style="Subtle.TButton",
            bootstyle="secondary",
        )
        save_button.grid(row=0, column=1)

        ttk.Label(
            actions_card,
            text="开始后按钮会锁定，直到任务完成、失败或手动停止，避免重复启动。",
            style="PanelMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))

        self._bind_scroll_events(actions, on_mousewheel)
        self._bind_scroll_events(primary_actions, on_mousewheel)
        self._bind_scroll_events(secondary_actions, on_mousewheel)
        self._bind_scroll_events(self.start_button, on_mousewheel)
        self._bind_scroll_events(self.stop_button, on_mousewheel)
        self._bind_scroll_events(open_button, on_mousewheel)
        self._bind_scroll_events(save_button, on_mousewheel)
        self._bind_key_scroll_events(actions, on_arrow_scroll)
        self._bind_key_scroll_events(primary_actions, on_arrow_scroll)
        self._bind_key_scroll_events(secondary_actions, on_arrow_scroll)
        self._bind_key_scroll_events(self.start_button, on_arrow_scroll)
        self._bind_key_scroll_events(self.stop_button, on_arrow_scroll)
        self._bind_key_scroll_events(open_button, on_arrow_scroll)
        self._bind_key_scroll_events(save_button, on_arrow_scroll)

    def _bind_scroll_events(self, widget: tk.Widget, on_mousewheel: Callable[[tk.Event], str]) -> None:
        widget.bind("<MouseWheel>", on_mousewheel, add="+")
        widget.bind("<Button-4>", lambda _event: on_mousewheel(_event), add="+")
        widget.bind("<Button-5>", lambda _event: on_mousewheel(_event), add="+")

    def _bind_key_scroll_events(self, widget: tk.Widget, on_arrow_scroll: Callable[[tk.Event], str]) -> None:
        widget.bind("<Up>", on_arrow_scroll, add="+")
        widget.bind("<Down>", on_arrow_scroll, add="+")
        widget.bind("<Prior>", on_arrow_scroll, add="+")
        widget.bind("<Next>", on_arrow_scroll, add="+")

    def _update_scroll_state(self, scrollbar: ttk.Scrollbar) -> None:
        if self.canvas is None:
            return

        bbox = self.canvas.bbox("all")
        content_height = 0 if bbox is None else max(bbox[3] - bbox[1], 0)
        viewport_height = max(self.canvas.winfo_height(), 0)
        can_scroll = content_height > viewport_height + 12
        self.scroll_enabled = can_scroll

        if can_scroll:
            scrollbar.state(("!disabled",))
            return

        self.canvas.yview_moveto(0)
        scrollbar.state(("disabled",))

    def _browse_value(self, key: str, mode: str) -> None:
        current_value = self.variables[key].get()
        initial_path = resolve_path(current_value)

        if mode == "dir":
            selected = filedialog.askdirectory(
                title="选择目录",
                initialdir=str(initial_path if initial_path.exists() else ROOT_DIR),
            )
        elif mode == "file":
            selected = filedialog.askopenfilename(
                title="选择文件",
                initialdir=str(initial_path.parent if initial_path.parent.exists() else ROOT_DIR),
            )
        elif mode == "save":
            selected = filedialog.asksaveasfilename(
                title="选择保存路径",
                initialdir=str(initial_path.parent if initial_path.parent.exists() else ROOT_DIR),
                initialfile=initial_path.name,
            )
        else:
            selected = ""

        if selected:
            self.variables[key].set(selected)

    def _register_drop_target(self, key: str, mode: str) -> None:
        if not self.app.drag_drop_enabled or DND_FILES is None or DND_COPY is None:
            return

        widget = self.path_widgets.get(key)
        if widget is None:
            return

        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<DropEnter>>", lambda _event, field_key=key: self._on_drop_enter(field_key))
            widget.dnd_bind("<<DropPosition>>", lambda _event, field_key=key: self._on_drop_enter(field_key))
            widget.dnd_bind("<<DropLeave>>", lambda _event, field_key=key: self._on_drop_leave(field_key))
            widget.dnd_bind(
                "<<Drop>>",
                lambda event, field_key=key, field_mode=mode: self._handle_drop(event, field_key, field_mode),
            )
        except Exception:
            return

    def _handle_drop(self, event: Any, key: str, mode: str) -> str:
        self._set_drop_target_visual(key, active=False)
        dropped_paths = self._extract_drop_paths(getattr(event, "data", ""))
        if not dropped_paths:
            return DND_COPY or "copy"

        selected = self._resolve_drop_target(dropped_paths[0], mode)
        if selected is not None:
            self.variables[key].set(str(selected))
        return DND_COPY or "copy"

    def _on_drop_enter(self, key: str) -> str:
        self._set_drop_target_visual(key, active=True)
        return DND_COPY or "copy"

    def _on_drop_leave(self, key: str) -> None:
        self._set_drop_target_visual(key, active=False)

    def _set_drop_target_visual(self, key: str, active: bool) -> None:
        widget = self.path_widgets.get(key)
        hint = self.path_hints.get(key)
        if widget is None:
            return

        try:
            widget.configure(style="DropActive.TEntry" if active else "TEntry")
        except tk.TclError:
            pass

        if hint is not None:
            hint.configure(style="DropHintActive.TLabel" if active else "DropHint.TLabel")

    @staticmethod
    def _drop_hint_text(mode: str) -> str:
        if mode == "dir":
            return "支持将文件夹直接拖到这里"
        if mode == "file":
            return "支持将文件直接拖到这里"
        if mode == "save":
            return "支持拖入目录，自动作为保存位置"
        return "支持拖放路径到这里"

    def _extract_drop_paths(self, raw_data: str) -> list[Path]:
        if not raw_data:
            return []

        try:
            values = self.tk.splitlist(raw_data)
        except tk.TclError:
            values = (raw_data,)

        paths: list[Path] = []
        for value in values:
            text = str(value).strip()
            if text.startswith("{") and text.endswith("}"):
                text = text[1:-1]
            if text:
                paths.append(Path(text))
        return paths

    def _resolve_drop_target(self, path: Path, mode: str) -> Path | None:
        if mode == "dir":
            return path if path.is_dir() else path.parent
        if mode == "file":
            return path if path.is_file() else None
        if mode == "save":
            return path if path.is_dir() else path.parent
        return path

    def collect_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for group in self.groups:
            for field in group.fields:
                raw_value = self.variables[field.key].get()
                if field.value_type == "bool":
                    values[field.key] = bool(raw_value)
                    continue

                if isinstance(raw_value, str):
                    raw_value = raw_value.strip()

                if raw_value == "" and field.optional:
                    values[field.key] = None
                    continue

                if field.value_type == "int":
                    values[field.key] = int(raw_value)
                elif field.value_type == "float":
                    values[field.key] = float(raw_value)
                else:
                    values[field.key] = raw_value
        return values

    def load_values(self, values: dict[str, Any]) -> None:
        for key, variable in self.variables.items():
            if key not in values:
                continue
            value = values[key]
            if isinstance(variable, tk.BooleanVar):
                variable.set(bool(value))
            else:
                variable.set("" if value is None else str(value))

    def set_running_state(self, running: bool) -> None:
        if self.start_button is not None:
            self.start_button.configure(state="disabled" if running else "normal")
        if self.stop_button is not None:
            self.stop_button.configure(state="normal" if running else "disabled")

    def start_task(self) -> None:
        try:
            values = self.collect_values()
            self._validate(values)
            commands = self.command_builder(values)
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc), parent=self)
            return

        self.app.start_task(self, values, commands)

    def _validate(self, values: dict[str, Any]) -> None:
        start_year = values.get("start_year")
        end_year = values.get("end_year")
        if start_year is not None and end_year is not None and start_year > end_year:
            raise ValueError("起始年份不能大于结束年份")

        if values.get("metadata_only") and values.get("download_pdf"):
            raise ValueError("“只抓元数据”与“下载 PDF”不能同时勾选")

    def open_output(self) -> None:
        output_value = self.variables.get(self.output_key)
        if output_value is None:
            return
        open_path(str(output_value.get()))


class DesktopApp:
    def __init__(self, root: ttk.Window) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(1280, 820)
        self._configure_initial_window()
        self._window_icon_image: tk.PhotoImage | None = None
        self._apply_window_icon()
        self.style = ttk.Style()
        self.drag_drop_enabled = self._enable_drag_and_drop()

        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: TaskWorker | None = None
        self.running_tab: TaskTab | None = None
        self.running_since: float | None = None
        self.exit_after_stop = False
        self.is_starting_task = False
        self.current_task_key: str | None = None
        self.current_task_values: dict[str, Any] | None = None
        self.total_steps = 0
        self.completed_steps = 0
        self.log_line_count = 0

        self.status_var = tk.StringVar(value="就绪")
        self.detail_var = tk.StringVar(value="选择一个页签后开始运行")
        self.progress_text_var = tk.StringVar(value="步骤进度：0/0")
        self.stage_var = tk.StringVar(value="当前阶段：-")
        self.results_var = tk.StringVar(value="结果统计：-")
        self.artifact_var = tk.StringVar(value="产物位置：-")
        self.log_count_var = tk.StringVar(value="日志行数：0")
        self.runtime_summary_var = tk.StringVar(value="运行摘要：总耗时 0s | 当前阶段 - | 日志 0 行")
        self.final_report_var = tk.StringVar(
            value="最终汇总\n\n仅在“一键抓取+提取”任务中展示。\n完成后这里会自动汇总抓取和提取两段结果。"
        )
        self.stage_status_vars = {key: tk.StringVar(value="未开始") for key in STAGE_SEQUENCE}
        self.stage_detail_vars = {key: tk.StringVar(value="等待任务开始") for key in STAGE_SEQUENCE}
        self.stage_progress_vars = {key: tk.StringVar(value="-") for key in STAGE_SEQUENCE}
        self.current_stage_key: str | None = None
        self.stage_started_at: dict[str, float | None] = {key: None for key in STAGE_SEQUENCE}
        self.stage_elapsed_seconds: dict[str, float] = {key: 0.0 for key in STAGE_SEQUENCE}
        self.stage_card_frames: dict[str, tk.Frame] = {}
        self.stage_card_accent_frames: dict[str, tk.Frame] = {}
        self.stage_card_icon_labels: dict[str, tk.Label] = {}
        self.stage_card_title_labels: dict[str, tk.Label] = {}
        self.stage_card_status_labels: dict[str, tk.Label] = {}
        self.stage_card_progress_labels: dict[str, tk.Label] = {}
        self.stage_card_detail_labels: dict[str, tk.Label] = {}
        self.result_sheet: Sheet | None = None
        self.result_table_placeholder: ttk.Label | None = None
        self.result_table_entries: dict[str, list[str]] = {}

        self._apply_theme()
        self.tabs: dict[str, TaskTab] = {}
        self._build_ui()
        self._reset_result_table()
        self.root.after(80, self._apply_window_effects)
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll_events)
        self.root.after(1000, self._refresh_runtime)

    def _apply_window_icon(self) -> None:
        if APP_ICON_PNG_PATH.exists():
            try:
                self._window_icon_image = tk.PhotoImage(file=str(APP_ICON_PNG_PATH))
                self.root.iconphoto(True, self._window_icon_image)
            except tk.TclError:
                self._window_icon_image = None

        if sys.platform.startswith("win") and APP_ICON_ICO_PATH.exists():
            try:
                self.root.iconbitmap(default=str(APP_ICON_ICO_PATH))
            except tk.TclError:
                pass

    def _configure_initial_window(self) -> None:
        self.root.update_idletasks()
        screen_width = max(self.root.winfo_screenwidth(), 1366)
        screen_height = max(self.root.winfo_screenheight(), 900)

        width = min(max(int(screen_width * 0.88), 1360), 1920)
        height = min(max(int(screen_height * 0.9), 860), 1180)
        x = max((screen_width - width) // 2, 16)
        y = max((screen_height - height) // 2 - 12, 16)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _configure_body_split(self) -> None:
        body = getattr(self, "body_pane", None)
        if body is None:
            return

        self.root.update_idletasks()
        total_width = max(body.winfo_width(), self.root.winfo_width() - 48)
        if total_width <= 0:
            return

        left_width = int(total_width * 0.6)
        try:
            body.sashpos(0, left_width)
        except tk.TclError:
            return

    def _enable_drag_and_drop(self) -> bool:
        if TkinterDnD is None:
            return False

        try:
            TkinterDnD._require(self.root)
        except Exception:
            return False
        return True

    def _apply_window_effects(self) -> None:
        if not sys.platform.startswith("win") or pywinstyles is None:
            return

        try:
            self.root.update_idletasks()
            build_number = getattr(sys.getwindowsversion(), "build", 0)
            if build_number >= WIN11_BUILD:
                pywinstyles.apply_style(self.root, "mica")
                pywinstyles.change_header_color(self.root, color="transparent")
                pywinstyles.change_title_color(self.root, color=ACCENT)
                pywinstyles.change_border_color(self.root, color=BORDER_SOFT)
            else:
                pywinstyles.apply_style(self.root, "optimised")
                pywinstyles.change_header_color(self.root, color=SURFACE_ELEVATED)
                pywinstyles.change_title_color(self.root, color=ACCENT)
                pywinstyles.change_border_color(self.root, color=BORDER_COLOR)
        except Exception:
            # Window effects are best-effort only and should never block the GUI.
            pass

    def _apply_theme(self) -> None:
        self.root.configure(bg=APP_BG)
        self.style.configure(".", background=APP_BG, foreground=TEXT_PRIMARY, font=(UI_FONT, 10))
        self.style.configure("App.TFrame", background=APP_BG)
        self.style.configure("Surface.TFrame", background=SURFACE_BG)
        self.style.configure("Panel.TFrame", background=SURFACE_PANEL)
        self.style.configure("HeaderBar.TFrame", background=ACCENT)
        self.style.configure("HeroCard.TFrame", background=SURFACE_ELEVATED, borderwidth=1, relief="solid")
        self.style.configure("TabIntro.TFrame", background=SURFACE_PANEL, borderwidth=1, relief="solid")
        self.style.configure(
            "Card.TLabelframe",
            background=SURFACE_BG,
            bordercolor=BORDER_COLOR,
            relief="solid",
            borderwidth=1,
        )
        self.style.configure(
            "SoftCard.TLabelframe",
            background=SURFACE_PANEL,
            bordercolor=BORDER_SOFT,
            relief="solid",
            borderwidth=1,
        )
        self.style.configure(
            "SoftCard.TLabelframe.Label",
            background=SURFACE_PANEL,
            foreground=ACCENT,
            font=(UI_FONT, 10, "bold"),
        )
        self.style.configure(
            "Card.TLabelframe.Label",
            background=SURFACE_BG,
            foreground=ACCENT,
            font=(UI_FONT, 10, "bold"),
        )
        self.style.configure(
            "SectionTitle.TLabel",
            background=APP_BG,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9, "bold"),
        )
        self.style.configure(
            "HeroTitle.TLabel",
            background=SURFACE_ELEVATED,
            foreground=ACCENT,
            font=(UI_FONT, 19, "bold"),
        )
        self.style.configure(
            "HeroSubtitle.TLabel",
            background=SURFACE_ELEVATED,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 10),
        )
        self.style.configure(
            "HeroMeta.TLabel",
            background=SURFACE_ELEVATED,
            foreground=ACCENT_ALT,
            font=(UI_FONT, 9, "bold"),
        )
        self.style.configure(
            "TabIntroTitle.TLabel",
            background=SURFACE_PANEL,
            foreground=ACCENT,
            font=(UI_FONT, 12, "bold"),
        )
        self.style.configure(
            "TabIntroBody.TLabel",
            background=SURFACE_PANEL,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        )
        self.style.configure(
            "TabIntroHint.TLabel",
            background=SURFACE_PANEL,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9),
        )
        self.style.configure(
            "Summary.TLabel",
            background=SURFACE_BG,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        )
        self.style.configure(
            "PanelSummary.TLabel",
            background=SURFACE_PANEL,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        )
        self.style.configure(
            "Muted.TLabel",
            background=SURFACE_BG,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9),
        )
        self.style.configure(
            "FieldLabel.TLabel",
            background=SURFACE_PANEL,
            foreground=ACCENT_ALT,
            font=(UI_FONT, 9, "bold"),
        )
        self.style.configure(
            "PanelMuted.TLabel",
            background=SURFACE_PANEL,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9),
        )
        self.style.configure(
            "DropHint.TLabel",
            background=SURFACE_PANEL,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9),
        )
        self.style.configure(
            "DropHintActive.TLabel",
            background=SURFACE_PANEL,
            foreground=ACCENT_ALT,
            font=(UI_FONT, 9, "bold"),
        )
        self.style.configure(
            "StatusEyebrow.TLabel",
            background=SURFACE_ELEVATED,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9, "bold"),
        )
        self.style.configure(
            "StatusHeadline.TLabel",
            background=SURFACE_ELEVATED,
            foreground=ACCENT,
            font=(UI_FONT, 16, "bold"),
        )
        self.style.configure(
            "StatusDetail.TLabel",
            background=SURFACE_ELEVATED,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        )
        self.style.configure(
            "StatusMeta.TLabel",
            background=SURFACE_ELEVATED,
            foreground=TEXT_MUTED,
            font=(UI_FONT, 9),
        )
        self.style.configure(
            "TNotebook",
            background=APP_BG,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        self.style.configure(
            "TNotebook.Tab",
            background=SURFACE_TINT,
            foreground=TEXT_MUTED,
            padding=(22, 12),
            font=(UI_FONT, 10, "bold"),
            borderwidth=0,
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", SURFACE_BG), ("active", GOLD_SOFT)],
            foreground=[("selected", ACCENT), ("active", ACCENT)],
        )
        self.style.configure(
            "TButton",
            font=(UI_FONT, 10, "bold"),
            padding=(14, 9),
            background=SURFACE_SOFT,
            foreground=ACCENT,
            borderwidth=0,
        )
        self.style.map(
            "TButton",
            background=[("pressed", GOLD_SOFT), ("active", GOLD_SOFT), ("disabled", "#eadfd0")],
            foreground=[("disabled", "#9f9589")],
        )
        self.style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="#ffffff",
            padding=(16, 10),
        )
        self.style.map(
            "Primary.TButton",
            background=[("pressed", ACCENT_ALT), ("active", ACCENT_ALT), ("disabled", "#8ca1b8")],
            foreground=[("disabled", "#eef2f6")],
        )
        self.style.configure(
            "Danger.TButton",
            background=DANGER_SOFT,
            foreground=DANGER,
            padding=(16, 10),
        )
        self.style.map(
            "Danger.TButton",
            background=[("pressed", "#f3cfd5"), ("active", "#f3cfd5"), ("disabled", "#f5e7ea")],
            foreground=[("disabled", "#ad7b83")],
        )
        self.style.configure(
            "Toolbar.TButton",
            background=SURFACE_SOFT,
            foreground=ACCENT,
            padding=(12, 8),
        )
        self.style.configure(
            "Subtle.TButton",
            background=SURFACE_PANEL,
            foreground=ACCENT_ALT,
            padding=(12, 8),
        )
        self.style.configure(
            "Link.TButton",
            background=APP_BG,
            foreground=ACCENT,
            padding=(8, 4),
        )
        self.style.configure(
            "TEntry",
            fieldbackground="#fffaf4",
            foreground=TEXT_PRIMARY,
            bordercolor=BORDER_COLOR,
            insertcolor=TEXT_PRIMARY,
            padding=7,
        )
        self.style.configure(
            "DropActive.TEntry",
            fieldbackground="#fff7eb",
            foreground=TEXT_PRIMARY,
            bordercolor=ACCENT_LINE,
            insertcolor=TEXT_PRIMARY,
            padding=7,
        )
        self.style.configure(
            "TCombobox",
            fieldbackground="#fffaf4",
            foreground=TEXT_PRIMARY,
            bordercolor=BORDER_COLOR,
            padding=7,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#fffaf4")],
            selectbackground=[("readonly", GOLD_SOFT)],
            selectforeground=[("readonly", TEXT_PRIMARY)],
        )
        self.style.configure(
            "TCheckbutton",
            background=SURFACE_PANEL,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        )
        self.style.map("TCheckbutton", background=[("active", SURFACE_PANEL)])
        self.style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#e8dccf",
            background=ACCENT_ALT,
            bordercolor="#e8dccf",
            lightcolor=ACCENT_ALT,
            darkcolor=ACCENT_ALT,
        )
        self.style.configure(
            "Vertical.TScrollbar",
            background=SURFACE_SOFT,
            troughcolor=APP_BG,
            bordercolor=APP_BG,
            arrowcolor=ACCENT,
        )
        self.style.configure(
            "Horizontal.TPanedwindow",
            background=APP_BG,
            sashthickness=8,
        )

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)

        title_block = ctk.CTkFrame(
            header,
            fg_color=SURFACE_ELEVATED,
            corner_radius=22,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        title_block.grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_block,
            text="桌面任务控制台",
            style="HeroTitle.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))
        ttk.Label(
            title_block,
            text="把现有爬取和文本提取脚本串成一个可操作的桌面入口。",
            style="HeroSubtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))

        stage_cards = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        stage_cards.grid(row=0, column=1, sticky="ew", padx=(28, 0))
        for index, stage_key in enumerate(STAGE_SEQUENCE):
            stage_cards.columnconfigure(index, weight=1)
            card = tk.Frame(stage_cards, bd=0, relief="flat", padx=14, pady=12, height=136, highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 12) if index < len(STAGE_SEQUENCE) - 1 else 0)
            card.columnconfigure(0, weight=1)
            card.grid_propagate(False)

            accent_bar = tk.Frame(card, height=7, bd=0, highlightthickness=0)
            accent_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

            header_frame = tk.Frame(card, bd=0, highlightthickness=0)
            header_frame.grid(row=1, column=0, sticky="ew")
            header_frame.columnconfigure(1, weight=1)

            icon_label = tk.Label(
                header_frame,
                text=STAGE_TYPE_ICONS.get(stage_key, "•"),
                anchor="w",
                font=(UI_FONT, 9, "bold"),
                width=4,
                padx=6,
                pady=3,
            )
            icon_label.grid(row=0, column=0, sticky="w", padx=(0, 4))

            title_label = tk.Label(
                header_frame,
                text=STAGE_LABELS[stage_key],
                anchor="w",
                font=("Microsoft YaHei UI", 10, "bold"),
            )
            title_label.grid(row=0, column=1, sticky="ew")

            status_label = tk.Label(
                card,
                anchor="center",
                font=("Microsoft YaHei UI", 9, "bold"),
                padx=8,
                pady=4,
            )
            status_label.grid(row=2, column=0, sticky="w", pady=(10, 8))

            progress_label = tk.Label(
                card,
                textvariable=self.stage_progress_vars[stage_key],
                anchor="nw",
                wraplength=220,
                justify="left",
                height=1,
                font=(UI_FONT, 10),
            )
            progress_label.grid(row=3, column=0, sticky="ew", pady=(2, 2))

            detail_label = tk.Label(
                card,
                textvariable=self.stage_detail_vars[stage_key],
                anchor="nw",
                wraplength=220,
                justify="left",
                height=2,
                font=(UI_FONT, 10),
            )
            detail_label.grid(row=4, column=0, sticky="ew", pady=(0, 0))

            self.stage_card_frames[stage_key] = card
            self.stage_card_accent_frames[stage_key] = accent_bar
            self.stage_card_icon_labels[stage_key] = icon_label
            self.stage_card_title_labels[stage_key] = title_label
            self.stage_card_status_labels[stage_key] = status_label
            self.stage_card_progress_labels[stage_key] = progress_label
            self.stage_card_detail_labels[stage_key] = detail_label
            self._apply_stage_card_visuals(stage_key)

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.body_pane = body

        top_panel = ttk.Frame(body, padding=0, style="Surface.TFrame")
        top_panel.columnconfigure(0, weight=1)
        top_panel.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(top_panel)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook = notebook

        for tab in self._build_tabs(notebook):
            notebook.add(tab, text=tab.title)
            self.tabs[tab.tab_key] = tab
        notebook.add(self._build_about_tab(notebook), text="关于")

        bottom_panel = ttk.Frame(body, padding=(2, 2, 2, 2), style="Surface.TFrame")
        bottom_panel.columnconfigure(0, weight=1)
        bottom_panel.rowconfigure(2, weight=1)

        status_frame = ctk.CTkFrame(
            bottom_panel,
            fg_color=SURFACE_ELEVATED,
            corner_radius=22,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        status_frame.columnconfigure(0, weight=1)
        status_frame.configure(height=240)
        status_frame.grid_propagate(False)

        ttk.Label(status_frame, text="运行状态", style="StatusEyebrow.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor="w",
            style="StatusHeadline.TLabel",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Label(
            status_frame,
            textvariable=self.detail_var,
            anchor="nw",
            justify="left",
            wraplength=420,
            style="StatusDetail.TLabel",
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.progress = ctk.CTkProgressBar(
            status_frame,
            mode="indeterminate",
            progress_color=ACCENT_ALT,
            fg_color=ACCENT_SOFT,
            corner_radius=999,
            width=128,
            height=14,
        )
        self.progress.grid(row=0, column=1, rowspan=3, sticky="e", padx=(14, 0))
        ttk.Label(
            status_frame,
            textvariable=self.runtime_summary_var,
            anchor="w",
            style="StatusMeta.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        metrics_frame = ttk.Labelframe(
            bottom_panel,
            text="进度与结果",
            padding=12,
            style="Card.TLabelframe",
            bootstyle="primary",
        )
        metrics_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        metrics_frame.columnconfigure(0, weight=1)
        metrics_frame.columnconfigure(1, weight=1)
        metrics_frame.rowconfigure(3, weight=1)

        tk.Label(
            metrics_frame,
            textvariable=self.progress_text_var,
            anchor="w",
            justify="left",
            height=1,
            bg=SURFACE_BG,
            fg=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(2, 4))
        tk.Label(
            metrics_frame,
            textvariable=self.stage_var,
            anchor="nw",
            wraplength=220,
            justify="left",
            height=2,
            bg=SURFACE_BG,
            fg=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        ).grid(row=0, column=1, sticky="ew", pady=(2, 4))
        tk.Label(
            metrics_frame,
            textvariable=self.results_var,
            anchor="nw",
            wraplength=220,
            justify="left",
            height=2,
            bg=SURFACE_BG,
            fg=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        ).grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(4, 4))
        ttk.Label(metrics_frame, textvariable=self.log_count_var, anchor="w", style="Muted.TLabel").grid(row=1, column=1, sticky="ew", pady=(4, 4))
        tk.Label(
            metrics_frame,
            textvariable=self.artifact_var,
            anchor="nw",
            wraplength=520,
            justify="left",
            height=3,
            bg=SURFACE_BG,
            fg=TEXT_MUTED,
            font=(UI_FONT, 9),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 2))

        result_table_frame = ttk.Labelframe(
            metrics_frame,
            text="结果明细表",
            padding=8,
            style="SoftCard.TLabelframe",
            bootstyle="info",
        )
        result_table_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 2))
        result_table_frame.columnconfigure(0, weight=1)
        result_table_frame.rowconfigure(0, weight=1)
        result_table_frame.configure(height=244)
        result_table_frame.grid_propagate(False)

        if Sheet is not None:
            self.result_sheet = Sheet(
                result_table_frame,
                show_row_index=False,
                width=560,
                height=212,
                headers=["阶段", "指标", "数值", "说明"],
                data=[],
                theme="light blue",
                font=(UI_FONT, 10, "normal"),
                header_font=(UI_FONT, 10, "bold"),
                default_header_height=28,
                default_row_height=28,
                align="w",
                header_align="w",
                table_bg=SURFACE_BG,
                table_fg=TEXT_PRIMARY,
                frame_bg=SURFACE_PANEL,
                header_bg=SURFACE_PANEL,
                header_fg=ACCENT,
                table_grid_fg=BORDER_SOFT,
                header_grid_fg=BORDER_SOFT,
                index_bg=SURFACE_PANEL,
                top_left_bg=SURFACE_PANEL,
                table_selected_cells_bg=ACCENT_SOFT,
                table_selected_cells_border_fg=ACCENT_ALT,
                table_selected_cells_fg=TEXT_PRIMARY,
                vertical_scroll_background=SURFACE_PANEL,
                horizontal_scroll_background=SURFACE_PANEL,
                vertical_scroll_troughcolor=SURFACE_SOFT,
                horizontal_scroll_troughcolor=SURFACE_SOFT,
                vertical_scroll_bordercolor=SURFACE_PANEL,
                horizontal_scroll_bordercolor=SURFACE_PANEL,
                vertical_scroll_not_active_bg="#d8cec0",
                horizontal_scroll_not_active_bg="#d8cec0",
                vertical_scroll_active_bg="#bfae99",
                horizontal_scroll_active_bg="#bfae99",
                scrollbar_theme_inheritance="default",
            )
            self.result_sheet.grid(row=0, column=0, sticky="nsew")
            self.result_sheet.readonly_columns([0, 1, 2, 3], redraw=False)
            self.result_sheet.headers(["阶段", "指标", "数值", "说明"], redraw=False)
            self.result_sheet.set_options(auto_resize_columns=220, redraw=True)
        else:
            self.result_table_placeholder = ttk.Label(
                result_table_frame,
                text="未启用 tksheet，结果明细表不可用。",
                style="PanelMuted.TLabel",
                anchor="w",
                justify="left",
            )
            self.result_table_placeholder.grid(row=0, column=0, sticky="nsew")

        final_report_frame = ttk.Labelframe(
            metrics_frame,
            text="最终汇总卡片",
            padding=10,
            style="SoftCard.TLabelframe",
            bootstyle="warning",
        )
        final_report_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        final_report_frame.columnconfigure(0, weight=1)
        final_report_frame.configure(height=188)
        final_report_frame.grid_propagate(False)
        tk.Label(
            final_report_frame,
            textvariable=self.final_report_var,
            anchor="nw",
            wraplength=520,
            justify="left",
            height=9,
            bg=SURFACE_PANEL,
            fg=TEXT_PRIMARY,
            font=(UI_FONT, 10),
        ).grid(row=0, column=0, sticky="ew")
        final_report_frame.grid_remove()

        log_frame = ttk.Labelframe(
            bottom_panel,
            text="运行日志",
            padding=10,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap="none",
            height=18,
            font=(UI_FONT, 10),
            relief="flat",
            padx=10,
            pady=10,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self._apply_log_console_theme()
        self._configure_log_tags()

        footer = ttk.Frame(bottom_panel, style="Surface.TFrame", padding=(12, 10, 12, 0))
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            footer,
            text="清空日志",
            command=self.clear_log,
            style="Toolbar.TButton",
            bootstyle="secondary",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            footer,
            text="打开工作目录",
            command=lambda: open_path(str(ROOT_DIR)),
            style="Toolbar.TButton",
            bootstyle="secondary",
        ).grid(row=0, column=1)

        body.add(top_panel, weight=5)
        body.add(bottom_panel, weight=4)
        self.root.after(180, self._configure_body_split)

    def _build_tabs(self, notebook: ttk.Notebook) -> list[TaskTab]:
        spider_tab = TaskTab(
            notebook,
            app=self,
            tab_key="spider",
            title="年报抓取",
            groups=[
                FieldGroup(
                    "抓取参数",
                    [
                        FieldSpec("start_year", "起始年份", "int", 2014),
                        FieldSpec("end_year", "结束年份", "int", 2024),
                        FieldSpec("se_date", "自定义公告日期范围", "str", "", optional=True),
                        FieldSpec("page_size", "每页条数", "int", 30),
                        FieldSpec("request_interval", "请求间隔（秒）", "float", 0.2),
                        FieldSpec("announcement_concurrency", "公告抓取并发数", "int", 2),
                        FieldSpec("download_concurrency", "PDF 下载并发数", "int", 2),
                    ],
                ),
                FieldGroup(
                    "路径与动作",
                    [
                        FieldSpec("output_dir", "输出目录", "str", "annual_reports", browse="dir"),
                        FieldSpec("state_dir", "状态目录", "str", ".", browse="dir"),
                        FieldSpec("download_pdf", "下载筛选后的 PDF", "bool", True),
                        FieldSpec("metadata_only", "只抓元数据（不下载 PDF）", "bool", False),
                        FieldSpec("audit_pdf", "执行 PDF 审计", "bool", False),
                        FieldSpec("cleanup_orphan_pdf", "清理孤儿 PDF", "bool", False),
                        FieldSpec("reset_checkpoint", "重置旧 checkpoint", "bool", False),
                        FieldSpec("delete_checkpoint_on_success", "成功后删除 checkpoint", "bool", False),
                    ],
                ),
            ],
            command_builder=build_spider_commands,
            output_key="output_dir",
        )

        extract_tab = TaskTab(
            notebook,
            app=self,
            tab_key="extract",
            title="文本提取",
            groups=[
                FieldGroup(
                    "提取参数",
                    [
                        FieldSpec("input_dir", "PDF 输入目录", "str", "annual_reports", browse="dir"),
                        FieldSpec("output_dir", "文本输出目录", "str", "txt_extract", browse="dir"),
                        FieldSpec("state_dir", "状态目录", "str", ".", browse="dir"),
                        FieldSpec("start_year", "起始年份", "int", 2014),
                        FieldSpec("end_year", "结束年份", "int", 2024),
                        FieldSpec("concurrency", "提取并发数", "int", 2),
                        FieldSpec("reset_checkpoint", "重置旧 checkpoint", "bool", False),
                        FieldSpec("delete_checkpoint_on_success", "成功后删除 checkpoint", "bool", False),
                    ],
                ),
            ],
            command_builder=build_extract_commands,
            output_key="output_dir",
        )

        pipeline_tab = TaskTab(
            notebook,
            app=self,
            tab_key="pipeline",
            title="一键抓取+提取",
            groups=[
                FieldGroup(
                    "基础范围",
                    [
                        FieldSpec("start_year", "起始年份", "int", 2014),
                        FieldSpec("end_year", "结束年份", "int", 2024),
                        FieldSpec("se_date", "自定义公告日期范围", "str", "", optional=True),
                        FieldSpec("state_dir", "状态目录", "str", ".", browse="dir"),
                    ],
                ),
                FieldGroup(
                    "抓取与提取参数",
                    [
                        FieldSpec("pdf_output_dir", "PDF 输出目录", "str", "annual_reports", browse="dir"),
                        FieldSpec("request_interval", "请求间隔（秒）", "float", 0.2),
                        FieldSpec("announcement_concurrency", "公告抓取并发数", "int", 2),
                        FieldSpec("download_concurrency", "PDF 下载并发数", "int", 2),
                        FieldSpec("extract_output_dir", "文本输出目录", "str", "txt_extract", browse="dir"),
                        FieldSpec("extract_concurrency", "文本提取并发数", "int", 2),
                        FieldSpec("reset_checkpoint", "重置旧 checkpoint", "bool", False),
                        FieldSpec("delete_checkpoint_on_success", "成功后删除 checkpoint", "bool", False),
                    ],
                ),
            ],
            command_builder=build_pipeline_commands,
            output_key="extract_output_dir",
        )

        return [spider_tab, extract_tab, pipeline_tab]

    def _build_about_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        about_tab = ttk.Frame(notebook, padding=16, style="Surface.TFrame")
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(2, weight=1)

        title_card = ttk.Labelframe(
            about_tab,
            text="项目说明",
            padding=14,
            style="SoftCard.TLabelframe",
            bootstyle="info",
        )
        title_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        title_card.columnconfigure(0, weight=1)

        ttk.Label(
            title_card,
            text=f"{APP_TITLE}  v{APP_VERSION}",
            style="TabIntroTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_card,
            text="这里汇总项目 README、GUI 说明和 GitHub 仓库入口，方便直接查看。",
            style="TabIntroBody.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        action_card = ttk.Labelframe(
            about_tab,
            text="快捷入口",
            padding=12,
            style="Card.TLabelframe",
            bootstyle="primary",
        )
        action_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for index in range(3):
            action_card.columnconfigure(index, weight=1)

        readme_path = README_PATH
        gui_readme_path = GUI_README_PATH
        github_url = get_github_url()

        ttk.Button(
            action_card,
            text="打开 README",
            command=lambda: open_path(str(readme_path)),
            style="Toolbar.TButton",
            bootstyle="secondary",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Button(
            action_card,
            text="打开 GUI_README",
            command=lambda: open_path(str(gui_readme_path)),
            style="Toolbar.TButton",
            bootstyle="secondary",
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Button(
            action_card,
            text="打开 GitHub",
            command=lambda: webbrowser.open(github_url) if github_url else None,
            style="Primary.TButton",
            bootstyle="primary",
        ).grid(row=0, column=2, sticky="w")

        reader_card = ttk.Labelframe(
            about_tab,
            text="README 预览",
            padding=10,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )
        reader_card.grid(row=2, column=0, sticky="nsew")
        reader_card.columnconfigure(0, weight=1)
        reader_card.rowconfigure(1, weight=1)

        summary_lines = [
            f"版本：{APP_VERSION}",
            f"发布者：{COMPANY_NAME}",
            f"README 文件：{readme_path}",
            f"GUI 说明：{gui_readme_path}",
            f"GitHub 地址：{github_url or '未发现 origin 地址'}",
        ]
        ttk.Label(
            reader_card,
            text="\n".join(summary_lines),
            anchor="w",
            justify="left",
            style="Summary.TLabel",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        about_text = scrolledtext.ScrolledText(
            reader_card,
            wrap="word",
            font=(UI_FONT, 10),
            relief="flat",
            padx=12,
            pady=12,
            bg=SURFACE_BG,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
        )
        about_text.grid(row=1, column=0, sticky="nsew")

        sections: list[str] = []
        if readme_path.exists():
            sections.append("# README.md\n\n" + load_text_file(readme_path).strip())
        if gui_readme_path.exists():
            sections.append("# GUI_README.md\n\n" + load_text_file(gui_readme_path).strip())
        if not sections:
            sections.append("未找到可展示的 README 文件。")

        about_text.insert("1.0", "\n\n" + ("\n\n" + ("-" * 72) + "\n\n").join(sections))
        about_text.configure(state="disabled")
        return about_tab

    def start_task(self, tab: TaskTab, values: dict[str, Any], commands: list[CommandSpec]) -> None:
        if self.is_starting_task or (self.worker is not None and self.worker.is_alive()):
            return

        self.is_starting_task = True
        self._set_all_tabs_running(True)
        self.status_var.set(f"正在准备：{tab.title}")
        self.detail_var.set("正在整理参数并启动后台任务，请稍候。")
        self.progress.configure(mode="indeterminate")
        self.progress.start(10)
        self.root.update_idletasks()
        self.root.after(10, lambda: self._launch_prepared_task(tab, values, commands))

    def _launch_prepared_task(self, tab: TaskTab, values: dict[str, Any], commands: list[CommandSpec]) -> None:
        try:
            self.clear_log()
            self.save_config(show_feedback=False)
            self.stop_event.clear()
            self.exit_after_stop = False
            self.current_task_key = tab.tab_key
            self.current_task_values = values
            self.total_steps = max(len(commands), 1)
            self.completed_steps = 0
            self.log_line_count = 0
            self._reset_result_table()
            self._set_result_metric("global.task", "全局", "任务", tab.title, "当前任务")
            self._set_result_metric("global.progress", "全局", "步骤", f"0/{self.total_steps}", "步骤进度")
            self._refresh_result_sheet()
            self.progress.configure(mode="indeterminate")
            self.progress.start(10)
            self.progress_text_var.set(f"步骤进度：0/{self.total_steps}")
            self.stage_var.set(f"当前阶段：准备启动（共 {self.total_steps} 步）")
            self.log_count_var.set("日志行数：0")
            if tab.tab_key != "pipeline":
                self.final_report_var.set("最终汇总：仅在“一键抓取+提取”任务中展示。")
            self._reset_stage_cards(tab.tab_key)
            active_stages = self._stage_keys_for_task(tab.tab_key)
            if active_stages:
                self.current_stage_key = active_stages[0]
                self._set_stage_card(
                    active_stages[0],
                    status="准备中",
                    detail="等待执行",
                    progress=f"步骤 1/{self.total_steps}",
                )
            self._refresh_result_summary()
            self.worker = TaskWorker(commands=commands, event_queue=self.event_queue, stop_event=self.stop_event)
            self.running_tab = tab
            self.running_since = time.time()
            self.status_var.set(f"运行中：{tab.title}")
            self.detail_var.set(f"任务已启动，当前任务为“{tab.title}”，日志会持续输出在右侧。")
            self._update_runtime_summary()
            self.worker.start()
        except Exception as exc:
            self.progress.stop()
            self._set_all_tabs_running(False)
            self.status_var.set("启动失败")
            self.detail_var.set(f"任务启动失败：{exc}")
            self.append_log(f"[失败] 任务启动失败：{exc}")
            messagebox.showerror("启动失败", f"任务启动失败：{exc}", parent=self.root)
        finally:
            self.is_starting_task = False

    def stop_running_task(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            return
        self.stop_event.set()
        self.status_var.set("正在停止任务")
        self.detail_var.set("已发送停止信号，等待子进程退出。")
        self._update_runtime_summary()

    def _set_all_tabs_running(self, running: bool) -> None:
        for tab in self.tabs.values():
            tab.set_running_state(running)

    def _stage_keys_for_task(self, task_key: str | None) -> tuple[str, ...]:
        if task_key == "pipeline":
            return STAGE_SEQUENCE
        if task_key in STAGE_LABELS:
            return (str(task_key),)
        return ()

    def _resolve_stage_key(self, action: str | None = None, title: str = "") -> str | None:
        action_name = (action or "").strip()
        if action_name == "spider_service":
            return "spider"
        if action_name == "extract_service":
            return "extract"

        title_text = title.strip()
        if "抓取" in title_text:
            return "spider"
        if "提取" in title_text:
            return "extract"
        return None

    def _set_stage_card(
        self,
        stage_key: str,
        *,
        status: str | None = None,
        detail: str | None = None,
        progress: str | None = None,
    ) -> None:
        if stage_key not in self.stage_status_vars:
            return
        if status is not None:
            self.stage_status_vars[stage_key].set(status)
        if detail is not None:
            self.stage_detail_vars[stage_key].set(detail)
        if progress is not None:
            self.stage_progress_vars[stage_key].set(progress)
        self._apply_stage_card_visuals(stage_key)

    def _format_elapsed(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes, remain = divmod(int(seconds), 60)
        if minutes < 60:
            return f"{minutes}m {remain}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"

    def _ensure_stage_started(self, stage_key: str) -> None:
        if stage_key in self.stage_started_at and self.stage_started_at[stage_key] is None:
            self.stage_started_at[stage_key] = time.time()

    def _finalize_stage_elapsed(self, stage_key: str, elapsed_seconds: float | None = None) -> None:
        if stage_key not in self.stage_elapsed_seconds:
            return
        if elapsed_seconds is not None:
            self.stage_elapsed_seconds[stage_key] = max(float(elapsed_seconds), 0.0)
            self.stage_started_at[stage_key] = None
            return
        started_at = self.stage_started_at.get(stage_key)
        if started_at is not None:
            self.stage_elapsed_seconds[stage_key] = max(time.time() - started_at, 0.0)
            self.stage_started_at[stage_key] = None

    def _stage_progress_with_elapsed(self, stage_key: str, base: str) -> str:
        started_at = self.stage_started_at.get(stage_key)
        if started_at is not None:
            elapsed = time.time() - started_at
            self.stage_elapsed_seconds[stage_key] = max(elapsed, 0.0)
        else:
            elapsed = self.stage_elapsed_seconds.get(stage_key, 0.0)

        elapsed_text = self._format_elapsed(elapsed)
        if base and base != "-":
            return f"{base} | 耗时 {elapsed_text}"
        return f"耗时 {elapsed_text}"

    def _configure_log_tags(self) -> None:
        self.log_text.tag_configure("timestamp", foreground=CONSOLE_MUTED)
        self.log_text.tag_configure("default", foreground=CONSOLE_FG)
        self.log_text.tag_configure("debug", foreground="#2b2b2b")
        self.log_text.tag_configure("info", foreground="#111111")
        self.log_text.tag_configure("success", foreground="#111111")
        self.log_text.tag_configure("warn", foreground=CONSOLE_ACCENT)
        self.log_text.tag_configure("error", foreground="#ff4d4f")
        self.log_text.tag_configure("status", foreground="#ff7875")
        self.log_text.tag_configure("command", foreground="#111111")

    def _apply_log_console_theme(self) -> None:
        self.log_text.configure(
            bg=CONSOLE_BG,
            fg=CONSOLE_FG,
            insertbackground=CONSOLE_FG,
            selectbackground="#f3d7d8",
            selectforeground="#111111",
            highlightthickness=0,
            bd=0,
        )
        try:
            self.log_text.frame.configure(bg=CONSOLE_BG)
        except Exception:
            pass

    @staticmethod
    def _resolve_log_tag(text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return "default"
        if stripped.startswith("$ "):
            return "command"
        if stripped.startswith("Traceback"):
            return "error"
        if stripped.startswith("[") and "]" in stripped:
            level = stripped[1:stripped.index("]")].strip().upper()
            if level in {"DEBUG"}:
                return "debug"
            if level in {"INFO"}:
                return "info"
            if level in {"SUCCESS", "完成"}:
                return "success"
            if level in {"WARNING", "WARN", "已停止", "停止"}:
                return "warn"
            if level in {"ERROR", "ERR", "失败"}:
                return "error"
            if level in {"STATUS"}:
                return "status"
        return "default"

    def _reset_result_table(self) -> None:
        self.result_table_entries.clear()
        self._set_result_metric("global.task", "全局", "任务", "待运行", "开始任务后显示结构化结果")
        self._set_result_metric("global.progress", "全局", "步骤", "0/0", "步骤进度")
        self._set_result_metric("global.stage", "全局", "阶段", "-", "当前阶段")
        self._set_result_metric("global.logs", "全局", "日志", "0", "日志行数")
        self._set_result_metric("global.artifact", "全局", "产物", "-", "输出路径或汇总文件")
        self._refresh_result_sheet()

    def _set_result_metric(self, key: str, stage: str, metric: str, value: Any, note: str = "") -> None:
        self.result_table_entries[key] = [stage, metric, str(value), str(note)]

    def _remove_result_metrics(self, prefix: str) -> None:
        for key in [key for key in self.result_table_entries if key.startswith(prefix)]:
            self.result_table_entries.pop(key, None)

    def _refresh_result_sheet(self) -> None:
        rows = list(self.result_table_entries.values()) or [["全局", "状态", "待运行", "开始任务后显示结构化结果"]]
        if self.result_sheet is not None:
            self.result_sheet.set_sheet_data(rows, redraw=False)
            self.result_sheet.readonly_columns([0, 1, 2, 3], redraw=True)
        elif self.result_table_placeholder is not None:
            preview = "\n".join(" | ".join(row[:3]) for row in rows[:4])
            self.result_table_placeholder.configure(text=preview)

    def _sync_result_overview(self) -> None:
        task_title = self.running_tab.title if self.running_tab is not None else "待运行"
        progress_text = f"{self.completed_steps}/{self.total_steps}" if self.total_steps else "0/0"
        stage_text = STAGE_LABELS.get(self.current_stage_key, "-") if self.current_stage_key else "-"
        self._set_result_metric("global.task", "全局", "任务", task_title, "当前任务")
        self._set_result_metric("global.progress", "全局", "步骤", progress_text, "步骤进度")
        self._set_result_metric("global.stage", "全局", "阶段", stage_text, "当前阶段")
        self._set_result_metric("global.logs", "全局", "日志", str(self.log_line_count), "日志行数")
        self._set_result_metric("global.artifact", "全局", "产物", self.artifact_var.get().replace("产物位置：", "", 1), "最新产物位置")
        self._refresh_result_sheet()

    def _sync_result_table_from_outputs(self, task_key: str | None, values: dict[str, Any]) -> None:
        if not task_key:
            self._refresh_result_sheet()
            return

        if task_key == "spider":
            output_dir = resolve_path(str(values.get("output_dir", "annual_reports")))
            checkpoint_path = resolve_path(str(values.get("state_dir", "."))) / SPIDER_CHECKPOINT_NAME
            summary = load_json_file(output_dir / SPIDER_SUMMARY_NAME)
            self._remove_result_metrics("spider.")
            if isinstance(summary, list):
                total_filtered = sum(int(item.get("filtered_total", 0)) for item in summary if isinstance(item, dict))
                total_downloaded = sum(int(item.get("downloaded", 0)) for item in summary if isinstance(item, dict))
                total_failed = sum(int(item.get("failed", 0)) for item in summary if isinstance(item, dict))
                self._set_result_metric("spider.status", "抓取", "状态", "已汇总", "来自 summary.json")
                self._set_result_metric("spider.years", "抓取", "年份", len(summary), "汇总年份数")
                self._set_result_metric("spider.filtered", "抓取", "保留公告", total_filtered, "筛选后保留")
                self._set_result_metric("spider.downloaded", "抓取", "下载", total_downloaded, "已下载 PDF")
                self._set_result_metric("spider.failed", "抓取", "失败", total_failed, "抓取失败数量")
            else:
                self._set_result_metric("spider.status", "抓取", "状态", "未生成汇总", "尚未发现 summary.json")
            self._set_result_metric("spider.output", "产物", "输出目录", output_dir, "抓取输出目录")
            self._set_result_metric("spider.checkpoint", "产物", "Checkpoint", checkpoint_path, "抓取断点文件")
            self._refresh_result_sheet()
            return

        if task_key == "extract":
            output_dir = resolve_path(str(values.get("output_dir", "txt_extract")))
            checkpoint_path = resolve_path(str(values.get("state_dir", "."))) / EXTRACT_CHECKPOINT_NAME
            summary = load_json_file(output_dir / EXTRACT_SUMMARY_NAME)
            self._remove_result_metrics("extract.")
            if isinstance(summary, dict):
                self._set_result_metric("extract.status", "提取", "状态", "已汇总", "来自文本汇总文件")
                self._set_result_metric("extract.pdf_total", "提取", "PDF 总数", summary.get("pdf_total", 0), "发现的 PDF 数量")
                self._set_result_metric("extract.extracted", "提取", "已提取", summary.get("extracted", 0), "成功提取文本")
                self._set_result_metric("extract.exists", "提取", "已存在", summary.get("exists", 0), "已存在文本")
                self._set_result_metric("extract.failed", "提取", "失败", summary.get("failed", 0), "提取失败数量")
            else:
                self._set_result_metric("extract.status", "提取", "状态", "未生成汇总", "尚未发现文本汇总文件")
            self._set_result_metric("extract.output", "产物", "输出目录", output_dir, "文本输出目录")
            self._set_result_metric("extract.checkpoint", "产物", "Checkpoint", checkpoint_path, "提取断点文件")
            self._refresh_result_sheet()
            return

        if task_key == "pipeline":
            spider_output_dir = resolve_path(str(values.get("pdf_output_dir", "annual_reports")))
            extract_output_dir = resolve_path(str(values.get("extract_output_dir", "txt_extract")))
            spider_summary = load_json_file(spider_output_dir / SPIDER_SUMMARY_NAME)
            extract_summary = load_json_file(extract_output_dir / EXTRACT_SUMMARY_NAME)
            self._remove_result_metrics("spider.")
            self._remove_result_metrics("extract.")
            self._remove_result_metrics("pipeline.")
            if isinstance(spider_summary, list):
                spider_total_filtered = sum(int(item.get("filtered_total", 0)) for item in spider_summary if isinstance(item, dict))
                spider_total_downloaded = sum(int(item.get("downloaded", 0)) for item in spider_summary if isinstance(item, dict))
                spider_total_failed = sum(int(item.get("failed", 0)) for item in spider_summary if isinstance(item, dict))
                self._set_result_metric("spider.status", "抓取", "状态", "已汇总", "管线抓取汇总")
                self._set_result_metric("spider.years", "抓取", "年份", len(spider_summary), "汇总年份数")
                self._set_result_metric("spider.filtered", "抓取", "保留公告", spider_total_filtered, "筛选后保留")
                self._set_result_metric("spider.downloaded", "抓取", "下载", spider_total_downloaded, "已下载 PDF")
                self._set_result_metric("spider.failed", "抓取", "失败", spider_total_failed, "抓取失败数量")
            else:
                self._set_result_metric("spider.status", "抓取", "状态", "未生成汇总", "管线抓取汇总缺失")
            if isinstance(extract_summary, dict):
                self._set_result_metric("extract.status", "提取", "状态", "已汇总", "管线提取汇总")
                self._set_result_metric("extract.pdf_total", "提取", "PDF 总数", extract_summary.get("pdf_total", 0), "发现的 PDF 数量")
                self._set_result_metric("extract.extracted", "提取", "已提取", extract_summary.get("extracted", 0), "成功提取文本")
                self._set_result_metric("extract.exists", "提取", "已存在", extract_summary.get("exists", 0), "已存在文本")
                self._set_result_metric("extract.failed", "提取", "失败", extract_summary.get("failed", 0), "提取失败数量")
            else:
                self._set_result_metric("extract.status", "提取", "状态", "未生成汇总", "管线提取汇总缺失")
            self._set_result_metric("pipeline.pdf_output", "产物", "PDF 目录", spider_output_dir, "抓取产物目录")
            self._set_result_metric("pipeline.txt_output", "产物", "TXT 目录", extract_output_dir, "提取产物目录")
            self._refresh_result_sheet()
            return

        self._refresh_result_sheet()

    def _update_runtime_summary(self) -> None:
        total_elapsed = 0.0
        if self.running_since is not None:
            total_elapsed = max(time.time() - self.running_since, 0.0)
        else:
            total_elapsed = sum(self.stage_elapsed_seconds.values())

        if self.current_stage_key is not None:
            stage_label = STAGE_LABELS.get(self.current_stage_key, self.current_stage_key)
            stage_elapsed_text = self._format_elapsed(self.stage_elapsed_seconds.get(self.current_stage_key, 0.0))
        else:
            stage_label = "-"
            stage_elapsed_text = "-"

        self.runtime_summary_var.set(
            f"运行摘要：总耗时 {self._format_elapsed(total_elapsed)} | 当前阶段 {stage_label} {stage_elapsed_text} | 日志 {self.log_line_count} 行"
        )

        self._sync_result_overview()

    def _apply_stage_card_visuals(self, stage_key: str) -> None:
        frame = self.stage_card_frames.get(stage_key)
        if frame is None:
            return

        status = self.stage_status_vars[stage_key].get()
        palette = STAGE_VISUALS.get(status, STAGE_VISUALS["未开始"])
        border_width = 2 if status in {"进行中", "已完成", "失败"} else 1
        frame.configure(
            bg=palette["bg"],
            highlightbackground=palette["border"],
            highlightcolor=palette["border"],
            highlightthickness=border_width,
        )

        accent_bar = self.stage_card_accent_frames.get(stage_key)
        if accent_bar is not None:
            accent_bar.configure(bg=palette["accent"])

        icon_label = self.stage_card_icon_labels.get(stage_key)
        if icon_label is not None:
            icon_label.master.configure(bg=palette["bg"])
            icon_label.configure(bg=palette["badge_bg"], fg=palette["badge_fg"])

        title_label = self.stage_card_title_labels.get(stage_key)
        status_label = self.stage_card_status_labels.get(stage_key)
        progress_label = self.stage_card_progress_labels.get(stage_key)
        detail_label = self.stage_card_detail_labels.get(stage_key)

        for label in (title_label, progress_label, detail_label):
            if label is not None:
                label.configure(bg=palette["bg"], fg=palette["text"])

        if title_label is not None:
            title_label.master.configure(bg=palette["bg"])
            title_label.configure(fg=palette["title"])
        if status_label is not None:
            status_label.configure(
                text=f"{palette['icon']} {status}",
                bg=palette["badge_bg"],
                fg=palette["badge_fg"],
            )

    def _reset_stage_cards(self, task_key: str | None) -> None:
        active_stages = set(self._stage_keys_for_task(task_key))
        self.current_stage_key = None
        for stage_key in STAGE_SEQUENCE:
            self.stage_started_at[stage_key] = None
            self.stage_elapsed_seconds[stage_key] = 0.0
            detail = "等待任务开始" if stage_key in active_stages else "当前任务未包含此阶段"
            self._set_stage_card(stage_key, status="未开始", detail=detail, progress="-")
        self._update_runtime_summary()

    def _handle_status_event(self, payload: Any) -> None:
        if isinstance(payload, dict):
            message = str(payload.get("message", ""))
            step = int(payload.get("step", self.completed_steps))
            total = int(payload.get("total", self.total_steps or 1))
            title = str(payload.get("title", "-"))
            action = str(payload.get("action", "") or "")
            stage_key = self._resolve_stage_key(action=action, title=title)
            self.total_steps = max(total, 1)
            self.progress_text_var.set(f"步骤进度：{max(step - 1, self.completed_steps)}/{self.total_steps}，正在执行第 {step} 步")
            if stage_key is not None:
                self.current_stage_key = stage_key
                self._ensure_stage_started(stage_key)
                self.stage_var.set(f"当前阶段：{STAGE_LABELS[stage_key]}（步骤 {step}/{self.total_steps}）")
                self._set_stage_card(
                    stage_key,
                    status="准备中",
                    detail=message,
                    progress=self._stage_progress_with_elapsed(stage_key, f"步骤 {step}/{self.total_steps}"),
                )
            else:
                self.stage_var.set(f"当前阶段：{title}（步骤 {step}/{self.total_steps}）")
            self.detail_var.set(message)
            self.append_log(f"[STATUS] {message}")
            return

        self.detail_var.set(str(payload))
        self.append_log(f"[STATUS] {payload}")

    def _handle_command_done(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self.completed_steps = int(payload.get("step", self.completed_steps))
            self.total_steps = max(int(payload.get("total", self.total_steps or 1)), 1)
            title = str(payload.get("title", "-"))
            action = str(payload.get("action", "") or "")
            stage_key = self._resolve_stage_key(action=action, title=title)
            self.progress_text_var.set(f"步骤进度：{self.completed_steps}/{self.total_steps}")
            if stage_key is not None:
                self.current_stage_key = stage_key
                detail = self.stage_detail_vars[stage_key].get()
                if detail in {"等待任务开始", "当前任务未包含此阶段", "等待执行"}:
                    detail = f"{STAGE_LABELS[stage_key]}已完成"
                self._finalize_stage_elapsed(stage_key)
                progress = self._stage_progress_with_elapsed(stage_key, f"步骤 {self.completed_steps}/{self.total_steps}")
                self._set_stage_card(stage_key, status="已完成", detail=detail, progress=progress)
                self.stage_var.set(f"当前阶段：{STAGE_LABELS[stage_key]}已完成")
            else:
                self.stage_var.set(f"当前阶段：{title} 已完成，等待下一步")
            self._refresh_result_summary()

    def _handle_extract_progress(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        phase = str(payload.get("phase", "extract"))
        completed = int(payload.get("completed", 0))
        total = int(payload.get("total", 0))
        extracted = int(payload.get("extracted", 0))
        existing = int(payload.get("existing", 0))
        failed = int(payload.get("failed", 0))

        if phase == "prepare":
            self.detail_var.set(f"文本提取准备完成：待处理 {total} 份，已存在 {existing} 份。")
            self.results_var.set(f"结果统计：提取={extracted}，已存在={existing}，失败={failed}")
            self._set_result_metric("extract.status", "提取", "状态", "准备中", "扫描待处理 PDF")
            self._set_result_metric("extract.total", "提取", "待处理", total, "待提取 PDF 数量")
            self._set_result_metric("extract.exists", "提取", "已存在", existing, "已生成文本")
            self._refresh_result_sheet()
            self.current_stage_key = "extract"
            self._ensure_stage_started("extract")
            self.stage_var.set("当前阶段：提取状态准备中")
            self._set_stage_card(
                "extract",
                status="准备中",
                detail=f"待处理 {total} 份，已存在 {existing} 份",
                progress=self._stage_progress_with_elapsed("extract", f"待处理 {total}"),
            )
            return

        if phase == "extract":
            current_pdf = payload.get("current_pdf")
            self.detail_var.set(f"文本提取进行中：{completed}/{total}")
            self.stage_var.set(f"当前阶段：文本提取（{completed}/{total}）")
            self.results_var.set(f"结果统计：提取={extracted}，已存在={existing}，失败={failed}")
            self._set_result_metric("extract.status", "提取", "状态", "运行中", "正在提取文本")
            self._set_result_metric("extract.progress", "提取", "进度", f"{completed}/{total}", "当前批次进度")
            self._set_result_metric("extract.extracted", "提取", "已提取", extracted, "成功提取文本")
            self._set_result_metric("extract.failed", "提取", "失败", failed, "提取失败数量")
            if current_pdf:
                self._set_result_metric("extract.current", "提取", "当前文件", current_pdf, "正在处理的 PDF")
            self._refresh_result_sheet()
            self.current_stage_key = "extract"
            self._ensure_stage_started("extract")
            self._set_stage_card(
                "extract",
                status="进行中",
                detail=f"提取={extracted}，已存在={existing}，失败={failed}",
                progress=self._stage_progress_with_elapsed("extract", f"{completed}/{total}"),
            )
            if current_pdf:
                self.artifact_var.set(f"当前文件：{current_pdf}")
            return

        if phase == "done":
            self.results_var.set(f"结果统计：提取={extracted}，已存在={existing}，失败={failed}")
            self._set_result_metric("extract.status", "提取", "状态", "已完成", "文本提取阶段完成")
            self._set_result_metric("extract.progress", "提取", "进度", f"{completed}/{total}" if total else "已完成", "最终进度")
            self._set_result_metric("extract.extracted", "提取", "已提取", extracted, "成功提取文本")
            self._set_result_metric("extract.failed", "提取", "失败", failed, "提取失败数量")
            self._refresh_result_sheet()
            self.current_stage_key = "extract"
            self._finalize_stage_elapsed("extract")
            self._set_stage_card(
                "extract",
                status="已完成",
                detail=f"提取={extracted}，已存在={existing}，失败={failed}",
                progress=self._stage_progress_with_elapsed("extract", f"{completed}/{total}" if total else "已完成"),
            )
            summary_path = payload.get("summary_path")
            checkpoint_path = payload.get("checkpoint_path")
            if summary_path and checkpoint_path:
                self.artifact_var.set(f"产物位置：汇总文件={summary_path} | checkpoint={checkpoint_path}")

    def _handle_service_result(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        stage_key = self._resolve_stage_key(
            action=str(payload.get("action", "") or ""),
            title=str(payload.get("title", "") or ""),
        )
        if stage_key == "spider":
            summary_count = int(payload.get("summary_count", 0))
            raw_total = int(payload.get("raw_total", 0))
            filtered_total = int(payload.get("filtered_total", 0))
            failed_total = int(payload.get("failed_total", 0))
            elapsed_seconds = float(payload.get("elapsed_seconds", 0))
            self._set_result_metric("spider.status", "抓取", "状态", "已完成", "抓取阶段完成")
            self._set_result_metric("spider.years", "抓取", "年份", summary_count, "汇总年份数")
            self._set_result_metric("spider.raw", "抓取", "原始公告", raw_total, "抓取到的公告数")
            self._set_result_metric("spider.filtered", "抓取", "保留公告", filtered_total, "筛选后保留")
            self._set_result_metric("spider.failed", "抓取", "失败", failed_total, "抓取失败数量")
            self._refresh_result_sheet()
            self.current_stage_key = "spider"
            self._finalize_stage_elapsed("spider", elapsed_seconds)
            self._set_stage_card(
                "spider",
                status="已完成",
                detail=f"年份={summary_count}，保留={filtered_total}，失败={failed_total}",
                progress=self._stage_progress_with_elapsed("spider", f"{summary_count} 年"),
            )
            if self.current_task_key == "pipeline":
                self._refresh_result_summary()
            else:
                self.results_var.set(
                    f"结果统计：年份={summary_count}，原始公告={raw_total}，保留={filtered_total}，失败={failed_total}"
                )
                self.artifact_var.set(
                    f"产物位置：输出={payload.get('output_dir')} | 汇总={payload.get('summary_path') or '未生成'} | 用时={elapsed_seconds:.2f}s"
                )
            return

        extracted = int(payload.get("extracted", 0))
        existing = int(payload.get("exists", 0))
        failed = int(payload.get("failed", 0))
        pdf_total = int(payload.get("pdf_total", 0))
        self._set_result_metric("extract.status", "提取", "状态", "已完成", "文本提取阶段完成")
        self._set_result_metric("extract.pdf_total", "提取", "PDF 总数", pdf_total, "发现的 PDF 数量")
        self._set_result_metric("extract.extracted", "提取", "已提取", extracted, "成功提取文本")
        self._set_result_metric("extract.exists", "提取", "已存在", existing, "已存在文本")
        self._set_result_metric("extract.failed", "提取", "失败", failed, "提取失败数量")
        self._refresh_result_sheet()
        self.current_stage_key = "extract"
        self._finalize_stage_elapsed("extract")
        self._set_stage_card(
            "extract",
            status="已完成",
            detail=f"提取={extracted}，已存在={existing}，失败={failed}",
            progress=self._stage_progress_with_elapsed("extract", f"PDF {pdf_total}"),
        )
        if self.current_task_key == "pipeline":
            self._refresh_result_summary()
        else:
            self.results_var.set(f"结果统计：PDF={pdf_total}，提取={extracted}，已存在={existing}，失败={failed}")
        summary_path = payload.get("summary_path")
        checkpoint_path = payload.get("checkpoint_path")
        if self.current_task_key != "pipeline" and summary_path and checkpoint_path:
            self.artifact_var.set(f"产物位置：汇总文件={summary_path} | checkpoint={checkpoint_path}")

    def _handle_spider_progress(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        phase = str(payload.get("phase", "log"))
        if phase == "log":
            message = str(payload.get("message", ""))
            self.detail_var.set(message)
            self._set_result_metric("spider.status", "抓取", "状态", "运行中", "抓取进行中")
            self._set_result_metric("spider.message", "抓取", "最新消息", message, "最近一条抓取状态")
            self._refresh_result_sheet()
            self.current_stage_key = "spider"
            self._ensure_stage_started("spider")
            self.stage_var.set("当前阶段：抓取状态进行中")
            self._set_stage_card(
                "spider",
                status="进行中",
                detail=message,
                progress=self._stage_progress_with_elapsed("spider", "运行中"),
            )
        elif phase == "done":
            summary_path = payload.get("summary_path")
            elapsed_seconds = float(payload.get("elapsed_seconds", 0))
            self._set_result_metric("spider.status", "抓取", "状态", "已完成", "抓取阶段完成")
            self._set_result_metric("spider.summary_path", "抓取", "汇总文件", summary_path or "未生成", "抓取汇总输出")
            self._refresh_result_sheet()
            self.current_stage_key = "spider"
            self._finalize_stage_elapsed("spider", elapsed_seconds)
            self.stage_var.set("当前阶段：年报抓取已完成")
            self._set_stage_card(
                "spider",
                status="已完成",
                detail=f"汇总文件：{summary_path or '未生成'}",
                progress=self._stage_progress_with_elapsed("spider", "已完成"),
            )
            self.artifact_var.set(
                f"产物位置：汇总文件={summary_path or '未生成'} | 用时={elapsed_seconds:.2f}s"
            )

    def _refresh_result_summary(self) -> None:
        task_key = self.current_task_key
        values = self.current_task_values or {}
        self._sync_result_table_from_outputs(task_key, values)

        self.final_report_var.set(
            "最终汇总\n\n仅在“一键抓取+提取”任务中展示。\n完成后这里会自动汇总抓取和提取两段结果。"
        )

        if task_key == "spider":
            output_dir = resolve_path(str(values.get("output_dir", "annual_reports")))
            summary_path = output_dir / SPIDER_SUMMARY_NAME
            checkpoint_path = resolve_path(str(values.get("state_dir", "."))) / SPIDER_CHECKPOINT_NAME
            summary = load_json_file(summary_path)
            self._remove_result_metrics("spider.")
            if isinstance(summary, list):
                total_filtered = sum(int(item.get("filtered_total", 0)) for item in summary if isinstance(item, dict))
                total_downloaded = sum(int(item.get("downloaded", 0)) for item in summary if isinstance(item, dict))
                total_failed = sum(int(item.get("failed", 0)) for item in summary if isinstance(item, dict))
                self.results_var.set(
                    f"结果统计：年份={len(summary)}，保留公告={total_filtered}，下载={total_downloaded}，失败={total_failed}"
                )
            else:
                self.results_var.set("结果统计：尚未发现抓取汇总")
            self.artifact_var.set(f"产物位置：输出目录={output_dir} | checkpoint={checkpoint_path}")
            return

        if task_key == "extract":
            output_dir = resolve_path(str(values.get("output_dir", "txt_extract")))
            summary_path = output_dir / EXTRACT_SUMMARY_NAME
            checkpoint_path = resolve_path(str(values.get("state_dir", "."))) / EXTRACT_CHECKPOINT_NAME
            summary = load_json_file(summary_path)
            if isinstance(summary, dict):
                self.results_var.set(
                    "结果统计："
                    f"PDF={summary.get('pdf_total', 0)}，提取={summary.get('extracted', 0)}，"
                    f"已存在={summary.get('exists', 0)}，失败={summary.get('failed', 0)}"
                )
            else:
                self.results_var.set("结果统计：尚未发现文本提取汇总")
            self.artifact_var.set(f"产物位置：输出目录={output_dir} | checkpoint={checkpoint_path}")
            return

        if task_key == "pipeline":
            spider_output_dir = resolve_path(str(values.get("pdf_output_dir", "annual_reports")))
            extract_output_dir = resolve_path(str(values.get("extract_output_dir", "txt_extract")))
            spider_summary = load_json_file(spider_output_dir / SPIDER_SUMMARY_NAME)
            extract_summary = load_json_file(extract_output_dir / EXTRACT_SUMMARY_NAME)

            spider_text = "抓取汇总未生成"
            spider_report = "抓取阶段：汇总未生成"
            if isinstance(spider_summary, list):
                spider_total_filtered = sum(
                    int(item.get("filtered_total", 0)) for item in spider_summary if isinstance(item, dict)
                )
                spider_total_downloaded = sum(
                    int(item.get("downloaded", 0)) for item in spider_summary if isinstance(item, dict)
                )
                spider_total_failed = sum(
                    int(item.get("failed", 0)) for item in spider_summary if isinstance(item, dict)
                )
                spider_text = f"抓取年份={len(spider_summary)}"
                spider_report = (
                    f"抓取阶段：年份={len(spider_summary)}，保留公告={spider_total_filtered}，"
                    f"下载={spider_total_downloaded}，失败={spider_total_failed}"
                )

            extract_text = "文本汇总未生成"
            extract_report = "提取阶段：汇总未生成"
            if isinstance(extract_summary, dict):
                extract_total = int(extract_summary.get("pdf_total", 0))
                extract_done = int(extract_summary.get("extracted", 0))
                extract_exists = int(extract_summary.get("exists", 0))
                extract_failed = int(extract_summary.get("failed", 0))
                extract_text = f"文本提取={extract_done}"
                extract_report = (
                    f"提取阶段：PDF={extract_total}，提取={extract_done}，"
                    f"已存在={extract_exists}，失败={extract_failed}"
                )

            self.results_var.set(f"结果统计：{spider_text}，{extract_text}")
            self.artifact_var.set(
                f"产物位置：PDF目录={spider_output_dir} | TXT目录={extract_output_dir}"
            )
            self.final_report_var.set(
                "最终汇总\n\n"
                "抓取阶段\n"
                f"{spider_report}\n\n"
                "提取阶段\n"
                f"{extract_report}\n\n"
                "产物位置\n"
                f"PDF目录={spider_output_dir}\nTXT目录={extract_output_dir}"
            )
            return

        self.results_var.set("结果统计：-")
        self.artifact_var.set("产物位置：-")

    def _poll_events(self) -> None:
        processed = 0
        started_at = time.perf_counter()
        pending_logs: list[str] = []

        def flush_logs() -> None:
            if pending_logs:
                self._append_log_lines(pending_logs)
                pending_logs.clear()

        try:
            while processed < MAX_EVENTS_PER_POLL and (time.perf_counter() - started_at) < MAX_POLL_SECONDS:
                event_type, payload = self.event_queue.get_nowait()
                processed += 1
                if event_type == "log":
                    pending_logs.append(str(payload))
                elif event_type == "status":
                    flush_logs()
                    self._handle_status_event(payload)
                elif event_type == "command_done":
                    flush_logs()
                    self._handle_command_done(payload)
                elif event_type == "extract_progress":
                    flush_logs()
                    self._handle_extract_progress(payload)
                elif event_type == "spider_progress":
                    flush_logs()
                    self._handle_spider_progress(payload)
                elif event_type == "service_result":
                    flush_logs()
                    self._handle_service_result(payload)
                elif event_type == "done":
                    flush_logs()
                    self._finish_run("完成", str(payload), is_error=False)
                elif event_type == "stopped":
                    flush_logs()
                    self._finish_run("已停止", str(payload), is_error=False)
                elif event_type == "error":
                    flush_logs()
                    self._finish_run("失败", str(payload), is_error=True)
        except queue.Empty:
            pass
        finally:
            if pending_logs:
                self._append_log_lines(pending_logs)
            next_delay = 25 if not self.event_queue.empty() else 80
            self.root.after(next_delay, self._poll_events)

    def _finish_run(self, status: str, detail: str, is_error: bool) -> None:
        self.progress.stop()
        self.is_starting_task = False
        self._set_all_tabs_running(False)
        self.status_var.set(status)
        self.detail_var.set(detail)
        self.append_log(f"[{status}] {detail}")
        if status == "完成":
            self.completed_steps = self.total_steps
            if self.current_stage_key is not None and self.stage_status_vars[self.current_stage_key].get() != "已完成":
                self._finalize_stage_elapsed(self.current_stage_key)
                self._set_stage_card(self.current_stage_key, status="已完成", detail=detail)
        elif self.current_stage_key is not None and self.stage_status_vars[self.current_stage_key].get() != "已完成":
            self._finalize_stage_elapsed(self.current_stage_key)
            self._set_stage_card(
                self.current_stage_key,
                status="失败" if is_error else "已停止",
                detail=detail,
                progress=self._stage_progress_with_elapsed(self.current_stage_key, self.stage_progress_vars[self.current_stage_key].get()),
            )
        self.progress_text_var.set(f"步骤进度：{self.completed_steps}/{self.total_steps}")
        self.stage_var.set(f"当前阶段：{status}")
        self._refresh_result_summary()
        self._update_runtime_summary()
        self.current_stage_key = None
        self.worker = None
        self.running_tab = None
        self.running_since = None
        self._update_runtime_summary()
        if is_error:
            messagebox.showerror("任务失败", detail, parent=self.root)
        if self.exit_after_stop:
            self.save_config(show_feedback=False)
            self.root.destroy()

    def _refresh_runtime(self) -> None:
        if self.running_since is not None and self.running_tab is not None:
            elapsed = int(time.time() - self.running_since)
            current_step = min(self.completed_steps + 1, self.total_steps) if self.total_steps else 0
            self.status_var.set(f"运行中：{self.running_tab.title}（{elapsed}s，步骤 {current_step}/{self.total_steps}）")
            for stage_key in STAGE_SEQUENCE:
                status = self.stage_status_vars[stage_key].get()
                if status in {"准备中", "进行中"} and self.stage_started_at.get(stage_key) is not None:
                    current_progress = self.stage_progress_vars[stage_key].get()
                    base_progress = current_progress.split(" | 耗时 ", 1)[0]
                    self._set_stage_card(
                        stage_key,
                        progress=self._stage_progress_with_elapsed(stage_key, base_progress),
                    )
        self._update_runtime_summary()
        self.root.after(1000, self._refresh_runtime)

    def append_log(self, text: str) -> None:
        self._append_log_lines([text])

    def _append_log_lines(self, lines: list[str]) -> None:
        if not lines:
            return

        self.log_line_count += len(lines)
        self.log_count_var.set(f"日志行数：{self.log_line_count}")
        for text in lines:
            timestamp = time.strftime("%H:%M:%S")
            line_tag = self._resolve_log_tag(text)
            self.log_text.insert("end", f"[{timestamp}] ", ("timestamp",))
            self.log_text.insert("end", f"{text}\n", (line_tag,))
        self.log_text.see("end")

        self._sync_result_overview()

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")
        self.log_line_count = 0
        self.log_count_var.set("日志行数：0")
        self._update_runtime_summary()

        self._sync_result_overview()

    def save_config(self, show_feedback: bool = True) -> None:
        data = {
            "last_tab": self.notebook.index(self.notebook.select()),
            "tabs": {key: tab.collect_values() for key, tab in self.tabs.items()},
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            if show_feedback:
                messagebox.showerror("保存失败", f"写入配置文件失败：{exc}", parent=self.root)
            return

        if show_feedback:
            self.detail_var.set(f"配置已保存到 {CONFIG_PATH.name}")

    def load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        tabs_data = data.get("tabs", {})
        for key, values in tabs_data.items():
            tab = self.tabs.get(key)
            if tab is not None and isinstance(values, dict):
                tab.load_values(values)

        last_tab = data.get("last_tab")
        tab_count = self.notebook.index("end")
        if isinstance(last_tab, int) and 0 <= last_tab < tab_count:
            self.notebook.select(last_tab)

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            confirmed = messagebox.askyesno(
                "确认退出",
                "当前仍有任务在运行，是否先发送停止信号并退出？",
                parent=self.root,
            )
            if not confirmed:
                return
            self.exit_after_stop = True
            self.stop_running_task()
            return

        self.save_config(show_feedback=False)
        self.root.destroy()


def build_spider_commands(values: dict[str, Any]) -> list[CommandSpec]:
    return wrap_with_checkpoint_actions(
        [
            CommandSpec(
                "年报抓取",
                action="spider_service",
                payload={
                    "start_year": values["start_year"],
                    "end_year": values["end_year"],
                    "se_date": values.get("se_date"),
                    "page_size": values["page_size"],
                    "request_interval": values["request_interval"],
                    "announcement_concurrency": values["announcement_concurrency"],
                    "download_concurrency": values["download_concurrency"],
                    "output_dir": str(values["output_dir"]),
                    "state_dir": str(values["state_dir"]),
                    "download_pdf": values["download_pdf"],
                    "metadata_only": values["metadata_only"],
                    "audit_pdf": values["audit_pdf"],
                    "cleanup_orphan_pdf": values["cleanup_orphan_pdf"],
                },
            )
        ],
        checkpoint_path=resolve_path(str(values["state_dir"])) / SPIDER_CHECKPOINT_NAME,
        reset_checkpoint=bool(values.get("reset_checkpoint")),
        delete_checkpoint_on_success=bool(values.get("delete_checkpoint_on_success")),
    )


def build_extract_commands(values: dict[str, Any]) -> list[CommandSpec]:
    return wrap_with_checkpoint_actions(
        [
            CommandSpec(
                "文本提取",
                action="extract_service",
                payload={
                    "input_dir": str(values["input_dir"]),
                    "output_dir": str(values["output_dir"]),
                    "state_dir": str(values["state_dir"]),
                    "start_year": values.get("start_year"),
                    "end_year": values.get("end_year"),
                    "concurrency": values["concurrency"],
                },
            )
        ],
        checkpoint_path=resolve_path(str(values["state_dir"])) / EXTRACT_CHECKPOINT_NAME,
        reset_checkpoint=bool(values.get("reset_checkpoint")),
        delete_checkpoint_on_success=bool(values.get("delete_checkpoint_on_success")),
    )


def build_pipeline_commands(values: dict[str, Any]) -> list[CommandSpec]:
    spider_values = {
        "start_year": values["start_year"],
        "end_year": values["end_year"],
        "se_date": values.get("se_date"),
        "page_size": 30,
        "request_interval": values["request_interval"],
        "announcement_concurrency": values["announcement_concurrency"],
        "download_concurrency": values["download_concurrency"],
        "output_dir": values["pdf_output_dir"],
        "state_dir": values["state_dir"],
        "download_pdf": True,
        "metadata_only": False,
        "audit_pdf": False,
        "cleanup_orphan_pdf": False,
        "reset_checkpoint": values["reset_checkpoint"],
        "delete_checkpoint_on_success": values["delete_checkpoint_on_success"],
    }
    extract_values = {
        "input_dir": values["pdf_output_dir"],
        "output_dir": values["extract_output_dir"],
        "state_dir": values["state_dir"],
        "start_year": values["start_year"],
        "end_year": values["end_year"],
        "concurrency": values["extract_concurrency"],
        "reset_checkpoint": values["reset_checkpoint"],
        "delete_checkpoint_on_success": values["delete_checkpoint_on_success"],
    }

    commands: list[CommandSpec] = []
    commands.extend(build_spider_commands(spider_values))
    commands.extend(build_extract_commands(extract_values))
    return commands


def main() -> None:
    multiprocessing.freeze_support()
    root = ttk.Window(themename="litera")
    app = DesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
