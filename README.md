# AnnualReportSpider

一个面向巨潮资讯 A 股年报场景的本地化工具集，用来把“公告抓取 -> 年报识别 -> PDF 下载 -> 文本提取 -> 数字化转型指标计算”串成一条可重复执行的工作流。

这个仓库现在同时支持两种使用方式：

- 命令行模式：适合批量运行、服务器执行和脚本集成
- 桌面 GUI 模式：基于 `Tkinter + ttkbootstrap`，适合日常人工操作和可视化查看运行状态

## 项目能力

### 1. 年报抓取

`spider.py` 负责从巨潮资讯公告接口抓取公告，并完成以下工作：

- 按报告年度推导默认公告发布日期窗口
- 过滤摘要、半年报、英文版、问询回复、ESG 等非目标公告
- 识别正式年报正文并提取真实 `report_year`
- 同一公司同一年份只保留一个主版本
- 可选下载筛选后的 PDF
- 可选执行 PDF 审计与孤儿文件清理

### 2. 文本提取

`extract_text.py` 负责把已下载 PDF 批量提取为文本文件：

- 保持按年份组织的目录结构
- 支持并发提取
- 支持断点续跑
- 输出阶段性汇总 JSON

### 3. 指标计算

`digital_transformation.py` 负责基于年报全文统计数字化转型相关关键词，生成面板数据：

- 按吴非等（2021）口径统计相关词频
- 输出面板 CSV
- 支持断点续跑
- 支持删除旧 checkpoint 或任务成功后自动删除 checkpoint

### 4. 桌面 GUI

`tkinter_app.py` 提供桌面入口，当前重点覆盖：

- `年报抓取`
- `文本提取`
- `一键抓取 + 提取`
- `关于`

GUI 特性包括：

- 左右布局，适合桌面宽屏使用
- 实时日志输出
- 阶段状态卡片与进度展示
- 最终汇总卡片
- 配置自动保存
- 运行时禁用重复点击“开始运行”

详细说明可参考 [GUI_README.md](./GUI_README.md)。

## 目录结构

```text
.
├─ main.py
├─ spider.py
├─ extract_text.py
├─ digital_transformation.py
├─ tkinter_app.py
├─ GUI_README.md
├─ requirements.txt
├─ test_spider.py
├─ test_digital_transformation.py
├─ annual_reports/                  # 抓取输出目录（运行后生成）
├─ txt_extract/                     # 文本提取输出目录（运行后生成）
├─ checkpoint.json                  # 抓取阶段 checkpoint（运行后生成）
├─ text_extract_checkpoint.json     # 提取阶段 checkpoint（运行后生成）
└─ digital_transformation_panel.csv # 指标计算结果（运行后生成）
```

说明：

- `main.py` 只是 CLI 入口，实际抓取逻辑在 `spider.py`
- `annual_reports/`、`txt_extract/`、各种 checkpoint 和 CSV 都属于运行产物

## 环境要求

- Python 3.10 或更高版本
- Windows 本地环境优先（GUI 默认面向 Windows 桌面使用）

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/Little-pig-create/AnnualReportSpider.git
cd AnnualReportSpider
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

当前 `requirements.txt` 里包含：

- `requests`
- `aiohttp`
- `ttkbootstrap`

如果你在本地运行 PDF 文本提取，通常还需要安装：

```bash
pip install pymupdf
```

## 快速开始

### 方式一：启动桌面 GUI

```bash
python tkinter_app.py
```

适合想直接在桌面界面里完成：

- 参数填写
- 任务启动 / 停止
- 日志查看
- 结果汇总

### 方式二：命令行运行

#### 1. 只抓公告元数据

```bash
python main.py --start-year 2019 --end-year 2024 --announcement-concurrency 4 --request-interval 0.5
```

#### 2. 抓公告并下载 PDF

```bash
python main.py --start-year 2019 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
```

#### 3. 提取 PDF 文本

```bash
python extract_text.py --input-dir annual_reports --output-dir txt_extract --start-year 2019 --end-year 2024 --concurrency 2
```

#### 4. 计算数字化转型指标

```bash
python digital_transformation.py --input-dir txt_extract --output-file digital_transformation_panel.csv --checkpoint-file digital_transformation_checkpoint.jsonl --start-year 2019 --end-year 2024 --workers 8 --executor process --log-every 500
```

## 命令行参数说明

### `spider.py`

常用参数：

- `--start-year`：报告年度起始值，默认 `2014`
- `--end-year`：报告年度结束值，默认 `2024`
- `--se-date`：自定义公告发布日期范围，例如 `2025-01-01~2026-06-30`
- `--page-size`：每页条数，默认 `30`
- `--request-interval`：请求间隔秒数，默认 `0.2`
- `--announcement-concurrency`：公告抓取并发数，默认 `8`
- `--download-concurrency`：PDF 下载并发数，默认 `8`
- `--output-dir`：输出目录，默认 `annual_reports`
- `--state-dir`：断点状态目录，默认当前目录
- `--download-pdf`：下载筛选后的 PDF
- `--metadata-only`：只抓元数据，不下载 PDF
- `--audit-pdf`：审计输出目录中的 PDF
- `--cleanup-orphan-pdf`：清理不在索引清单中的孤儿 PDF

### `extract_text.py`

常用参数：

- `--input-dir`：PDF 输入目录，默认 `annual_reports`
- `--output-dir`：文本输出目录，默认 `txt_extract`
- `--state-dir`：断点状态目录，默认当前目录
- `--start-year`：起始年份过滤
- `--end-year`：结束年份过滤
- `--concurrency`：提取并发数，默认 `2`

### `digital_transformation.py`

常用参数：

- `--input-dir`：文本目录，默认 `txt_extract`
- `--output-file`：输出面板 CSV，默认 `digital_transformation_panel.csv`
- `--label-file`：可选字段标签 CSV
- `--checkpoint-file`：断点续跑文件
- `--meta-file`：可选公司元数据 CSV
- `--workers`：并行线程数
- `--executor`：`process` 或 `thread`
- `--start-year`：起始年份，默认 `2014`
- `--end-year`：结束年份，默认 `2024`
- `--log-level`：日志级别
- `--log-every`：每处理多少份年报输出一次进度
- `--reset-checkpoint`：删除旧 checkpoint 后重跑
- `--delete-checkpoint-on-success`：成功后自动删除 checkpoint

## 工作流说明

### 默认抓取窗口

当不传 `--se-date` 时，抓取阶段会按报告年度自动推导公告窗口：

```text
report_year -> (report_year + 1)-01-01 ~ (report_year + 2)-06-30
```

例如 `2014` 年报，对应默认查询窗口为：

```text
2015-01-01 ~ 2016-06-30
```

### 主版本与替换版本

对于同一公司、同一报告年度的多个正式版本：

- 主版本输出到 `annual_reports/<year>/`
- 被替换旧版本输出到 `annual_reports/<year>/replaced_pdfs/`

同时会生成索引文件，例如：

- `filtered_announcements.jsonl`
- `filtered_out_announcements.jsonl`
- `replaced_announcements.jsonl`
- `metadata.csv`
- `replaced_metadata.csv`

### 文本提取输出

`extract_text.py` 会把 `annual_reports/` 中的 PDF 输出到：

```text
txt_extract/<year>/*.txt
```

并生成汇总文件：

- `txt_extract/text_extract_summary.json`

### 指标计算输出

`digital_transformation.py` 典型输出包括：

- `digital_transformation_panel.csv`
- `digital_transformation_checkpoint.jsonl`
- 可选 `digital_transformation_labels.csv`

## 常见输出文件

### 抓取阶段

- `annual_reports/<year>/*.pdf`
- `annual_reports/<year>/filtered_announcements.jsonl`
- `annual_reports/<year>/filtered_out_announcements.jsonl`
- `annual_reports/<year>/replaced_announcements.jsonl`
- `annual_reports/summary.json`

### 文本提取阶段

- `txt_extract/<year>/*.txt`
- `txt_extract/text_extract_summary.json`

### 指标计算阶段

- `digital_transformation_panel.csv`
- `digital_transformation_checkpoint.jsonl`

## 测试

可运行现有单元测试：

```bash
python -m unittest test_spider.py test_digital_transformation.py
```

## 注意事项

- 建议先用较小年份范围和较低并发验证规则，再扩大规模
- 标题识别依赖公告命名规范，极少数异常标题可能需要人工复核
- 如果只关心最终结果、不想保留状态文件，可在相关阶段使用 `--delete-checkpoint-on-success`
- `gui_config.json` 属于本地 GUI 配置文件，一般不建议提交到仓库

## 推荐使用顺序

如果你是第一次使用，推荐按下面顺序验证：

1. 先用 GUI 或 CLI 抓取一个较小年份范围
2. 检查 `annual_reports/summary.json` 和 PDF 输出
3. 再运行文本提取
4. 最后按需运行数字化转型指标计算

## 后续可扩展方向

- 增加更多结果可视化和统计报表
- 提供可打包发布的桌面安装版
- 抽象统一服务层，减少 CLI 与 GUI 之间的重复封装

## License

当前仓库未附带明确的开源许可证文件。  
如果计划公开分发或对外协作，建议补充 `LICENSE` 文件后再正式发布。
