# 巨潮沪深 A 股年报爬虫

企业年报抓取工具。项目以“**按真实报告年度归档**、**同公司同年度多版本去重**、**PDF 可追溯下载**”为核心目标，覆盖公告抓取、年报识别、版本归档、断点续传、PDF 审计与孤儿文件清理的完整流程。

适用对象：

- 需要批量抓取中国沪深 A 股上市公司年报公告
- 需要从公告结果中筛出正式年度报告 PDF
- 需要同时保留主版本和被替换旧版本
- 需要对本地 PDF 结果做审计、补全和清理

使用建议：

- 默认建议使用较低并发运行，避免对巨潮服务器造成过多压力
- README 中的示例命令优先采用保守并发配置
- 如确有需要，再逐步提高并发数并观察失败率

## 目录

- [核心能力](#核心能力)
- [处理规则](#处理规则)
- [项目结构](#项目结构)
- [安装](#安装)
- [快速开始](#快速开始)
- [命令示例](#命令示例)
- [参数说明](#参数说明)
- [输出说明](#输出说明)
- [时间窗口规则](#时间窗口规则)
- [版本保留规则](#版本保留规则)
- [PDF 命名与下载规则](#pdf-命名与下载规则)
- [运行建议](#运行建议)
- [FAQ](#faq)
- [限制说明](#限制说明)

## 核心能力

### 1. 按真实报告年度归档

抓取窗口按公告发布日期查询，但程序不会按“任务年份”强行落盘，而是会从标题中提取真实 `report_year`，并将结果自动写入对应年度目录。

例如：

- 在 `2016` 任务中抓到 `2014年年度报告`
- 不会写入 `annual_reports/2016/`
- 会自动写入 `annual_reports/2014/`

### 2. 正式年度报告识别

程序会从公告标题中筛出正式年度报告正文，并过滤掉常见非目标文件，例如：

- 年报摘要
- 半年报 / 季报 / 中期报告
- 英文版 / 外文版
- ESG / CSR / 社会责任报告
- 审计意见、核查意见、独立意见
- 问询函回复、工作函回复
- 董事会、监事会、审计委员会等附件

### 3. 同公司同年度多版本去重

对于同一公司、同一报告年度的多个正式年报版本，程序会自动比较优先级，只保留一个主版本，其余正式旧版本不会丢弃，而是单独归档。

### 4. 主版本与旧版本分离保存

- 主版本 PDF 保存到 `annual_reports/<year>/`
- 被替换旧版本保存到 `annual_reports/<year>/replaced_pdfs/`
- 主版本清单写入 `filtered_announcements.jsonl`
- 旧版本清单写入 `replaced_announcements.jsonl`
- 非目标公告写入 `filtered_out_announcements.jsonl`

### 5. 并发抓取与并发下载

- 公告抓取支持 `--announcement-concurrency`
- PDF 下载支持 `--download-concurrency`
- 请求支持失败重试
- 公告抓取支持按月拆分、超阈值自动拆到按天

### 6. 断点续传

- 公告抓取支持页级断点续传
- PDF 下载支持 `.pdf.part` 续传
- 可复用 `checkpoint.json` 和 `cache/`
- 已存在完整 PDF 会自动跳过

### 7. PDF 审计与孤儿清理

支持对当前输出目录执行完整审计：

- 检查主版本 PDF 是否缺失
- 检查旧版本 PDF 是否缺失
- 检查异常小文件
- 检查 PDF 文件头
- 查找不在清单中的孤儿 PDF
- 清理真正可删除的孤儿文件

## 处理规则

项目的处理流程如下：

1. 根据报告年度生成默认抓取窗口
2. 从巨潮资讯网页公告接口抓取公告
3. 识别正式年度报告标题
4. 提取真实报告年度
5. 将结果按真实年度分配到对应目录
6. 对同公司同年度多版本做优先级比较
7. 输出主版本、旧版本、过滤结果和索引文件
8. 按需下载 PDF
9. 按需执行 PDF 审计和孤儿清理

## 项目结构

核心文件：

- [main.py](main.py)：程序入口
- [spider.py](spider.py)：抓取、筛选、下载、审计、清理主逻辑
- [requirements.txt](requirements.txt)：运行依赖

默认运行后会生成：

- `annual_reports/`：输出目录
- `checkpoint.json`：抓取断点状态
- `cache/`：公告抓取缓存

## 安装

### 环境要求

- Python 3
- Windows / Linux / macOS 均可运行

### 安装依赖

```bash
pip install -r requirements.txt
```

当前依赖：

- `requests`
- `aiohttp`

## 快速开始

### 1. 只抓公告，不下载 PDF

```bash
python main.py --start-year 2014 --end-year 2024 --announcement-concurrency 4 --request-interval 0.5
```

适用场景：

- 先检查筛选规则
- 先检查主版本 / 旧版本归档是否符合预期
- 先生成清单，再决定是否下载 PDF

### 2. 抓取并下载 PDF

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
```

该命令会同时下载：

- 主版本 PDF
- 旧版本 PDF

### 3. 下载 PDF

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --download-concurrency 2 --request-interval 0.5
```

该命令会同时下载：

- 主版本 PDF
- 旧版本 PDF

### 4. 只跑某一年

```bash
python main.py --start-year 2017 --end-year 2017 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
```

### 5. 手动指定公告发布日期范围

```bash
python main.py --start-year 2014 --end-year 2014 --se-date 2015-01-01~2016-06-30 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
```

## 命令示例

### 保守模式

推荐默认使用。适合首次全量运行，也更适合控制对服务器的访问压力。

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
```

### 提高并发模式

仅在规则已经确认、网络较稳定，且你明确接受更高服务器压力时使用。

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 8 --download-concurrency 4 --request-interval 0.2
```

### 仅抓元数据

`--metadata-only` 是兼容旧参数，等价于只抓公告、不下载 PDF。

```bash
python main.py --start-year 2014 --end-year 2024 --metadata-only --announcement-concurrency 4 --request-interval 0.5
```

### PDF 审计

```bash
python main.py --audit-pdf
```

### 清理孤儿 PDF

```bash
python main.py --cleanup-orphan-pdf
```

### 使用全新输出目录重跑

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5 --output-dir annual_reports_v2 --state-dir state_v2
```

## 参数说明

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--start-year` | 报告年度起始值 | `2014` |
| `--end-year` | 报告年度结束值 | `2024` |
| `--se-date` | 自定义公告发布日期范围，例如 `2025-01-01~2026-06-30` | 自动推导 |
| `--page-size` | 公告接口分页大小 | `30` |
| `--request-interval` | API 请求间隔秒数 | `0.2` |
| `--announcement-concurrency` | 公告抓取并发数 | `8` |
| `--download-concurrency` | PDF 下载并发数 | `8` |
| `--output-dir` | 输出目录 | `annual_reports` |
| `--state-dir` | 断点状态目录 | 当前目录 |
| `--download-pdf` | 下载筛选后的年报 PDF | 关闭 |
| `--metadata-only` | 兼容旧参数，只抓公告不下载 PDF | 关闭 |
| `--audit-pdf` | 审计当前输出目录中的 PDF | 关闭 |
| `--cleanup-orphan-pdf` | 清理不在目标清单中的孤儿 PDF | 关闭 |

说明：

- 上表中的 `8` / `8` 是程序当前默认值
- 出于控制访问压力的考虑，README 示例命令默认推荐从 `announcement-concurrency 4`、`download-concurrency 2`、`request-interval 0.5` 开始
- 不建议一开始就使用更高并发

查看完整帮助：

```bash
python main.py --help
```

## 输出说明

默认输出目录为 `annual_reports/`。

示例结构：

```text
annual_reports/
├── 2014/
│   ├── 000001_平安银行_2014年年度报告_1200694563.pdf
│   ├── filtered_announcements.jsonl
│   ├── filtered_out_announcements.jsonl
│   ├── metadata.csv
│   ├── replaced_announcements.jsonl
│   ├── replaced_metadata.csv
│   └── replaced_pdfs/
│       └── 000001_平安银行_2014年年度报告（更新前）_1200123456.pdf
├── 2024/
│   ├── 600712_南宁百货_南宁百货大楼股份有限公司2024年年度报告_1222929930.pdf
│   ├── filtered_announcements.jsonl
│   ├── filtered_out_announcements.jsonl
│   ├── metadata.csv
│   ├── replaced_announcements.jsonl
│   ├── replaced_metadata.csv
│   └── replaced_pdfs/
├── summary.json
├── pdf_audit_report.json
├── non_target_pdf_cleanup_report.json
└── pdf_audit_after_cleanup.json
```

### `filtered_announcements.jsonl`

主版本年报清单，用于：

- 主版本 PDF 下载
- 主版本 PDF 审计
- 主版本索引生成

### `replaced_announcements.jsonl`

旧版本年报清单，用于：

- 旧版本 PDF 下载
- 旧版本 PDF 审计
- 旧版本归档和追溯

### `filtered_out_announcements.jsonl`

非目标公告清单。这里保存的是被过滤掉的记录，不包含被主版本替换掉的旧版本。

### `metadata.csv`

主版本 PDF 索引，字段如下：

| 字段 | 含义 |
| --- | --- |
| `report_year` | 真实报告年度 |
| `sec_code` | 证券代码 |
| `sec_name` | 证券简称 |
| `announcement_id` | 公告 ID |
| `announcement_title` | 公告标题 |
| `pdf_url` | PDF 地址 |
| `local_path` | 本地路径 |

### `replaced_metadata.csv`

旧版本 PDF 索引，除基础字段外，还会写出“被谁替换、为什么被替换”。

额外字段：

| 字段 | 含义 |
| --- | --- |
| `replacement_announcement_id` | 替代它的主版本公告 ID |
| `replacement_announcement_title` | 替代它的主版本标题 |
| `replacement_pdf_url` | 替代它的主版本 PDF 地址 |
| `replacement_local_path` | 替代它的主版本本地路径 |
| `replacement_reason` | 被替换原因 |

`replacement_reason` 的典型示例：

- `同公司同年度存在announcement_id更大的版本，保留 1203314633，替换 1202041162`
- `同公司同年度存在标题优先级更高的版本，保留 1203314633`
- `同公司同年度存在修订优先级更高的版本，保留 1203314633`
- `同公司同年度存在发布时间更晚的版本，保留 1203314633`

### 其他汇总文件

| 文件 | 说明 |
| --- | --- |
| `summary.json` | 本次运行的年度汇总结果 |
| `pdf_audit_report.json` | PDF 审计结果 |
| `non_target_pdf_cleanup_report.json` | 孤儿 PDF 清理结果 |
| `pdf_audit_after_cleanup.json` | 清理后的再次审计结果 |

## 时间窗口规则

默认情况下，如果不传 `--se-date`，程序会为每个报告年度使用：

```text
report_year -> (report_year + 1)-01-01 ~ (report_year + 2)-06-30
```

单个年度示例：

- `2014` 年报默认抓取窗口：`2015-01-01~2016-06-30`
- `2024` 年报默认抓取窗口：`2025-01-01~2026-06-30`

如果抓取的是连续年度区间，可以将其理解为一个整体覆盖窗口：

```text
start_year~end_year -> (start_year + 1)-01-01 ~ (end_year + 2)-06-30
```

区间示例：

- `2014-2024` 年报整体默认覆盖：`2015-01-01~2026-06-30`
- `2020-2024` 年报整体默认覆盖：`2021-01-01~2026-06-30`

注意：

- “整体覆盖窗口”用于理解整批任务触达的最早和最晚公告日期
- 程序内部仍然按每个 `report_year` 分别构造窗口并逐年执行
- 不是将整个年份区间合并成单个查询请求

## 版本保留规则

对于同公司、同年度、多个正式年报版本，当前主版本保留顺序如下：

1. 优先比较 `announcement_id` 数值大小
2. `announcement_id` 更大的版本优先保留
3. 如仍无法区分，再比较标题优先级
4. 再比较修订优先级
5. 最后比较发布时间

这意味着：

- 不是简单按“是否带更新后字样”决定
- 不是默认保留第一次抓到的版本
- 当前主版本规则以 `announcement_id` 更大优先为核心

示例：

- `1202041162`
- `1203314633`

当前规则会保留：

```text
1203314633
```

## PDF 命名与下载规则

### 命名格式

```text
证券代码_证券简称_公告标题_announcement_id.pdf
```

示例：

```text
600712_南宁百货_南宁百货大楼股份有限公司2024年年度报告_1222929930.pdf
```

### 下载行为

- 已完整存在的 PDF 会自动跳过
- 旧命名文件会被识别并复用
- 错误目录中的完整 PDF 会自动归位
- `.pdf.part` 会用于断点续传
- 主版本与旧版本使用不同目录保存

### 当前实现的预检查优化

下载前的“预检查”阶段会先按年份建立本地 PDF 索引，再统一判断：

- 已存在主版本
- 已存在旧版本
- 需要归位的文件
- 本轮真正需要下载的增量任务

这样可以避免对几千个 PDF 逐条反复扫描目录，显著缩短大年份任务的预检查耗时。

## 运行建议

### 推荐顺序

```bash
python main.py --start-year 2014 --end-year 2024 --announcement-concurrency 4 --request-interval 0.5
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5
python main.py --audit-pdf
python main.py --cleanup-orphan-pdf
```

### 建议做法

- 第一次运行先只抓公告，先审查清单
- 规则确认后再下载 PDF
- 全量重跑时优先使用新的 `--output-dir` 和 `--state-dir`
- 默认建议使用较低并发，失败率明显上升时应立即回退参数
- 如无必要，不建议长期使用高并发配置

## FAQ

### 为什么在 2016 任务里会看到 2014 年年报？

因为抓取窗口按公告发布日期查询，不按报告年度查询。程序会在结果层面提取真实 `report_year`，再重新分配到对应年份目录。

### 为什么旧版本也要下载？

因为旧版本仍然是正式年报，只是不再是当前主版本。保留旧版本便于后续追溯、人工复核和版本对比。

### 为什么下载前会停一段时间？

那通常不是卡死，而是在执行预检查：扫描本地 PDF、识别已存在文件、识别旧命名文件、识别可归位文件，并计算真实增量下载任务。

### 如何从中断处继续运行？

直接重新执行原命令即可。程序会自动复用：

- `checkpoint.json`
- `cache/`
- 已下载完整 PDF
- `.pdf.part` 断点文件

### 如何按新规则重新全量跑？

最稳妥的方式是：

```bash
python main.py --start-year 2014 --end-year 2024 --download-pdf --announcement-concurrency 4 --download-concurrency 2 --request-interval 0.5 --output-dir annual_reports_v2 --state-dir state_v2
```

## 限制说明

### 1. 数据来源

本项目当前面向的是巨潮资讯网页公告抓取流程，不是官方数据镜像，也不是数据库导出工具。

### 2. 标题识别依赖公告命名规范

真实报告年度提取、正文识别和非目标过滤都依赖公告标题。极个别命名异常的公告，仍可能需要人工复核。

### 3. 并发不是越高越好

更高并发可能导致：

- 接口失败率升高
- 网络抖动时重试增多
- 总耗时不降反升
- 对目标服务器造成更高压力

建议优先从较低并发开始，逐步调参，而不是直接拉高到较大数值。
