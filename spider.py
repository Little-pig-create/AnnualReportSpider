"""
巨潮资讯网 - A股年报PDF下载爬虫 (v4)

参考 cninfo_annual_report_spider.py 重构，核心改进：
  1. plate="sz;szmb;szcy;sh;shmb;shkcp" 一次查全部板块
  2. 自动日期分片：按月查询，超阈值自动拆到按天，绕开100页API上限
  3. asyncio + aiohttp 异步并发下载
  4. 页级断点续传 + 重复页检测
  5. 修订版优先级排序
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Callable
from urllib.parse import urljoin

import requests

try:
    import aiohttp
except ModuleNotFoundError:
    aiohttp = None

# ==================== 常量 ====================

API_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
SEARCH_PAGE_URL = "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search&lastPage=index"
PDF_HOST = "https://static.cninfo.com.cn/"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": SEARCH_PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
}
DOWNLOAD_HEADERS = {
    "User-Agent": DEFAULT_HEADERS["User-Agent"],
    "Referer": SEARCH_PAGE_URL,
    "Accept": "application/pdf,*/*",
}

# 全部A股板块（一次查询覆盖沪深所有板块）
ALL_PLATES = "sz;szmb;szcy;sh;shmb;shkcp"

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

# 修订版本关键词，按优先级从高到低排列
REVISION_KEYWORDS = ("二次修订", "修订版", "修订稿", "修订", "修正稿", "更正版", "更正后", "更正", "更新后", "更新")

# 排除关键词
EXCLUDE_KEYWORDS = ("摘要", "英文", "外文", "已取消", "取消", "半年度", "季度", "中期",
                    "审计报告", "内部控制", "社会责任", "致歉",
                    "Environmental", "Social", "CSR", "ESG", "sustainability",
                    "H股", "审阅", "补遗")

# 会提到“年度报告”但实际不是正文 PDF 的附件类关键词
ATTACHMENT_KEYWORDS = (
    "书面确认意见",
    "确认意见",
    "独立意见",
    "书面审核意见",
    "审核意见",
    "核查意见",
    "回复",
    "问询函",
    "工作函",
    "关注函",
    "监管函",
    "议案",
    "审议",
    "公告",
    "说明",
    "董事会",
    "监事会",
    "独立董事",
    "董事、监事",
    "高级管理人员",
    "审计委员会",
    "会计师事务所",
)

YEAR_IN_REPORT_TITLE_RE = re.compile(r"(?<!\d)(20\d{2})(?:年|[_\-—–:：]){0,3}年度报告")
REPORT_TITLE_SUFFIX_RE = r"(?:全文)?(?:_?合并报告)?(?:[（(][^）)]*[）)])?"

# 自动拆分阈值：月级查询超过此页数时，自动拆到日级
AUTO_SPLIT_THRESHOLD = 12

MIN_VALID_PDF_SIZE = 1024
PDF_CHUNK_SIZE = 256 * 1024
PERMANENT_DOWNLOAD_HTTP_STATUSES = {404, 410}
AUDIT_SAMPLE_LIMIT = 50
PDF_AUDIT_REPORT_NAME = "pdf_audit_report.json"
PDF_AUDIT_AFTER_CLEANUP_REPORT_NAME = "pdf_audit_after_cleanup.json"
NON_TARGET_PDF_CLEANUP_REPORT_NAME = "non_target_pdf_cleanup_report.json"
ANNOUNCEMENT_ID_IN_FILENAME_RE = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)
DELETABLE_ORPHAN_CATEGORY = "same_sec_code_newer_target_exists"
PRESERVED_NON_TARGET_CATEGORY = "same_year_no_target_sec_code"
REPLACED_REPORTS_MANIFEST_NAME = "replaced_announcements.jsonl"
REPLACED_REPORTS_METADATA_NAME = "replaced_metadata.csv"
REPLACED_PDF_DIRNAME = "replaced_pdfs"
DOWNLOAD_FAILURES_NAME = "download_failures.jsonl"
LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[dict[str, Any]], None]
CancelCallback = Callable[[], bool]
_cancel_requested_hook: CancelCallback | None = None


@dataclass(slots=True)
class SpiderConfig:
    start_year: int = 2014
    end_year: int = 2024
    se_date: str | None = None
    page_size: int = 30
    request_interval: float = 0.2
    announcement_concurrency: int = 8
    download_concurrency: int = 8
    output_dir: str = "annual_reports"
    state_dir: str = "."
    download_pdf: bool = False
    metadata_only: bool = False
    audit_pdf: bool = False
    cleanup_orphan_pdf: bool = False


@dataclass(slots=True)
class SpiderResult:
    mode: str
    output_dir: Path
    state_dir: Path
    summary_path: Path | None
    summary: list[dict[str, Any]] | None
    elapsed_seconds: float


@dataclass(slots=True)
class PdfDownloadResult:
    output_dir: Path
    state_dir: Path
    summary_path: Path | None
    summary: list[dict[str, Any]] | None
    elapsed_seconds: float
    pdf_total: int
    downloaded: int
    exists: int
    failed: int
    skipped: int


class SpiderCancelled(Exception):
    """Raised when a GUI-driven spider task is cancelled."""


# ==================== 工具函数 ====================

def raise_if_cancelled() -> None:
    if _cancel_requested_hook is not None and _cancel_requested_hook():
        raise SpiderCancelled("spider cancelled")


def sleep_with_cancel(seconds: float) -> None:
    deadline = time.perf_counter() + max(seconds, 0.0)
    while True:
        raise_if_cancelled()
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


async def async_sleep_with_cancel(seconds: float) -> None:
    deadline = time.perf_counter() + max(seconds, 0.0)
    while True:
        raise_if_cancelled()
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        await asyncio.sleep(min(0.2, remaining))


def log(level: str, msg: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{level}] {now} {msg}", flush=True)


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub("", HTML_TAG_RE.sub("", text or "")).strip()


def safe_filename(name: str, max_len: int = 200) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', '_', name).strip(" .")
    return cleaned[:max_len] if len(cleaned) > max_len else cleaned


def extract_year_from_title(title: str) -> Optional[int]:
    """从标题提取报告年份，如 '2023年年度报告' / '2023年度报告' -> 2023"""
    m = YEAR_IN_REPORT_TITLE_RE.search(normalize_text(title))
    return int(m.group(1)) if m else None


def matches_primary_annual_report_title(text: str, year: int) -> bool:
    return bool(re.fullmatch(
        rf".*?{year}(?:年|[_\-—–:：]){{0,3}}年度报告{REPORT_TITLE_SUFFIX_RE}",
        text,
    ))


def matches_fallback_annual_report_title(text: str) -> bool:
    return bool(re.fullmatch(rf".*?年度报告{REPORT_TITLE_SUFFIX_RE}", text))


def annual_report_title_priority(title: str, year: int) -> int:
    text = normalize_text(title)
    if "年度报告" not in text:
        return 0
    if any(kw in text for kw in EXCLUDE_KEYWORDS):
        return 0
    if any(kw in text for kw in ATTACHMENT_KEYWORDS):
        return 0
    if matches_primary_annual_report_title(text, year):
        return 2
    if matches_fallback_annual_report_title(text):
        return 1
    return 0


def is_annual_report(title: str, year: int) -> bool:
    """判断是否为目标年份的正式年报"""
    return annual_report_title_priority(title, year) > 0


def revision_priority(title: str) -> int:
    """修订版本优先级，值越大越优先"""
    text = normalize_text(title)
    for idx, kw in enumerate(REVISION_KEYWORDS):
        if kw in text:
            return len(REVISION_KEYWORDS) - idx
    return 0


def announcement_id_priority(announcement_id: str) -> int:
    try:
        return int((announcement_id or "").strip())
    except (TypeError, ValueError):
        return -1


def report_preference_key(item: ReportItem) -> tuple[int, int, int, int]:
    return (
        announcement_id_priority(item.announcement_id),
        annual_report_title_priority(item.announcement_title, item.report_year),
        revision_priority(item.announcement_title),
        item.announcement_time,
    )


def should_replace_report(old: ReportItem, new: ReportItem) -> bool:
    return report_preference_key(new) > report_preference_key(old)


def page_signature(items: list[dict]) -> str:
    """计算页内容签名，用于检测重复页"""
    if not items:
        return "EMPTY"
    tokens = []
    for ann in items[:10]:
        aid = str(ann.get("announcementId", ""))
        ts = str(ann.get("announcementTime", ""))
        tokens.append(f"{aid}:{ts}")
    return "|".join(tokens)


def _log_matched_reports(announcements: list[dict], report_year: int) -> int:
    """统计当前页命中的正式年报数量。"""
    matched = 0
    for ann in announcements:
        title = str(ann.get("announcementTitle", ""))
        if is_annual_report(title, report_year):
            matched += 1
    return matched


# ==================== 日期分片 ====================

def parse_se_date(se_date: str) -> tuple[date, date]:
    s, e = [x.strip() for x in se_date.split("~", 1)]
    return datetime.strptime(s, "%Y-%m-%d").date(), datetime.strptime(e, "%Y-%m-%d").date()


def format_se_date(start: date, end: date) -> str:
    return f"{start:%Y-%m-%d}~{end:%Y-%m-%d}"


def default_se_date(report_year: int) -> str:
    """单个报告年度默认抓取窗口。"""
    return f"{report_year + 1}-01-01~{report_year + 2}-06-30"


def default_se_date_for_year_range(start_year: int, end_year: int) -> str:
    """连续报告年度区间的整体默认覆盖窗口。"""
    return f"{start_year + 1}-01-01~{end_year + 2}-06-30"


def format_report_year_range(start_year: int, end_year: int) -> str:
    if start_year == end_year:
        return str(start_year)
    return f"{start_year}-{end_year}"


def split_monthly(se_date: str) -> list[str]:
    start, end = parse_se_date(se_date)
    ranges = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        next_m = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
        ranges.append(format_se_date(max(cur, start), min(next_m - timedelta(days=1), end)))
        cur = next_m
    return ranges


def split_daily(se_date: str) -> list[str]:
    start, end = parse_se_date(se_date)
    ranges = []
    cur = start
    while cur <= end:
        ranges.append(format_se_date(cur, cur))
        cur += timedelta(days=1)
    return ranges


# ==================== 数据类 ====================

@dataclass
class ReportItem:
    report_year: int
    sec_code: str
    sec_name: str
    announcement_id: str
    announcement_title: str
    announcement_time: int
    adjunct_url: str

    @property
    def pdf_url(self) -> str:
        return urljoin(PDF_HOST, self.adjunct_url)

    @property
    def filename(self) -> str:
        parts = [self.sec_code, self.sec_name, self.announcement_title]
        if self.announcement_id:
            parts.append(self.announcement_id)
        return safe_filename("_".join(parts) + ".pdf")

    @property
    def legacy_filename(self) -> str:
        return safe_filename(
            f"{self.sec_code}_{self.sec_name}_{self.announcement_title}.pdf"
        )


@dataclass
class FilteredOutItem:
    report_year: int
    sec_code: str
    sec_name: str
    announcement_id: str
    announcement_title: str
    announcement_time: int
    adjunct_url: str
    filter_reason: str


@dataclass
class YearOutputArtifacts:
    filtered_paths: list[str]
    filtered_out_paths: list[str]
    replaced_paths: list[str]
    metadata_paths: list[str]
    replaced_metadata_paths: list[str]
    active_main_reports: dict[int, list["ReportItem"]]
    active_replaced_reports: dict[int, list["ReportItem"]]


@dataclass
class YearPdfLocator:
    year_dir: Path
    legacy_dir: Path
    replaced_dir: Path
    paths_by_name: dict[str, list[Path]]
    paths_by_announcement_id: dict[str, list[Path]]


# ==================== 断点管理 ====================

def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def write_jsonl(path: Path, rows: list[Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if hasattr(row, "__dataclass_fields__"):
                row = asdict(row)
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def batched_pages(pages: list[int], batch_size: int) -> list[list[int]]:
    if batch_size <= 0:
        batch_size = 1
    return [pages[idx:idx + batch_size] for idx in range(0, len(pages), batch_size)]


# ==================== API客户端 ====================

class CninfoClient:
    def __init__(self, timeout: float = 40.0, request_interval: float = 0.2):
        self.timeout = timeout
        self.request_interval = request_interval
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def warmup(self):
        """预热：访问搜索页获取cookie"""
        try:
            raise_if_cancelled()
            self.session.get(SEARCH_PAGE_URL, timeout=self.timeout)
        except Exception:
            pass

    def query_page(self, page: int, page_size: int, se_date: str, searchkey: str = "") -> dict:
        """查询单页公告"""
        payload = self.build_payload(page, page_size, se_date, searchkey)
        cookies = requests.utils.dict_from_cookiejar(self.session.cookies)

        for attempt in range(1, 9):
            try:
                raise_if_cancelled()
                if self.request_interval > 0:
                    sleep_with_cancel(self.request_interval + random.uniform(0, self.request_interval))

                raise_if_cancelled()
                resp = requests.post(
                    API_URL,
                    data=payload,
                    headers=self.session.headers,
                    cookies=cookies,
                    timeout=self.timeout,
                )

                if resp.status_code == 200:
                    try:
                        return json.loads(resp.content.decode("utf-8"))
                    except Exception:
                        resp.encoding = "utf-8"
                        return resp.json()

                if resp.status_code in (403, 429) and attempt < 8:
                    sleep_with_cancel(min(2 ** attempt, 20))
                    continue

                raise RuntimeError(f"HTTP {resp.status_code}")
            except Exception as e:
                if attempt == 8:
                    raise RuntimeError(f"查询失败: {e}") from e
                sleep_with_cancel(min(2 ** attempt, 20))

        raise RuntimeError("unreachable")

    def build_payload(self, page: int, page_size: int, se_date: str, searchkey: str = "") -> dict[str, str]:
        return {
            "pageNum": str(page),
            "pageSize": str(page_size),
            "column": "szse",
            "tabName": "fulltext",
            "plate": ALL_PLATES,
            "stock": "",
            "searchkey": searchkey,
            "secid": "",
            "category": "category_ndbg_szsh",
            "trade": "",
            "seDate": se_date,
            "sortName": "time",
            "sortType": "desc",
            "isHLtitle": "true",
        }


# ==================== 公告抓取（带断点续传） ====================

async def fetch_pages_batch(
    client: CninfoClient,
    announcement_session,
    pages: list[int],
    page_size: int,
    se_date: str,
) -> list[tuple[int, dict]]:
    raise_if_cancelled()
    if announcement_session is None or aiohttp is None:
        tasks = [
            asyncio.to_thread(client.query_page, page, page_size, se_date)
            for page in pages
        ]
        results = await asyncio.gather(*tasks)
        return list(zip(pages, results))

    tasks = [
        query_page_async(client, announcement_session, page, page_size, se_date)
        for page in pages
    ]
    results = await asyncio.gather(*tasks)
    return list(zip(pages, results))


async def query_page_async(
    client: CninfoClient,
    session,
    page: int,
    page_size: int,
    se_date: str,
    searchkey: str = "",
) -> dict:
    payload = client.build_payload(page, page_size, se_date, searchkey)
    for attempt in range(1, 9):
        try:
            raise_if_cancelled()
            if client.request_interval > 0:
                await async_sleep_with_cancel(client.request_interval + random.uniform(0, client.request_interval))

            raise_if_cancelled()
            async with session.post(API_URL, data=payload) as resp:
                if resp.status == 200:
                    text = await resp.text(encoding="utf-8")
                    return json.loads(text)

                if resp.status in (403, 429) and attempt < 8:
                    await async_sleep_with_cancel(min(2 ** attempt, 20))
                    continue

                raise RuntimeError(f"HTTP {resp.status}")
        except Exception as e:
            if attempt == 8:
                raise RuntimeError(f"查询失败: {e}") from e
            await async_sleep_with_cancel(min(2 ** attempt, 20))

    raise RuntimeError("unreachable")


async def fetch_announcements_for_year(
    client: CninfoClient,
    announcement_session,
    report_year: int,
    se_date: str,
    page_size: int,
    state_dir: Path,
    announcement_concurrency: int,
) -> list[dict]:
    """
    抓取指定年份的全部年报公告。
    自动按月分片，超阈值拆到按天。逐页断点续传。
    """
    cache_dir = state_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = state_dir / "checkpoint.json"
    cache_path = cache_dir / f"{report_year}.jsonl"

    # 初始按月分片
    query_ranges = split_monthly(se_date)

    # 加载断点
    checkpoint = read_json(checkpoint_path) or {}
    year_ck = checkpoint.get(str(report_year))
    resumed = False

    if isinstance(year_ck, dict) and year_ck.get("se_date") == se_date and cache_path.exists():
        saved_ranges = year_ck.get("query_ranges", [])
        range_states = year_ck.get("ranges", {})
        query_ranges = saved_ranges
        resumed = True
        done = sum(1 for r in query_ranges if range_states.get(r, {}).get("completed"))
        log("INFO", f"{report_year} 年检测到断点：{done}/{len(query_ranges)} 个区间已完成")
    else:
        # 清除旧缓存
        if cache_path.exists():
            cache_path.unlink()
        range_states = {}

    # 保存断点辅助函数
    def save_ck():
        checkpoint[str(report_year)] = {
            "se_date": se_date,
            "query_ranges": query_ranges,
            "ranges": range_states,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        write_json(checkpoint_path, checkpoint)

    if not resumed:
        save_ck()
        log("INFO", f"{report_year} 年开始抓取：{len(query_ranges)} 个月级区间，seDate={se_date}")

    all_announcements: list[dict] = []

    # 加载已缓存的公告
    if resumed and cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_announcements.append(json.loads(line))
                    except Exception:
                        pass
        log("INFO", f"{report_year}年 从缓存加载 {len(all_announcements)} 条公告")

    range_idx = 0
    while range_idx < len(query_ranges):
        raise_if_cancelled()
        range_date = query_ranges[range_idx]
        rs = range_states.get(range_date, {})

        if rs.get("completed"):
            range_idx += 1
            continue

        last_page = rs.get("last_completed_page", 0)
        total_pages = rs.get("total_pages", 0)
        last_sig = rs.get("last_signature", "")
        pending: list[dict] = []

        # 首页查询（如果还没查过）
        if last_page <= 0:
            if announcement_session is not None and aiohttp is not None:
                first_data = await query_page_async(client, announcement_session, 1, page_size, range_date)
            else:
                first_data = await asyncio.to_thread(client.query_page, 1, page_size, range_date)
            first_anns = first_data.get("announcements") or []
            total_count = int(first_data.get("totalAnnouncement") or len(first_anns))
            total_pages_all = max(1, math.ceil(total_count / page_size))

            # auto拆分：月级查询页数太多时，拆到日级
            if total_pages_all > AUTO_SPLIT_THRESHOLD:
                start_d, end_d = parse_se_date(range_date)
                if start_d != end_d:  # 不是单日才拆
                    daily_ranges = split_daily(range_date)
                    query_ranges[range_idx:range_idx + 1] = daily_ranges
                    range_states.pop(range_date, None)
                    save_ck()
                    log("INFO", f"{report_year}年 {range_date} 页数={total_pages_all} > {AUTO_SPLIT_THRESHOLD}, 自动拆分为{len(daily_ranges)}天")
                    continue

            total_pages = total_pages_all
            rs = {
                "total_pages": total_pages,
                "last_completed_page": 0,
                "last_signature": "",
                "completed": False,
            }

            log("INFO", f"{report_year}年 [{range_idx+1}/{len(query_ranges)}] {range_date}: {total_count}条公告(含非年报), {total_pages}页")

            all_announcements.extend(first_anns)
            pending.extend(first_anns)
            last_sig = page_signature(first_anns)
            last_page = 1

            if total_pages <= 1:
                rs.update(last_completed_page=1, last_signature=last_sig, completed=True)
                range_states[range_date] = rs
                # 刷盘
                if pending:
                    with cache_path.open("a", encoding="utf-8") as f:
                        for ann in pending:
                            f.write(json.dumps(ann, ensure_ascii=False) + "\n")
                save_ck()
                range_idx += 1
                continue

        else:
            log("INFO", f"{report_year}年 [{range_idx+1}/{len(query_ranges)}] {range_date}: 续抓 page {last_page+1}/{total_pages}")

        # 后续页：按批次并发抓取
        duplicate_page_hit = False
        remaining_pages = list(range(last_page + 1, total_pages + 1))
        for page_batch in batched_pages(remaining_pages, announcement_concurrency):
            raise_if_cancelled()
            batch_results = await fetch_pages_batch(client, announcement_session, page_batch, page_size, range_date)

            for page, data in batch_results:
                raise_if_cancelled()
                page_anns = data.get("announcements") or []
                sig = page_signature(page_anns)

                # 重复页检测（API在100页后可能回放）
                if page > 1 and last_sig and sig == last_sig:
                    await async_sleep_with_cancel(2)
                    if announcement_session is not None and aiohttp is not None:
                        retry_data = await query_page_async(client, announcement_session, page, page_size, range_date)
                    else:
                        retry_data = await asyncio.to_thread(client.query_page, page, page_size, range_date)
                    page_anns = retry_data.get("announcements") or []
                    sig = page_signature(page_anns)
                    if sig == last_sig:
                        log("WARN", f"{report_year}年 {range_date} page={page} 重复页，停止此区间")
                        rs.update(last_completed_page=page - 1, last_signature=last_sig, completed=True)
                        duplicate_page_hit = True
                        break

                all_announcements.extend(page_anns)
                pending.extend(page_anns)
                last_sig = sig
                last_page = page

                matched = _log_matched_reports(page_anns, report_year)
                log("INFO", f"  page {page}/{total_pages}, 本页年报{matched}份, 累计公告{len(all_announcements)}条")

            if pending:
                with cache_path.open("a", encoding="utf-8") as f:
                    for ann in pending:
                        f.write(json.dumps(ann, ensure_ascii=False) + "\n")
                pending = []

            rs.update(
                last_completed_page=last_page,
                last_signature=last_sig,
                completed=duplicate_page_hit or (last_page >= total_pages),
            )
            range_states[range_date] = rs
            save_ck()

            if duplicate_page_hit:
                break

        # 刷残余
        if pending:
            with cache_path.open("a", encoding="utf-8") as f:
                for ann in pending:
                    f.write(json.dumps(ann, ensure_ascii=False) + "\n")
        if not rs.get("completed"):
            rs.update(last_completed_page=last_page, last_signature=last_sig, completed=True)
        range_states[range_date] = rs
        save_ck()
        range_idx += 1

    # 按 announcementId 去重
    seen: dict[str, dict] = {}
    for ann in all_announcements:
        aid = str(ann.get("announcementId", ""))
        if aid:
            old = seen.get(aid)
            if old is None or int(ann.get("announcementTime", 0)) > int(old.get("announcementTime", 0)):
                seen[aid] = ann

    unique = list(seen.values())
    if len(unique) < len(all_announcements):
        log("INFO", f"{report_year}年 去重: {len(all_announcements)} -> {len(unique)}")

    return unique


# ==================== 筛选 ====================

def build_filtered_out_item(ann: dict, report_year: int, reason: str) -> FilteredOutItem:
    return FilteredOutItem(
        report_year=report_year,
        sec_code=str(ann.get("secCode", "")),
        sec_name=str(ann.get("secName", "")),
        announcement_id=str(ann.get("announcementId", "")),
        announcement_title=normalize_text(str(ann.get("announcementTitle", ""))),
        announcement_time=int(ann.get("announcementTime", 0) or 0),
        adjunct_url=str(ann.get("adjunctUrl", "")),
        filter_reason=reason,
    )


def classify_reports_with_replaced(
    announcements: list[dict],
    task_report_year: int,
) -> tuple[list[ReportItem], list[FilteredOutItem], list[ReportItem]]:
    best: dict[tuple[str, int], ReportItem] = {}
    filtered_out: list[FilteredOutItem] = []
    replaced_reports: list[ReportItem] = []

    for ann in announcements:
        title = str(ann.get("announcementTitle", ""))
        sec_code = str(ann.get("secCode", ""))
        adjunct_url = str(ann.get("adjunctUrl", ""))
        inferred_year = extract_year_from_title(title)
        effective_year = inferred_year if inferred_year is not None else task_report_year
        annual_report_priority = annual_report_title_priority(title, effective_year)

        if not sec_code:
            filtered_out.append(build_filtered_out_item(ann, effective_year, "缺少证券代码"))
            continue
        if not adjunct_url:
            filtered_out.append(build_filtered_out_item(ann, effective_year, "缺少PDF地址"))
            continue
        if not sec_code.startswith(("0", "3", "6")):
            filtered_out.append(build_filtered_out_item(ann, effective_year, "非沪深A股代码"))
            continue

        if inferred_year is None and annual_report_priority <= 0:
            filtered_out.append(build_filtered_out_item(ann, effective_year, "标题无法识别报告年份"))
            continue
        if annual_report_priority <= 0:
            filtered_out.append(build_filtered_out_item(ann, effective_year, "非正式年度报告"))
            continue

        item = ReportItem(
            report_year=effective_year,
            sec_code=sec_code,
            sec_name=str(ann.get("secName", "")),
            announcement_id=str(ann.get("announcementId", "")),
            announcement_title=normalize_text(title),
            announcement_time=int(ann.get("announcementTime", 0) or 0),
            adjunct_url=adjunct_url,
        )

        best_key = (sec_code, effective_year)
        old = best.get(best_key)
        if old is None:
            best[best_key] = item
            continue

        if should_replace_report(old, item):
            log("INFO", f"  {sec_code}: 替换 [{old.announcement_title}] -> [{item.announcement_title}]")
            replaced_reports.append(old)
            best[best_key] = item
        else:
            replaced_reports.append(item)

    filtered = sorted(best.values(), key=lambda x: (x.report_year, x.sec_code))
    filtered_out = sorted(
        filtered_out,
        key=lambda x: (x.sec_code, x.announcement_time, x.announcement_id),
    )
    replaced_reports = dedupe_report_items(replaced_reports)

    reason_counter = Counter(item.filter_reason for item in filtered_out)
    if reason_counter:
        reason_summary = ", ".join(
            f"{reason}={count}" for reason, count in reason_counter.most_common(6)
        )
        log("INFO", f"  {task_report_year}年任务 被过滤公告: {len(filtered_out)}条 | {reason_summary}")
    log(
        "INFO",
        f"  {task_report_year}年任务 筛选: {len(announcements)}条公告 -> 保留{len(filtered)}条, 更新前版本{len(replaced_reports)}条, 过滤{len(filtered_out)}条",
    )
    return filtered, filtered_out, replaced_reports


def read_jsonl_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def load_report_items(path: Path) -> list[ReportItem]:
    items: list[ReportItem] = []
    for row in read_jsonl_rows(path):
        try:
            items.append(ReportItem(**row))
        except TypeError:
            continue
    return items


def load_filtered_out_items(path: Path) -> list[FilteredOutItem]:
    items: list[FilteredOutItem] = []
    for row in read_jsonl_rows(path):
        try:
            items.append(FilteredOutItem(**row))
        except TypeError:
            continue
    return items


def dedupe_report_items(items: list[ReportItem], excluded_ids: Optional[set[str]] = None) -> list[ReportItem]:
    excluded_ids = excluded_ids or set()
    deduped: dict[tuple[str, str, str, int], ReportItem] = {}
    for item in items:
        if item.announcement_id and item.announcement_id in excluded_ids:
            continue
        key = (
            item.announcement_id,
            item.sec_code,
            item.announcement_title,
            item.announcement_time,
        )
        old = deduped.get(key)
        if old is None or report_preference_key(item) > report_preference_key(old):
            deduped[key] = item
    return sorted(
        deduped.values(),
        key=lambda x: (x.report_year, x.sec_code, x.announcement_time, x.announcement_id),
    )


def report_identity(item: ReportItem) -> tuple[int, str, str, str, int]:
    return (
        item.report_year,
        item.sec_code,
        item.announcement_id,
        item.announcement_title,
        item.announcement_time,
    )


def choose_best_reports(items: list[ReportItem]) -> tuple[list[ReportItem], list[ReportItem]]:
    unique_by_announcement: dict[str, ReportItem] = {}
    normalized_items: list[ReportItem] = []
    for item in items:
        if item.announcement_id:
            old = unique_by_announcement.get(item.announcement_id)
            if old is None or item.announcement_time > old.announcement_time:
                unique_by_announcement[item.announcement_id] = item
        else:
            normalized_items.append(item)
    normalized_items.extend(unique_by_announcement.values())

    latest: dict[tuple[str, int], ReportItem] = {}
    replaced: list[ReportItem] = []
    for item in normalized_items:
        key = (item.sec_code, item.report_year)
        old = latest.get(key)
        if old is None:
            latest[key] = item
            continue
        if should_replace_report(old, item):
            replaced.append(old)
            latest[key] = item
        else:
            replaced.append(item)
    kept = sorted(latest.values(), key=lambda x: (x.report_year, x.sec_code))
    return kept, replaced


def dedupe_filtered_out(items: list[FilteredOutItem], kept_ids: set[str]) -> list[FilteredOutItem]:
    deduped: dict[tuple[str, str, str, int, str], FilteredOutItem] = {}
    for item in items:
        if item.announcement_id and item.announcement_id in kept_ids:
            continue
        key = (
            item.announcement_id,
            item.sec_code,
            item.announcement_title,
            item.announcement_time,
            item.filter_reason,
        )
        deduped[key] = item
    return sorted(
        deduped.values(),
        key=lambda x: (x.report_year, x.sec_code, x.announcement_time, x.announcement_id, x.filter_reason),
    )


def sync_year_outputs_with_replaced(
    output_dir: Path,
    reports: list[ReportItem],
    filtered_out: list[FilteredOutItem],
    replaced_reports: list[ReportItem],
) -> YearOutputArtifacts:
    reports_by_year: dict[int, list[ReportItem]] = defaultdict(list)
    filtered_out_by_year: dict[int, list[FilteredOutItem]] = defaultdict(list)
    replaced_by_year: dict[int, list[ReportItem]] = defaultdict(list)

    for item in reports:
        reports_by_year[item.report_year].append(item)
    for item in filtered_out:
        filtered_out_by_year[item.report_year].append(item)
    for item in replaced_reports:
        replaced_by_year[item.report_year].append(item)

    target_years = sorted(
        set(reports_by_year.keys())
        | set(filtered_out_by_year.keys())
        | set(replaced_by_year.keys())
    )

    filtered_paths: list[str] = []
    filtered_out_paths: list[str] = []
    replaced_paths: list[str] = []
    metadata_paths: list[str] = []
    replaced_metadata_paths: list[str] = []
    active_main_reports: dict[int, list[ReportItem]] = {}
    active_replaced_reports: dict[int, list[ReportItem]] = {}

    for target_year in target_years:
        year_dir = output_dir / str(target_year)
        year_dir.mkdir(parents=True, exist_ok=True)
        filtered_path = year_dir / "filtered_announcements.jsonl"
        filtered_out_path = year_dir / "filtered_out_announcements.jsonl"
        replaced_path = year_dir / REPLACED_REPORTS_MANIFEST_NAME
        metadata_csv = year_dir / "metadata.csv"
        replaced_metadata_csv = year_dir / REPLACED_REPORTS_METADATA_NAME

        existing_reports = load_report_items(filtered_path)
        existing_replaced = load_report_items(replaced_path)
        current_reports = reports_by_year.get(target_year, [])
        current_replaced = replaced_by_year.get(target_year, [])
        merged_reports, newly_replaced_reports = choose_best_reports(
            existing_reports + current_reports
        )
        kept_ids = {item.announcement_id for item in merged_reports if item.announcement_id}
        merged_replaced = dedupe_report_items(
            existing_replaced
            + current_replaced
            + newly_replaced_reports,
            excluded_ids=kept_ids,
        )
        merged_filtered_out = (
            load_filtered_out_items(filtered_out_path)
            + filtered_out_by_year.get(target_year, [])
        )
        merged_filtered_out = dedupe_filtered_out(merged_filtered_out, kept_ids)

        current_report_keys = {report_identity(item) for item in current_reports}
        merged_main_current = [
            item for item in merged_reports
            if report_identity(item) in current_report_keys
        ]
        active_main_reports[target_year] = merged_main_current
        active_replaced_reports[target_year] = merged_replaced

        write_jsonl(filtered_path, merged_reports)
        write_jsonl(filtered_out_path, merged_filtered_out)
        write_jsonl(replaced_path, merged_replaced)
        _write_metadata_csv(metadata_csv, merged_reports, {})
        _write_replaced_metadata_csv(
            replaced_metadata_csv,
            merged_replaced,
            {},
            merged_reports,
            {},
        )

        filtered_paths.append(str(filtered_path))
        filtered_out_paths.append(str(filtered_out_path))
        replaced_paths.append(str(replaced_path))
        metadata_paths.append(str(metadata_csv))
        replaced_metadata_paths.append(str(replaced_metadata_csv))

    return YearOutputArtifacts(
        filtered_paths=filtered_paths,
        filtered_out_paths=filtered_out_paths,
        replaced_paths=replaced_paths,
        metadata_paths=metadata_paths,
        replaced_metadata_paths=replaced_metadata_paths,
        active_main_reports=active_main_reports,
        active_replaced_reports=active_replaced_reports,
    )


# ==================== PDF下载 ====================

class PermanentDownloadError(RuntimeError):
    pass


def get_pdf_target_path(output_dir: Path, item: ReportItem) -> Path:
    return output_dir / str(item.report_year) / item.filename


def get_replaced_pdf_target_path(output_dir: Path, item: ReportItem) -> Path:
    return output_dir / str(item.report_year) / REPLACED_PDF_DIRNAME / item.filename


def is_permanent_download_status(status: int) -> bool:
    return status in PERMANENT_DOWNLOAD_HTTP_STATUSES


def permanent_download_message(status: int) -> str:
    return f"permanent HTTP {status}"


def is_permanent_download_message(message: str) -> bool:
    return str(message).startswith("permanent HTTP ")


def _has_pdf_signature(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_file():
            return False
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def _validate_pdf_artifact(path: Path) -> tuple[bool, str]:
    try:
        if not path.exists() or not path.is_file():
            return False, "file missing"
        if path.stat().st_size < MIN_VALID_PDF_SIZE:
            return False, "file too small"
    except OSError as exc:
        return False, str(exc)

    if not _has_pdf_signature(path):
        return False, "invalid pdf header"
    return True, ""


def is_download_complete(path: Path) -> bool:
    try:
        return (
            path.exists()
            and path.is_file()
            and path.stat().st_size >= MIN_VALID_PDF_SIZE
            and _has_pdf_signature(path)
        )
    except OSError:
        return False


def _normalize_partial_download(path: Path) -> tuple[Path, bool]:
    part_path = path.with_suffix(path.suffix + ".part")

    if is_download_complete(path):
        return part_path, True

    if part_path.exists() and not _has_pdf_signature(part_path):
        part_path.unlink(missing_ok=True)

    if path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if _has_pdf_signature(path):
            path_size = path.stat().st_size
            part_size = part_path.stat().st_size if part_path.exists() else -1
            if path_size > part_size:
                path.replace(part_path)
            else:
                path.unlink(missing_ok=True)
        else:
            path.unlink(missing_ok=True)

    return part_path, False


def _pdf_base_dir_rank(locator: YearPdfLocator, path: Path) -> int:
    if path.parent == locator.year_dir:
        return 0
    if path.parent == locator.legacy_dir:
        return 1
    if path.parent == locator.replaced_dir:
        return 2
    return 3


def _sort_pdf_candidates(locator: YearPdfLocator, paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: (_pdf_base_dir_rank(locator, path), path.name, str(path)))


def _register_complete_pdf(locator: YearPdfLocator, path: Path):
    if not is_download_complete(path):
        return

    by_name = locator.paths_by_name.setdefault(path.name, [])
    if path not in by_name:
        by_name.append(path)
        locator.paths_by_name[path.name] = _sort_pdf_candidates(locator, by_name)

    announcement_id = extract_announcement_id_from_filename(path)
    if announcement_id:
        by_announcement_id = locator.paths_by_announcement_id.setdefault(announcement_id, [])
        if path not in by_announcement_id:
            by_announcement_id.append(path)
            locator.paths_by_announcement_id[announcement_id] = _sort_pdf_candidates(locator, by_announcement_id)


def _unregister_pdf_path(locator: YearPdfLocator, path: Path):
    paths_by_name = locator.paths_by_name.get(path.name)
    if paths_by_name is not None:
        locator.paths_by_name[path.name] = [candidate for candidate in paths_by_name if candidate != path]
        if not locator.paths_by_name[path.name]:
            locator.paths_by_name.pop(path.name, None)

    announcement_id = extract_announcement_id_from_filename(path)
    if announcement_id:
        paths_by_announcement_id = locator.paths_by_announcement_id.get(announcement_id)
        if paths_by_announcement_id is not None:
            locator.paths_by_announcement_id[announcement_id] = [
                candidate for candidate in paths_by_announcement_id if candidate != path
            ]
            if not locator.paths_by_announcement_id[announcement_id]:
                locator.paths_by_announcement_id.pop(announcement_id, None)


def build_year_pdf_locator(output_dir: Path, report_year: int) -> YearPdfLocator:
    year_dir = output_dir / str(report_year)
    legacy_dir = year_dir / "pdf"
    replaced_dir = year_dir / REPLACED_PDF_DIRNAME
    locator = YearPdfLocator(
        year_dir=year_dir,
        legacy_dir=legacy_dir,
        replaced_dir=replaced_dir,
        paths_by_name={},
        paths_by_announcement_id={},
    )
    for base_dir in (year_dir, legacy_dir, replaced_dir):
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.glob("*.pdf")):
            _register_complete_pdf(locator, path)
    return locator


def get_year_pdf_locator(
    output_dir: Path,
    report_year: int,
    locator_cache: Optional[dict[int, YearPdfLocator]] = None,
) -> YearPdfLocator:
    if locator_cache is None:
        return build_year_pdf_locator(output_dir, report_year)

    locator = locator_cache.get(report_year)
    if locator is None:
        locator = build_year_pdf_locator(output_dir, report_year)
        locator_cache[report_year] = locator
    return locator


def build_pdf_locator_cache_for_years(output_dir: Path, years: set[int]) -> dict[int, YearPdfLocator]:
    return {
        report_year: build_year_pdf_locator(output_dir, report_year)
        for report_year in sorted(years)
    }


def build_pdf_locator_cache_for_items(output_dir: Path, items: list[ReportItem]) -> dict[int, YearPdfLocator]:
    return build_pdf_locator_cache_for_years(output_dir, {item.report_year for item in items})


def register_pdf_locator_path(
    output_dir: Path,
    report_year: int,
    path: Path,
    locator_cache: Optional[dict[int, YearPdfLocator]] = None,
):
    if locator_cache is None:
        return
    locator = get_year_pdf_locator(output_dir, report_year, locator_cache)
    _register_complete_pdf(locator, path)


def update_pdf_locator_after_relocation(
    output_dir: Path,
    report_year: int,
    old_path: Path,
    new_path: Path,
    locator_cache: Optional[dict[int, YearPdfLocator]] = None,
):
    if locator_cache is None:
        return
    locator = get_year_pdf_locator(output_dir, report_year, locator_cache)
    _unregister_pdf_path(locator, old_path)
    _register_complete_pdf(locator, new_path)


def find_existing_pdf_path(
    output_dir: Path,
    item: ReportItem,
    locator_cache: Optional[dict[int, YearPdfLocator]] = None,
) -> Optional[Path]:
    locator = get_year_pdf_locator(output_dir, item.report_year, locator_cache)
    candidates: list[Path] = []
    candidates.extend(locator.paths_by_name.get(item.filename, []))
    candidates.extend(locator.paths_by_name.get(item.legacy_filename, []))
    if item.announcement_id:
        candidates.extend(locator.paths_by_announcement_id.get(item.announcement_id, []))

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if is_download_complete(candidate):
            return candidate
        _unregister_pdf_path(locator, candidate)
    return None


def relocate_existing_pdf(existing_path: Path, target_path: Path) -> Path:
    if existing_path.resolve() == target_path.resolve():
        return existing_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if is_download_complete(target_path):
        existing_path.unlink(missing_ok=True)
        return target_path
    existing_path.replace(target_path)
    return target_path


def load_target_reports_from_output_dir(output_dir: Path) -> list[ReportItem]:
    manifest_paths = sorted(
        path
        for path in output_dir.glob("*/filtered_announcements.jsonl")
        if path.parent.is_dir() and path.parent.name.isdigit()
    )
    if not manifest_paths:
        raise FileNotFoundError(
            f"未找到筛选结果清单: {output_dir / '*/filtered_announcements.jsonl'}"
        )

    items: list[ReportItem] = []
    for path in manifest_paths:
        items.extend(load_report_items(path))

    kept, _ = choose_best_reports(items)
    return kept


def load_replaced_reports_from_output_dir(output_dir: Path) -> list[ReportItem]:
    manifest_paths = sorted(
        path
        for path in output_dir.glob(f"*/{REPLACED_REPORTS_MANIFEST_NAME}")
        if path.parent.is_dir() and path.parent.name.isdigit()
    )
    items: list[ReportItem] = []
    for path in manifest_paths:
        items.extend(load_report_items(path))
    return dedupe_report_items(items)


def load_filtered_out_index(output_dir: Path) -> dict[str, FilteredOutItem]:
    index: dict[str, FilteredOutItem] = {}
    manifest_paths = sorted(
        path
        for path in output_dir.glob("*/filtered_out_announcements.jsonl")
        if path.parent.is_dir() and path.parent.name.isdigit()
    )
    for path in manifest_paths:
        for item in load_filtered_out_items(path):
            if item.announcement_id and item.announcement_id not in index:
                index[item.announcement_id] = item
    return index


def iter_pdf_files(output_dir: Path) -> list[Path]:
    pdf_paths: list[Path] = []
    for year_dir in sorted(
        path for path in output_dir.iterdir() if path.is_dir() and path.name.isdigit()
    ):
        pdf_paths.extend(
            sorted(path.resolve() for path in year_dir.rglob("*.pdf") if path.is_file())
        )
    return pdf_paths


def report_item_to_dict(item: ReportItem) -> dict[str, Any]:
    return {
        "report_year": item.report_year,
        "sec_code": item.sec_code,
        "sec_name": item.sec_name,
        "announcement_id": item.announcement_id,
        "announcement_title": item.announcement_title,
        "announcement_time": item.announcement_time,
        "adjunct_url": item.adjunct_url,
        "expected_filename": item.filename,
    }


def download_failure_key(role: str, item: ReportItem) -> tuple[str, str, str]:
    return role, item.announcement_id, item.adjunct_url


def download_failures_path(output_dir: Path, report_year: int) -> Path:
    return output_dir / str(report_year) / DOWNLOAD_FAILURES_NAME


def load_permanent_download_failures(output_dir: Path, years: set[int]) -> set[tuple[str, str, str]]:
    failures: set[tuple[str, str, str]] = set()
    for year in years:
        for row in read_jsonl_rows(download_failures_path(output_dir, year)):
            if not row.get("permanent"):
                continue
            failures.add((
                str(row.get("role", "")),
                str(row.get("announcement_id", "")),
                str(row.get("adjunct_url", "")),
            ))
    return failures


def append_permanent_download_failure(
    output_dir: Path,
    role: str,
    item: ReportItem,
    path: Path,
    message: str,
    existing_keys: set[tuple[str, str, str]],
):
    key = download_failure_key(role, item)
    if key in existing_keys:
        return

    failure_path = download_failures_path(output_dir, item.report_year)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        **report_item_to_dict(item),
        "role": role,
        "permanent": True,
        "error": message,
        "pdf_url": item.pdf_url,
        "target_path": str(path),
        "failed_at": datetime.now().isoformat(timespec="seconds"),
    }
    with failure_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False))
        f.write("\n")
    existing_keys.add(key)


def classify_non_target_pdf_record(output_dir: Path, path: Path, target_by_year_sec: dict[tuple[str, str], ReportItem]) -> dict[str, Any]:
    resolved_output_dir = output_dir.resolve()
    try:
        relative_path = path.relative_to(resolved_output_dir)
        year = relative_path.parts[0]
    except ValueError:
        relative_path = path
        year = path.parent.name

    sec_code = path.name.split("_", 1)[0] if "_" in path.name else ""
    announcement_id = extract_announcement_id_from_filename(path)
    replacement_item = target_by_year_sec.get((year, sec_code))
    category = (
        DELETABLE_ORPHAN_CATEGORY
        if replacement_item is not None
        else PRESERVED_NON_TARGET_CATEGORY
    )

    return {
        "path": str(path),
        "relative_path": relative_path.as_posix(),
        "year": year,
        "sec_code": sec_code,
        "announcement_id": announcement_id,
        "category": category,
    }


def collect_pdf_audit_state(output_dir: Path) -> dict[str, Any]:
    target_items = load_target_reports_from_output_dir(output_dir)
    replaced_items = load_replaced_reports_from_output_dir(output_dir)
    pdf_locator_cache = build_pdf_locator_cache_for_items(output_dir, target_items + replaced_items)
    matched_paths: set[Path] = set()
    matched_replaced_paths: set[Path] = set()
    missing_targets: list[dict[str, Any]] = []
    missing_replaced: list[dict[str, Any]] = []
    target_by_year_sec: dict[tuple[str, str], ReportItem] = {}

    for item in target_items:
        target_by_year_sec[(str(item.report_year), item.sec_code)] = item
        existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
        if existing_path is None:
            missing_targets.append(report_item_to_dict(item))
            continue
        matched_paths.add(existing_path.resolve())

    for item in replaced_items:
        existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
        if existing_path is None:
            missing_replaced.append(report_item_to_dict(item))
            continue
        matched_replaced_paths.add(existing_path.resolve())

    pdf_paths = iter_pdf_files(output_dir)
    non_target_paths = [
        path
        for path in pdf_paths
        if path not in matched_paths and path not in matched_replaced_paths
    ]
    orphan_paths: list[Path] = []
    preserved_non_target_paths: list[Path] = []
    orphan_records: list[dict[str, Any]] = []
    preserved_non_target_records: list[dict[str, Any]] = []
    for path in non_target_paths:
        record = classify_non_target_pdf_record(output_dir, path, target_by_year_sec)
        if record["category"] == DELETABLE_ORPHAN_CATEGORY:
            orphan_paths.append(path)
            orphan_records.append(record)
        else:
            preserved_non_target_paths.append(path)
            preserved_non_target_records.append(record)

    small_files: list[Path] = []
    invalid_headers: list[Path] = []
    for path in pdf_paths:
        try:
            if path.stat().st_size < MIN_VALID_PDF_SIZE:
                small_files.append(path)
            with path.open("rb") as f:
                if f.read(5) != b"%PDF-":
                    invalid_headers.append(path)
        except OSError:
            invalid_headers.append(path)

    return {
        "output_dir": output_dir.resolve(),
        "target_items": target_items,
        "replaced_items": replaced_items,
        "pdf_locator_cache": pdf_locator_cache,
        "target_by_year_sec": target_by_year_sec,
        "matched_paths": matched_paths,
        "matched_replaced_paths": matched_replaced_paths,
        "missing_targets": missing_targets,
        "missing_replaced": missing_replaced,
        "pdf_paths": pdf_paths,
        "non_target_paths": non_target_paths,
        "orphan_paths": orphan_paths,
        "orphan_records": orphan_records,
        "preserved_non_target_paths": preserved_non_target_paths,
        "preserved_non_target_records": preserved_non_target_records,
        "small_files": small_files,
        "invalid_headers": invalid_headers,
    }


def build_pdf_audit_report(audit_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workspace": str(Path.cwd().resolve()),
        "base_dir": str(audit_state["output_dir"]),
        "pdf_total": len(audit_state["pdf_paths"]),
        "target_total": len(audit_state["target_items"]),
        "replaced_report_total": len(audit_state["replaced_items"]),
        "matched_target_pdf_count": len(audit_state["matched_paths"]),
        "matched_replaced_pdf_count": len(audit_state["matched_replaced_paths"]),
        "missing_target_pdf_count": len(audit_state["missing_targets"]),
        "missing_replaced_pdf_count": len(audit_state["missing_replaced"]),
        "non_target_pdf_count_total": len(audit_state["non_target_paths"]),
        "orphan_pdf_count": len(audit_state["orphan_paths"]),
        "preserved_non_target_pdf_count": len(audit_state["preserved_non_target_paths"]),
        "small_file_count": len(audit_state["small_files"]),
        "invalid_header_count": len(audit_state["invalid_headers"]),
        "missing_samples": audit_state["missing_targets"][:AUDIT_SAMPLE_LIMIT],
        "missing_replaced_samples": audit_state["missing_replaced"][:AUDIT_SAMPLE_LIMIT],
        "orphan_samples": [record["path"] for record in audit_state["orphan_records"][:AUDIT_SAMPLE_LIMIT]],
        "preserved_non_target_samples": [
            record["path"] for record in audit_state["preserved_non_target_records"][:AUDIT_SAMPLE_LIMIT]
        ],
        "small_file_samples": [str(path) for path in audit_state["small_files"][:AUDIT_SAMPLE_LIMIT]],
        "invalid_header_samples": [str(path) for path in audit_state["invalid_headers"][:AUDIT_SAMPLE_LIMIT]],
    }


def write_pdf_audit_report(output_dir: Path, report_name: str, audit_state: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    audit_state = audit_state or collect_pdf_audit_state(output_dir)
    report = build_pdf_audit_report(audit_state)
    write_json(output_dir / report_name, report)
    return report


def extract_announcement_id_from_filename(path: Path) -> str:
    m = ANNOUNCEMENT_ID_IN_FILENAME_RE.search(path.name)
    return m.group(1) if m else ""


def cleanup_orphan_pdfs(
    output_dir: Path,
    audit_before: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit_before = audit_before or collect_pdf_audit_state(output_dir)
    filtered_out_index = load_filtered_out_index(output_dir)

    deleted_records: list[dict[str, Any]] = []
    retained_records: list[dict[str, Any]] = []
    deleted_by_year: Counter[str] = Counter()
    deleted_by_category: Counter[str] = Counter()
    deleted_by_reason: Counter[str] = Counter()
    retained_by_category: Counter[str] = Counter()
    delete_errors: list[dict[str, Any]] = []

    for base_record in audit_before["orphan_records"] + audit_before["preserved_non_target_records"]:
        path = Path(base_record["path"])
        relative_path = Path(base_record["relative_path"])
        year = base_record["year"]
        sec_code = base_record["sec_code"]
        announcement_id = base_record["announcement_id"]
        filtered_out_item = filtered_out_index.get(announcement_id)
        replacement_item = audit_before["target_by_year_sec"].get((year, sec_code))
        category = base_record["category"]
        filter_reason = ""
        if filtered_out_item is not None:
            filter_reason = filtered_out_item.filter_reason
        elif category == DELETABLE_ORPHAN_CATEGORY:
            filter_reason = "被同公司更高优先级版本替代"
        else:
            filter_reason = "保留：同年无目标证券代码"

        record = {
            "path": str(path),
            "relative_path": relative_path.as_posix(),
            "year": year,
            "sec_code": sec_code,
            "announcement_id": announcement_id,
            "category": category,
            "filtered_out_reason": filter_reason,
        }
        if filtered_out_item is not None:
            record["filtered_out_title"] = filtered_out_item.announcement_title
        if replacement_item is not None:
            replacement_path = find_existing_pdf_path(
                output_dir,
                replacement_item,
                audit_before.get("pdf_locator_cache"),
            )
            record["replacement_target"] = {
                "announcement_id": replacement_item.announcement_id,
                "announcement_title": replacement_item.announcement_title,
                "filename": replacement_item.filename,
                "path": str(replacement_path.resolve()) if replacement_path is not None else "",
            }

        if category == PRESERVED_NON_TARGET_CATEGORY:
            record["action"] = "kept"
            retained_records.append(record)
            retained_by_category[category] += 1
            continue

        try:
            path.unlink()
            record["action"] = "deleted"
            deleted_records.append(record)
            deleted_by_year[year] += 1
            deleted_by_category[category] += 1
            deleted_by_reason[filter_reason] += 1
        except OSError as exc:
            delete_errors.append(
                {
                    "path": str(path),
                    "relative_path": relative_path.as_posix(),
                    "error": str(exc),
                }
            )

    audit_after = collect_pdf_audit_state(output_dir)
    cleanup_report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workspace": str(Path.cwd().resolve()),
        "base_dir": str(output_dir.resolve()),
        "non_target_pdf_count_before_cleanup": len(audit_before["non_target_paths"]),
        "orphan_pdf_count_before_delete": len(audit_before["orphan_paths"]),
        "preserved_non_target_pdf_count_before_delete": len(audit_before["preserved_non_target_paths"]),
        "deleted_pdf_count": len(deleted_records),
        "retained_non_target_pdf_count": len(retained_records),
        "delete_error_count": len(delete_errors),
        "deleted_by_year": dict(sorted(deleted_by_year.items())),
        "deleted_by_category": dict(sorted(deleted_by_category.items())),
        "deleted_by_filtered_out_reason": dict(sorted(deleted_by_reason.items())),
        "retained_by_category": dict(sorted(retained_by_category.items())),
        "missing_target_count_before_delete": len(audit_before["missing_targets"]),
        "remaining_orphan_count_after_delete": len(audit_after["orphan_paths"]),
        "remaining_preserved_non_target_count_after_delete": len(audit_after["preserved_non_target_paths"]),
        "delete_errors": delete_errors[:AUDIT_SAMPLE_LIMIT],
        "records": deleted_records,
        "retained_records": retained_records,
    }
    write_json(output_dir / NON_TARGET_PDF_CLEANUP_REPORT_NAME, cleanup_report)

    audit_after_report = build_pdf_audit_report(audit_after)
    write_json(output_dir / PDF_AUDIT_AFTER_CLEANUP_REPORT_NAME, audit_after_report)
    return cleanup_report, audit_after_report


def log_pdf_audit_summary(report: dict[str, Any], title: str):
    log("INFO", title)
    log("INFO", f"  PDF总数: {report['pdf_total']}")
    log("INFO", f"  目标年报数: {report['target_total']}")
    log("INFO", f"  更新前版本数: {report['replaced_report_total']}")
    log("INFO", f"  已匹配目标PDF: {report['matched_target_pdf_count']}")
    log("INFO", f"  已匹配更新前版本PDF: {report['matched_replaced_pdf_count']}")
    log("INFO", f"  缺失目标PDF: {report['missing_target_pdf_count']}")
    log("INFO", f"  缺失更新前版本PDF: {report['missing_replaced_pdf_count']}")
    log("INFO", f"  非目标PDF总数: {report['non_target_pdf_count_total']}")
    log("INFO", f"  孤儿PDF: {report['orphan_pdf_count']}")
    log("INFO", f"  保留型非目标PDF: {report['preserved_non_target_pdf_count']}")
    log("INFO", f"  小文件: {report['small_file_count']}")
    log("INFO", f"  非PDF头文件: {report['invalid_header_count']}")


def run_pdf_maintenance(args) -> bool:
    if not args.audit_pdf and not args.cleanup_orphan_pdf:
        return False

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        raise FileNotFoundError(f"输出目录不存在: {output_dir}")

    if args.cleanup_orphan_pdf:
        audit_before_state = collect_pdf_audit_state(output_dir)
        audit_before_report = write_pdf_audit_report(
            output_dir,
            PDF_AUDIT_REPORT_NAME,
            audit_before_state,
        )
        log_pdf_audit_summary(audit_before_report, "清理前PDF审计结果")
        cleanup_report, audit_after_report = cleanup_orphan_pdfs(output_dir, audit_before_state)
        log(
            "INFO",
            f"孤儿 PDF 清理完成：删除={cleanup_report['deleted_pdf_count']}，保留未删={cleanup_report['retained_non_target_pdf_count']}，删除失败={cleanup_report['delete_error_count']}，剩余可删孤儿={cleanup_report['remaining_orphan_count_after_delete']}",
        )
        log("INFO", f"  清理报告: {output_dir / NON_TARGET_PDF_CLEANUP_REPORT_NAME}")
        log_pdf_audit_summary(audit_after_report, "清理后PDF审计结果")
        log("INFO", f"  审计报告: {output_dir / PDF_AUDIT_AFTER_CLEANUP_REPORT_NAME}")
        return True

    audit_report = write_pdf_audit_report(output_dir, PDF_AUDIT_REPORT_NAME)
    log_pdf_audit_summary(audit_report, "PDF审计结果")
    log("INFO", f"  审计报告: {output_dir / PDF_AUDIT_REPORT_NAME}")
    return True


def merge_download_stats_into_summary(
    summary_path: Path,
    yearly_stats: dict[int, dict[str, int]],
) -> list[dict[str, Any]] | None:
    if not summary_path.exists():
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list):
        return None

    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            year = int(row.get("year"))
        except Exception:
            continue
        stats = yearly_stats.get(year)
        if stats is None:
            continue
        row.update(stats)

    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def download_pdf_sync(url: str, path: Path, retries: int = 6) -> tuple[bool, str]:
    part_path, already_ready = _normalize_partial_download(path)
    if already_ready:
        return True, "exists"

    for attempt in range(1, retries + 1):
        try:
            raise_if_cancelled()
            resume_from = part_path.stat().st_size if part_path.exists() else 0
            headers = dict(DOWNLOAD_HEADERS)
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"

            with requests.get(url, headers=headers, timeout=90, stream=True) as resp:
                if resp.status_code == 416 and resume_from >= MIN_VALID_PDF_SIZE:
                    ok, reason = _validate_pdf_artifact(part_path)
                    if ok:
                        part_path.replace(path)
                        return True, "exists"
                    part_path.unlink(missing_ok=True)
                    raise RuntimeError(reason)
                if resp.status_code not in (200, 206):
                    if is_permanent_download_status(resp.status_code):
                        raise PermanentDownloadError(permanent_download_message(resp.status_code))
                    raise RuntimeError(f"HTTP {resp.status_code}")

                append_mode = resume_from > 0 and resp.status_code == 206
                if resume_from > 0 and not append_mode and part_path.exists():
                    part_path.unlink()
                    resume_from = 0

                path.parent.mkdir(parents=True, exist_ok=True)
                with part_path.open("ab" if append_mode else "wb") as f:
                    for chunk in resp.iter_content(chunk_size=PDF_CHUNK_SIZE):
                        raise_if_cancelled()
                        if chunk:
                            f.write(chunk)

            ok, reason = _validate_pdf_artifact(part_path)
            if not ok:
                part_path.unlink(missing_ok=True)
                raise RuntimeError(reason)
            part_path.replace(path)
            return True, "downloaded"
        except PermanentDownloadError as e:
            part_path.unlink(missing_ok=True)
            return False, str(e)
        except Exception as e:
            if attempt == retries:
                return False, str(e)
            sleep_with_cancel(min(2 ** attempt, 20))
    return False, "unreachable"


async def download_pdf_async(
    session, url: str, path: Path, sem: asyncio.Semaphore, retries: int = 6
) -> tuple[bool, str]:
    part_path, already_ready = _normalize_partial_download(path)
    if already_ready:
        return True, "exists"

    for attempt in range(1, retries + 1):
        try:
            raise_if_cancelled()
            resume_from = part_path.stat().st_size if part_path.exists() else 0
            headers = dict(DOWNLOAD_HEADERS)
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"

            async with sem:
                raise_if_cancelled()
                if session is not None and aiohttp is not None:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 416 and resume_from >= MIN_VALID_PDF_SIZE:
                            ok, reason = _validate_pdf_artifact(part_path)
                            if ok:
                                part_path.replace(path)
                                return True, "exists"
                            part_path.unlink(missing_ok=True)
                            raise RuntimeError(reason)
                        if resp.status not in (200, 206):
                            if is_permanent_download_status(resp.status):
                                raise PermanentDownloadError(permanent_download_message(resp.status))
                            raise RuntimeError(f"HTTP {resp.status}")

                        append_mode = resume_from > 0 and resp.status == 206
                        if resume_from > 0 and not append_mode and part_path.exists():
                            part_path.unlink()

                        path.parent.mkdir(parents=True, exist_ok=True)
                        with part_path.open("ab" if append_mode else "wb") as f:
                            async for chunk in resp.content.iter_chunked(PDF_CHUNK_SIZE):
                                raise_if_cancelled()
                                if chunk:
                                    f.write(chunk)
                else:
                    ok, msg = await asyncio.to_thread(download_pdf_sync, url, path, 1)
                    if ok:
                        return ok, msg
                    if is_permanent_download_message(msg):
                        raise PermanentDownloadError(msg)
                    raise RuntimeError(msg)

            ok, reason = _validate_pdf_artifact(part_path)
            if not ok:
                part_path.unlink(missing_ok=True)
                raise RuntimeError(reason)
            part_path.replace(path)
            return True, "downloaded"
        except PermanentDownloadError as e:
            part_path.unlink(missing_ok=True)
            return False, str(e)
        except Exception as e:
            if attempt == retries:
                return False, str(e)
            await async_sleep_with_cancel(min(2 ** attempt, 20))

    return False, "unreachable"


# ==================== 主流程 ====================

def _write_metadata_csv(csv_path: Path, reports: list[ReportItem], path_map: dict[str, Path]):
    import csv
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["report_year", "sec_code", "sec_name", "announcement_id",
                         "announcement_title", "pdf_url", "local_path"])
        for item in reports:
            local = path_map.get(item.announcement_id, "")
            writer.writerow([item.report_year, item.sec_code, item.sec_name,
                            item.announcement_id, item.announcement_title,
                            item.pdf_url, str(local)])


def replacement_reason(old_item: ReportItem, new_item: Optional[ReportItem]) -> str:
    if new_item is None:
        return ""

    old_aid = announcement_id_priority(old_item.announcement_id)
    new_aid = announcement_id_priority(new_item.announcement_id)
    if new_aid != old_aid:
        return (
            f"同公司同年度存在announcement_id更大的版本，保留 {new_item.announcement_id}，"
            f"替换 {old_item.announcement_id}"
        )

    old_title_priority = annual_report_title_priority(old_item.announcement_title, old_item.report_year)
    new_title_priority = annual_report_title_priority(new_item.announcement_title, new_item.report_year)
    if new_title_priority != old_title_priority:
        return (
            f"同公司同年度存在标题优先级更高的版本，保留 {new_item.announcement_id}"
        )

    old_revision = revision_priority(old_item.announcement_title)
    new_revision = revision_priority(new_item.announcement_title)
    if new_revision != old_revision:
        return (
            f"同公司同年度存在修订优先级更高的版本，保留 {new_item.announcement_id}"
        )

    if new_item.announcement_time != old_item.announcement_time:
        return (
            f"同公司同年度存在发布时间更晚的版本，保留 {new_item.announcement_id}"
        )

    return f"同公司同年度存在更高优先级版本，保留 {new_item.announcement_id}"


def _write_replaced_metadata_csv(
    csv_path: Path,
    replaced_reports: list[ReportItem],
    replaced_path_map: dict[str, Path],
    primary_reports: list[ReportItem],
    primary_path_map: dict[str, Path],
):
    import csv

    primary_by_key = {
        (item.report_year, item.sec_code): item
        for item in primary_reports
    }

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "report_year",
            "sec_code",
            "sec_name",
            "announcement_id",
            "announcement_title",
            "pdf_url",
            "local_path",
            "replacement_announcement_id",
            "replacement_announcement_title",
            "replacement_pdf_url",
            "replacement_local_path",
            "replacement_reason",
        ])
        for item in replaced_reports:
            local = replaced_path_map.get(item.announcement_id, "")
            replacement_item = primary_by_key.get((item.report_year, item.sec_code))
            replacement_local = ""
            replacement_id = ""
            replacement_title = ""
            replacement_pdf_url = ""
            reason = ""
            if replacement_item is not None:
                replacement_local = str(primary_path_map.get(replacement_item.announcement_id, ""))
                replacement_id = replacement_item.announcement_id
                replacement_title = replacement_item.announcement_title
                replacement_pdf_url = replacement_item.pdf_url
                reason = replacement_reason(item, replacement_item)

            writer.writerow([
                item.report_year,
                item.sec_code,
                item.sec_name,
                item.announcement_id,
                item.announcement_title,
                item.pdf_url,
                str(local),
                replacement_id,
                replacement_title,
                replacement_pdf_url,
                replacement_local,
                reason,
            ])


async def _download_with_role_info(
    session,
    item: ReportItem,
    path: Path,
    sem: asyncio.Semaphore,
    role: str,
):
    ok, msg = await download_pdf_async(session, item.pdf_url, path, sem)
    if not ok:
        msg = f"{msg}; announcement_id={item.announcement_id}; url={item.pdf_url}"
    return role, item, path, ok, msg


def build_year_result(
    report_year: int,
    announcements: list[dict],
    reports: list[ReportItem],
    replaced_reports: list[ReportItem],
    filtered_out: list[FilteredOutItem],
    artifacts: YearOutputArtifacts,
    main_stats: Optional[dict[str, int]] = None,
    replaced_stats: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    main_stats = main_stats or {"downloaded": 0, "exists": 0, "failed": 0}
    replaced_stats = replaced_stats or {"downloaded": 0, "exists": 0, "failed": 0}
    main_skipped = main_stats.get("skipped", 0)
    replaced_skipped = replaced_stats.get("skipped", 0)
    return {
        "year": report_year,
        "raw_total": len(announcements),
        "filtered_total": len(reports),
        "replaced_total": len(replaced_reports),
        "filtered_out_total": len(filtered_out),
        "downloaded": main_stats["downloaded"] + replaced_stats["downloaded"],
        "exists": main_stats["exists"] + replaced_stats["exists"],
        "failed": main_stats["failed"] + replaced_stats["failed"],
        "skipped": main_skipped + replaced_skipped,
        "replaced_downloaded": replaced_stats["downloaded"],
        "replaced_exists": replaced_stats["exists"],
        "replaced_failed": replaced_stats["failed"],
        "replaced_skipped": replaced_skipped,
        "filtered_paths": artifacts.filtered_paths,
        "filtered_out_paths": artifacts.filtered_out_paths,
        "replaced_paths": artifacts.replaced_paths,
        "metadata_csv_paths": artifacts.metadata_paths,
        "replaced_metadata_csv_paths": artifacts.replaced_metadata_paths,
    }


async def process_year_with_replaced(
    client: CninfoClient,
    announcement_session,
    download_session,
    report_year: int,
    se_date: str,
    output_dir: Path,
    state_dir: Path,
    page_size: int,
    announcement_concurrency: int,
    download_sem: Optional[asyncio.Semaphore],
    metadata_only: bool = False,
) -> dict:
    announcements = await fetch_announcements_for_year(
        client,
        announcement_session,
        report_year,
        se_date,
        page_size,
        state_dir,
        announcement_concurrency,
    )
    reports, filtered_out, replaced_reports = classify_reports_with_replaced(
        announcements,
        report_year,
    )
    artifacts = sync_year_outputs_with_replaced(
        output_dir,
        reports,
        filtered_out,
        replaced_reports,
    )

    if metadata_only:
        log(
            "INFO",
            f"{report_year} 年仅抓取公告：原始公告={len(announcements)}，保留={len(reports)}，更新前版本={len(replaced_reports)}，过滤={len(filtered_out)}",
        )
        return build_year_result(
            report_year,
            announcements,
            reports,
            replaced_reports,
            filtered_out,
            artifacts,
        )

    primary_reports = dedupe_report_items([
        item
        for items in artifacts.active_main_reports.values()
        for item in items
    ])
    archived_reports = dedupe_report_items([
        item
        for items in artifacts.active_replaced_reports.values()
        for item in items
    ])

    if not primary_reports and not archived_reports:
        log("WARN", f"{report_year}年没有筛选到可下载的年报")
        return build_year_result(
            report_year,
            announcements,
            reports,
            replaced_reports,
            filtered_out,
            artifacts,
        )

    log(
        "INFO",
        f"{report_year} 年开始下载：主版本 {len(primary_reports)} 份，更新前版本 {len(archived_reports)} 份",
    )

    log("INFO", f"{report_year}年下载前预检查：正在核对已存在PDF、断点文件和目录归位")

    touched_years = set(artifacts.active_main_reports.keys()) | set(artifacts.active_replaced_reports.keys())
    touched_years.update(item.report_year for item in primary_reports)
    touched_years.update(item.report_year for item in archived_reports)
    pdf_locator_cache = build_pdf_locator_cache_for_years(output_dir, touched_years)

    tasks = []
    path_map: dict[str, Path] = {}
    archived_path_map: dict[str, Path] = {}
    stats = {
        "main": {"downloaded": 0, "exists": 0, "failed": 0, "skipped": 0},
        "replaced": {"downloaded": 0, "exists": 0, "failed": 0, "skipped": 0},
    }
    permanent_failure_keys = load_permanent_download_failures(output_dir, touched_years)

    for role, items, target_fn, role_path_map in (
        ("main", primary_reports, get_pdf_target_path, path_map),
        ("replaced", archived_reports, get_replaced_pdf_target_path, archived_path_map),
    ):
        for item in items:
            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
            target_path = target_fn(output_dir, item)
            if existing_path is not None:
                final_path = relocate_existing_pdf(existing_path, target_path)
                update_pdf_locator_after_relocation(
                    output_dir,
                    item.report_year,
                    existing_path,
                    final_path,
                    pdf_locator_cache,
                )
                role_path_map[item.announcement_id] = final_path
                stats[role]["exists"] += 1
                continue

            if download_failure_key(role, item) in permanent_failure_keys:
                stats[role]["skipped"] += 1
                log(
                    "WARN",
                    f"{report_year} 年跳过永久失败 [{role}]：{item.sec_code} {item.sec_name} | "
                    f"{item.announcement_title} | announcement_id={item.announcement_id}",
                )
                continue

            tasks.append(
                asyncio.create_task(
                    _download_with_role_info(download_session, item, target_path, download_sem, role)
                )
            )

    log(
        "INFO",
        f"{report_year} 年预检查完成：主版本已存在 {stats['main']['exists']} 份，旧版本已存在 {stats['replaced']['exists']} 份，"
        f"永久失败跳过 {stats['main']['skipped'] + stats['replaced']['skipped']} 份，待下载 {len(tasks)} 份",
    )

    finished = 0
    total = len(tasks)
    for coro in asyncio.as_completed(tasks):
        role, item, path, ok, msg = await coro
        finished += 1
        progress = f"[{finished}/{total}]"
        if ok:
            register_pdf_locator_path(output_dir, item.report_year, path, pdf_locator_cache)
        if ok and msg == "downloaded":
            stats[role]["downloaded"] += 1
            if role == "main":
                path_map[item.announcement_id] = path
            else:
                archived_path_map[item.announcement_id] = path
            log("INFO", f"{report_year}年下载成功 {progress} [{role}]: {item.sec_code} {item.sec_name} | {item.announcement_title}")
        elif ok and msg == "exists":
            stats[role]["exists"] += 1
            if role == "main":
                path_map[item.announcement_id] = path
            else:
                archived_path_map[item.announcement_id] = path
            log("INFO", f"{report_year}年已存在 {progress} [{role}]: {item.sec_code} {item.sec_name}")
        elif is_permanent_download_message(msg):
            stats[role]["skipped"] += 1
            append_permanent_download_failure(
                output_dir,
                role,
                item,
                path,
                msg,
                permanent_failure_keys,
            )
            log("WARN", f"{report_year}年远端PDF不可用，已记录并跳过 {progress} [{role}]: {item.sec_code} {item.sec_name} | {msg}")
        else:
            stats[role]["failed"] += 1
            log("ERROR", f"{report_year} 年下载失败 {progress} [{role}]：{item.sec_code} {item.sec_name} | {msg}")

    main_reports_by_year: dict[int, list[ReportItem]] = {}
    main_path_maps_by_year: dict[int, dict[str, Path]] = {}

    for filtered_path, metadata_path in zip(artifacts.filtered_paths, artifacts.metadata_paths):
        year_reports = load_report_items(Path(filtered_path))
        year_path_map: dict[str, Path] = {}
        for item in year_reports:
            if item.announcement_id in path_map:
                year_path_map[item.announcement_id] = path_map[item.announcement_id]
                continue
            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
            if existing_path is not None:
                target_path = get_pdf_target_path(output_dir, item)
                final_path = relocate_existing_pdf(
                    existing_path,
                    target_path,
                )
                update_pdf_locator_after_relocation(
                    output_dir,
                    item.report_year,
                    existing_path,
                    final_path,
                    pdf_locator_cache,
                )
                year_path_map[item.announcement_id] = final_path
        _write_metadata_csv(Path(metadata_path), year_reports, year_path_map)
        year_value = int(Path(filtered_path).parent.name)
        main_reports_by_year[year_value] = year_reports
        main_path_maps_by_year[year_value] = year_path_map

    for replaced_path, metadata_path in zip(artifacts.replaced_paths, artifacts.replaced_metadata_paths):
        year_reports = load_report_items(Path(replaced_path))
        year_path_map: dict[str, Path] = {}
        for item in year_reports:
            if item.announcement_id in archived_path_map:
                year_path_map[item.announcement_id] = archived_path_map[item.announcement_id]
                continue
            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
            if existing_path is not None:
                target_path = get_replaced_pdf_target_path(output_dir, item)
                final_path = relocate_existing_pdf(
                    existing_path,
                    target_path,
                )
                update_pdf_locator_after_relocation(
                    output_dir,
                    item.report_year,
                    existing_path,
                    final_path,
                    pdf_locator_cache,
                )
                year_path_map[item.announcement_id] = final_path
        year_value = int(Path(replaced_path).parent.name)
        _write_replaced_metadata_csv(
            Path(metadata_path),
            year_reports,
            year_path_map,
            main_reports_by_year.get(year_value, []),
            main_path_maps_by_year.get(year_value, {}),
        )

    log(
        "INFO",
        f"{report_year} 年完成：原始公告={len(announcements)}，保留={len(reports)}，更新前版本={len(replaced_reports)}，过滤={len(filtered_out)}，"
        f"主版本下载={stats['main']['downloaded']}，主版本已存在={stats['main']['exists']}，主版本跳过={stats['main']['skipped']}，主版本失败={stats['main']['failed']}，"
        f"旧版本下载={stats['replaced']['downloaded']}，旧版本已存在={stats['replaced']['exists']}，旧版本跳过={stats['replaced']['skipped']}，旧版本失败={stats['replaced']['failed']}",
    )
    return build_year_result(
        report_year,
        announcements,
        reports,
        replaced_reports,
        filtered_out,
        artifacts,
        stats["main"],
        stats["replaced"],
    )


# ==================== 入口 ====================

async def async_main(args):
    output_dir = Path(args.output_dir)
    state_dir = Path(args.state_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    report_year_range_label = format_report_year_range(args.start_year, args.end_year)
    overall_default_se_date = default_se_date_for_year_range(args.start_year, args.end_year)
    per_year_default_dates = {
        year: default_se_date(year)
        for year in range(args.start_year, args.end_year + 1)
    }

    client = CninfoClient(timeout=40.0, request_interval=args.request_interval)
    if args.se_date:
        log("INFO", f"{report_year_range_label} 年报使用自定义抓取窗口：{args.se_date}")
        if args.start_year != args.end_year:
            log("INFO", "说明: 当前自定义 se-date 会应用到每个年份任务，不会按年份自动展开默认窗口。")
    else:
        if args.start_year == args.end_year:
            log("INFO", f"{args.start_year} 年报默认抓取窗口：{overall_default_se_date}")
        else:
            log("INFO", f"{report_year_range_label} 年报默认抓取窗口整体覆盖：{overall_default_se_date}")
            log(
                "INFO",
                f"按年执行窗口: {args.start_year}年->{per_year_default_dates[args.start_year]} | "
                f"{args.end_year}年->{per_year_default_dates[args.end_year]}",
            )
    log("INFO", "预热: 访问巨潮资讯网...")
    await asyncio.to_thread(client.warmup)

    download_pdf = bool(args.download_pdf and not args.metadata_only)
    download_sem = asyncio.Semaphore(args.download_concurrency) if download_pdf else None
    summary = []

    async def run_years(announcement_session, download_session):
        for year in range(args.start_year, args.end_year + 1):
            raise_if_cancelled()
            se_date = args.se_date or default_se_date(year)
            log("INFO", f"\n{'='*50} {year} 年年报 {'='*50}")
            result = await process_year_with_replaced(
                client=client,
                announcement_session=announcement_session,
                download_session=download_session,
                report_year=year,
                se_date=se_date,
                output_dir=output_dir,
                state_dir=state_dir,
                page_size=args.page_size,
                announcement_concurrency=args.announcement_concurrency,
                download_sem=download_sem,
                metadata_only=not download_pdf,
            )
            result["report_year_range"] = report_year_range_label
            result["default_year_se_date"] = per_year_default_dates[year]
            result["overall_default_se_date"] = overall_default_se_date
            result["effective_se_date"] = se_date
            result["se_date_mode"] = "custom" if args.se_date else "default_per_year"
            summary.append(result)

    if not download_pdf:
        log("INFO", "当前模式仅抓取 announcement，PDF 下载已关闭。")
        if aiohttp is None:
            await run_years(announcement_session=None, download_session=None)
        else:
            timeout = aiohttp.ClientTimeout(total=120)
            connector = aiohttp.TCPConnector(limit=max(32, args.announcement_concurrency * 4))
            async with aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=DEFAULT_HEADERS,
                cookies=client.session.cookies.get_dict(),
            ) as announcement_session:
                await run_years(announcement_session=announcement_session, download_session=None)

        summary_path = output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        log("INFO", "\n" + "=" * 60)
        log("INFO", "全部完成，汇总如下：")
        total_raw = sum(r.get("raw_total", 0) for r in summary)
        total_filtered = sum(r.get("filtered_total", 0) for r in summary)
        total_filtered_out = sum(r.get("filtered_out_total", 0) for r in summary)
        log("INFO", f"  原始公告总数: {total_raw}")
        log("INFO", f"  筛选后年报数: {total_filtered}")
        log("INFO", f"  被过滤公告数: {total_filtered_out}")
        log("INFO", f"  输出目录：{output_dir}")
        log("INFO", f"  汇总文件：{summary_path}")
        log("INFO", "=" * 60)
        return

    if aiohttp is None:
        log("WARN", "未安装 aiohttp，PDF下载退化为 requests 线程模式（建议 pip install aiohttp）")
        await run_years(announcement_session=None, download_session=None)
    else:
        timeout = aiohttp.ClientTimeout(total=120)
        ann_connector = aiohttp.TCPConnector(limit=max(32, args.announcement_concurrency * 4))
        dl_connector = aiohttp.TCPConnector(limit=max(32, args.download_concurrency * 4))
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=ann_connector,
            headers=DEFAULT_HEADERS,
            cookies=client.session.cookies.get_dict(),
        ) as announcement_session:
            async with aiohttp.ClientSession(timeout=timeout, connector=dl_connector) as session:
                await run_years(announcement_session=announcement_session, download_session=session)

    # 汇总
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    log("INFO", "\n" + "=" * 60)
    log("INFO", "全部完成，汇总如下：")
    total_raw = sum(r.get("raw_total", 0) for r in summary)
    total_filtered = sum(r.get("filtered_total", 0) for r in summary)
    total_filtered_out = sum(r.get("filtered_out_total", 0) for r in summary)
    total_dl = sum(r.get("downloaded", 0) for r in summary)
    total_ex = sum(r.get("exists", 0) for r in summary)
    total_fail = sum(r.get("failed", 0) for r in summary)
    total_skip = sum(r.get("skipped", 0) for r in summary)
    log("INFO", f"  原始公告总数：{total_raw}")
    log("INFO", f"  保留公告总数：{total_filtered}")
    log("INFO", f"  被过滤公告总数：{total_filtered_out}")
    log("INFO", f"  新下载：{total_dl}，已存在：{total_ex}，永久失败跳过：{total_skip}，失败：{total_fail}")
    log("INFO", f"  输出目录：{output_dir}")
    log("INFO", f"  汇总文件：{summary_path}")
    log("INFO", "=" * 60)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="A股年报公告爬虫 v4 - 巨潮资讯网")
    p.add_argument(
        "--start-year",
        type=int,
        default=2014,
        help="报告年度起始值；默认整体抓取窗口起点为 (start-year + 1)-01-01",
    )
    p.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="报告年度结束值；默认整体抓取窗口终点为 (end-year + 2)-06-30",
    )
    p.add_argument(
        "--se-date",
        default=None,
        help=(
            "自定义公告发布日期范围，如 2025-01-01~2026-06-30；"
            "不传时按每个 report_year 使用 year+1-01-01~year+2-06-30"
        ),
    )
    p.add_argument("--page-size", type=int, default=30)
    p.add_argument("--request-interval", type=float, default=0.2, help="API请求间隔(秒)")
    p.add_argument("--announcement-concurrency", type=int, default=8, help="公告抓取并发数")
    p.add_argument("--download-concurrency", type=int, default=8, help="PDF下载并发数")
    p.add_argument("--output-dir", default="annual_reports", help="输出目录")
    p.add_argument("--state-dir", default=".", help="断点状态目录")
    p.add_argument("--download-pdf", action="store_true", help="下载筛选后的年报 PDF")
    p.add_argument("--metadata-only", action="store_true", help="兼容旧参数：只抓元数据，不下载PDF")
    p.add_argument(
        "--audit-pdf",
        action="store_true",
        help=f"审计输出目录中的PDF（含 replaced_announcements.jsonl 对应旧版本），并写出 {PDF_AUDIT_REPORT_NAME}",
    )
    p.add_argument(
        "--cleanup-orphan-pdf",
        action="store_true",
        help=(
            "删除不在 filtered_announcements.jsonl 或 replaced_announcements.jsonl 清单中的孤儿PDF，"
            f"并写出 {NON_TARGET_PDF_CLEANUP_REPORT_NAME} 与 {PDF_AUDIT_AFTER_CLEANUP_REPORT_NAME}"
        ),
    )
    return p


def namespace_from_spider_config(config: SpiderConfig) -> argparse.Namespace:
    return argparse.Namespace(
        start_year=config.start_year,
        end_year=config.end_year,
        se_date=config.se_date,
        page_size=config.page_size,
        request_interval=config.request_interval,
        announcement_concurrency=config.announcement_concurrency,
        download_concurrency=config.download_concurrency,
        output_dir=config.output_dir,
        state_dir=config.state_dir,
        download_pdf=config.download_pdf,
        metadata_only=config.metadata_only,
        audit_pdf=config.audit_pdf,
        cleanup_orphan_pdf=config.cleanup_orphan_pdf,
    )


def build_spider_config_from_args(args: argparse.Namespace) -> SpiderConfig:
    return SpiderConfig(
        start_year=args.start_year,
        end_year=args.end_year,
        se_date=args.se_date,
        page_size=args.page_size,
        request_interval=args.request_interval,
        announcement_concurrency=args.announcement_concurrency,
        download_concurrency=args.download_concurrency,
        output_dir=args.output_dir,
        state_dir=args.state_dir,
        download_pdf=args.download_pdf,
        metadata_only=args.metadata_only,
        audit_pdf=args.audit_pdf,
        cleanup_orphan_pdf=args.cleanup_orphan_pdf,
    )


async def run_spider_service(
    config: SpiderConfig,
    *,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    console_log: bool = True,
) -> SpiderResult:
    global _cancel_requested_hook
    args = namespace_from_spider_config(config)
    if args.start_year > args.end_year:
        raise ValueError("start-year > end-year")

    start_time = time.perf_counter()
    output_dir = Path(args.output_dir)
    state_dir = Path(args.state_dir)
    summary_path = output_dir / "summary.json"

    original_log = globals()["log"]
    original_cancel_hook = _cancel_requested_hook
    _cancel_requested_hook = cancel_requested

    def bridged_log(level: str, msg: str):
        if console_log:
            original_log(level, msg)
        if log_callback is not None:
            log_callback(level, msg)
        if progress_callback is not None:
            progress_callback({"phase": "log", "message": msg, "level": level})
        if cancel_requested is not None and cancel_requested():
            raise SpiderCancelled("spider cancelled")

    globals()["log"] = bridged_log
    try:
        if run_pdf_maintenance(args):
            elapsed = time.perf_counter() - start_time
            return SpiderResult(
                mode="maintenance",
                output_dir=output_dir,
                state_dir=state_dir,
                summary_path=summary_path if summary_path.exists() else None,
                summary=None,
                elapsed_seconds=elapsed,
            )

        await async_main(args)
        summary = None
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                summary = None
        elapsed = time.perf_counter() - start_time
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "done",
                    "summary_path": str(summary_path) if summary_path.exists() else "",
                    "elapsed_seconds": elapsed,
                }
            )
        return SpiderResult(
            mode="download" if args.download_pdf and not args.metadata_only else "metadata",
            output_dir=output_dir,
            state_dir=state_dir,
            summary_path=summary_path if summary_path.exists() else None,
            summary=summary if isinstance(summary, list) else None,
            elapsed_seconds=elapsed,
        )
    finally:
        _cancel_requested_hook = original_cancel_hook
        globals()["log"] = original_log


async def run_pdf_download_service(
    config: SpiderConfig,
    *,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    console_log: bool = True,
) -> PdfDownloadResult:
    global _cancel_requested_hook

    start_time = time.perf_counter()
    output_dir = Path(config.output_dir)
    state_dir = Path(config.state_dir)
    summary_path = output_dir / "summary.json"

    if not output_dir.exists():
        raise FileNotFoundError(f"输出目录不存在: {output_dir}")

    original_log = globals()["log"]
    original_cancel_hook = _cancel_requested_hook
    _cancel_requested_hook = cancel_requested

    def bridged_log(level: str, msg: str):
        if console_log:
            original_log(level, msg)
        if log_callback is not None:
            log_callback(level, msg)
        if progress_callback is not None:
            progress_callback({"phase": "log", "message": msg, "level": level})
        if cancel_requested is not None and cancel_requested():
            raise SpiderCancelled("pdf download cancelled")

    globals()["log"] = bridged_log
    try:
        return await _run_pdf_download_service_impl(
            config=config,
            output_dir=output_dir,
            state_dir=state_dir,
            summary_path=summary_path,
            progress_callback=progress_callback,
        )
        target_items = load_target_reports_from_output_dir(output_dir)
        replaced_items = load_replaced_reports_from_output_dir(output_dir)
        pdf_total = len(target_items) + len(replaced_items)

        if pdf_total == 0:
            raise FileNotFoundError(f"未找到可下载清单: {output_dir}")

        touched_years = {item.report_year for item in target_items}
        touched_years.update(item.report_year for item in replaced_items)
        pdf_locator_cache = build_pdf_locator_cache_for_items(output_dir, target_items + replaced_items)
        permanent_failure_keys = load_permanent_download_failures(output_dir, touched_years)
        download_sem = asyncio.Semaphore(max(1, int(config.download_concurrency)))

        path_map: dict[str, Path] = {}
        archived_path_map: dict[str, Path] = {}
        aggregate = {"downloaded": 0, "exists": 0, "failed": 0, "skipped": 0}
        yearly_stats: dict[int, dict[str, int]] = {
            year: {"downloaded": 0, "exists": 0, "failed": 0, "skipped": 0}
            for year in touched_years
        }
        pending_downloads: list[tuple[str, ReportItem, Path]] = []

        for role, items, target_fn, role_path_map in (
            ("main", target_items, get_pdf_target_path, path_map),
            ("replaced", replaced_items, get_replaced_pdf_target_path, archived_path_map),
        ):
            for item in items:
                raise_if_cancelled()
                existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
                target_path = target_fn(output_dir, item)
                if existing_path is not None:
                    final_path = relocate_existing_pdf(existing_path, target_path)
                    update_pdf_locator_after_relocation(
                        output_dir,
                        item.report_year,
                        existing_path,
                        final_path,
                        pdf_locator_cache,
                    )
                    role_path_map[item.announcement_id] = final_path
                    aggregate["exists"] += 1
                    yearly_stats[item.report_year]["exists"] += 1
                    continue

                if download_failure_key(role, item) in permanent_failure_keys:
                    aggregate["skipped"] += 1
                    yearly_stats[item.report_year]["skipped"] += 1
                    log(
                        "WARN",
                        f"{item.report_year} 年跳过永久失败 [{role}]：{item.sec_code} {item.sec_name} | "
                        f"{item.announcement_title} | announcement_id={item.announcement_id}",
                    )
                    continue

                pending_downloads.append((role, item, target_path))

        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "prepare",
                    "pdf_total": pdf_total,
                    "total": len(pending_downloads),
                    "completed": 0,
                    "downloaded": 0,
                    "exists": aggregate["exists"],
                    "failed": 0,
                    "skipped": aggregate["skipped"],
                }
            )

        log("INFO", f"PDF 下载阶段开始：目标 {pdf_total} 份，待下载 {len(tasks)} 份")

        if pending_downloads:
            if aiohttp is None:
                log("WARN", "未安装 aiohttp，PDF 下载退化为 requests 线程模式")
                session_cm = None
            else:
                timeout = aiohttp.ClientTimeout(total=120)
                dl_connector = aiohttp.TCPConnector(limit=max(32, int(config.download_concurrency) * 4))
                session_cm = aiohttp.ClientSession(timeout=timeout, connector=dl_connector)

            async def run_tasks(download_session):
                finished = 0
                total = len(tasks)
                for coro in asyncio.as_completed(tasks):
                    raise_if_cancelled()
                    role, item, path, ok, msg = await coro
                    finished += 1
                    if ok:
                        register_pdf_locator_path(output_dir, item.report_year, path, pdf_locator_cache)
                    if ok and msg == "downloaded":
                        aggregate["downloaded"] += 1
                        yearly_stats[item.report_year]["downloaded"] += 1
                        if role == "main":
                            path_map[item.announcement_id] = path
                        else:
                            archived_path_map[item.announcement_id] = path
                        log("INFO", f"{item.report_year}年下载成功 [{finished}/{total}] [{role}]：{item.sec_code} {item.sec_name}")
                    elif ok and msg == "exists":
                        aggregate["exists"] += 1
                        yearly_stats[item.report_year]["exists"] += 1
                        if role == "main":
                            path_map[item.announcement_id] = path
                        else:
                            archived_path_map[item.announcement_id] = path
                    elif is_permanent_download_message(msg):
                        aggregate["skipped"] += 1
                        yearly_stats[item.report_year]["skipped"] += 1
                        append_permanent_download_failure(
                            output_dir,
                            role,
                            item,
                            path,
                            msg,
                            permanent_failure_keys,
                        )
                        log("WARN", f"{item.report_year}年远端PDF不可用 [{finished}/{total}] [{role}]：{item.sec_code} {item.sec_name}")
                    else:
                        aggregate["failed"] += 1
                        yearly_stats[item.report_year]["failed"] += 1
                        log("ERROR", f"{item.report_year}年下载失败 [{finished}/{total}] [{role}]：{item.sec_code} {item.sec_name} | {msg}")

                    if progress_callback is not None:
                        progress_callback(
                            {
                                "phase": "download",
                                "pdf_total": pdf_total,
                                "total": total,
                                "completed": finished,
                                "downloaded": aggregate["downloaded"],
                                "exists": aggregate["exists"],
                                "failed": aggregate["failed"],
                                "skipped": aggregate["skipped"],
                                "current_title": item.announcement_title,
                                "current_code": item.sec_code,
                            }
                        )

            if session_cm is None:
                await run_tasks(None)
            else:
                async with session_cm as session:
                    real_tasks: list[asyncio.Task] = []
                    for task in tasks:
                        task.cancel()
                    tasks = []
                    for role, items, target_fn, _role_path_map in (
                        ("main", target_items, get_pdf_target_path, path_map),
                        ("replaced", replaced_items, get_replaced_pdf_target_path, archived_path_map),
                    ):
                        for item in items:
                            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
                            target_path = target_fn(output_dir, item)
                            if existing_path is None and download_failure_key(role, item) not in permanent_failure_keys:
                                real_tasks.append(
                                    asyncio.create_task(
                                        _download_with_role_info(session, item, target_path, download_sem, role)
                                    )
                                )
                    tasks = real_tasks
                    await run_tasks(session)

        main_reports_by_year: dict[int, list[ReportItem]] = {}
        main_path_maps_by_year: dict[int, dict[str, Path]] = {}

        for filtered_path in sorted(output_dir.glob("*/filtered_announcements.jsonl")):
            year_reports = load_report_items(filtered_path)
            metadata_path = filtered_path.parent / "metadata.csv"
            year_path_map: dict[str, Path] = {}
            for item in year_reports:
                if item.announcement_id in path_map:
                    year_path_map[item.announcement_id] = path_map[item.announcement_id]
                    continue
                existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
                if existing_path is not None:
                    target_path = get_pdf_target_path(output_dir, item)
                    final_path = relocate_existing_pdf(existing_path, target_path)
                    update_pdf_locator_after_relocation(
                        output_dir,
                        item.report_year,
                        existing_path,
                        final_path,
                        pdf_locator_cache,
                    )
                    year_path_map[item.announcement_id] = final_path
            _write_metadata_csv(metadata_path, year_reports, year_path_map)
            year_value = int(filtered_path.parent.name)
            main_reports_by_year[year_value] = year_reports
            main_path_maps_by_year[year_value] = year_path_map

        for replaced_path in sorted(output_dir.glob(f"*/{REPLACED_REPORTS_MANIFEST_NAME}")):
            year_reports = load_report_items(replaced_path)
            metadata_path = replaced_path.parent / REPLACED_REPORTS_METADATA_NAME
            year_path_map: dict[str, Path] = {}
            for item in year_reports:
                if item.announcement_id in archived_path_map:
                    year_path_map[item.announcement_id] = archived_path_map[item.announcement_id]
                    continue
                existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
                if existing_path is not None:
                    target_path = get_replaced_pdf_target_path(output_dir, item)
                    final_path = relocate_existing_pdf(existing_path, target_path)
                    update_pdf_locator_after_relocation(
                        output_dir,
                        item.report_year,
                        existing_path,
                        final_path,
                        pdf_locator_cache,
                    )
                    year_path_map[item.announcement_id] = final_path
            year_value = int(replaced_path.parent.name)
            _write_replaced_metadata_csv(
                metadata_path,
                year_reports,
                year_path_map,
                main_reports_by_year.get(year_value, []),
                main_path_maps_by_year.get(year_value, {}),
            )

        merged_summary = merge_download_stats_into_summary(summary_path, yearly_stats)
        elapsed = time.perf_counter() - start_time
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "done",
                    "elapsed_seconds": elapsed,
                    "pdf_total": pdf_total,
                    "downloaded": aggregate["downloaded"],
                    "exists": aggregate["exists"],
                    "failed": aggregate["failed"],
                    "skipped": aggregate["skipped"],
                }
            )

        return PdfDownloadResult(
            output_dir=output_dir,
            state_dir=state_dir,
            summary_path=summary_path if summary_path.exists() else None,
            summary=merged_summary,
            elapsed_seconds=elapsed,
            pdf_total=pdf_total,
            downloaded=aggregate["downloaded"],
            exists=aggregate["exists"],
            failed=aggregate["failed"],
            skipped=aggregate["skipped"],
        )
    finally:
        _cancel_requested_hook = original_cancel_hook
        globals()["log"] = original_log


async def _run_pdf_download_service_impl(
    *,
    config: SpiderConfig,
    output_dir: Path,
    state_dir: Path,
    summary_path: Path,
    progress_callback: ProgressCallback | None,
) -> PdfDownloadResult:
    start_time = time.perf_counter()

    if not output_dir.exists():
        raise FileNotFoundError(f"输出目录不存在: {output_dir}")

    target_items = load_target_reports_from_output_dir(output_dir)
    replaced_items = load_replaced_reports_from_output_dir(output_dir)
    pdf_total = len(target_items) + len(replaced_items)
    if pdf_total == 0:
        raise FileNotFoundError(f"未找到可下载清单: {output_dir}")

    touched_years = {item.report_year for item in target_items}
    touched_years.update(item.report_year for item in replaced_items)
    pdf_locator_cache = build_pdf_locator_cache_for_items(output_dir, target_items + replaced_items)
    permanent_failure_keys = load_permanent_download_failures(output_dir, touched_years)
    download_sem = asyncio.Semaphore(max(1, int(config.download_concurrency)))

    path_map: dict[str, Path] = {}
    archived_path_map: dict[str, Path] = {}
    aggregate = {"downloaded": 0, "exists": 0, "failed": 0, "skipped": 0}
    yearly_stats: dict[int, dict[str, int]] = {
        year: {"downloaded": 0, "exists": 0, "failed": 0, "skipped": 0}
        for year in touched_years
    }
    pending_downloads: list[tuple[str, ReportItem, Path]] = []

    for role, items, target_fn, role_path_map in (
        ("main", target_items, get_pdf_target_path, path_map),
        ("replaced", replaced_items, get_replaced_pdf_target_path, archived_path_map),
    ):
        for item in items:
            raise_if_cancelled()
            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
            target_path = target_fn(output_dir, item)
            if existing_path is not None:
                final_path = relocate_existing_pdf(existing_path, target_path)
                update_pdf_locator_after_relocation(
                    output_dir,
                    item.report_year,
                    existing_path,
                    final_path,
                    pdf_locator_cache,
                )
                role_path_map[item.announcement_id] = final_path
                aggregate["exists"] += 1
                yearly_stats[item.report_year]["exists"] += 1
                continue

            if download_failure_key(role, item) in permanent_failure_keys:
                aggregate["skipped"] += 1
                yearly_stats[item.report_year]["skipped"] += 1
                log(
                    "WARN",
                    f"{item.report_year} 年跳过永久失败 [{role}]：{item.sec_code} {item.sec_name} | "
                    f"{item.announcement_title} | announcement_id={item.announcement_id}",
                )
                continue

            pending_downloads.append((role, item, target_path))

    if progress_callback is not None:
        progress_callback(
            {
                "phase": "prepare",
                "pdf_total": pdf_total,
                "total": len(pending_downloads),
                "completed": 0,
                "downloaded": 0,
                "exists": aggregate["exists"],
                "failed": 0,
                "skipped": aggregate["skipped"],
            }
        )

    log("INFO", f"PDF 下载阶段开始：目标 {pdf_total} 份，待下载 {len(pending_downloads)} 份")

    async def run_tasks(download_session) -> None:
        tasks = [
            asyncio.create_task(
                _download_with_role_info(download_session, item, target_path, download_sem, role)
            )
            for role, item, target_path in pending_downloads
        ]
        finished = 0
        total = len(tasks)
        try:
            for coro in asyncio.as_completed(tasks):
                raise_if_cancelled()
                role, item, path, ok, msg = await coro
                finished += 1
                if ok:
                    register_pdf_locator_path(output_dir, item.report_year, path, pdf_locator_cache)
                if ok and msg == "downloaded":
                    aggregate["downloaded"] += 1
                    yearly_stats[item.report_year]["downloaded"] += 1
                    if role == "main":
                        path_map[item.announcement_id] = path
                    else:
                        archived_path_map[item.announcement_id] = path
                    log("INFO", f"{item.report_year}年下载成功 [{finished}/{total}] [{role}]：{item.sec_code} {item.sec_name}")
                elif ok and msg == "exists":
                    aggregate["exists"] += 1
                    yearly_stats[item.report_year]["exists"] += 1
                    if role == "main":
                        path_map[item.announcement_id] = path
                    else:
                        archived_path_map[item.announcement_id] = path
                elif is_permanent_download_message(msg):
                    aggregate["skipped"] += 1
                    yearly_stats[item.report_year]["skipped"] += 1
                    append_permanent_download_failure(
                        output_dir,
                        role,
                        item,
                        path,
                        msg,
                        permanent_failure_keys,
                    )
                    log("WARN", f"{item.report_year}年远端PDF不可用 [{finished}/{total}] [{role}]：{item.sec_code} {item.sec_name}")
                else:
                    aggregate["failed"] += 1
                    yearly_stats[item.report_year]["failed"] += 1
                    log("ERROR", f"{item.report_year}年下载失败 [{finished}/{total}] [{role}]：{item.sec_code} {item.sec_name} | {msg}")

                if progress_callback is not None:
                    progress_callback(
                        {
                            "phase": "download",
                            "pdf_total": pdf_total,
                            "total": total,
                            "completed": finished,
                            "downloaded": aggregate["downloaded"],
                            "exists": aggregate["exists"],
                            "failed": aggregate["failed"],
                            "skipped": aggregate["skipped"],
                            "current_title": item.announcement_title,
                            "current_code": item.sec_code,
                        }
                    )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    if pending_downloads:
        if aiohttp is None:
            log("WARN", "未安装 aiohttp，PDF 下载退化为 requests 线程模式")
            await run_tasks(None)
        else:
            timeout = aiohttp.ClientTimeout(total=120)
            dl_connector = aiohttp.TCPConnector(limit=max(32, int(config.download_concurrency) * 4))
            async with aiohttp.ClientSession(timeout=timeout, connector=dl_connector) as session:
                await run_tasks(session)

    main_reports_by_year: dict[int, list[ReportItem]] = {}
    main_path_maps_by_year: dict[int, dict[str, Path]] = {}

    for filtered_path in sorted(output_dir.glob("*/filtered_announcements.jsonl")):
        year_reports = load_report_items(filtered_path)
        metadata_path = filtered_path.parent / "metadata.csv"
        year_path_map: dict[str, Path] = {}
        for item in year_reports:
            if item.announcement_id in path_map:
                year_path_map[item.announcement_id] = path_map[item.announcement_id]
                continue
            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
            if existing_path is not None:
                target_path = get_pdf_target_path(output_dir, item)
                final_path = relocate_existing_pdf(existing_path, target_path)
                update_pdf_locator_after_relocation(
                    output_dir,
                    item.report_year,
                    existing_path,
                    final_path,
                    pdf_locator_cache,
                )
                year_path_map[item.announcement_id] = final_path
        _write_metadata_csv(metadata_path, year_reports, year_path_map)
        year_value = int(filtered_path.parent.name)
        main_reports_by_year[year_value] = year_reports
        main_path_maps_by_year[year_value] = year_path_map

    for replaced_path in sorted(output_dir.glob(f"*/{REPLACED_REPORTS_MANIFEST_NAME}")):
        year_reports = load_report_items(replaced_path)
        metadata_path = replaced_path.parent / REPLACED_REPORTS_METADATA_NAME
        year_path_map: dict[str, Path] = {}
        for item in year_reports:
            if item.announcement_id in archived_path_map:
                year_path_map[item.announcement_id] = archived_path_map[item.announcement_id]
                continue
            existing_path = find_existing_pdf_path(output_dir, item, pdf_locator_cache)
            if existing_path is not None:
                target_path = get_replaced_pdf_target_path(output_dir, item)
                final_path = relocate_existing_pdf(existing_path, target_path)
                update_pdf_locator_after_relocation(
                    output_dir,
                    item.report_year,
                    existing_path,
                    final_path,
                    pdf_locator_cache,
                )
                year_path_map[item.announcement_id] = final_path
        year_value = int(replaced_path.parent.name)
        _write_replaced_metadata_csv(
            metadata_path,
            year_reports,
            year_path_map,
            main_reports_by_year.get(year_value, []),
            main_path_maps_by_year.get(year_value, {}),
        )

    merged_summary = merge_download_stats_into_summary(summary_path, yearly_stats)
    elapsed = time.perf_counter() - start_time
    if progress_callback is not None:
        progress_callback(
            {
                "phase": "done",
                "elapsed_seconds": elapsed,
                "pdf_total": pdf_total,
                "downloaded": aggregate["downloaded"],
                "exists": aggregate["exists"],
                "failed": aggregate["failed"],
                "skipped": aggregate["skipped"],
            }
        )

    return PdfDownloadResult(
        output_dir=output_dir,
        state_dir=state_dir,
        summary_path=summary_path if summary_path.exists() else None,
        summary=merged_summary,
        elapsed_seconds=elapsed,
        pdf_total=pdf_total,
        downloaded=aggregate["downloaded"],
        exists=aggregate["exists"],
        failed=aggregate["failed"],
        skipped=aggregate["skipped"],
    )


def main():
    args = build_parser().parse_args()
    if run_pdf_maintenance(args):
        return
    if args.start_year > args.end_year:
        raise ValueError("start-year > end-year")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
