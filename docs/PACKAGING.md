# Windows 打包说明

项目支持两种 Windows 分发形式：

1. 直接生成 GUI 可执行文件 `exe`
2. 基于 GUI 构建 Inno Setup 安装包

## 1. 构建 GUI

先安装 `PyInstaller`：

```powershell
pip install pyinstaller
```

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_gui.ps1 -Mode onedir
```

如需单文件模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_gui.ps1 -Mode onefile
```

输出位置：

- `onedir`：`dist\AnnualReportSpiderGUI\AnnualReportSpiderGUI.exe`
- `onefile`：`dist\AnnualReportSpiderGUI.exe`

## 2. 生成安装包

先安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)。

默认推荐基于 `onedir` 构建安装包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir
```

如果你已经提前构建好 GUI，也可以跳过 GUI 构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir -SkipGuiBuild
```

如果 `ISCC.exe` 不在系统路径中，可以显式指定：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir -ISCCPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

输出位置：

- 安装包目录：`dist\installer`

## 3. 当前打包特性

- 自动嵌入应用图标
- 自动写入 Windows 文件版本号和公司信息
- 打包时附带 `README.md` 与 `docs/RELEASE_NOTES.md`
- GUI 与安装包共用同一套版本元数据
- PyInstaller 规格文件统一放在 `scripts/pyinstaller`

## 4. 版本同步

发布前可执行：

```powershell
python .\scripts\sync_update_manifest.py 4.4.0
```

这会同步以下文件：

- `app_metadata.py`
- `update.json`
- `config/update.json.example`

更新清单会自动包含：

- 主下载链接 `url` / `downloadUrl`
- `github` / `gitee` 双渠道下载地址
- 与实际安装包一致的文件名，例如 `AnnualReportSpiderGUI-Setup-4.4.0-onedir.exe`

## 5. 推荐发布方式

- 日常测试：`onedir`
- 快速试用：`onefile`
- 正式交付：`onedir + 安装包`

## 6. 构建后归档

如果你想在打包完成后清理项目根目录中的构建产物，可以执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\archive_build_outputs.ps1 -Label 4.4.0
```

只预览归档动作时可使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\archive_build_outputs.ps1 -Label 4.4.0 -DryRun
```
