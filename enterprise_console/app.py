from __future__ import annotations

import json
import tkinter as tk
import time
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from .backend import (
    ConsoleSettings,
    ExecutionWorker,
    build_about_payload,
    default_settings,
    load_settings,
    resolve_path,
    save_settings,
)
from .theme import (
    ACCENT_PANEL,
    ACCENT_PANEL_BORDER,
    APP_BG,
    BORDER,
    DANGER,
    DANGER_SOFT,
    FONT_FAMILY,
    FONT_MONO,
    INFO,
    INFO_SOFT,
    PRIMARY,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
    SCREEN_BG,
    SCREEN_BLUE,
    SCREEN_CYAN,
    SCREEN_GLOW,
    SCREEN_GREEN,
    SCREEN_GRID,
    SCREEN_MUTED,
    SCREEN_PANEL,
    SCREEN_PANEL_ALT,
    SCREEN_RED,
    SCREEN_TEXT,
    SEGMENT_BG,
    SEGMENT_IDLE,
    SEGMENT_IDLE_HOVER,
    SEGMENT_TEXT,
    SUCCESS,
    SUCCESS_SOFT,
    SURFACE,
    SURFACE_ALT,
    SURFACE_SOFT,
    TEXT,
    HINT_TEXT,
    TEXT_MUTED,
    WARNING,
    WARNING_SOFT,
    configure_theme,
)


class EnterpriseConsoleApp(ctk.CTk):
    def __init__(self) -> None:
        configure_theme()
        super().__init__()
        self.settings = load_settings()
        self.event_queue: Queue[dict[str, Any]] = Queue()
        self.worker: ExecutionWorker | None = None
        self._run_start_pending = False
        self._command_refresh_pending = False
        self._last_link_ui_update = 0.0
        self._last_pdf_ui_update = 0.0
        self._last_extract_ui_update = 0.0
        self._displayed_progress = 0.0
        self._progress_target = 0.0
        self._progress_animation_pending = False
        self.current_page = "command"
        self.current_mode = "pipeline"
        self.stage_state: dict[str, dict[str, Any]] = {
            "spider": {"status": "待命", "progress": 0.0},
            "extract": {"status": "待命", "progress": 0.0},
        }
        self.stage_state = {
            "links": {"status": "待命", "progress": 0.0},
            "pdf": {"status": "待命", "progress": 0.0},
            "extract": {"status": "待命", "progress": 0.0},
        }
        self.stage_state["spider"] = self.stage_state["links"]
        self.kpi_values: dict[str, str] = {
            "run_mode": "全流程",
            "pdf_total": "0",
            "extracted": "0",
            "failed": "0",
            "elapsed": "0s",
        }
        self.recent_events: list[str] = []
        self.alert_state: dict[str, str] = {
            "level": "idle",
            "title": "系统提醒",
            "body": "暂无异常，准备执行。",
        }
        self.spider_mode = "download"
        self.spider_field_widgets: dict[str, Any] = {}
        self.spider_check_widgets: dict[str, Any] = {}
        self.spider_preview_rows: list[dict[str, Any]] = []
        self.extract_summary: dict[str, Any] = {}
        self.progress_history: dict[str, list[float]] = {"overall": [], "spider": [], "extract": []}
        self.progress_history = {"overall": [], "links": [], "pdf": [], "extract": []}
        self.progress_history["spider"] = list(self.progress_history["links"])
        self._last_chart_record_at = 0.0
        self.about_payload = build_about_payload()

        self.title("Annual Report Spider Enterprise Console")
        self.geometry("1580x980")
        self.minsize(1440, 900)
        self.configure(fg_color=APP_BG)

        self._configure_grid()
        self._build_header()
        self._build_left_nav()
        self._build_content_area()
        self._load_initial_form_values()
        self.start_pipeline_btn.configure(text="一键三步全流程")
        self.start_spider_btn.configure(text="公告链接抓取")
        self.start_pdf_btn.configure(text="PDF 文件爬取")
        self.start_extract_btn.configure(text="文本提取")
        self.show_page("command")
        self.after(120, self._drain_event_queue)

    def _configure_grid(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=248)
        self.grid_columnconfigure(1, weight=1, minsize=1040)
        self.grid_rowconfigure(0, weight=0, minsize=84)
        self.grid_rowconfigure(1, weight=1, minsize=760)

    def _panel(self, master: Any, *, fg_color: str = SURFACE, height: int | None = None) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            master,
            fg_color=fg_color,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        if height is not None:
            frame.configure(height=height)
            frame.grid_propagate(False)
        return frame

    def _build_header(self) -> None:
        header = self._panel(self, fg_color=SURFACE, height=72)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 10))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title_wrap = ctk.CTkFrame(header, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        ctk.CTkLabel(
            title_wrap,
            text="年报采取器",
            font=(FONT_FAMILY, 28, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")

        self.run_badge = ctk.CTkLabel(
            header,
            text="系统空闲",
            width=120,
            height=34,
            corner_radius=17,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=(FONT_FAMILY, 12, "bold"),
        )
        self.run_badge.grid(row=0, column=1, sticky="e", padx=20)

    def _build_left_nav(self) -> None:
        nav = ctk.CTkScrollableFrame(
            self,
            fg_color=SURFACE,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
            scrollbar_button_color=SURFACE_ALT,
            scrollbar_button_hover_color=PRIMARY_SOFT,
        )
        nav.grid(row=1, column=0, sticky="nsew", padx=(18, 10), pady=(0, 18))
        nav.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(nav, fg_color=PRIMARY, corner_radius=18, height=150)
        brand.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        brand.grid_propagate(False)
        ctk.CTkLabel(
            brand,
            text="ARS",
            font=(FONT_FAMILY, 22, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(10, 0))
        ctk.CTkLabel(
            brand,
            text="Annual Report Spider",
            font=(FONT_FAMILY, 12, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(4, 0))
        ctk.CTkLabel(
            brand,
            text="企业版控制台",
            font=(FONT_FAMILY, 10),
            text_color="#DCE7FF",
        ).pack(anchor="w", padx=16, pady=(4, 10))

        actions = self._panel(nav, fg_color=SURFACE_ALT)
        actions.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            actions,
            text="执行控制",
            font=(FONT_FAMILY, 14, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8))

        self.start_pipeline_btn = ctk.CTkButton(
            actions,
            text="开始全流程",
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            height=36,
            corner_radius=12,
            font=(FONT_FAMILY, 13, "bold"),
            command=lambda: self.start_run("pipeline"),
        )
        self.start_pipeline_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        self.start_spider_btn = ctk.CTkButton(
            actions,
            text="仅抓取",
            fg_color=SURFACE,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            hover_color=SURFACE_SOFT,
            height=34,
            corner_radius=12,
            font=(FONT_FAMILY, 12, "bold"),
            command=lambda: self.start_run("links"),
        )
        self.start_spider_btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        self.start_pdf_btn = ctk.CTkButton(
            actions,
            text="PDF 文件爬取",
            fg_color=SURFACE,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            hover_color=SURFACE_SOFT,
            height=34,
            corner_radius=12,
            font=(FONT_FAMILY, 12, "bold"),
            command=lambda: self.start_run("pdf"),
        )
        self.start_pdf_btn.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        self.start_extract_btn = ctk.CTkButton(
            actions,
            text="仅提取",
            fg_color=SURFACE,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            hover_color=SURFACE_SOFT,
            height=34,
            corner_radius=12,
            font=(FONT_FAMILY, 12, "bold"),
            command=lambda: self.start_run("extract"),
        )
        self.start_extract_btn.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        self.stop_btn = ctk.CTkButton(
            actions,
            text="停止任务",
            fg_color=DANGER,
            hover_color="#991B1B",
            height=34,
            corner_radius=12,
            font=(FONT_FAMILY, 12, "bold"),
            state="disabled",
            command=self.stop_run,
        )
        self.stop_btn.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        actions.grid_columnconfigure((0, 1), weight=1)

        nav_group = self._panel(nav, fg_color=SURFACE_ALT, height=470)
        nav_group.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        nav_group.grid_propagate(False)
        ctk.CTkLabel(
            nav_group,
            text="导航",
            font=(FONT_FAMILY, 14, "bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=16, pady=(12, 8))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("command", "指挥台"),
            ("logs", "日志中心"),
            ("workspace", "工作区"),
            ("spider", "抓取配置"),
            ("extract", "提取配置"),
            ("about", "关于"),
        ]
        nav_items = [
            ("command", "指挥台"),
            ("logs", "日志中心"),
            ("workspace", "工作区"),
            ("links_config", "公告链接抓取"),
            ("pdf_config", "PDF 文件抓取"),
            ("extract", "提取配置"),
            ("about", "关于"),
        ]
        for page_key, label in nav_items:
            btn = ctk.CTkButton(
                nav_group,
                text=label,
                height=34,
                corner_radius=12,
                anchor="w",
                fg_color="transparent",
                hover_color=SURFACE_SOFT,
                text_color=TEXT,
                font=(FONT_FAMILY, 13, "bold"),
                command=lambda key=page_key: self.show_page(key),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[page_key] = btn

    def _build_content_area(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=1, column=1, sticky="nsew", padx=(0, 18), pady=(0, 18))
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        self.page_wrap = wrap
        self.pages: dict[str, ctk.CTkFrame] = {}

        self.pages["command"] = self._build_command_page()
        self.pages["logs"] = self._build_logs_page()
        self.pages["workspace"] = self._build_workspace_page()
        self.pages["links_config"] = self._build_links_config_page()
        self.pages["pdf_config"] = self._build_pdf_config_page()
        self.pages["extract"] = self._build_extract_page()
        self.pages["about"] = self._build_about_page()

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

    def _build_command_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2)
        self.kpi_cards = {}
        self.monitor_metrics = {}

        hero = self._panel(page, fg_color=SURFACE, height=148)
        hero.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 12))
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hero,
            text="企业级执行指挥台",
            font=(FONT_FAMILY, 24, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 6))
        self.command_hint = ctk.CTkLabel(
            hero,
            text="当前待执行：全流程",
            font=(FONT_FAMILY, 15, "bold"),
            text_color=PRIMARY,
        )
        self.command_hint.grid(row=1, column=0, sticky="w", padx=20, pady=(10, 18))

        monitor_card = self._panel(page, fg_color=SURFACE, height=148)
        monitor_card.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 12))
        monitor_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            monitor_card,
            text="运行总览",
            font=(FONT_FAMILY, 18, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))
        self.overall_progress = ctk.CTkProgressBar(
            monitor_card,
            height=14,
            corner_radius=7,
            progress_color=PRIMARY,
        )
        self.overall_progress.grid(row=1, column=0, sticky="ew", padx=18)
        self.overall_progress.set(0)
        self.overall_status = ctk.CTkLabel(
            monitor_card,
            text="等待执行",
            font=(FONT_FAMILY, 13),
            text_color=TEXT_MUTED,
        )
        self.overall_status.grid(row=2, column=0, sticky="w", padx=18, pady=(10, 2))
        self.monitor_metrics["elapsed"] = ctk.CTkLabel(
            monitor_card,
            text="0s",
            font=(FONT_FAMILY, 13, "bold"),
            text_color=TEXT,
        )
        self.monitor_metrics["elapsed"].grid(row=3, column=0, sticky="w", padx=18, pady=(10, 14))

        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        cards.grid_columnconfigure((0, 1, 2, 3), weight=1)
        card_specs = [
            ("run_mode", "执行模式"),
            ("pdf_total", "PDF 总量"),
            ("extracted", "提取成功"),
            ("failed", "失败数量"),
        ]
        for idx, (key, label) in enumerate(card_specs):
            card = self._panel(cards, fg_color=SURFACE, height=92)
            card.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 6, 6 if idx < 3 else 0))
            ctk.CTkLabel(
                card,
                text=label,
                font=(FONT_FAMILY, 13),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=16, pady=(12, 4))
            value = ctk.CTkLabel(
                card,
                text="0",
                font=(FONT_FAMILY, 26, "bold"),
                text_color=TEXT,
            )
            value.pack(anchor="w", padx=16)
            self.kpi_cards[key] = value
            if key != "run_mode":
                self.monitor_metrics[key] = value

        middle = ctk.CTkFrame(page, fg_color="transparent")
        middle.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
        middle.grid_columnconfigure(0, weight=3)
        middle.grid_columnconfigure(1, weight=2)

        stages_wrap = ctk.CTkFrame(middle, fg_color="transparent")
        stages_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        stages_wrap.grid_columnconfigure((0, 1, 2), weight=1)

        self.stage_cards = {}
        for idx, (stage_key, title) in enumerate((("links", "公告链接抓取"), ("pdf", "PDF 文件爬取"), ("extract", "文本提取"))):
            card = self._panel(stages_wrap, fg_color=SURFACE, height=170)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            card.grid_columnconfigure(1, weight=1)

            icon = ctk.CTkLabel(
                card,
                text="LK" if stage_key == "links" else "PDF" if stage_key == "pdf" else "TX",
                width=46,
                height=46,
                corner_radius=16,
                fg_color=SURFACE_ALT,
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 13, "bold"),
            )
            icon.grid(row=0, column=0, sticky="nw", padx=(18, 12), pady=(18, 0))

            title_row = ctk.CTkFrame(card, fg_color="transparent")
            title_row.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=(16, 4))
            title_row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                title_row,
                text=title,
                font=(FONT_FAMILY, 16, "bold"),
                text_color=TEXT,
            ).grid(row=0, column=0, sticky="w")
            subtitle = ctk.CTkLabel(
                title_row,
                text="等待执行",
                font=(FONT_FAMILY, 12),
                text_color=TEXT_MUTED,
            )
            subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))
            badge = ctk.CTkLabel(
                title_row,
                text="待命",
                width=68,
                height=28,
                corner_radius=14,
                fg_color=SURFACE_ALT,
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 12, "bold"),
            )
            badge.grid(row=0, column=1, rowspan=2, sticky="e")

            progress = ctk.CTkProgressBar(card, height=12, corner_radius=6, progress_color=PRIMARY)
            progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 10))
            progress.set(0)
            message = ctk.CTkLabel(
                card,
                text="尚未开始",
                font=(FONT_FAMILY, 12),
                text_color=TEXT_MUTED,
                anchor="w",
                justify="left",
            )
            message.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 4))
            footer = ctk.CTkLabel(
                card,
                text="0% | 等待执行",
                font=(FONT_FAMILY, 11),
                text_color=TEXT_MUTED,
                anchor="w",
            )
            footer.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 14))
            self.stage_cards[stage_key] = {
                "badge": badge,
                "icon": icon,
                "progress": progress,
                "subtitle": subtitle,
                "message": message,
                "footer": footer,
            }

        side_stack = ctk.CTkFrame(middle, fg_color="transparent")
        side_stack.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        side_stack.grid_columnconfigure(0, weight=1)

        alert = self._panel(side_stack, fg_color=SURFACE, height=144)
        alert.grid(row=0, column=0, sticky="ew")
        alert.grid_columnconfigure(0, weight=1)
        header_row = ctk.CTkFrame(alert, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        header_row.grid_columnconfigure(0, weight=1)
        self.alert_title = ctk.CTkLabel(
            header_row,
            text="系统提醒",
            font=(FONT_FAMILY, 16, "bold"),
            text_color=TEXT,
        )
        self.alert_title.grid(row=0, column=0, sticky="w")
        self.alert_badge = ctk.CTkLabel(
            header_row,
            text="IDLE",
            width=58,
            height=24,
            corner_radius=12,
            fg_color=SURFACE_ALT,
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.alert_badge.grid(row=0, column=1, sticky="e")
        self.alert_label = ctk.CTkLabel(
            alert,
            text="暂无异常，准备执行。",
            justify="left",
            wraplength=360,
            font=(FONT_FAMILY, 13),
            text_color=TEXT_MUTED,
        )
        self.alert_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))

        analytics = ctk.CTkFrame(page, fg_color="transparent")
        analytics.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        analytics.grid_columnconfigure(0, weight=1)

        progress_chart_card = ctk.CTkFrame(
            analytics,
            fg_color=SCREEN_PANEL,
            corner_radius=22,
            border_width=1,
            border_color=SCREEN_GLOW,
            height=360,
        )
        progress_chart_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        progress_chart_card.grid_columnconfigure(0, weight=1)
        chart_header = ctk.CTkFrame(progress_chart_card, fg_color="transparent")
        chart_header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
        chart_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            chart_header,
            text="运行态势大屏",
            font=(FONT_FAMILY, 20, "bold"),
            text_color=SCREEN_TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            chart_header,
            text="总进度 / 抓取 / 提取",
            font=(FONT_FAMILY, 12),
            text_color=SCREEN_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.progress_chart = tk.Canvas(
            progress_chart_card,
            bg=SCREEN_PANEL,
            highlightthickness=0,
            relief="flat",
            height=278,
        )
        self.progress_chart.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.progress_chart.bind("<Configure>", lambda _event: self._refresh_charts())

        stats_chart_card = ctk.CTkFrame(
            analytics,
            fg_color=SCREEN_PANEL_ALT,
            corner_radius=22,
            border_width=1,
            border_color=SCREEN_GLOW,
            height=310,
        )
        stats_chart_card.grid(row=1, column=0, sticky="ew")
        stats_chart_card.grid_columnconfigure(0, weight=1)
        stats_header = ctk.CTkFrame(stats_chart_card, fg_color="transparent")
        stats_header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
        stats_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            stats_header,
            text="产出与失败分布",
            font=(FONT_FAMILY, 20, "bold"),
            text_color=SCREEN_TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            stats_header,
            text="PDF 总量 / 提取成功 / 失败数量",
            font=(FONT_FAMILY, 12),
            text_color=SCREEN_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.stats_chart = tk.Canvas(
            stats_chart_card,
            bg=SCREEN_PANEL_ALT,
            highlightthickness=0,
            relief="flat",
            height=226,
        )
        self.stats_chart.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.stats_chart.bind("<Configure>", lambda _event: self._refresh_charts())

        return page

    def _build_logs_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        progress_card = self._panel(page, fg_color=SURFACE, height=138)
        progress_card.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        progress_card.grid_columnconfigure(1, weight=1)
        progress_card.grid_columnconfigure(2, weight=0)

        title_block = ctk.CTkFrame(progress_card, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="nw", padx=(20, 16), pady=(18, 14))
        ctk.CTkLabel(
            title_block,
            text="运行进度",
            font=(FONT_FAMILY, 24, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        bar_block = ctk.CTkFrame(progress_card, fg_color="transparent")
        bar_block.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(18, 14))
        bar_block.grid_columnconfigure(0, weight=1)

        info_row = ctk.CTkFrame(bar_block, fg_color="transparent")
        info_row.grid(row=0, column=0, sticky="ew")
        info_row.grid_columnconfigure(1, weight=1)
        self.log_status_cards: dict[str, ctk.CTkLabel] = {}
        self.log_status_cards["mode"] = ctk.CTkLabel(
            info_row,
            text="全流程",
            height=28,
            corner_radius=14,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=(FONT_FAMILY, 12, "bold"),
            padx=14,
        )
        self.log_status_cards["mode"].grid(row=0, column=0, sticky="w")
        self.log_status_cards["state"] = ctk.CTkLabel(
            info_row,
            text="系统空闲",
            font=(FONT_FAMILY, 13),
            text_color=TEXT_MUTED,
        )
        self.log_status_cards["state"].grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.log_status_cards["progress"] = ctk.CTkLabel(
            info_row,
            text="0%",
            font=(FONT_FAMILY, 28, "bold"),
            text_color=TEXT,
        )
        self.log_status_cards["progress"].grid(row=0, column=2, sticky="e")

        self.log_progress_bar = ctk.CTkProgressBar(
            bar_block,
            height=18,
            corner_radius=9,
            progress_color=PRIMARY,
        )
        self.log_progress_bar.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        self.log_progress_bar.set(0)

        self.log_progress_caption = ctk.CTkLabel(
            bar_block,
            text="等待执行",
            font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.log_progress_caption.grid(row=2, column=0, sticky="w")

        accent_block = ctk.CTkFrame(progress_card, fg_color="transparent")
        accent_block.grid(row=0, column=2, sticky="ne", padx=(0, 20), pady=(18, 14))
        self.log_progress_badge = ctk.CTkLabel(
            accent_block,
            text="READY",
            width=84,
            height=84,
            corner_radius=24,
            fg_color=PRIMARY_SOFT,
            text_color=PRIMARY,
            font=(FONT_FAMILY, 16, "bold"),
        )
        self.log_progress_badge.pack()

        panel = self._panel(page, fg_color=SURFACE, height=620)
        panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 6))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="实时日志流",
            font=(FONT_FAMILY, 18, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="普通日志黑色 | 时间戳灰色 | 告警/错误/状态红色",
            font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        text_wrap = ctk.CTkFrame(panel, fg_color=SURFACE_ALT, corner_radius=14)
        text_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        text_wrap.grid_rowconfigure(0, weight=1)
        text_wrap.grid_columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            text_wrap,
            bg="#FFFFFF",
            fg="#000000",
            insertbackground="#000000",
            relief="flat",
            borderwidth=0,
            font=(FONT_FAMILY, 15),
            wrap="word",
            padx=18,
            pady=16,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(text_wrap, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.tag_configure("timestamp", foreground="#7A7A7A")
        self.log_text.tag_configure("default", foreground="#000000")
        self.log_text.tag_configure("info", foreground="#000000")
        self.log_text.tag_configure("warning", foreground="#B91C1C")
        self.log_text.tag_configure("error", foreground="#B91C1C")
        self.log_text.tag_configure("status", foreground="#DC2626")
        self.log_text.tag_configure("timestamp", spacing1=2, spacing2=3, spacing3=2)
        self.log_text.tag_configure("default", spacing1=2, spacing2=3, spacing3=2)
        self.log_text.tag_configure("info", spacing1=2, spacing2=3, spacing3=2)
        self.log_text.tag_configure("warning", spacing1=2, spacing2=3, spacing3=2)
        self.log_text.tag_configure("error", spacing1=2, spacing2=3, spacing3=2)
        self.log_text.tag_configure("status", spacing1=2, spacing2=3, spacing3=2)
        self.log_text.configure(state="disabled")
        return page

    def _build_workspace_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        top = self._panel(page, fg_color=SURFACE)
        top.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        ctk.CTkLabel(top, text="工作区与路径", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 6))
        form = self._panel(page, fg_color=SURFACE)
        form.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        form.grid_columnconfigure(1, weight=1)

        self.workspace_vars = {
            "project_root": tk.StringVar(),
            "annual_report_dir": tk.StringVar(),
            "text_output_dir": tk.StringVar(),
            "state_dir": tk.StringVar(),
            "start_year": tk.StringVar(),
            "end_year": tk.StringVar(),
        }
        rows = [
            ("项目根目录", "project_root", "dir"),
            ("年报输出目录", "annual_report_dir", "dir"),
            ("文本输出目录", "text_output_dir", "dir"),
            ("状态目录", "state_dir", "dir"),
            ("开始年份", "start_year", None),
            ("结束年份", "end_year", None),
        ]
        for idx, (label, key, browse) in enumerate(rows):
            self._build_form_row(form, idx, label, self.workspace_vars[key], browse=browse)
        return page

    def _build_spider_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        form = self._panel(page, fg_color=SURFACE)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="抓取配置", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 12))

        mode_card = ctk.CTkFrame(
            form,
            fg_color=ACCENT_PANEL,
            corner_radius=16,
            border_width=1,
            border_color=ACCENT_PANEL_BORDER,
        )
        mode_card.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 12))
        mode_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(mode_card, text="执行模式", font=(FONT_FAMILY, 14, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))
        self.spider_mode_selector = ctk.CTkSegmentedButton(
            mode_card,
            values=["抓取并下载PDF", "仅抓取公告", "审计PDF", "清理孤儿PDF"],
            command=self._on_spider_mode_selected,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color=SEGMENT_BG,
            selected_color=PRIMARY,
            selected_hover_color=PRIMARY_HOVER,
            unselected_color=SEGMENT_IDLE,
            unselected_hover_color=SEGMENT_IDLE_HOVER,
            text_color=SEGMENT_TEXT,
            )
        self.spider_mode_selector.grid(row=1, column=0, sticky="ew", padx=16)
        self.spider_mode_hint = ctk.CTkLabel(
            mode_card,
            text="",
            font=(FONT_FAMILY, 12),
            text_color=HINT_TEXT,
            justify="left",
            anchor="w",
            wraplength=860,
        )
        self.spider_mode_hint.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 14))

        self.spider_vars = {
            "page_size": tk.StringVar(),
            "request_interval": tk.StringVar(),
            "announcement_concurrency": tk.StringVar(),
            "download_concurrency": tk.StringVar(),
            "download_pdf": tk.BooleanVar(),
            "metadata_only": tk.BooleanVar(),
            "audit_pdf": tk.BooleanVar(),
            "cleanup_orphan_pdf": tk.BooleanVar(),
            "reset_checkpoint": tk.BooleanVar(),
            "delete_checkpoint_on_success": tk.BooleanVar(),
        }
        rows = [
            ("分页大小", "page_size"),
            ("请求间隔(秒)", "request_interval"),
            ("公告并发数", "announcement_concurrency"),
            ("下载并发数", "download_concurrency"),
        ]
        for idx, (label, key) in enumerate(rows, start=2):
            self.spider_field_widgets[key] = self._build_form_row(form, idx, label, self.spider_vars[key])

        checks = ctk.CTkFrame(form, fg_color="transparent")
        checks.grid(row=6, column=0, columnspan=3, sticky="ew", padx=20, pady=(8, 18))
        checks.grid_columnconfigure((0, 1), weight=1)
        check_labels = [
            ("重置旧 checkpoint", "reset_checkpoint"),
            ("成功后删除 checkpoint", "delete_checkpoint_on_success"),
        ]
        for idx, (label, key) in enumerate(check_labels):
            checkbox = ctk.CTkCheckBox(
                checks,
                text=label,
                variable=self.spider_vars[key],
                font=(FONT_FAMILY, 12),
                text_color=TEXT,
                checkbox_width=18,
                checkbox_height=18,
            )
            checkbox.grid(row=idx // 2, column=idx % 2, sticky="w", padx=8, pady=8)
            self.spider_check_widgets[key] = checkbox
        return page

    def _build_links_config_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        form = self._panel(page, fg_color=SURFACE)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="公告链接抓取配置", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 12))

        hint_card = ctk.CTkFrame(
            form,
            fg_color=ACCENT_PANEL,
            corner_radius=16,
            border_width=1,
            border_color=ACCENT_PANEL_BORDER,
        )
        hint_card.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 12))
        hint_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hint_card, text="步骤一", font=(FONT_FAMILY, 14, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))
        self.links_page_hint = ctk.CTkLabel(
            hint_card,
            text="抓取公告链接、筛选年度报告，并生成 filtered_announcements.jsonl。",
            font=(FONT_FAMILY, 12),
            text_color=HINT_TEXT,
            justify="left",
            anchor="w",
            wraplength=860,
        )
        self.links_page_hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        if not hasattr(self, "spider_vars"):
            self.spider_vars = {
                "page_size": tk.StringVar(),
                "request_interval": tk.StringVar(),
                "announcement_concurrency": tk.StringVar(),
                "download_concurrency": tk.StringVar(),
                "download_pdf": tk.BooleanVar(),
                "metadata_only": tk.BooleanVar(),
                "audit_pdf": tk.BooleanVar(),
                "cleanup_orphan_pdf": tk.BooleanVar(),
                "reset_checkpoint": tk.BooleanVar(),
                "delete_checkpoint_on_success": tk.BooleanVar(),
            }

        self.link_field_widgets = {}
        rows = [
            ("分页大小", "page_size"),
            ("请求间隔(秒)", "request_interval"),
            ("公告并发数", "announcement_concurrency"),
        ]
        for idx, (label, key) in enumerate(rows, start=2):
            widget = self._build_form_row(form, idx, label, self.spider_vars[key])
            self.link_field_widgets[key] = widget
            self.spider_field_widgets[key] = widget

        checks = ctk.CTkFrame(form, fg_color="transparent")
        checks.grid(row=5, column=0, columnspan=3, sticky="ew", padx=20, pady=(8, 18))
        checks.grid_columnconfigure((0, 1), weight=1)
        for idx, (label, key) in enumerate((
            ("重置旧 checkpoint", "reset_checkpoint"),
            ("成功后删除 checkpoint", "delete_checkpoint_on_success"),
        )):
            checkbox = ctk.CTkCheckBox(
                checks,
                text=label,
                variable=self.spider_vars[key],
                font=(FONT_FAMILY, 12),
                text_color=TEXT,
                checkbox_width=18,
                checkbox_height=18,
            )
            checkbox.grid(row=idx // 2, column=idx % 2, sticky="w", padx=8, pady=8)
            self.spider_check_widgets[key] = checkbox
        return page

    def _build_pdf_config_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        form = self._panel(page, fg_color=SURFACE)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="PDF 文件抓取配置", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 12))

        hint_card = ctk.CTkFrame(
            form,
            fg_color=ACCENT_PANEL,
            corner_radius=16,
            border_width=1,
            border_color=ACCENT_PANEL_BORDER,
        )
        hint_card.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 12))
        hint_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hint_card, text="步骤二", font=(FONT_FAMILY, 14, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))
        self.pdf_page_hint = ctk.CTkLabel(
            hint_card,
            text="读取步骤一生成的公告清单并下载 PDF，自动回写 metadata.csv。",
            font=(FONT_FAMILY, 12),
            text_color=HINT_TEXT,
            justify="left",
            anchor="w",
            wraplength=860,
        )
        self.pdf_page_hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        if not hasattr(self, "spider_vars"):
            self.spider_vars = {
                "page_size": tk.StringVar(),
                "request_interval": tk.StringVar(),
                "announcement_concurrency": tk.StringVar(),
                "download_concurrency": tk.StringVar(),
                "download_pdf": tk.BooleanVar(),
                "metadata_only": tk.BooleanVar(),
                "audit_pdf": tk.BooleanVar(),
                "cleanup_orphan_pdf": tk.BooleanVar(),
                "reset_checkpoint": tk.BooleanVar(),
                "delete_checkpoint_on_success": tk.BooleanVar(),
            }

        widget = self._build_form_row(form, 2, "PDF 下载并发数", self.spider_vars["download_concurrency"])
        self.spider_field_widgets["download_concurrency"] = widget

        note = ctk.CTkFrame(form, fg_color="transparent")
        note.grid(row=3, column=0, columnspan=3, sticky="ew", padx=20, pady=(8, 18))
        ctk.CTkLabel(
            note,
            text="PDF 下载阶段不单独维护 checkpoint；是否重置旧 checkpoint 请在“公告链接抓取”页面设置。",
            font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=960,
        ).grid(row=0, column=0, sticky="w")
        return page

    def _build_extract_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        form = self._panel(page, fg_color=SURFACE)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="提取配置", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 12))

        self.extract_vars = {
            "concurrency": tk.StringVar(),
            "reset_checkpoint": tk.BooleanVar(),
            "delete_checkpoint_on_success": tk.BooleanVar(),
        }
        self._build_form_row(form, 1, "提取并发数", self.extract_vars["concurrency"])
        self.extract_hint = ctk.CTkLabel(
            form,
            text="",
            font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED,
            justify="left",
            anchor="w",
            wraplength=860,
        )
        self.extract_hint.grid(row=2, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 8))

        checks = ctk.CTkFrame(form, fg_color="transparent")
        checks.grid(row=3, column=0, columnspan=3, sticky="ew", padx=20, pady=(8, 18))
        ctk.CTkCheckBox(
            checks,
            text="重置旧 checkpoint",
            variable=self.extract_vars["reset_checkpoint"],
            font=(FONT_FAMILY, 12),
            text_color=TEXT,
            checkbox_width=18,
            checkbox_height=18,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ctk.CTkCheckBox(
            checks,
            text="成功后删除 checkpoint",
            variable=self.extract_vars["delete_checkpoint_on_success"],
            font=(FONT_FAMILY, 12),
            text_color=TEXT,
            checkbox_width=18,
            checkbox_height=18,
        ).grid(row=0, column=1, sticky="w", padx=8, pady=8)
        return page

    def _build_results_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        top = self._panel(page, fg_color=SURFACE, height=88)
        top.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="结果中心", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(top, text="支持查看抓取摘要预览与文本提取摘要。", font=(FONT_FAMILY, 12), text_color=TEXT_MUTED).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 14))
        ctk.CTkButton(
            top,
            text="加载结果",
            width=110,
            height=36,
            corner_radius=12,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            font=(FONT_FAMILY, 12, "bold"),
            command=self.reload_results,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=20)

        overview = ctk.CTkFrame(page, fg_color="transparent")
        overview.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        overview.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.result_summary_cards: dict[str, ctk.CTkLabel] = {}
        summary_specs = [
            ("spider_rows", "抓取记录"),
            ("spider_years", "覆盖年份"),
            ("extract_success", "提取成功"),
            ("extract_failed", "提取失败"),
        ]
        for idx, (key, label) in enumerate(summary_specs):
            card = self._panel(overview, fg_color=SURFACE, height=96)
            card.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 6, 6 if idx < 3 else 0))
            ctk.CTkLabel(card, text=label, font=(FONT_FAMILY, 12), text_color=TEXT_MUTED).pack(anchor="w", padx=16, pady=(12, 4))
            value = ctk.CTkLabel(card, text="-", font=(FONT_FAMILY, 24, "bold"), text_color=TEXT)
            value.pack(anchor="w", padx=16)
            self.result_summary_cards[key] = value

        result_card = self._panel(page, fg_color=SURFACE)
        result_card.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        result_card.grid_rowconfigure(2, weight=1)
        result_card.grid_columnconfigure(0, weight=1)

        selector = ctk.CTkSegmentedButton(
            result_card,
            values=["抓取摘要", "提取摘要"],
            command=self._switch_result_dataset,
            font=(FONT_FAMILY, 12, "bold"),
        )
        selector.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 12))
        selector.set("抓取摘要")
        self.result_selector = selector

        self.result_hint = ctk.CTkLabel(
            result_card,
            text="结果来源将在运行后自动刷新。",
            font=(FONT_FAMILY, 11),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self.result_hint.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        sheet_host = ctk.CTkFrame(result_card, fg_color=SURFACE_ALT, corner_radius=14)
        sheet_host.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        sheet_host.grid_rowconfigure(0, weight=1)
        sheet_host.grid_columnconfigure(0, weight=1)

        self.result_fallback = ctk.CTkTextbox(
            sheet_host,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=(FONT_MONO, 11),
            border_width=0,
            wrap="none",
        )
        self.result_fallback.grid(row=0, column=0, sticky="nsew")

        self.result_sheet = None
        if Sheet is not None:
            self.result_fallback.grid_remove()
            self.result_sheet = Sheet(
                sheet_host,
                theme="light green",
                show_x_scrollbar=True,
                show_y_scrollbar=True,
                headers=[],
                data=[],
            )
            self.result_sheet.enable_bindings("all")
            self.result_sheet.grid(row=0, column=0, sticky="nsew")
        return page

    def _build_about_page(self) -> ctk.CTkFrame:
        page = ctk.CTkScrollableFrame(
            self.page_wrap,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        page.grid_columnconfigure(0, weight=1)

        top = self._panel(page, fg_color=SURFACE, height=96)
        top.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="关于", font=(FONT_FAMILY, 22, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 6))
        ctk.CTkLabel(top, text=f"GitHub: {self.about_payload['github_url']}", font=(FONT_FAMILY, 12), text_color=PRIMARY).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 16))
        ctk.CTkButton(
            top,
            text="打开 GitHub",
            width=120,
            height=36,
            corner_radius=12,
            fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER,
            font=(FONT_FAMILY, 12, "bold"),
            command=lambda: webbrowser.open(self.about_payload["github_url"]),
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=20)

        body = self._panel(page, fg_color=SURFACE)
        body.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(body, text="README / GUI README", font=(FONT_FAMILY, 16, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 10))
        self.about_text = ctk.CTkTextbox(
            body,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=(FONT_FAMILY, 12),
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
            wrap="word",
        )
        self.about_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        return page

    def _build_monitor_panel(self) -> None:
        monitor = self._panel(self, fg_color=SURFACE)
        monitor.grid(row=1, column=2, sticky="nsew", padx=(10, 18), pady=(0, 0))
        monitor.grid_columnconfigure(0, weight=1)
        self.monitor_panel = monitor

        ctk.CTkLabel(monitor, text="运行监控", font=(FONT_FAMILY, 18, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 12))

        overall = self._panel(monitor, fg_color=SURFACE_ALT, height=112)
        overall.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        overall.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(overall, text="总进度", font=(FONT_FAMILY, 13, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))
        self.overall_progress = ctk.CTkProgressBar(overall, height=14, corner_radius=7, progress_color=PRIMARY)
        self.overall_progress.grid(row=1, column=0, sticky="ew", padx=16)
        self.overall_progress.set(0)
        self.overall_status = ctk.CTkLabel(overall, text="等待执行", font=(FONT_FAMILY, 12), text_color=TEXT_MUTED)
        self.overall_status.grid(row=2, column=0, sticky="w", padx=16, pady=(8, 2))
        self.overall_caption = ctk.CTkLabel(
            overall,
            text="阶段进度会按抓取与提取权重汇总。",
            font=(FONT_FAMILY, 11),
            text_color=TEXT_MUTED,
        )
        self.overall_caption.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 10))

        self.stage_cards: dict[str, dict[str, Any]] = {}
        for row_idx, (stage_key, title) in enumerate((("spider", "年报抓取"), ("extract", "文本提取")), start=2):
            card = self._panel(monitor, fg_color=SURFACE_ALT, height=122)
            card.grid(row=row_idx, column=0, sticky="ew", padx=18, pady=(0, 12))
            card.grid_columnconfigure(1, weight=1)
            title_row = ctk.CTkFrame(card, fg_color="transparent")
            title_row.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(12, 2))
            title_row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(title_row, text=title, font=(FONT_FAMILY, 14, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
            subtitle = ctk.CTkLabel(
                title_row,
                text="等待执行",
                font=(FONT_FAMILY, 11),
                text_color=TEXT_MUTED,
            )
            subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))
            badge = ctk.CTkLabel(
                title_row,
                text="待命",
                width=72,
                height=28,
                corner_radius=14,
                fg_color=SURFACE,
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 11, "bold"),
            )
            badge.grid(row=0, column=1, rowspan=2, sticky="e")

            icon = ctk.CTkLabel(
                card,
                text="AR" if stage_key == "spider" else "TX",
                width=44,
                height=44,
                corner_radius=16,
                fg_color=SURFACE,
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 13, "bold"),
            )
            icon.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(16, 12), pady=(14, 0))

            progress = ctk.CTkProgressBar(card, height=12, corner_radius=6, progress_color=PRIMARY)
            progress.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=(4, 8))
            progress.set(0)
            message = ctk.CTkLabel(card, text="尚未开始", font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, justify="left", anchor="w")
            message.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 4))
            footer = ctk.CTkLabel(
                card,
                text="0% | 等待执行",
                font=(FONT_FAMILY, 10),
                text_color=TEXT_MUTED,
                anchor="w",
            )
            footer.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))
            self.stage_cards[stage_key] = {
                "badge": badge,
                "icon": icon,
                "progress": progress,
                "subtitle": subtitle,
                "message": message,
                "footer": footer,
            }

        metrics = self._panel(monitor, fg_color=SURFACE_ALT, height=132)
        metrics.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 12))
        metrics.grid_columnconfigure((0, 1), weight=1)
        metric_specs = [("elapsed", "已用时"), ("pdf_total", "PDF 总量"), ("extracted", "提取成功"), ("failed", "失败数量")]
        self.monitor_metrics: dict[str, ctk.CTkLabel] = {}
        for idx, (key, label) in enumerate(metric_specs):
            cell = ctk.CTkFrame(metrics, fg_color=SURFACE, corner_radius=14)
            cell.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=10, pady=10)
            ctk.CTkLabel(cell, text=label, font=(FONT_FAMILY, 11), text_color=TEXT_MUTED).pack(anchor="w", padx=12, pady=(10, 2))
            value = ctk.CTkLabel(cell, text="0", font=(FONT_FAMILY, 20, "bold"), text_color=TEXT)
            value.pack(anchor="w", padx=12, pady=(0, 10))
            self.monitor_metrics[key] = value

        alert = self._panel(monitor, fg_color=SURFACE_ALT, height=102)
        alert.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))
        alert.grid_columnconfigure(0, weight=1)
        header_row = ctk.CTkFrame(alert, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        header_row.grid_columnconfigure(0, weight=1)
        self.alert_title = ctk.CTkLabel(header_row, text="系统提醒", font=(FONT_FAMILY, 13, "bold"), text_color=TEXT)
        self.alert_title.grid(row=0, column=0, sticky="w")
        self.alert_badge = ctk.CTkLabel(
            header_row,
            text="IDLE",
            width=58,
            height=24,
            corner_radius=12,
            fg_color=SURFACE,
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.alert_badge.grid(row=0, column=1, sticky="e")
        self.alert_label = ctk.CTkLabel(
            alert,
            text="暂无异常，准备执行。",
            justify="left",
            wraplength=280,
            font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED,
        )
        self.alert_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

    def _build_log_panel(self) -> None:
        panel = self._panel(self, fg_color=SURFACE, height=300)
        panel.grid(row=2, column=1, columnspan=2, sticky="nsew", padx=(0, 18), pady=(10, 18))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="日志中心", font=(FONT_FAMILY, 18, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="普通日志黑色 | 时间戳灰色 | 告警/错误/状态红色",
            font=(FONT_FAMILY, 11),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        text_wrap = ctk.CTkFrame(panel, fg_color=SURFACE_ALT, corner_radius=14)
        text_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        text_wrap.grid_rowconfigure(0, weight=1)
        text_wrap.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            text_wrap,
            bg="#FFFFFF",
            fg="#000000",
            insertbackground="#000000",
            relief="flat",
            borderwidth=0,
            font=(FONT_MONO, 11),
            wrap="word",
            padx=14,
            pady=12,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(text_wrap, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.tag_configure("timestamp", foreground="#7A7A7A")
        self.log_text.tag_configure("default", foreground="#000000")
        self.log_text.tag_configure("info", foreground="#000000")
        self.log_text.tag_configure("warning", foreground="#B91C1C")
        self.log_text.tag_configure("error", foreground="#B91C1C")
        self.log_text.tag_configure("status", foreground="#DC2626")
        self.log_text.configure(state="disabled")

    def _build_form_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: tk.Variable,
        *,
        browse: str | None = None,
    ) -> Any:
        ctk.CTkLabel(parent, text=label, font=(FONT_FAMILY, 13, "bold"), text_color=TEXT).grid(row=row, column=0, sticky="w", padx=20, pady=10)
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=38,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=(FONT_FAMILY, 13),
        )
        entry.grid(row=row, column=1, sticky="ew", padx=12, pady=10)
        if browse:
            ctk.CTkButton(
                parent,
                text="浏览",
                width=72,
                height=36,
                corner_radius=12,
                fg_color=SURFACE,
                text_color=TEXT,
                border_width=1,
                border_color=BORDER,
                hover_color=SURFACE_SOFT,
                font=(FONT_FAMILY, 13, "bold"),
                command=lambda key=variable: self._browse_path(key, browse),
            ).grid(row=row, column=2, sticky="e", padx=(0, 20), pady=10)
        return entry

    def _spider_mode_label(self, mode: str) -> str:
        return {
            "download": "抓取并下载PDF",
            "metadata": "仅抓取公告",
            "audit": "审计PDF",
            "cleanup": "清理孤儿PDF",
        }.get(mode, "抓取并下载PDF")

    def _spider_mode_from_label(self, label: str) -> str:
        return {
            "抓取并下载PDF": "download",
            "仅抓取公告": "metadata",
            "审计PDF": "audit",
            "清理孤儿PDF": "cleanup",
        }.get(label, "download")

    def _infer_spider_mode(self) -> str:
        spider = self.settings.spider
        if spider.cleanup_orphan_pdf:
            return "cleanup"
        if spider.audit_pdf:
            return "audit"
        if spider.metadata_only or not spider.download_pdf:
            return "metadata"
        return "download"

    def _on_spider_mode_selected(self, label: str) -> None:
        self.spider_mode = self._spider_mode_from_label(label)
        self._apply_spider_mode_to_form()
        self._refresh_strategy_preview()

    def _apply_spider_mode_to_form(self) -> None:
        spider_mode = self.spider_mode
        disabled_fields: set[str] = set()
        disable_checkpoint_ops = False
        hint = "会抓取公告并下载 PDF，支持一键全流程。"

        if spider_mode == "metadata":
            disabled_fields = {"download_concurrency"}
            hint = "只抓取公告与摘要，不下载 PDF。一键全流程会自动禁用。"
        elif spider_mode == "audit":
            disabled_fields = {"page_size", "request_interval", "announcement_concurrency", "download_concurrency"}
            disable_checkpoint_ops = True
            hint = "只审计输出目录中的现有 PDF，不执行抓取下载，也不会生成新的 checkpoint。"
        elif spider_mode == "cleanup":
            disabled_fields = {"page_size", "request_interval", "announcement_concurrency", "download_concurrency"}
            disable_checkpoint_ops = True
            hint = "只清理输出目录中的孤儿 PDF，并输出清理前后审计报告，不执行抓取下载。"

        for key, widget in self.spider_field_widgets.items():
            widget.configure(state="disabled" if key in disabled_fields else "normal")

        if disable_checkpoint_ops:
            self.spider_vars["reset_checkpoint"].set(False)
            self.spider_vars["delete_checkpoint_on_success"].set(False)
        for key in ("reset_checkpoint", "delete_checkpoint_on_success"):
            if key in self.spider_check_widgets:
                self.spider_check_widgets[key].configure(state="disabled" if disable_checkpoint_ops else "normal")

        if hasattr(self, "spider_mode_hint"):
            self.spider_mode_hint.configure(text=hint)
        if hasattr(self, "extract_hint"):
            if spider_mode == "download":
                self.extract_hint.configure(text="提取阶段会读取抓取输出目录中的 PDF，适合直接执行一键全流程。")
            else:
                self.extract_hint.configure(text="当前抓取模式不会产出新的 PDF，因此一键全流程已禁用；如果目录里已有 PDF，仍可单独执行提取。")

        running = self._run_start_pending or (self.worker is not None and self.worker.is_alive())
        self._set_running_state(running)

    def _load_initial_form_values(self) -> None:
        workspace = self.settings.workspace
        spider = self.settings.spider
        extract = self.settings.extract

        self.workspace_vars["project_root"].set(workspace.project_root)
        self.workspace_vars["annual_report_dir"].set(workspace.annual_report_dir)
        self.workspace_vars["text_output_dir"].set(workspace.text_output_dir)
        self.workspace_vars["state_dir"].set(workspace.state_dir)
        self.workspace_vars["start_year"].set(str(workspace.start_year))
        self.workspace_vars["end_year"].set(str(workspace.end_year))

        self.spider_vars["page_size"].set(str(spider.page_size))
        self.spider_vars["request_interval"].set(str(spider.request_interval))
        self.spider_vars["announcement_concurrency"].set(str(spider.announcement_concurrency))
        self.spider_vars["download_concurrency"].set(str(spider.download_concurrency))
        self.spider_vars["download_pdf"].set(spider.download_pdf)
        self.spider_vars["metadata_only"].set(spider.metadata_only)
        self.spider_vars["audit_pdf"].set(spider.audit_pdf)
        self.spider_vars["cleanup_orphan_pdf"].set(spider.cleanup_orphan_pdf)
        self.spider_vars["reset_checkpoint"].set(spider.reset_checkpoint)
        self.spider_vars["delete_checkpoint_on_success"].set(spider.delete_checkpoint_on_success)
        self.spider_mode = "download"
        if hasattr(self, "spider_mode_selector"):
            self.spider_mode_selector.set(self._spider_mode_label(self.spider_mode))

        self.extract_vars["concurrency"].set(str(extract.concurrency))
        self.extract_vars["reset_checkpoint"].set(extract.reset_checkpoint)
        self.extract_vars["delete_checkpoint_on_success"].set(extract.delete_checkpoint_on_success)

        self.about_text.delete("1.0", "end")
        self.about_text.insert("1.0", self.about_payload["readme"])
        self.about_text.insert("end", "\n\n" + "=" * 72 + "\n\n")
        self.about_text.insert("end", self.about_payload["gui_readme"])
        self._apply_spider_mode_to_form()
        if hasattr(self, "spider_mode_hint"):
            self.spider_mode_hint.configure(text="步骤一和步骤二共用此配置，固定执行为：公告链接抓取 -> PDF 文件爬取。")
        if hasattr(self, "extract_hint"):
            self.extract_hint.configure(text="步骤三会读取 annual_reports 目录中的 PDF，并输出到文本提取目录。")
        self._refresh_strategy_preview()
        self.reload_results()
        self._set_alert_state(
            self.alert_state["level"],
            self.alert_state["title"],
            self.alert_state["body"],
        )
        self._refresh_command_page()

    def _browse_path(self, variable: tk.Variable, browse: str) -> None:
        initial_dir = self.workspace_vars["project_root"].get() or "."
        if browse == "dir":
            selected = filedialog.askdirectory(initialdir=initial_dir)
        else:
            selected = filedialog.askopenfilename(initialdir=initial_dir)
        if selected:
            variable.set(selected)
            self._refresh_strategy_preview()

    def show_page(self, page_key: str) -> None:
        self.current_page = page_key
        for key, page in self.pages.items():
            if key == page_key:
                page.grid()
            else:
                page.grid_remove()
        for key, button in self.nav_buttons.items():
            if key == page_key:
                button.configure(fg_color=PRIMARY, text_color="white")
            else:
                button.configure(fg_color="transparent", text_color=TEXT)

    def _collect_settings_from_form(self) -> ConsoleSettings:
        workspace = self.settings.workspace
        workspace.project_root = self.workspace_vars["project_root"].get().strip() or workspace.project_root
        workspace.annual_report_dir = self.workspace_vars["annual_report_dir"].get().strip() or workspace.annual_report_dir
        workspace.text_output_dir = self.workspace_vars["text_output_dir"].get().strip() or workspace.text_output_dir
        workspace.state_dir = self.workspace_vars["state_dir"].get().strip() or workspace.state_dir
        workspace.start_year = int(self.workspace_vars["start_year"].get().strip() or workspace.start_year)
        workspace.end_year = int(self.workspace_vars["end_year"].get().strip() or workspace.end_year)

        spider = self.settings.spider
        spider.page_size = max(1, int(self.spider_vars["page_size"].get().strip() or spider.page_size))
        spider.request_interval = max(0.0, float(self.spider_vars["request_interval"].get().strip() or spider.request_interval))
        spider.announcement_concurrency = max(1, int(self.spider_vars["announcement_concurrency"].get().strip() or spider.announcement_concurrency))
        spider.download_concurrency = max(1, int(self.spider_vars["download_concurrency"].get().strip() or spider.download_concurrency))
        spider.reset_checkpoint = bool(self.spider_vars["reset_checkpoint"].get())
        spider.delete_checkpoint_on_success = bool(self.spider_vars["delete_checkpoint_on_success"].get())
        spider.download_pdf = True
        spider.metadata_only = False
        spider.audit_pdf = False
        spider.cleanup_orphan_pdf = False

        extract = self.settings.extract
        extract.concurrency = max(1, int(self.extract_vars["concurrency"].get().strip() or extract.concurrency))
        extract.reset_checkpoint = bool(self.extract_vars["reset_checkpoint"].get())
        extract.delete_checkpoint_on_success = bool(self.extract_vars["delete_checkpoint_on_success"].get())
        return self.settings

    def _refresh_strategy_preview(self) -> None:
        settings = self._collect_settings_from_form()
        workspace = settings.workspace
        spider = settings.spider
        extract = settings.extract

        spider_checkpoint = resolve_path(workspace.project_root, workspace.state_dir) / "checkpoint.json"
        extract_checkpoint = resolve_path(workspace.project_root, workspace.state_dir) / "text_extract_checkpoint.json"
        lines = [
            f"项目根目录: {workspace.project_root}",
            f"抓取输出: {resolve_path(workspace.project_root, workspace.annual_report_dir)}",
            f"提取输出: {resolve_path(workspace.project_root, workspace.text_output_dir)}",
            f"年份范围: {workspace.start_year} - {workspace.end_year}",
            "",
            "步骤一 公告链接抓取:",
            f"- 分页大小: {spider.page_size}",
            f"- 请求间隔: {spider.request_interval}",
            f"- 公告并发: {spider.announcement_concurrency}",
            f"- checkpoint: {spider_checkpoint}",
            "",
            "步骤二 PDF 文件爬取:",
            f"- 下载并发: {spider.download_concurrency}",
            f"- 输入依赖: annual_reports/*/filtered_announcements.jsonl",
            "",
            "步骤三 文本提取:",
            f"- 提取并发: {extract.concurrency}",
            f"- checkpoint: {extract_checkpoint}",
            "",
            f"重置旧 checkpoint: {'是' if spider.reset_checkpoint else '否'} / {'是' if extract.reset_checkpoint else '否'}",
            f"成功后删除 checkpoint: {'是' if spider.delete_checkpoint_on_success else '否'} / {'是' if extract.delete_checkpoint_on_success else '否'}",
        ]
        plan_text = "\n".join(lines)
        if hasattr(self, "plan_preview"):
            self.plan_preview.delete("1.0", "end")
            self.plan_preview.insert("1.0", plan_text)
        if hasattr(self, "plan_text"):
            self.plan_text.delete("1.0", "end")
            self.plan_text.insert("1.0", self._build_run_blueprint())
        return
        settings = self._collect_settings_from_form()
        workspace = settings.workspace
        spider = settings.spider
        extract = settings.extract

        spider_checkpoint = resolve_path(workspace.project_root, workspace.state_dir) / "checkpoint.json"
        extract_checkpoint = resolve_path(workspace.project_root, workspace.state_dir) / "text_extract_checkpoint.json"
        lines = [
            f"项目根目录: {workspace.project_root}",
            f"抓取输出: {resolve_path(workspace.project_root, workspace.annual_report_dir)}",
            f"提取输出: {resolve_path(workspace.project_root, workspace.text_output_dir)}",
            f"年份范围: {workspace.start_year} - {workspace.end_year}",
            "",
            "抓取阶段:",
            f"- 执行模式: {self._spider_mode_label(self.spider_mode)}",
            f"- 下载 PDF: {'是' if spider.download_pdf else '否'}",
            f"- 公告并发 / 下载并发: {spider.announcement_concurrency} / {spider.download_concurrency if spider.download_pdf else '-'}",
            f"- 重置 checkpoint: {'是' if spider.reset_checkpoint else '否'}",
            f"- 成功后删除 checkpoint: {'是' if spider.delete_checkpoint_on_success else '否'}",
            f"- checkpoint 路径: {spider_checkpoint}",
            "",
            "提取阶段:",
            f"- 并发数: {extract.concurrency}",
            f"- 重置 checkpoint: {'是' if extract.reset_checkpoint else '否'}",
            f"- 成功后删除 checkpoint: {'是' if extract.delete_checkpoint_on_success else '否'}",
            f"- checkpoint 路径: {extract_checkpoint}",
        ]
        if self.spider_mode != "download":
            lines.extend(["", "注意:", "- 当前抓取模式不产出新的 PDF，一键全流程已禁用。"])
        plan_text = "\n".join(lines)
        if hasattr(self, "plan_preview"):
            self.plan_preview.delete("1.0", "end")
            self.plan_preview.insert("1.0", plan_text)
        if hasattr(self, "plan_text"):
            self.plan_text.delete("1.0", "end")
            self.plan_text.insert("1.0", self._build_run_blueprint())

    def _set_alert_state(self, level: str, title: str, body: str) -> None:
        self.alert_state = {"level": level, "title": title, "body": body}
        if not hasattr(self, "alert_title"):
            return

        palette = {
            "idle": (SURFACE_ALT, SURFACE, TEXT, TEXT_MUTED, "IDLE"),
            "info": (INFO_SOFT, INFO_SOFT, INFO, INFO, "INFO"),
            "warning": (WARNING_SOFT, WARNING_SOFT, WARNING, WARNING, "WARN"),
            "error": (DANGER_SOFT, DANGER_SOFT, DANGER, DANGER, "ERROR"),
            "success": (SUCCESS_SOFT, SUCCESS_SOFT, SUCCESS, SUCCESS, "DONE"),
        }
        panel_color, badge_color, title_color, body_color, badge_text = palette.get(
            level,
            palette["idle"],
        )
        self.alert_title.configure(text=title, text_color=title_color)
        self.alert_badge.configure(text=badge_text, fg_color=badge_color, text_color=title_color)
        self.alert_label.configure(text=body, text_color=body_color)
        self.alert_title.master.master.configure(fg_color=panel_color)

    def _refresh_result_summary_cards(self) -> None:
        if not hasattr(self, "result_summary_cards"):
            return
        spider_rows = len(self.spider_preview_rows)
        years = sorted(
            {
                str(row.get("report_year"))
                for row in self.spider_preview_rows
                if isinstance(row, dict) and row.get("report_year") not in (None, "")
            }
        )
        success_count = self.extract_summary.get("extracted", 0) if self.extract_summary else 0
        failed_count = self.extract_summary.get("failed", 0) if self.extract_summary else 0
        self.result_summary_cards["spider_rows"].configure(text=str(spider_rows))
        self.result_summary_cards["spider_years"].configure(
            text=f"{years[0]}-{years[-1]}" if len(years) >= 2 else (years[0] if years else "-")
        )
        self.result_summary_cards["extract_success"].configure(text=str(success_count))
        self.result_summary_cards["extract_failed"].configure(text=str(failed_count))

    def _build_run_blueprint(self) -> str:
        settings = self.settings
        return "\n".join(
            [
                "1. 校验工作区路径、输出目录和年份范围。",
                "2. 执行步骤一：公告链接抓取，生成每年的筛选结果清单。",
                "3. 执行步骤二：PDF 文件爬取，读取步骤一产物并回写 metadata.csv。",
                "4. 执行步骤三：文本提取，读取 annual_reports 目录中的 PDF。",
                "5. 实时把日志、阶段进度、KPI 和图表同步到 GUI。",
                "",
                f"默认年份: {settings.workspace.start_year} - {settings.workspace.end_year}",
                f"公告并发: {settings.spider.announcement_concurrency}",
                f"下载并发: {settings.spider.download_concurrency}",
                f"提取并发: {settings.extract.concurrency}",
            ]
        )
        settings = self.settings
        steps = [
            "1. 校验工作区路径、输出目录和年份范围。",
            "2. 进入抓取阶段，复用 spider.py 的原生服务函数。",
            "3. 将日志和进度桥接到 GUI 事件队列，避免主线程卡顿。",
            "4. 如执行全流程，抓取结束后自动切到文本提取。",
            "5. 提取阶段按配置并发执行，实时刷新 KPI 与阶段卡片。",
            "6. 运行阶段把抓取与提取摘要回写到状态卡、日志和本地 summary 文件。",
            "",
            f"当前默认年份: {settings.workspace.start_year} - {settings.workspace.end_year}",
            f"默认抓取并发: {settings.spider.announcement_concurrency} / {settings.spider.download_concurrency}",
            f"默认提取并发: {settings.extract.concurrency}",
        ]
        return "\n".join(steps)

    def _refresh_command_page(self) -> None:
        self._command_refresh_pending = False
        self.command_hint.configure(text=f"当前待执行：{self._mode_label(self.current_mode)}")
        self.kpi_cards["run_mode"].configure(text=self._mode_label(self.current_mode))
        self.monitor_metrics["elapsed"].configure(text=self.kpi_values["elapsed"])
        self.monitor_metrics["pdf_total"].configure(text=self.kpi_values["pdf_total"])
        self.monitor_metrics["extracted"].configure(text=self.kpi_values["extracted"])
        self.monitor_metrics["failed"].configure(text=self.kpi_values["failed"])
        self.kpi_cards["pdf_total"].configure(text=self.kpi_values["pdf_total"])
        self.kpi_cards["extracted"].configure(text=self.kpi_values["extracted"])
        self.kpi_cards["failed"].configure(text=self.kpi_values["failed"])
        progress_percent = self._progress_percent()
        if self.current_page == "command" and hasattr(self, "summary_text"):
            summary = [
                f"当前模式: {self._mode_label(self.current_mode)}",
                f"抓取模式: {self._spider_mode_label(self.spider_mode)}",
                f"系统状态: {self.run_badge.cget('text')}",
                f"总进度: {progress_percent}%",
                "",
                "阶段状态:",
                f"- 年报抓取: {self.stage_state['spider']['status']}",
                f"- 文本提取: {self.stage_state['extract']['status']}",
                "",
                "最近事件:",
            ]
            summary.extend(f"- {item}" for item in self.recent_events[:6])
            self.summary_text.delete("1.0", "end")
            self.summary_text.insert("1.0", "\n".join(summary))
        if hasattr(self, "log_status_cards"):
            self.log_status_cards["mode"].configure(text=self._mode_label(self.current_mode))
            self.log_status_cards["state"].configure(text=self.run_badge.cget("text"))
            self.log_status_cards["progress"].configure(text=f"{progress_percent}%")
        if hasattr(self, "log_progress_bar"):
            progress_value = self._displayed_progress
            state_text = self.run_badge.cget("text")
            progress_color = PRIMARY
            badge_color = PRIMARY_SOFT
            badge_text_color = PRIMARY
            badge_text = "RUN"
            caption = f"{self._mode_label(self.current_mode)} | {state_text}"
            if state_text in {"已完成", "完成"}:
                progress_color = SUCCESS
                badge_color = SUCCESS_SOFT
                badge_text_color = SUCCESS
                badge_text = "DONE"
                caption = f"{self._mode_label(self.current_mode)} 已完成，耗时 {self.kpi_values['elapsed']}"
            elif state_text in {"失败"}:
                progress_color = DANGER
                badge_color = DANGER_SOFT
                badge_text_color = DANGER
                badge_text = "ERR"
                caption = f"{self._mode_label(self.current_mode)} 执行失败"
            elif state_text in {"停止中", "已停止"}:
                progress_color = WARNING
                badge_color = WARNING_SOFT
                badge_text_color = WARNING
                badge_text = "STOP"
                caption = f"{self._mode_label(self.current_mode)} {'停止中，等待退出' if state_text == '停止中' else '已停止'}"
            elif state_text in {"准备启动", "执行中"}:
                badge_text = "LIVE"
            else:
                badge_text = "READY"
            self.log_progress_bar.configure(progress_color=progress_color)
            self.log_progress_bar.set(progress_value)
            self.log_progress_caption.configure(text=caption)
            self.log_progress_badge.configure(
                text=badge_text,
                fg_color=badge_color,
                text_color=badge_text_color,
            )
        self._refresh_charts()

    def _refresh_charts(self) -> None:
        if not hasattr(self, "progress_chart") or not hasattr(self, "stats_chart"):
            return
        self.progress_history["spider"] = self.progress_history["links"]
        now = time.perf_counter()
        if now - self._last_chart_record_at >= 0.28 or not self.progress_history["overall"]:
            for key, value in (
                ("overall", self._displayed_progress),
                ("links", self.stage_state["links"]["progress"]),
                ("pdf", self.stage_state["pdf"]["progress"]),
                ("spider", self.stage_state["spider"]["progress"]),
                ("extract", self.stage_state["extract"]["progress"]),
            ):
                history = self.progress_history[key]
                history.append(max(0.0, min(1.0, float(value))))
                if len(history) > 48:
                    del history[:-48]
            self._last_chart_record_at = now
        self._draw_progress_chart()
        self._draw_stats_chart()

    def _draw_canvas_round_rect(
        self,
        canvas: tk.Canvas,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        radius: float,
        *,
        fill: str,
        outline: str,
        width: int = 1,
    ) -> None:
        radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline=outline, width=width)
        canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline=outline, width=width)
        canvas.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, fill=fill, outline=outline, width=width)
        canvas.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, fill=fill, outline=outline, width=width)
        canvas.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, fill=fill, outline=outline, width=width)
        canvas.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, fill=fill, outline=outline, width=width)

    def _chart_points(self, history: list[float], left: float, top: float, right: float, bottom: float) -> list[tuple[float, float]]:
        if not history:
            return []
        step = (right - left) / max(len(history) - 1, 1)
        return [
            (left + idx * step, bottom - (bottom - top) * max(0.0, min(1.0, value)))
            for idx, value in enumerate(history)
        ]

    def _draw_progress_chart(self) -> None:
        canvas = self.progress_chart
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 278)
        canvas.delete("all")
        canvas.configure(bg=SCREEN_PANEL)

        left, top, right, bottom = 18, 24, width - 188, height - 26
        self._draw_canvas_round_rect(
            canvas,
            left,
            top,
            right,
            bottom,
            18,
            fill="#081726",
            outline=SCREEN_GRID,
            width=1,
        )

        for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = bottom - (bottom - top) * ratio
            canvas.create_line(left + 12, y, right - 12, y, fill=SCREEN_GRID, width=1)
            if ratio < 1.0:
                canvas.create_text(right + 34, y, text=f"{int(ratio * 100)}%", fill=SCREEN_MUTED, font=(FONT_FAMILY, 11, "bold"))

        for x_ratio in (0.2, 0.4, 0.6, 0.8):
            x = left + 12 + (right - left - 24) * x_ratio
            canvas.create_line(x, top + 12, x, bottom - 12, fill="#12304A", width=1)

        overall_points = self._chart_points(self.progress_history["overall"], left + 12, top + 12, right - 12, bottom - 12)
        if len(overall_points) >= 2:
            area_points = [(overall_points[0][0], bottom - 12), *overall_points, (overall_points[-1][0], bottom - 12)]
            flat_area: list[float] = []
            for x, y in area_points:
                flat_area.extend((x, y))
            canvas.create_polygon(*flat_area, fill="#103A63", outline="", smooth=True)
            flat_line: list[float] = []
            for x, y in overall_points:
                flat_line.extend((x, y))
            canvas.create_line(*flat_line, fill=SCREEN_BLUE, width=4, smooth=True)
            last_x, last_y = overall_points[-1]
            canvas.create_oval(last_x - 7, last_y - 7, last_x + 7, last_y + 7, fill=SCREEN_BLUE, outline="#DFF4FF", width=2)

        for key, color in (("spider", SCREEN_CYAN), ("extract", SCREEN_RED)):
            points = self._chart_points(self.progress_history[key], left + 12, top + 12, right - 12, bottom - 12)
            if len(points) >= 2:
                flat_line: list[float] = []
                for x, y in points:
                    flat_line.extend((x, y))
                canvas.create_line(*flat_line, fill=color, width=3, smooth=True, dash=(9, 5))
                last_x, last_y = points[-1]
                canvas.create_oval(last_x - 5, last_y - 5, last_x + 5, last_y + 5, fill=color, outline="#E8F7FF", width=1)

        legend_x = right + 18
        legend_specs = [
            ("总进度", SCREEN_BLUE, self._progress_percent()),
            ("抓取", SCREEN_CYAN, round(self.stage_state["spider"]["progress"] * 100)),
            ("提取", SCREEN_RED, round(self.stage_state["extract"]["progress"] * 100)),
        ]
        for idx, (label, color, value) in enumerate(legend_specs):
            y = top + idx * 72
            self._draw_canvas_round_rect(
                canvas,
                legend_x,
                y,
                width - 16,
                y + 56,
                14,
                fill="#0F2335",
                outline="#18374F",
                width=1,
            )
            canvas.create_rectangle(legend_x + 14, y + 18, legend_x + 32, y + 36, fill=color, outline=color)
            canvas.create_text(legend_x + 44, y + 19, text=label, anchor="w", fill=SCREEN_MUTED, font=(FONT_FAMILY, 11, "bold"))
            canvas.create_text(legend_x + 44, y + 40, text=f"{value}%", anchor="w", fill=SCREEN_TEXT, font=(FONT_FAMILY, 18, "bold"))

    def _draw_stats_chart(self) -> None:
        canvas = self.stats_chart
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 226)
        canvas.delete("all")
        canvas.configure(bg=SCREEN_PANEL_ALT)

        def metric_value(key: str) -> int:
            try:
                return max(0, int(str(self.kpi_values.get(key, "0")).strip().replace(",", "")))
            except Exception:
                return 0

        metrics = [
            ("PDF 总量", metric_value("pdf_total"), SCREEN_BLUE),
            ("提取成功", metric_value("extracted"), SCREEN_GREEN),
            ("失败数量", metric_value("failed"), SCREEN_RED),
        ]
        max_value = max([value for _, value, _ in metrics] + [1])
        left, top, right = 20, 22, width - 20
        row_height = 62

        for idx, (label, value, color) in enumerate(metrics):
            y1 = top + idx * row_height
            y2 = y1 + 42
            bar_left = left + 118
            bar_right = right - 60
            fill_ratio = value / max_value if max_value else 0.0
            fill_right = bar_left + (bar_right - bar_left) * fill_ratio

            canvas.create_text(left, y1 + 21, text=label, anchor="w", fill=SCREEN_MUTED, font=(FONT_FAMILY, 12, "bold"))
            self._draw_canvas_round_rect(
                canvas,
                bar_left,
                y1 + 6,
                bar_right,
                y2 - 6,
                10,
                fill="#0A1B2B",
                outline="#17344A",
                width=1,
            )
            if fill_right > bar_left:
                self._draw_canvas_round_rect(
                    canvas,
                    bar_left,
                    y1 + 6,
                    fill_right,
                    y2 - 6,
                    10,
                    fill=color,
                    outline=color,
                    width=1,
                )
            canvas.create_text(right - 8, y1 + 21, text=str(value), anchor="e", fill=SCREEN_TEXT, font=(FONT_FAMILY, 16, "bold"))

        summary_y = top + len(metrics) * row_height + 10
        canvas.create_text(left, summary_y, text="当前峰值基准", anchor="w", fill=SCREEN_MUTED, font=(FONT_FAMILY, 11))
        canvas.create_text(right - 8, summary_y, text=str(max_value), anchor="e", fill=SCREEN_TEXT, font=(FONT_FAMILY, 11, "bold"))

    def _schedule_command_refresh(self) -> None:
        if self._command_refresh_pending:
            return
        self._command_refresh_pending = True
        self.after(80, self._refresh_command_page)

    def _set_progress_target(self, value: float, *, immediate: bool = False) -> None:
        bounded = max(0.0, min(value, 1.0))
        self._progress_target = 1.0 if bounded >= 0.995 else bounded
        if immediate:
            self._displayed_progress = self._progress_target
            self._sync_progress_widgets()
            self._schedule_command_refresh()
            return
        self._ensure_progress_animation()

    def _progress_percent(self) -> int:
        progress = 1.0 if self._displayed_progress >= 0.995 else self._displayed_progress
        return max(0, min(100, round(progress * 100)))

    def _sync_progress_widgets(self) -> None:
        if hasattr(self, "overall_progress"):
            self.overall_progress.set(self._displayed_progress)
        if hasattr(self, "log_progress_bar"):
            self.log_progress_bar.set(self._displayed_progress)
        if hasattr(self, "log_status_cards"):
            self.log_status_cards["progress"].configure(text=f"{self._progress_percent()}%")

    def _ensure_progress_animation(self) -> None:
        if self._progress_animation_pending:
            return
        self._progress_animation_pending = True
        self.after(24, self._animate_progress_bars)

    def _animate_progress_bars(self) -> None:
        delta = self._progress_target - self._displayed_progress
        if self._progress_target >= 1.0 and self._displayed_progress >= 0.985:
            self._displayed_progress = 1.0
        elif abs(delta) < 0.004:
            self._displayed_progress = self._progress_target
        else:
            step = max(0.01, min(abs(delta) * 0.22, 0.08))
            self._displayed_progress += step if delta > 0 else -step
            if self._progress_target >= 1.0 and self._displayed_progress >= 0.985:
                self._displayed_progress = 1.0

        self._sync_progress_widgets()
        self._schedule_command_refresh()

        if abs(self._progress_target - self._displayed_progress) < 0.004:
            self._progress_animation_pending = False
        else:
            self.after(24, self._animate_progress_bars)

    def _mode_label(self, mode: str) -> str:
        return {
            "pipeline": "一键三步全流程",
            "links": "公告链接抓取",
            "pdf": "PDF 文件爬取",
            "extract": "文本提取",
        }.get(mode, mode)
        return {
            "pipeline": "全流程",
            "spider": "仅抓取",
            "extract": "仅提取",
        }.get(mode, mode)

    def start_run(self, mode: str) -> None:
        if self._run_start_pending or (self.worker is not None and self.worker.is_alive()):
            return
        self._run_start_pending = True
        self.current_mode = mode
        self._clear_runtime_view()
        self.show_page("logs")
        self.run_badge.configure(text="准备启动", fg_color=PRIMARY, text_color="white")
        self.overall_status.configure(text=f"{self._mode_label(mode)}准备中")
        self.kpi_values["run_mode"] = self._mode_label(mode)
        self._set_running_state(True)
        self._append_log("STATUS", f"开始准备: {self._mode_label(mode)}", tag="status")
        self._set_alert_state("info", "正在准备任务", f"{self._mode_label(mode)} 的参数校验和线程启动即将开始。")
        self._refresh_command_page()
        self.configure(cursor="watch")
        self.after(20, lambda run_mode=mode: self._prepare_run_start(run_mode))

    def _prepare_run_start(self, mode: str) -> None:
        try:
            self._collect_settings_from_form()
            if self.settings.workspace.start_year > self.settings.workspace.end_year:
                raise ValueError("开始年份不能大于结束年份")
            if False and mode == "pipeline" and self.spider_mode != "download":
                raise ValueError("一键全流程要求抓取模式为“抓取并下载PDF”。")
            save_settings(self.settings)
            self._refresh_strategy_preview()
        except Exception as exc:
            self._run_start_pending = False
            self.configure(cursor="")
            self.run_badge.configure(text="系统空闲", fg_color=SURFACE_ALT, text_color=TEXT)
            self.overall_status.configure(text="等待执行")
            self._set_running_state(False)
            self._set_alert_state("error", "参数错误", str(exc))
            messagebox.showerror("参数错误", str(exc))
            return

        self.run_badge.configure(text="执行中", fg_color=PRIMARY, text_color="white")
        self.overall_status.configure(text=f"{self._mode_label(mode)}已启动")
        self._append_log("STATUS", f"开始执行: {self._mode_label(mode)}", tag="status")
        self._refresh_command_page()
        self.after(20, lambda run_mode=mode: self._launch_worker(run_mode))

    def _launch_worker(self, mode: str) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        self._run_start_pending = False
        self.configure(cursor="")
        self.worker = ExecutionWorker(queue=self.event_queue, mode=mode, settings=self.settings)
        self.worker.start()

    def stop_run(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            return
        self.worker.cancel()
        self.stop_btn.configure(state="disabled")
        self.run_badge.configure(text="停止中", fg_color=WARNING, text_color="white")
        self.overall_status.configure(text="停止中，等待后台退出")
        self._append_log("STATUS", "已发出停止请求，等待后台任务退出。", tag="status")
        self._set_alert_state("warning", "停止请求已发送", "已请求停止任务，等待后台清理。")

    def _set_running_state(self, running: bool) -> None:
        pipeline_state = "disabled" if running else "normal"
        start_state = "disabled" if running else "normal"
        stop_state = "normal" if running else "disabled"
        self.start_pipeline_btn.configure(state=pipeline_state)
        self.start_spider_btn.configure(state=start_state)
        self.start_pdf_btn.configure(state=start_state)
        self.start_extract_btn.configure(state=start_state)
        self.stop_btn.configure(state=stop_state)

    def _clear_runtime_view(self) -> None:
        self._set_progress_target(0.0, immediate=True)
        self._last_link_ui_update = 0.0
        self._last_pdf_ui_update = 0.0
        self._last_extract_ui_update = 0.0
        for stage in ("links", "pdf", "extract"):
            self.stage_state[stage] = {"status": "待命", "progress": 0.0}
            self._set_stage_visual(stage, "待命", 0.0, "尚未开始")
        self.stage_state["spider"] = self.stage_state["links"]
        self.kpi_values.update({"pdf_total": "0", "extracted": "0", "failed": "0", "elapsed": "0s"})
        self.recent_events.clear()
        self._set_alert_state("idle", "系统提醒", "暂无异常，准备执行。")
        self._schedule_command_refresh()
        return
        self._set_progress_target(0.0, immediate=True)
        self._last_spider_ui_update = 0.0
        self._last_extract_ui_update = 0.0
        for stage in ("spider", "extract"):
            self.stage_state[stage] = {"status": "待命", "progress": 0.0}
            self._set_stage_visual(stage, "待命", 0.0, "尚未开始")
        self.kpi_values.update({"pdf_total": "0", "extracted": "0", "failed": "0", "elapsed": "0s"})
        self.recent_events.clear()
        self._set_alert_state("idle", "系统提醒", "暂无异常，准备执行。")
        self._schedule_command_refresh()

    def _set_stage_visual(self, stage: str, status: str, progress: float, message: str) -> None:
        card = self.stage_cards[stage]
        badge = card["badge"]
        icon = card["icon"]
        bar = card["progress"]
        subtitle = card["subtitle"]
        msg = card["message"]
        footer = card["footer"]
        self.stage_state[stage] = {"status": status, "progress": progress}
        bounded_progress = max(0.0, min(progress, 1.0))
        bar.set(bounded_progress)
        if status in {"完成", "成功"}:
            badge.configure(text=status, fg_color="#DCFCE7", text_color=SUCCESS)
            icon.configure(fg_color=SUCCESS_SOFT, text_color=SUCCESS)
            subtitle.configure(text="阶段已完成", text_color=SUCCESS)
        elif status in {"运行中", "处理中"}:
            badge.configure(text=status, fg_color="#DBEAFE", text_color=PRIMARY)
            icon.configure(fg_color=PRIMARY_SOFT, text_color=PRIMARY)
            subtitle.configure(text="后台执行中", text_color=PRIMARY)
        elif status in {"已停止", "失败"}:
            badge.configure(text=status, fg_color="#FEE2E2", text_color=DANGER)
            icon.configure(fg_color=DANGER_SOFT, text_color=DANGER)
            subtitle.configure(text="需要关注", text_color=DANGER)
        else:
            badge.configure(text=status, fg_color=SURFACE, text_color=TEXT_MUTED)
            icon.configure(fg_color=SURFACE, text_color=TEXT_MUTED)
            subtitle.configure(text="等待执行", text_color=TEXT_MUTED)
        msg.configure(text=message)
        footer.configure(text=f"{int(bounded_progress * 100)}% | {status}")
        self._update_overall_progress()

    def _update_overall_progress(self) -> None:
        links_progress = self.stage_state["links"]["progress"]
        pdf_progress = self.stage_state["pdf"]["progress"]
        extract_progress = self.stage_state["extract"]["progress"]
        if self.current_mode == "links":
            overall = links_progress
        elif self.current_mode == "pdf":
            overall = pdf_progress
        elif self.current_mode == "extract":
            overall = extract_progress
        else:
            overall = links_progress * 0.25 + pdf_progress * 0.45 + extract_progress * 0.30
        self._set_progress_target(overall)
        return
        spider_progress = self.stage_state["spider"]["progress"]
        extract_progress = self.stage_state["extract"]["progress"]
        if self.current_mode == "spider":
            overall = spider_progress
        elif self.current_mode == "extract":
            overall = extract_progress
        else:
            overall = spider_progress * 0.45 + extract_progress * 0.55
        self._set_progress_target(overall)

    def _push_recent_event(self, text: str) -> None:
        self.recent_events.insert(0, text)
        self.recent_events = self.recent_events[:8]
        self._schedule_command_refresh()

    def _append_log(self, level: str, message: str, *, tag: str | None = None, timestamp: str | None = None) -> None:
        timestamp = timestamp or ""
        level_upper = level.upper()
        if tag is None:
            if level_upper in {"ERROR", "WARNING", "STATUS"}:
                tag = "error" if level_upper == "ERROR" else "warning" if level_upper == "WARNING" else "status"
            else:
                tag = "default"
        self.log_text.configure(state="normal")
        if timestamp:
            self.log_text.insert("end", f"[{timestamp}] ", ("timestamp",))
        self.log_text.insert("end", f"[{level_upper}] ", (tag,))
        self.log_text.insert("end", f"{message}\n", (tag if tag != "default" else "default",))
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _drain_event_queue(self) -> None:
        processed = 0
        max_events_per_tick = 24
        while processed < max_events_per_tick:
            try:
                event = self.event_queue.get_nowait()
            except Empty:
                break
            self._handle_event(event)
            processed += 1
        next_delay = 15 if processed >= max_events_per_tick else 45
        self.after(next_delay, self._drain_event_queue)

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event")
        timestamp = event.get("timestamp", "")
        if event_type == "run_started":
            self._push_recent_event(f"{timestamp} 启动 {self._mode_label(event['mode'])}")
            self.overall_status.configure(text=f"{self._mode_label(event['mode'])}运行中")
            self._set_alert_state("info", "任务已启动", f"当前模式: {self._mode_label(event['mode'])}")
        elif event_type == "stage_started":
            stage = event["stage"]
            self._set_stage_visual(stage, "运行中", 0.05, f"{event.get('title', stage)}已启动")
            self._push_recent_event(f"{timestamp} 启动阶段: {stage}")
            self._append_log("STATUS", f"{event.get('title', stage)}已启动", tag="status", timestamp=timestamp)
        elif event_type == "stage_notice":
            self._append_log("STATUS", event["message"], tag="status", timestamp=timestamp)
            self._set_alert_state("warning", "阶段提示", event["message"])
        elif event_type == "log":
            self._append_log(event.get("level", "INFO"), event.get("message", ""), timestamp=timestamp)
        elif event_type == "link_progress":
            self._handle_link_progress(event["payload"], timestamp)
        elif event_type == "pdf_progress":
            self._handle_pdf_progress(event["payload"], timestamp)
        elif event_type == "spider_progress":
            self._handle_link_progress(event["payload"], timestamp)
        elif event_type == "extract_progress":
            self._handle_extract_progress(event["payload"], timestamp)
        elif event_type == "stage_completed":
            self._handle_stage_completed(event["stage"], event["payload"], timestamp)
        elif event_type == "run_completed":
            self._handle_run_completed(event, timestamp)
        elif event_type == "run_stopped":
            self._finish_running_state("已停止", DANGER, f"任务已停止，用时 {self._format_seconds(event.get('elapsed_seconds', 0))}")
        elif event_type == "run_error":
            error_message = event.get("error", "未知错误")
            self._set_alert_state("error", "执行失败", error_message)
            self._append_log("ERROR", error_message, timestamp=timestamp)
            self._finish_running_state("失败", DANGER, f"任务失败，用时 {self._format_seconds(event.get('elapsed_seconds', 0))}")

    def _handle_link_progress(self, payload: dict[str, Any], timestamp: str) -> None:
        phase = payload.get("phase")
        if phase == "done":
            self._set_stage_visual("links", "完成", 1.0, f"链接抓取完成，用时 {self._format_seconds(payload.get('elapsed_seconds', 0))}")
            self._push_recent_event(f"{timestamp} 公告链接抓取完成")
            self._set_alert_state("info", "链接抓取完成", "公告链接抓取阶段已完成。")
        elif phase == "log":
            now = time.perf_counter()
            if now - self._last_link_ui_update >= 0.18:
                self._last_link_ui_update = now
                current = self.stage_state["links"]["progress"]
                next_progress = min(max(current, 0.12) + 0.03, 0.9)
                self._set_stage_visual("links", "运行中", next_progress, payload.get("message", "抓取中"))
        self._schedule_command_refresh()

    def _handle_pdf_progress(self, payload: dict[str, Any], timestamp: str) -> None:
        phase = payload.get("phase")
        if phase == "prepare":
            total = max(int(payload.get("total", 0)), 0)
            self.kpi_values["pdf_total"] = str(payload.get("pdf_total", 0))
            message = f"待下载 {total}，已存在 {payload.get('exists', 0)}，跳过 {payload.get('skipped', 0)}"
            self._set_stage_visual("pdf", "运行中", 0.05 if total else 1.0, message)
            self._push_recent_event(f"{timestamp} PDF 下载准备完成")
        elif phase == "download":
            now = time.perf_counter()
            total = max(int(payload.get("total", 0)), 1)
            completed = int(payload.get("completed", 0))
            progress = completed / total if total else 1.0
            self.kpi_values["pdf_total"] = str(payload.get("pdf_total", self.kpi_values["pdf_total"]))
            self.kpi_values["failed"] = str(payload.get("failed", self.kpi_values["failed"]))
            message = payload.get("current_title") or f"{completed}/{total}"
            if now - self._last_pdf_ui_update >= 0.12 or completed >= total:
                self._last_pdf_ui_update = now
                self._set_stage_visual("pdf", "运行中", progress, message)
        elif phase == "done":
            self.kpi_values["pdf_total"] = str(payload.get("pdf_total", self.kpi_values["pdf_total"]))
            self.kpi_values["failed"] = str(payload.get("failed", self.kpi_values["failed"]))
            self._set_stage_visual("pdf", "完成", 1.0, "PDF 文件爬取完成")
            self._push_recent_event(f"{timestamp} PDF 文件爬取完成")
            self._set_alert_state("info", "PDF 下载完成", "PDF 文件爬取阶段已完成。")
        self._schedule_command_refresh()

    def _handle_spider_progress(self, payload: dict[str, Any], timestamp: str) -> None:
        phase = payload.get("phase")
        if phase == "done":
            self._set_stage_visual("spider", "完成", 1.0, f"抓取完成，用时 {self._format_seconds(payload.get('elapsed_seconds', 0))}")
            self._push_recent_event(f"{timestamp} 年报抓取完成")
            self._set_alert_state("info", "抓取完成", "年报抓取阶段已完成，正在等待下一阶段或汇总。")
        elif phase == "log":
            now = time.perf_counter()
            if now - self._last_spider_ui_update >= 0.18:
                self._last_spider_ui_update = now
                current = self.stage_state["spider"]["progress"]
                next_progress = min(max(current, 0.12) + 0.03, 0.9)
                self._set_stage_visual("spider", "运行中", next_progress, payload.get("message", "抓取中"))

    def _handle_extract_progress(self, payload: dict[str, Any], timestamp: str) -> None:
        phase = payload.get("phase")
        if phase == "prepare":
            total = max(int(payload.get("total", 0)), 1)
            existing = int(payload.get("existing", 0))
            pdf_total = int(payload.get("pdf_total", 0))
            self.kpi_values["pdf_total"] = str(pdf_total)
            self._set_stage_visual("extract", "运行中", 0.05 if total else 1.0, f"待提取 {payload.get('total', 0)}，已存在 {existing}")
            self._push_recent_event(f"{timestamp} 文本提取准备完成")
        elif phase == "extract":
            now = time.perf_counter()
            total = max(int(payload.get("total", 0)), 1)
            completed = int(payload.get("completed", 0))
            extracted = int(payload.get("extracted", 0))
            failed = int(payload.get("failed", 0))
            progress = completed / total if total else 1.0
            current_pdf = payload.get("current_pdf", "")
            self.kpi_values["extracted"] = str(extracted)
            self.kpi_values["failed"] = str(failed)
            if now - self._last_extract_ui_update >= 0.12 or completed >= total:
                self._last_extract_ui_update = now
                self._set_stage_visual("extract", "运行中", progress, current_pdf or f"{completed}/{total}")
        elif phase == "done":
            self.kpi_values["extracted"] = str(payload.get("extracted", 0))
            self.kpi_values["failed"] = str(payload.get("failed", 0))
            self._set_stage_visual("extract", "完成", 1.0, "文本提取完成")
            self._push_recent_event(f"{timestamp} 文本提取完成")
            self._set_alert_state("info", "提取完成", "文本提取阶段已完成，摘要数据已同步到状态卡与本地 summary。")
        self._schedule_command_refresh()

    def _handle_stage_completed(self, stage: str, payload: dict[str, Any], timestamp: str) -> None:
        if stage == "links":
            self.spider_preview_rows = payload.get("preview", [])
            self.kpi_values["pdf_total"] = str(payload.get("rows", 0))
            self._set_alert_state("info", "链接摘要已更新", payload.get("summary_path", "无"))
            self._push_recent_event(f"{timestamp} 阶段完成: links")
            self.reload_results()
            self._schedule_command_refresh()
            return
        if stage == "pdf":
            self.kpi_values["pdf_total"] = str(payload.get("pdf_total", self.kpi_values["pdf_total"]))
            self.kpi_values["failed"] = str(payload.get("failed", 0))
            self._set_alert_state("info", "PDF 摘要已更新", payload.get("summary_path", "无"))
            self._push_recent_event(f"{timestamp} 阶段完成: pdf")
            self.reload_results()
            self._schedule_command_refresh()
            return
        if stage == "spider":
            self.spider_preview_rows = payload.get("preview", [])
            self.kpi_values["pdf_total"] = str(payload.get("rows", 0))
            self._set_alert_state("info", "抓取摘要已更新", payload.get("summary_path", "无"))
        elif stage == "extract":
            self.extract_summary = payload.get("summary", {})
            self.kpi_values["pdf_total"] = str(payload.get("pdf_total", self.kpi_values["pdf_total"]))
            self.kpi_values["extracted"] = str(payload.get("extracted", 0))
            self.kpi_values["failed"] = str(payload.get("failed", 0))
            self._set_alert_state("info", "提取摘要已更新", payload.get("summary_path", "无"))
        self._push_recent_event(f"{timestamp} 阶段完成: {stage}")
        self.reload_results()
        self._schedule_command_refresh()

    def _handle_run_completed(self, event: dict[str, Any], timestamp: str) -> None:
        elapsed = self._format_seconds(event.get("elapsed_seconds", 0))
        self.kpi_values["elapsed"] = elapsed
        self._set_progress_target(1.0, immediate=True)
        self.overall_status.configure(text=f"{self._mode_label(event['mode'])}执行完成")
        self._append_log("STATUS", f"任务完成，总耗时 {elapsed}", tag="status", timestamp=timestamp)
        self._push_recent_event(f"{timestamp} 全部完成")
        self._set_alert_state("success", "任务完成", f"总耗时 {elapsed}")
        self._finish_running_state("已完成", SUCCESS, f"任务完成，总耗时 {elapsed}")

    def _finish_running_state(self, badge_text: str, badge_color: str, status_text: str) -> None:
        self._run_start_pending = False
        self.configure(cursor="")
        self.run_badge.configure(text=badge_text, fg_color=badge_color, text_color="white")
        self.overall_status.configure(text=status_text)
        if badge_text == "已停止":
            for stage in ("links", "pdf", "extract"):
                if self.stage_state.get(stage, {}).get("status") == "运行中":
                    self._set_stage_visual(stage, "已停止", self.stage_state[stage]["progress"], "已停止")
            self._set_alert_state("warning", "任务已停止", status_text)
        elif badge_text == "失败":
            for stage in ("extract", "pdf", "links"):
                if self.stage_state.get(stage, {}).get("status") == "运行中":
                    self._set_stage_visual(stage, "失败", self.stage_state[stage]["progress"], "执行失败")
                    break
            self._set_alert_state("error", "任务失败", status_text)
        self._set_running_state(False)
        self.worker = None
        self._refresh_command_page()
        return
        self._run_start_pending = False
        self.configure(cursor="")
        self.run_badge.configure(text=badge_text, fg_color=badge_color, text_color="white")
        self.overall_status.configure(text=status_text)
        if badge_text == "已停止":
            if self.current_mode == "pipeline":
                if self.stage_state["spider"]["status"] == "运行中":
                    self._set_stage_visual("spider", "已停止", self.stage_state["spider"]["progress"], "已停止")
                if self.stage_state["extract"]["status"] == "运行中":
                    self._set_stage_visual("extract", "已停止", self.stage_state["extract"]["progress"], "已停止")
            self._set_alert_state("warning", "任务已停止", status_text)
        elif badge_text == "失败":
            if self.stage_state["extract"]["status"] == "运行中":
                self._set_stage_visual("extract", "失败", self.stage_state["extract"]["progress"], "执行失败")
            elif self.stage_state["spider"]["status"] == "运行中":
                self._set_stage_visual("spider", "失败", self.stage_state["spider"]["progress"], "执行失败")
            self._set_alert_state("error", "任务失败", status_text)
        self._set_running_state(False)
        self.worker = None
        self._refresh_command_page()

    def _format_seconds(self, seconds: Any) -> str:
        try:
            value = max(float(seconds), 0.0)
        except Exception:
            return "0s"
        if value < 60:
            return f"{value:.1f}s"
        minutes, remain = divmod(int(value), 60)
        if minutes < 60:
            return f"{minutes}m {remain}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"

    def reload_results(self) -> None:
        workspace = self.settings.workspace
        project_root = workspace.project_root
        spider_summary_path = resolve_path(project_root, workspace.annual_report_dir) / "summary.json"
        extract_summary_path = resolve_path(project_root, workspace.text_output_dir) / "text_extract_summary.json"

        self.spider_preview_rows = []
        self.extract_summary = {}

        if spider_summary_path.exists():
            try:
                payload = json.loads(spider_summary_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    self.spider_preview_rows = payload[:200]
            except Exception:
                pass
        if extract_summary_path.exists():
            try:
                payload = json.loads(extract_summary_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self.extract_summary = payload
            except Exception:
                pass
        if self.extract_summary and self.kpi_values["pdf_total"] == "0":
            self.kpi_values["pdf_total"] = str(self.extract_summary.get("pdf_total", 0))
            self.kpi_values["extracted"] = str(self.extract_summary.get("extracted", 0))
            self.kpi_values["failed"] = str(self.extract_summary.get("failed", 0))
        self._schedule_command_refresh()

    def _switch_result_dataset(self, label: str) -> None:
        self.result_dataset = "spider" if label == "抓取摘要" else "extract"
        self._render_results()

    def _render_results(self) -> None:
        if self.result_dataset == "spider":
            rows = self.spider_preview_rows
            result_path = resolve_path(self.settings.workspace.project_root, self.settings.workspace.annual_report_dir) / "summary.json"
            if rows:
                headers = sorted({key for row in rows for key in row.keys()})
                matrix = [[row.get(key, "") for key in headers] for row in rows]
                self.result_hint.configure(text=f"抓取摘要来源: {result_path}")
                self._render_sheet(headers, matrix)
            else:
                self.result_hint.configure(text=f"抓取摘要来源: {result_path}")
                self._render_text("暂无抓取摘要数据。")
        else:
            result_path = resolve_path(self.settings.workspace.project_root, self.settings.workspace.text_output_dir) / "text_extract_summary.json"
            if self.extract_summary:
                headers = ["字段", "值"]
                matrix = [[key, self.extract_summary.get(key, "")] for key in sorted(self.extract_summary.keys())]
                self.result_hint.configure(text=f"提取摘要来源: {result_path}")
                self._render_sheet(headers, matrix)
            else:
                self.result_hint.configure(text=f"提取摘要来源: {result_path}")
                self._render_text("暂无提取摘要数据。")

    def _render_sheet(self, headers: list[str], matrix: list[list[Any]]) -> None:
        if self.result_sheet is not None:
            self.result_fallback.grid_remove()
            self.result_sheet.grid()
            self.result_sheet.headers(headers)
            self.result_sheet.set_sheet_data(matrix)
            self.result_sheet.refresh()
        else:
            lines = ["\t".join(headers)]
            lines.extend("\t".join(map(str, row)) for row in matrix)
            self._render_text("\n".join(lines))

    def _render_text(self, text: str) -> None:
        if self.result_sheet is not None:
            self.result_sheet.grid_remove()
        self.result_fallback.grid()
        self.result_fallback.delete("1.0", "end")
        self.result_fallback.insert("1.0", text)


def launch() -> None:
    app = EnterpriseConsoleApp()
    app.mainloop()
