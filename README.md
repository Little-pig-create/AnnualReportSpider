# AnnualReportSpiderGUI

一个基于 `Python + pywebview + Vue` 的桌面版年报处理工具。

## 功能
- 公告链接抓取
- PDF 下载
- 文本提取
- 任务暂停、继续、终止
- 实时日志与进度展示
- 历史任务记录
- 配置保存与更新检查

## 结构
```text
AnnualReportSpiderGUI/
├─ app_metadata.py
├─ assets/
├─ webview_console/
├─ webui/
├─ build_gui.ps1
├─ build_installer.ps1
├─ installer/
├─ update.json
└─ requirements.txt
```

## 运行
1. 安装 Python 依赖：`pip install -r requirements.txt`
2. 安装前端依赖：`cd webui && npm install`
3. 构建前端：`npm run build`
4. 检查前端类型：`npm run typecheck`
5. 启动桌面程序：`python -m webview_console`

## 说明
- `webview_console` 是桌面后端与运行时
- `webui` 是前端界面
- `app_metadata.py` 维护版本号、仓库地址、更新源和图标信息
- `update.json` / `update.json.example` 维护远端更新清单
- `sync_update_manifest.py` 用于同步版本号与更新地址

## 打包
- 构建 GUI：`powershell -ExecutionPolicy Bypass -File .\build_gui.ps1 -Mode onedir`
- 构建安装包：`powershell -ExecutionPolicy Bypass -File .\build_installer.ps1 -Mode onedir`

## 资源
- 图标：`assets/annual_report_spider.ico`
- 启动图片：`assets/annual_report_spider.png`
- 前端赞赏码图片：`webui/src/assets/wechat_reward_code.png`
