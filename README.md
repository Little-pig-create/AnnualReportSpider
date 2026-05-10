# AnnualReportSpiderGUI

基于 `Python + pywebview + Vue` 的年报抓取桌面应用。

## 功能

- 公告链接抓取
- PDF 下载
- 文本提取
- 任务暂停、继续、终止
- 实时日志与进度展示
- 历史任务记录
- 配置保存与更新检查

## 项目结构

```text
AnnualReportSpiderGUI/
├─ app_metadata.py
├─ assets/
├─ config/
│  ├─ README.md
│  ├─ update.json.example
│  └─ webview_config.example.json
├─ docs/
│  ├─ PACKAGING.md
│  └─ RELEASE_NOTES.md
├─ installer/
├─ scripts/
│  ├─ pyinstaller/
│  │  ├─ report_spider_gui.spec
│  │  └─ report_spider_gui_onefile.spec
│  ├─ build_gui.ps1
│  ├─ build_installer.ps1
│  ├─ archive_build_outputs.ps1
│  ├─ build_version_info.py
│  └─ sync_update_manifest.py
├─ tests/
│  └─ test_release_metadata.py
├─ webui/
├─ webview_console/
├─ update.json
└─ webview_desktop.py
```

## 本地运行

1. 安装 Python 依赖：`pip install -r requirements.txt`
2. 安装前端依赖：`cd webui && npm install`
3. 构建前端：`npm run build`
4. 检查前端类型：`npm run typecheck`
5. 启动桌面程序：`python -m webview_console`

## 目录说明

- `webview_console`：桌面端后端逻辑与运行入口
- `webui`：Vue 前端界面
- `scripts`：构建、版本同步、安装包脚本
- `scripts/pyinstaller`：PyInstaller 打包配置
- `config`：样例配置与辅助清单
- `docs`：打包说明与发布说明
- `tests`：版本与更新清单校验测试
- `app_metadata.py`：版本号、更新源、应用元数据
- `update.json`：远端更新清单
- `config/update.json.example`：更新清单样例
- `config/webview_config.example.json`：桌面端配置样例

## 常用命令

- 同步版本到更新清单：`python .\scripts\sync_update_manifest.py 4.4.0`
- 更新清单默认主下载链接指向安装包实际文件名，如 `AnnualReportSpiderGUI-Setup-4.4.0-onedir.exe`
- 更新清单同时包含 `github` / `gitee` 双渠道下载地址
- 构建 GUI：`powershell -ExecutionPolicy Bypass -File .\scripts\build_gui.ps1 -Mode onedir`
- 构建安装包：`powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir`
- 归档构建产物：`powershell -ExecutionPolicy Bypass -File .\scripts\archive_build_outputs.ps1 -Label 4.4.0`
- 运行测试：`python -m unittest .\tests\test_release_metadata.py`

## 相关文档

- 打包说明：`docs/PACKAGING.md`
- 发布说明：`docs/RELEASE_NOTES.md`
- 发布流程：`docs/RELEASE_PROCESS.md`

## 资源

- 应用图标：`assets/annual_report_spider.ico`
- 启动图片：`assets/annual_report_spider.png`
- 赞赏码：`webui/src/assets/wechat_reward_code.png`
