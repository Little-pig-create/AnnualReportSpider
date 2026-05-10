# Windows 打包说明

这个项目提供两层 Windows 分发方式：

1. 直接构建 GUI 可执行文件（`.exe`）
2. 进一步生成安装包（`Setup.exe`）

## 1. 构建 GUI

推荐先安装 PyInstaller：

```powershell
pip install pyinstaller
```

然后在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_gui.ps1 -Mode onedir
```

可选的单文件模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_gui.ps1 -Mode onefile
```

输出位置：

- `onedir`: `dist\AnnualReportSpiderGUI\AnnualReportSpiderGUI.exe`
- `onefile`: `dist\AnnualReportSpiderGUI.exe`

## 2. 生成安装包

先安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)。

默认推荐基于 `onedir` 构建安装包：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_installer.ps1 -Mode onedir
```

如果你已经提前打好 GUI 包，也可以跳过 GUI 构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_installer.ps1 -Mode onedir -SkipGuiBuild
```

如果 `ISCC.exe` 不在系统路径里，可以显式指定：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_installer.ps1 -Mode onedir -ISCCPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

输出位置：

- 安装包目录：`dist\installer`

## 3. 当前打包特性

- 已嵌入应用图标
- 已写入 Windows 文件版本号和公司信息
- 打包时自动附带 `README.md` 与 `RELEASE_NOTES.md`
- GUI 运行时和安装后快捷方式使用统一应用名

## 4. 版本同步

发布前可执行：

```powershell
python .\sync_update_manifest.py 4.4.0
```

这会同步：

- `app_metadata.py`
- `update.json`
- `update.json.example`

## 5. 推荐发布方式

- 日常测试：`onedir`
- 发给单个用户快速试用：`onefile`
- 正式交付：`onedir + 安装包`
