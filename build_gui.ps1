param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$readmePath = Join-Path $projectRoot "README.md"
$entryScriptPath = Join-Path $projectRoot "webview_desktop.py"
$iconPath = Join-Path $projectRoot "assets\annual_report_spider.ico"
$iconPngPath = Join-Path $projectRoot "assets\annual_report_spider.png"
$versionInfoPath = Join-Path $projectRoot "build\version_info.txt"
Set-Location $projectRoot

Write-Host "Project root: $projectRoot"
Write-Host "Build mode: $Mode"

python .\sync_update_manifest.py | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Update manifest sync failed."
}

python .\build_version_info.py | Out-Null

if (-not (Test-Path $iconPath)) {
    throw "Build icon not found: $iconPath"
}

if ($Mode -eq "onedir") {
    python -m PyInstaller --noconfirm --clean report_spider_gui.spec
}
else {
    $oneFileSpecPath = Join-Path $projectRoot "build\onefile"
    New-Item -ItemType Directory -Force -Path $oneFileSpecPath | Out-Null

    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name AnnualReportSpiderGUI `
        --specpath $oneFileSpecPath `
        --icon $iconPath `
        --version-file $versionInfoPath `
        --exclude-module pandas `
        --exclude-module scipy `
        --exclude-module numba `
        --exclude-module openpyxl `
        --exclude-module lxml `
        --add-data "${readmePath};." `
        --add-data "${iconPath};assets" `
        --add-data "${iconPngPath};assets" `
        $entryScriptPath
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
