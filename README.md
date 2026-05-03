# AnnualReportSpider

一个面向巨潮资讯的 A 股年报抓取与分析小工具，核心目标是把“公告抓取、正式年报识别、PDF 下载、文本提取、数字化转型指标计算”串成一条可重复执行的流水线。

## 项目做什么

这个仓库目前包含 3 个主要阶段：

1. `spider.py`
   从巨潮公告接口抓取公告，识别正式年度报告，按真实报告年度归档，并处理同公司同年度的多版本替换关系。
2. `extract_text.py`
   从已下载 PDF 中提取纯文本，输出到 `txt_extract/`。
3. `digital_transformation.py`
   基于年报全文做关键词统计，生成数字化转型面板数据。

## 项目特点

- 按真实 `report_year` 归档，而不是简单按抓取任务年份落盘
- 自动过滤摘要、半年报、英文版、问询回复、ESG 等非目标公告
- 同公司同年度只保留一个主版本，其余版本归档到 `replaced_pdfs/`
- 支持断点续跑、PDF 续传、缺失审计和孤儿文件清理
- 支持把 PDF 进一步加工成文本和分析面板

## 目录结构

```text
.
├── main.py
├── spider.py
├── extract_text.py
├── digital_transformation.py
├── test_spider.py
├── test_digital_transformation.py
├── annual_reports/          # 年报 PDF 与索引输出
└── txt_extract/             # 文本提取输出
```

说明：

- `main.py` 只是入口，实际主流程在 `spider.py`
- `annual_reports/` 和 `txt_extract/` 都是运行产物，不建议提交到仓库

## 安装

建议使用 Python 3.10+。

```bash
pip install -r requirements.txt
pip install pymupdf
```

`requirements.txt` 当前包含：

- `requests`
- `aiohttp`

文本提取还需要：

- `pymupdf`

## 最常用命令

只抓公告，不下载 PDF：

```bash
python main.py --start-year 2014 --end-year 2024 --announcement-concurrency 4 --request-interval 0.5
```

抓公告并下载 PDF：

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
```

提取文本：

```bash
python extract_text.py --start-year 2014 --end-year 2024 --concurrency 4
```

生成数字化转型面板：

```bash
python digital_transformation.py --input-dir txt_extract --output-file digital_transformation_panel.csv
```

运行测试：

```bash
python -m unittest test_spider.py test_digital_transformation.py
```

## 主流程说明

### 1. 抓公告

`spider.py` 会调用巨潮接口抓取公告，默认按报告年度推导查询窗口：

```text
report_year -> (report_year + 1)-01-01 ~ (report_year + 2)-06-30
```

例如抓 `2014` 年报时，默认查询窗口是 `2015-01-01~2016-06-30`。

### 2. 识别正式年报

程序会根据公告标题筛选正式年度报告正文，并提取真实年份。像年报摘要、半年报、英文版、问询回复这类文件会被过滤掉。

### 3. 主版本和旧版本分离

同一公司、同一报告年度如果有多个正式版本，程序会按优先级选择一个主版本，其余版本归档。

主版本输出到：

- `annual_reports/<year>/`

旧版本输出到：

- `annual_reports/<year>/replaced_pdfs/`

索引文件包括：

- `filtered_announcements.jsonl`
- `filtered_out_announcements.jsonl`
- `replaced_announcements.jsonl`
- `metadata.csv`
- `replaced_metadata.csv`

### 4. 文本提取

`extract_text.py` 会把 `annual_reports/` 下的 PDF 转成 `txt_extract/` 下的文本文件，并保持年份目录结构一致。

### 5. 指标计算

`digital_transformation.py` 会读取 `txt_extract/` 中的文本，按关键词词典统计数字技术相关词频，并生成面板数据 CSV。

## 输出文件

抓取阶段常见输出：

- `annual_reports/<year>/*.pdf`
- `annual_reports/<year>/filtered_announcements.jsonl`
- `annual_reports/<year>/filtered_out_announcements.jsonl`
- `annual_reports/<year>/replaced_announcements.jsonl`
- `annual_reports/summary.json`

文本提取阶段常见输出：

- `txt_extract/<year>/*.txt`
- `txt_extract/text_extract_summary.json`

分析阶段常见输出：

- `digital_transformation_panel.csv`

## 断点与恢复

抓取阶段会用到：

- `checkpoint.json`
- `cache/`
- `*.pdf.part`

文本提取阶段会用到：

- `text_extract_checkpoint.json`

分析阶段会用到：

- `digital_transformation_checkpoint.jsonl`

中断后通常直接重跑原命令即可继续。

## 注意事项

- 默认建议低并发起步，先验证规则，再扩大任务规模
- `annual_reports/`、`txt_extract/`、CSV 面板结果都属于运行产物，建议不要直接提交到仓库
- 标题识别依赖公告命名规范，极少数异常标题可能仍需人工复核

## License

如需开源发布，建议补充明确的许可证文件。
