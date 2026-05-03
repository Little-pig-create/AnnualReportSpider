# AnnualReportSpider

一个面向巨潮资讯 A 股年报的抓取与分析工具，核心目标是把“公告抓取、正式年报识别、PDF 下载、文本提取、数字化转型指标计算”串成一条可重复执行的流程。

## 项目包含什么

当前仓库主要包含 3 个阶段：

1. `spider.py`
   从巨潮公告接口抓取公告，识别正式年度报告，按真实报告年度归档，并处理同一公司同一年份的多版本替换关系。

2. `extract_text.py`
   从已下载 PDF 中提取纯文本，输出到 `txt_extract/`。

3. `digital_transformation.py`
   基于年报全文统计数字化转型相关关键词，生成面板数据 CSV。

## 项目特点

- 按真实 `report_year` 归档，而不是简单按抓取任务年份落盘
- 自动过滤摘要、半年报、英文版、问询回复、ESG 等非目标公告
- 同公司同年度只保留一个主版本，其余版本归档到 `replaced_pdfs/`
- 支持断点续跑、PDF 续传、缺失审计和孤儿文件清理
- 支持将 PDF 进一步加工成文本并计算数字化转型指标

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
- `annual_reports/`、`txt_extract/`、面板 CSV 和 checkpoint 都是运行产物

## 安装

建议使用 Python 3.10+。

```bash
pip install -r requirements.txt
pip install pymupdf
```

当前依赖包括：

- `requests`
- `aiohttp`
- `pymupdf`

## 常用命令

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
python digital_transformation.py --input-dir txt_extract --output-file digital_transformation_panel.csv --checkpoint-file digital_transformation_checkpoint.jsonl --start-year 2014 --end-year 2024 --workers 8 --executor process --log-every 500
```

如果要从头重跑数字化转型面板：

```bash
python digital_transformation.py --input-dir txt_extract --output-file digital_transformation_panel.csv --checkpoint-file digital_transformation_checkpoint.jsonl --start-year 2014 --end-year 2024 --reset-checkpoint
```

如果任务完整结束后希望自动删除 checkpoint：

```bash
python digital_transformation.py --input-dir txt_extract --output-file digital_transformation_panel.csv --checkpoint-file digital_transformation_checkpoint.jsonl --start-year 2014 --end-year 2024 --delete-checkpoint-on-success
```

运行测试：

```bash
python -m unittest test_spider.py test_digital_transformation.py
```

## 数字化转型脚本说明

`digital_transformation.py` 会读取 `txt_extract/` 中的年报全文文本，基于吴非等（2021）图 1 的结构化关键词体系统计词频，并输出面板数据。

### 默认时间范围

默认参数为：

- `--start-year 2014`
- `--end-year 2024`

也可以按需要改成任意区间，例如：

```bash
python digital_transformation.py --start-year 2021 --end-year 2021
```

### 断点续跑

脚本支持断点续跑，依赖：

- `--checkpoint-file`

默认行为：

- 中途中断后保留 checkpoint
- 下次重跑同一命令时自动跳过已完成文件
- 任务完整结束后默认仍保留 checkpoint

可选行为：

- `--reset-checkpoint`：删除旧 checkpoint，从头开始
- `--delete-checkpoint-on-success`：成功结束后自动删除 checkpoint

### 日志

脚本会输出以下日志信息：

- 已加载元数据条数
- checkpoint 已恢复条数
- 待处理样本量
- 执行器类型与并发数
- 处理进度
- 输出文件路径
- 总耗时

### 输出字段

当前面板 CSV 包含以下核心字段：

- `stkcd`
- `year`
- `类别`
- `公司简称`
- `是否ST`
- `全文文本总长度`
- `仅中英文文本总长度`
- `人工智能技术`
- `区块链技术`
- `云计算技术`
- `大数据技术`
- `数字技术应用`
- `数字化转型`
- `ln人工智能技术`
- `ln区块链技术`
- `ln云计算技术`
- `ln大数据技术`
- `ln数字技术应用`
- `lndigit`

说明：

- `类别` 当前统一输出为 `A股`
- `是否ST` 基于最终 `公司简称` 判断，包含 `ST` 则为 `1`，否则为 `0`
- `数字化转型` 当前定义为五个一级类别词频之和：
  `人工智能技术 + 区块链技术 + 云计算技术 + 大数据技术 + 数字技术应用`
- 默认不输出字段标签文件；只有显式传入 `--label-file` 时才会生成

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
- `digital_transformation_checkpoint.jsonl`

## 注意事项

- 默认建议先用较低并发验证规则，再逐步扩大任务规模
- 标题识别依赖公告命名规范，极少数异常标题可能仍需人工复核
- 如果只想保留最终面板、不想保留状态文件，可以在完整结束时加 `--delete-checkpoint-on-success`

## License

如需开源发布，建议补充明确的许可证文件。
