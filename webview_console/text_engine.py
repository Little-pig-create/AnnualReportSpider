from __future__ import annotations

import argparse
import asyncio
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import fitz
except ModuleNotFoundError as exc:
    raise SystemExit(
        "PyMuPDF is required. Install dependencies with: pip install -r requirements.txt"
    ) from exc


DEFAULT_INPUT_DIR = "annual_reports"
DEFAULT_OUTPUT_DIR = "txt_extract"
DEFAULT_STATE_DIR = "."
CHECKPOINT_NAME = "text_extract_checkpoint.json"
SUMMARY_NAME = "text_extract_summary.json"
FAILED_SAMPLE_LIMIT = 50
LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[dict[str, Any]], None]


def log(level: str, message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{level}] {now} {message}", flush=True)


@dataclass(slots=True)
class ExtractTextConfig:
    input_dir: Path
    output_dir: Path
    state_dir: Path
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    concurrency: int = 2


@dataclass(slots=True)
class ExtractTextResult:
    summary: dict[str, Any]
    summary_path: Path
    checkpoint_path: Path
    stats: dict[str, int]
    pdf_total: int
    pending_total: int


class ExtractionCancelled(Exception):
    """Raised when an extraction task is cancelled by the caller."""


def read_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def build_job_key(input_dir: Path, output_dir: Path) -> str:
    return f"{input_dir.resolve()}::{output_dir.resolve()}"


def collect_pdf_paths(
    input_dir: Path,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")

    year_dirs = sorted(
        path for path in input_dir.iterdir() if path.is_dir() and path.name.isdigit()
    )
    if year_dirs:
        pdf_paths: list[Path] = []
        for year_dir in year_dirs:
            year = int(year_dir.name)
            if start_year is not None and year < start_year:
                continue
            if end_year is not None and year > end_year:
                continue
            pdf_paths.extend(
                sorted(
                    path
                    for path in year_dir.rglob("*.pdf")
                    if path.is_file() and "replaced_pdfs" not in path.parts
                )
            )
        return pdf_paths

    return sorted(
        path
        for path in input_dir.rglob("*.pdf")
        if path.is_file() and "replaced_pdfs" not in path.parts
    )


def build_output_path(input_dir: Path, output_dir: Path, pdf_path: Path) -> Path:
    return (output_dir / pdf_path.relative_to(input_dir)).with_suffix(".txt")


def is_output_complete(path: Path) -> bool:
    return path.exists() and path.is_file()


def extract_text(pdf_path: Path) -> tuple[str, int]:
    page_texts: list[str] = []
    with fitz.open(pdf_path) as doc:
        page_count = len(doc)
        for page in doc:
            page_texts.append(page.get_text("text", sort=True) or "")
    return "\n\n".join(page_texts), page_count


def extract_text_to_file(pdf_path: Path, output_path: Path) -> tuple[int, int]:
    text, page_count = extract_text(pdf_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)
    return page_count, len(text)


async def extract_one(
    pdf_path: Path,
    output_path: Path,
    executor: ProcessPoolExecutor,
) -> tuple[Path, Path, bool, str, int, int]:
    try:
        loop = asyncio.get_running_loop()
        page_count, char_count = await loop.run_in_executor(
            executor,
            extract_text_to_file,
            pdf_path,
            output_path,
        )
        return pdf_path, output_path, True, "", page_count, char_count
    except Exception as exc:
        return pdf_path, output_path, False, str(exc), 0, 0


def build_summary(
    input_dir: Path,
    output_dir: Path,
    pdf_paths: list[Path],
    stats: dict[str, int],
    start_year: Optional[int],
    end_year: Optional[int],
    failed_samples: list[dict[str, str]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workspace": str(Path.cwd().resolve()),
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "pdf_total": len(pdf_paths),
        "year_filter": {
            "start_year": start_year,
            "end_year": end_year,
        },
        **stats,
    }
    if failed_samples:
        summary["failed_samples"] = failed_samples
    return summary


def emit_log(log_callback: Optional[LogCallback], level: str, message: str) -> None:
    if log_callback is None:
        log(level, message)
        return
    log_callback(level, message)


def emit_progress(progress_callback: Optional[ProgressCallback], **payload: Any) -> None:
    if progress_callback is None:
        return
    progress_callback(payload)


def build_config_from_args(args: argparse.Namespace) -> ExtractTextConfig:
    return ExtractTextConfig(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        state_dir=Path(args.state_dir),
        start_year=args.start_year,
        end_year=args.end_year,
        concurrency=args.concurrency,
    )


async def run_extraction(
    config: ExtractTextConfig,
    *,
    log_callback: Optional[LogCallback] = None,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_requested: Optional[Callable[[], bool]] = None,
) -> ExtractTextResult:
    input_dir = config.input_dir
    output_dir = config.output_dir
    state_dir = config.state_dir

    if config.start_year is not None and config.end_year is not None and config.start_year > config.end_year:
        raise ValueError("起始年份不能大于结束年份")

    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = collect_pdf_paths(input_dir, config.start_year, config.end_year)
    checkpoint_path = state_dir / CHECKPOINT_NAME
    checkpoint = read_json(checkpoint_path) or {}
    jobs = checkpoint.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}
        checkpoint["jobs"] = jobs

    job_key = build_job_key(input_dir, output_dir)
    job = jobs.get(job_key)
    if not isinstance(job, dict):
        job = {}
        jobs[job_key] = job

    files = job.get("files")
    if not isinstance(files, dict):
        files = {}
        job["files"] = files

    job["input_dir"] = str(input_dir.resolve())
    job["output_dir"] = str(output_dir.resolve())
    job["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(checkpoint_path, checkpoint)

    stats = {"extracted": 0, "exists": 0, "failed": 0}
    failed_samples: list[dict[str, str]] = []
    work_items: list[tuple[Path, Path]] = []

    for pdf_path in pdf_paths:
        rel_pdf = pdf_path.relative_to(input_dir).as_posix()
        output_path = build_output_path(input_dir, output_dir, pdf_path)
        rel_txt = output_path.relative_to(output_dir).as_posix()
        state = files.get(rel_pdf, {})

        if state.get("status") == "completed" and is_output_complete(output_path):
            stats["exists"] += 1
            continue

        if is_output_complete(output_path):
            stats["exists"] += 1
            files[rel_pdf] = {
                "status": "completed",
                "output": rel_txt,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            continue

        work_items.append((pdf_path, output_path))

    job["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(checkpoint_path, checkpoint)

    emit_log(
        log_callback,
        "INFO",
        (
            f"文本提取开始：输入目录={input_dir}，输出目录={output_dir}，"
            f"已存在={stats['exists']}，待处理={len(work_items)}，workers={max(1, config.concurrency)}"
        ),
    )
    emit_progress(
        progress_callback,
        phase="prepare",
        total=len(work_items),
        completed=0,
        existing=stats["exists"],
        failed=stats["failed"],
        extracted=stats["extracted"],
        pdf_total=len(pdf_paths),
    )

    worker_count = max(1, config.concurrency)
    executor = ProcessPoolExecutor(max_workers=worker_count)
    try:
        tasks = [
            asyncio.create_task(extract_one(pdf_path, output_path, executor))
            for pdf_path, output_path in work_items
        ]

        finished = 0
        total = len(tasks)
        for task in asyncio.as_completed(tasks):
            if cancel_requested is not None and cancel_requested():
                for pending_task in tasks:
                    pending_task.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                raise ExtractionCancelled("文本提取已取消")

            pdf_path, output_path, ok, err, page_count, char_count = await task
            finished += 1
            rel_pdf = pdf_path.relative_to(input_dir).as_posix()
            rel_txt = output_path.relative_to(output_dir).as_posix()

            if ok:
                stats["extracted"] += 1
                files[rel_pdf] = {
                    "status": "completed",
                    "output": rel_txt,
                    "pages": page_count,
                    "chars": char_count,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                emit_log(log_callback, "INFO", f"文本提取完成 [{finished}/{total}]：{rel_pdf}")
            else:
                stats["failed"] += 1
                files[rel_pdf] = {
                    "status": "failed",
                    "output": rel_txt,
                    "error": err,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                if len(failed_samples) < FAILED_SAMPLE_LIMIT:
                    failed_samples.append({"pdf": rel_pdf, "error": err})
                emit_log(log_callback, "ERROR", f"文本提取失败 [{finished}/{total}]：{rel_pdf} | {err}")

            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
            write_json(checkpoint_path, checkpoint)
            emit_progress(
                progress_callback,
                phase="extract",
                total=total,
                completed=finished,
                existing=stats["exists"],
                failed=stats["failed"],
                extracted=stats["extracted"],
                current_pdf=rel_pdf,
                current_output=rel_txt,
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    summary = build_summary(
        input_dir,
        output_dir,
        pdf_paths,
        stats,
        config.start_year,
        config.end_year,
        failed_samples,
    )
    summary_path = output_dir / SUMMARY_NAME
    write_json(summary_path, summary)

    emit_log(
        log_callback,
        "INFO",
        f"文本提取完成：提取={stats['extracted']}，已存在={stats['exists']}，失败={stats['failed']}",
    )
    emit_log(log_callback, "INFO", f"  checkpoint：{checkpoint_path}")
    emit_log(log_callback, "INFO", f"  汇总文件：{summary_path}")
    emit_progress(
        progress_callback,
        phase="done",
        total=len(work_items),
        completed=len(work_items),
        existing=stats["exists"],
        failed=stats["failed"],
        extracted=stats["extracted"],
        summary_path=str(summary_path),
        checkpoint_path=str(checkpoint_path),
    )
    return ExtractTextResult(
        summary=summary,
        summary_path=summary_path,
        checkpoint_path=checkpoint_path,
        stats=dict(stats),
        pdf_total=len(pdf_paths),
        pending_total=len(work_items),
    )


async def run(args: argparse.Namespace) -> None:
    await run_extraction(build_config_from_args(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从已下载年报 PDF 中提取文本，支持断点续跑")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="PDF 输入目录")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="文本输出目录")
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR, help="断点状态目录")
    parser.add_argument("--start-year", type=int, default=None, help="起始年份过滤")
    parser.add_argument("--end-year", type=int, default=None, help="结束年份过滤")
    parser.add_argument("--concurrency", type=int, default=2, help="提取并发数")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
