param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$readmePath = Join-Path $projectRoot "README.md"
$entryScriptPath = Join-Path $projectRoot "webview_desktop.py"
$iconPath = Join-Path $projectRoot "assets\annual_report_spider.ico"
$iconPngPath = Join-Path $projectRoot "assets\annual_report_spider.png"
$versionInfoPath = Join-Path $projectRoot "build\version_info.txt"
$syncScriptPath = Join-Path $projectRoot "scripts\sync_update_manifest.py"
$versionScriptPath = Join-Path $projectRoot "scripts\build_version_info.py"
$onedirSpecPath = Join-Path $projectRoot "scripts\pyinstaller\report_spider_gui.spec"
$onefileSpecPath = Join-Path $projectRoot "scripts\pyinstaller\report_spider_gui_onefile.spec"
Set-Location $projectRoot

Write-Host "Project root: $projectRoot"
Write-Host "Build mode: $Mode"

python $syncScriptPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Update manifest sync failed."
}

python $versionScriptPath | Out-Null

if (-not (Test-Path $iconPath)) {
    throw "Build icon not found: $iconPath"
}

if ($Mode -eq "onedir") {
    python -m PyInstaller --noconfirm --clean $onedirSpecPath
}
else {
    python -m PyInstaller --noconfirm --clean $onefileSpecPath
}

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

Write-Host ""
Write-Host "Build completed."
if ($Mode -eq "onedir") {
    Write-Host "Output: dist\\AnnualReportSpiderGUI\\AnnualReportSpiderGUI.exe"
}
else {
    Write-Host "Output: dist\\AnnualReportSpiderGUI.exe"
}
