# AnnualReportSpider（桌面版）

一个面向中国上市公司年报场景的桌面化工具，提供从**公告链接抓取 → PDF 下载 → 文本提取**的完整流水线，并支持阶段化单独执行、可视化进度、任务历史与一键复跑。

项目仓库：<https://github.com/Little-pig-create/AnnualReportSpider>

---

## 1. 核心能力

- 公告链接抓取（支持沪深 A 股 / B 股 / 北交所）
- PDF 批量下载（按年份组织，支持断点）
- 文本批量提取（按年份组织，支持断点）
- 全流程执行与单阶段执行
- 实时阶段进度、图表、日志
- 历史任务中心（筛选/搜索/导出 JSON/查看详情/一键复跑）
- 任务完成通知（Element Plus Notification + 可选提示音）

---

## 2. 技术架构

### 桌面端
- `Python + pywebview` 作为桌面壳与本地 IPC（JS API）
- 后端运行时位于 `webview_console/`

### 前端
- `Vue 3 + TypeScript + Pinia + ECharts + Element Plus`
- 前端工程位于 `webui/`

### 业务脚本（保持可独立使用）
- `spider.py`：公告抓取与 PDF 下载主逻辑
- `extract_text.py`：PDF 文本提取
- `spider_fast.py`：加速版抓取能力（用于桌面流程优化）

---

## 3. 目录结构（关键部分）

```text
report_spider/
├─ webview_desktop.py            # 桌面入口
├─ webview_console/              # pywebview 后端与运行时
├─ webui/                        # Vue 前端
├─ spider.py                     # 原始抓取逻辑
├─ spider_fast.py                # 加速抓取逻辑
├─ extract_text.py               # 文本提取逻辑
├─ build_gui.ps1                 # Windows 打包脚本
├─ build_installer.ps1           # Windows 安装包脚本
├─ PACKAGING.md                  # 打包说明
└─ RELEASE_NOTES.md              # 版本说明
```

---

## 4. 环境要求

- Python 3.10+
- Node.js 18+（前端构建）
- Windows 10/11（推荐）
- WebView2 Runtime（Windows 通常默认具备）

---

## 5. 快速开始（开发运行）

### 5.1 安装 Python 依赖

```bash
pip install -r requirements.txt
pip install -r webview_console/requirements.txt
```

### 5.2 构建前端

```bash
cd webui
npm install
npm run build
cd ..
```

### 5.3 启动桌面应用

```bash
python webview_desktop.py
```

---

## 6. 命令行独立运行（可选）

### 6.1 抓取公告链接并下载 PDF

```bash
python main.py --start-year 2019 --end-year 2024 --download-pdf
```

### 6.2 仅文本提取

```bash
python extract_text.py --input-dir annual_reports --output-dir txt_extract --start-year 2019 --end-year 2024
```

---

## 7. 打包发布（Windows）

详见 `PACKAGING.md`，常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_gui.ps1 -Mode onedir
```

输出：

- `dist\AnnualReportSpiderGUI\AnnualReportSpiderGUI.exe`

---

## 8. 常见问题

### Q1：启动报“Frontend build not found”
前端未构建，请先执行 `webui/npm run build`。

### Q2：出现“pywebview 桥接尚未就绪”
通常为启动阶段短暂状态；若持续出现，检查 WebView2 环境与杀软拦截。

### Q3：历史任务一键复跑失败
该任务可能缺少 `settingsSnapshot`；请先手工保存当前配置再执行。

---

## 9. 版本与发布

- 当前版本信息见 `RELEASE_NOTES.md`
- 发布建议：
  1. 更新 `README.md` 与 `RELEASE_NOTES.md`
  2. 提交代码并打标签（例如 `4.3.0`）
  3. 推送分支与标签到 GitHub

---

## 10. License

仓库当前未附带明确开源许可证文件。若准备公开分发，建议补充 `LICENSE` 后再对外发布。
