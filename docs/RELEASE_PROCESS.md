# 发布流程

本文档用于规范 `AnnualReportSpiderGUI` 的本地发布、打包、归档与更新清单同步流程。

## 1. 发布前检查

在项目根目录确认以下内容：

- 版本号位于 `app_metadata.py`
- 更新清单位于 `update.json`，样例位于 `config/update.json.example`
- 前端代码和桌面端代码都已完成本次修改

推荐先执行：

```powershell
python .\scripts\sync_update_manifest.py
python -m unittest .\tests\test_release_metadata.py
```

## 2. 如需升级版本

例如发布 `4.4.1`：

```powershell
python .\scripts\sync_update_manifest.py 4.4.1
python -m unittest .\tests\test_release_metadata.py
```

这会同步：

- `app_metadata.py`
- `update.json`
- `config/update.json.example`

更新清单约定：

- `url` / `downloadUrl` 指向主渠道安装包下载地址
- `downloads.installer.github` / `downloads.installer.gitee` 提供双渠道安装包地址
- `downloads.portable.github` / `downloads.portable.gitee` 提供便携版地址
- 文件名应与真实发布产物一致

## 3. 前端准备

首次构建或前端依赖发生变化时：

```powershell
cd .\webui
npm install
npm run build
npm run typecheck
cd ..
```

## 4. 构建 GUI

推荐使用 `onedir`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_gui.ps1 -Mode onedir
```

如需单文件版本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_gui.ps1 -Mode onefile
```

## 5. 构建安装包

确保已安装 Inno Setup 6，然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir
```

如果 GUI 已经提前构建完成：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir -SkipGuiBuild
```

## 6. 构建产物归档

打包完成后，建议把本地构建产物归档，避免根目录长期堆积：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\archive_build_outputs.ps1 -Label 4.4.0
```

归档后会把项目根目录下的：

- `build`
- `dist`

移动到：

- `_archive/build_artifacts/<时间戳>_4.4.0`

如需先预览归档动作：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\archive_build_outputs.ps1 -Label 4.4.0 -DryRun
```

## 7. 发布建议顺序

建议按以下顺序执行：

1. 同步版本
2. 跑测试
3. 构建前端
4. 构建 GUI
5. 构建安装包
6. 检查 `update.json`
7. 上传发布文件
8. 归档本地 `build` / `dist`

## 8. 建议提交内容

正式发布前，建议至少确认以下文件已纳入提交：

- `app_metadata.py`
- `update.json`
- `config/update.json.example`
- `docs/RELEASE_NOTES.md`
- `scripts/pyinstaller/report_spider_gui.spec`
- 必要源码变更

本地构建产物一般不建议提交到版本库。
