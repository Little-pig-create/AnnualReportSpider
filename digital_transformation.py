import argparse
import csv
import functools
import json
import logging
import math
import os
import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path


KEYWORD_GROUPS = {
    "人工智能技术": [
        "人工智能",
        "商业智能",
        "图像理解",
        "投资决策辅助系统",
        "智能数据分析",
        "智能机器人",
        "机器学习",
        "深度学习",
        "语义搜索",
        "生物识别技术",
        "人脸识别",
        "语音识别",
        "身份验证",
        "自动驾驶",
        "自然语言处理",
    ],
    "大数据技术": [
        "大数据",
        "数据挖掘",
        "文本挖掘",
        "数据可视化",
        "异构数据",
        "征信",
        "增强现实",
        "混合现实",
        "虚拟现实",
    ],
    "云计算技术": [
        "云计算",
        "流计算",
        "图计算",
        "内存计算",
        "多方安全计算",
        "类脑计算",
        "绿色计算",
        "认知计算",
        "融合架构",
        "亿级并发",
        "eb级存储",
        "物联网",
        "信息物理系统",
    ],
    "区块链技术": [
        "区块链",
        "数字货币",
        "分布式计算",
        "差分隐私技术",
        "智能金融合约",
    ],
    "数字技术应用": [
        "移动互联网",
        "工业互联网",
        "移动互联",
        "互联网医疗",
        "电子商务",
        "移动支付",
        "第三方支付",
        "nfc支付",
        "智能能源",
        "b2b",
        "b2c",
        "c2b",
        "c2c",
        "o2o",
        "网联",
        "智能穿戴",
        "智慧农业",
        "智能交通",
        "智能医疗",
        "智能客服",
        "智能家居",
        "智能投顾",
        "智能文旅",
        "智能环保",
        "智能电网",
        "智能营销",
        "数字营销",
        "无人零售",
        "互联网金融",
        "数字金融",
        "fintech",
        "金融科技",
        "量化金融",
        "开放银行",
    ],
}

NEGATIVE_WORDS = (
    "没",
    "没有",
    "无",
    "不",
    "未",
    "非",
    "并非",
    "尚未",
    "无法",
    "难以",
    "拒绝",
    "停止",
    "放弃",
    "禁止",
)

NON_NEGATING_PREFIXES = (
    "不仅",
    "不但",
    "不止",
    "不只",
    "不乏",
)

NEGATION_PATTERN = re.compile(
    r"(?:没有|并非|尚未|无法|难以|拒绝|停止|放弃|禁止|没|无|不|未|非)[\u4e00-\u9fff]{0,2}$"
)

VARIABLE_LABELS = [
    ("stkcd", "股票代码"),
    ("year", "年份"),
    ("类别", "类别"),
    ("公司简称", "公司简称"),
    ("是否ST", "是否ST"),
    ("全文文本总长度", "全文-文本总长度"),
    ("仅中英文文本总长度", "仅中英文-文本总长度"),
    ("人工智能技术", "人工智能技术词频数"),
    ("区块链技术", "区块链技术词频数"),
    ("云计算技术", "云计算技术词频数"),
    ("大数据技术", "大数据技术词频数"),
    ("数字技术应用", "数字技术应用词频数"),
    ("数字化转型", "数字化转型词频数"),
    ("ln人工智能技术", "人工智能技术加1取数"),
    ("ln区块链技术", "区块链技术加1取数"),
    ("ln云计算技术", "云计算技术加1取数"),
    ("ln大数据技术", "大数据技术加1取数"),
    ("ln数字技术应用", "数字技术应用加1取数"),
    ("lndigit", "数字化转型加1取数"),
]

CATEGORY_VALUE = "A股"
CHECKPOINT_VERSION = 1
LOGGER = logging.getLogger(__name__)
DEFAULT_START_YEAR = 2014
DEFAULT_END_YEAR = 2024


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"\s+", "", text)
    return text


def clean_company_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name or "")
    normalized = re.sub(r"[\u3000\s]+", "", normalized)
    normalized = normalized.strip("：:;；,，。.!！?？()（）[]【】<>《》\"'“”‘’")
    return normalized


def is_company_name_candidate(part: str) -> bool:
    candidate = clean_company_name(part)
    if not candidate:
        return False
    if candidate.isdigit():
        return False
    if re.fullmatch(r"20\d{2}年.*", candidate):
        return False
    if "年度报告" in candidate or "半年度报告" in candidate or "摘要" in candidate:
        return False
    return True


def extract_company_name_from_filename(file_path: Path) -> str:
    parts = [clean_company_name(part) for part in file_path.stem.split("_")[1:]]
    for index, part in enumerate(parts):
        if not is_company_name_candidate(part):
            continue
        if part == "S" and index + 1 < len(parts):
            next_part = parts[index + 1]
            if next_part.startswith("ST") or next_part.startswith("*ST"):
                return f"{part}{next_part}"
        return part
    return ""


def is_st_company(company_name: str) -> int:
    return int("ST" in clean_company_name(company_name).upper())


def _is_negated(text: str, keyword_start: int, window: int = 4) -> bool:
    prefix = text[max(0, keyword_start - window):keyword_start]
    if any(prefix.endswith(marker) for marker in NON_NEGATING_PREFIXES):
        return False
    return bool(NEGATION_PATTERN.search(prefix))


def _build_keyword_pattern(keywords: list[str]) -> re.Pattern:
    normalized_keywords = sorted(
        {_normalize_text(keyword) for keyword in keywords},
        key=len,
        reverse=True,
    )
    return re.compile("|".join(re.escape(keyword) for keyword in normalized_keywords))


def _build_master_keyword_index() -> tuple[re.Pattern, dict[str, list[str]]]:
    keyword_to_groups: dict[str, list[str]] = defaultdict(list)
    for group_name, keywords in KEYWORD_GROUPS.items():
        for keyword in keywords:
            keyword_to_groups[_normalize_text(keyword)].append(group_name)

    pattern = _build_keyword_pattern(list(keyword_to_groups))
    return pattern, dict(keyword_to_groups)


MASTER_KEYWORD_PATTERN, KEYWORD_TO_GROUPS = _build_master_keyword_index()

def count_group_frequencies(text: str) -> dict:
    if not text or not text.strip():
        return {group_name: 0 for group_name in KEYWORD_GROUPS}

    normalized_text = _normalize_text(text)
    group_counts = {group_name: 0 for group_name in KEYWORD_GROUPS}

    for match in MASTER_KEYWORD_PATTERN.finditer(normalized_text):
        if _is_negated(normalized_text, match.start()):
            continue
        for group_name in KEYWORD_TO_GROUPS[match.group(0)]:
            group_counts[group_name] += 1

    return group_counts


def count_digital_keywords(text: str) -> int:
    return sum(count_group_frequencies(text).values())


def calculate_digital_transformation(text: str) -> float:
    """
    根据吴非等（2021）图1的关键词词典，基于年报全文测算企业数字化转型强度指标。

    参数:
        text: 企业年报全文文本

    返回:
        对数化后的数字化转型强度指标，即 log(1 + 有效关键词词频)
    """
    return math.log1p(count_digital_keywords(text))


def parse_report_metadata(file_path: Path) -> dict:
    stem_parts = file_path.stem.split("_")
    stock_code = stem_parts[0] if stem_parts else ""
    company_name = extract_company_name_from_filename(file_path)

    report_year_match = re.search(r"(20\d{2})年年度报告", file_path.stem)
    report_year = report_year_match.group(1) if report_year_match else file_path.parent.name

    return {
        "stkcd": stock_code.zfill(6),
        "year": report_year,
        "公司简称": company_name.strip(),
        "file_name": file_path.name,
        "file_path": str(file_path),
    }


def count_chinese_english_length(text: str) -> int:
    return sum(1 for ch in text if ("\u4e00" <= ch <= "\u9fff") or ("a" <= ch.lower() <= "z"))


def iter_report_files(input_dir: Path):
    for file_path in sorted(input_dir.rglob("*.txt")):
        if any(part == "replaced_pdfs" for part in file_path.parts):
            continue
        yield file_path


def file_in_year_range(file_path: Path, start_year: int | None, end_year: int | None) -> bool:
    metadata = parse_report_metadata(file_path)
    try:
        year = int(metadata["year"])
    except ValueError:
        return False

    if start_year is not None and year < start_year:
        return False
    if end_year is not None and year > end_year:
        return False
    return True


def load_company_meta(meta_file: Path | None) -> dict:
    if meta_file is None or not meta_file.exists():
        return {}

    with meta_file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        records = {}
        for row in reader:
            stock_code = (
                row.get("stkcd")
                or row.get("stock_code")
                or row.get("sec_code")
                or row.get("证券代码")
                or row.get("股票代码")
                or ""
            ).strip().zfill(6)
            year = (
                row.get("year")
                or row.get("report_year")
                or row.get("年份")
                or ""
            ).strip()
            if not stock_code:
                continue

            key = (stock_code, year) if year else (stock_code, "")
            records[key] = {
                "类别": (row.get("类别") or row.get("category") or row.get("board") or "").strip(),
                "公司简称": (row.get("公司简称") or row.get("company_name") or row.get("sec_name") or "").strip(),
            }
        return records


def lookup_company_meta(meta_map: dict, stock_code: str, year: str) -> dict:
    return meta_map.get((stock_code, year)) or meta_map.get((stock_code, "")) or {}


def process_report(file_path: Path, meta_map: dict) -> dict:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    group_counts = count_group_frequencies(text)
    total_count = sum(group_counts.values())
    report_meta = parse_report_metadata(file_path)
    company_meta = lookup_company_meta(meta_map, report_meta["stkcd"], report_meta["year"])
    company_name = (
        clean_company_name(company_meta.get("公司简称", ""))
        or report_meta["公司简称"]
    )

    row = {
        "stkcd": report_meta["stkcd"],
        "year": report_meta["year"],
        "类别": CATEGORY_VALUE,
        "公司简称": company_name,
        "是否ST": is_st_company(company_name),
        "全文文本总长度": len(text),
        "仅中英文文本总长度": count_chinese_english_length(text),
        "人工智能技术": group_counts["人工智能技术"],
        "区块链技术": group_counts["区块链技术"],
        "云计算技术": group_counts["云计算技术"],
        "大数据技术": group_counts["大数据技术"],
        "数字技术应用": group_counts["数字技术应用"],
        "数字化转型": total_count,
        "ln人工智能技术": round(math.log1p(group_counts["人工智能技术"]), 6),
        "ln区块链技术": round(math.log1p(group_counts["区块链技术"]), 6),
        "ln云计算技术": round(math.log1p(group_counts["云计算技术"]), 6),
        "ln大数据技术": round(math.log1p(group_counts["大数据技术"]), 6),
        "ln数字技术应用": round(math.log1p(group_counts["数字技术应用"]), 6),
        "lndigit": round(math.log1p(total_count), 6),
    }
    return row


def checkpoint_key(file_path: Path) -> str:
    return str(file_path.resolve())


def load_checkpoint(checkpoint_file: Path) -> dict[str, dict]:
    if not checkpoint_file.exists():
        return {}

    checkpoint_rows: dict[str, dict] = {}
    with checkpoint_file.open("r", encoding="utf-8") as checkpoint:
        for line_number, line in enumerate(checkpoint, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                LOGGER.warning(
                    "checkpoint 第 %s 行损坏，已跳过。通常是上次中断时留下的半行数据。",
                    line_number,
                )
                continue

            if payload.get("version") != CHECKPOINT_VERSION:
                continue

            file_key = payload.get("file_key")
            row = payload.get("row")
            if not file_key or not isinstance(row, dict):
                continue
            checkpoint_rows[file_key] = row

    return checkpoint_rows


def append_checkpoint_entry(checkpoint, file_key: str, row: dict) -> None:
    payload = {
        "version": CHECKPOINT_VERSION,
        "file_key": file_key,
        "row": row,
    }
    checkpoint.write(json.dumps(payload, ensure_ascii=False) + "\n")
    checkpoint.flush()


def write_output_files(rows: list[dict], output_file: Path, label_file: Path | None) -> None:
    fieldnames = [name for name, _ in VARIABLE_LABELS]
    rows.sort(key=lambda row: (int(row["year"]), row["stkcd"]))

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if label_file:
        with label_file.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["name", "label"])
            writer.writerows(VARIABLE_LABELS)


def build_panel(
    input_dir: Path,
    output_file: Path,
    label_file: Path | None,
    checkpoint_file: Path,
    meta_file: Path | None = None,
    workers: int | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    executor_type: str = "process",
    log_every: int = 1000,
    reset_checkpoint: bool = False,
    delete_checkpoint_on_success: bool = False,
) -> None:
    start_time = time.perf_counter()
    meta_map = load_company_meta(meta_file)
    report_files = [
        file_path
        for file_path in iter_report_files(input_dir)
        if file_in_year_range(file_path, start_year, end_year)
    ]
    if not report_files:
        raise FileNotFoundError(
            f"在 {input_dir} 中未找到 {start_year}-{end_year} 年范围内的年报文本文件。"
        )

    if reset_checkpoint and checkpoint_file.exists():
        checkpoint_file.unlink()
        LOGGER.info("已删除旧 checkpoint: %s", checkpoint_file)

    checkpoint_rows = load_checkpoint(checkpoint_file)
    pending_files = [
        file_path
        for file_path in report_files
        if checkpoint_key(file_path) not in checkpoint_rows
    ]
    report_keys = {checkpoint_key(file_path) for file_path in report_files}

    if workers is None:
        workers = min(8, os.cpu_count() or 4)

    LOGGER.info("加载元数据 %s 条。", len(meta_map))
    LOGGER.info("已加载 checkpoint 结果 %s 条。", len(checkpoint_rows))
    LOGGER.info(
        "准备处理 %s 份年报文本，年份范围 %s-%s，执行器=%s，workers=%s，待处理=%s。",
        len(report_files),
        start_year,
        end_year,
        executor_type,
        workers,
        len(pending_files),
    )

    worker = functools.partial(process_report, meta_map=meta_map)
    max_workers = max(1, workers)
    executor_cls = ThreadPoolExecutor if executor_type == "thread" else ProcessPoolExecutor
    completed = len(checkpoint_rows)
    total = len(report_files)

    if pending_files:
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with checkpoint_file.open("a", encoding="utf-8") as checkpoint:
            with executor_cls(max_workers=max_workers) as executor:
                row_iterator = executor.map(worker, pending_files, chunksize=100)
                for file_path, row in zip(pending_files, row_iterator):
                    file_key = checkpoint_key(file_path)
                    checkpoint_rows[file_key] = row
                    append_checkpoint_entry(checkpoint, file_key, row)
                    completed += 1
                    if completed == total or (log_every > 0 and completed % log_every == 0):
                        LOGGER.info("已处理 %s/%s 份年报。", completed, total)
    else:
        LOGGER.info("当前年份范围内的年报都已在 checkpoint 中，直接重建输出文件。")

    output_rows = [checkpoint_rows[file_key] for file_key in report_keys if file_key in checkpoint_rows]
    write_output_files(output_rows, output_file, label_file)

    if delete_checkpoint_on_success and checkpoint_file.exists():
        checkpoint_file.unlink()

    elapsed = time.perf_counter() - start_time
    LOGGER.info("面板数据已写入: %s", output_file)
    if label_file:
        LOGGER.info("字段标签已写入: %s", label_file)
    if delete_checkpoint_on_success:
        LOGGER.info("任务已完整结束，checkpoint 已删除: %s", checkpoint_file)
    else:
        LOGGER.info("任务已完整结束，checkpoint 已保留: %s", checkpoint_file)
    LOGGER.info("全部完成，用时 %.2f 秒。", elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="按吴非等（2021）口径测算企业数字化转型指标")
    parser.add_argument(
        "--input-dir",
        default="txt_extract",
        help="年报文本目录，默认使用 txt_extract",
    )
    parser.add_argument(
        "--output-file",
        default="digital_transformation_panel.csv",
        help="输出面板 CSV 文件路径",
    )
    parser.add_argument(
        "--label-file",
        default="",
        help="可选字段标签 CSV 文件路径；不传则不输出",
    )
    parser.add_argument(
        "--checkpoint-file",
        default="digital_transformation_checkpoint.jsonl",
        help="断点续跑 checkpoint 文件路径",
    )
    parser.add_argument(
        "--meta-file",
        default="",
        help="可选公司元数据 CSV，用于补充 类别/行业名称/行业代码",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 4),
        help="并行线程数，默认最多 8",
    )
    parser.add_argument(
        "--executor",
        choices=("process", "thread"),
        default="process",
        help="并行执行器，默认 process",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help="起始年份，默认 2014",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=DEFAULT_END_YEAR,
        help="结束年份，默认 2024",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="日志级别，默认 INFO",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=1000,
        help="每处理多少份年报打印一次进度，默认 1000",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="忽略并删除旧 checkpoint，从头开始重跑",
    )
    parser.add_argument(
        "--delete-checkpoint-on-success",
        action="store_true",
        help="任务完整结束后自动删除 checkpoint；默认保留",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    meta_file = Path(args.meta_file) if args.meta_file else None
    label_file = Path(args.label_file) if args.label_file else None
    if args.start_year > args.end_year:
        raise ValueError(f"起始年份不能大于结束年份: {args.start_year}-{args.end_year}")
    build_panel(
        input_dir=Path(args.input_dir),
        output_file=Path(args.output_file),
        label_file=label_file,
        checkpoint_file=Path(args.checkpoint_file),
        meta_file=meta_file,
        workers=args.workers,
        start_year=args.start_year,
        end_year=args.end_year,
        executor_type=args.executor,
        log_every=args.log_every,
        reset_checkpoint=args.reset_checkpoint,
        delete_checkpoint_on_success=args.delete_checkpoint_on_success,
    )


if __name__ == "__main__":
    main()
