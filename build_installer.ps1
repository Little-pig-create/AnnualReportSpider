param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir",
    [switch]$SkipGuiBuild,
    [string]$ISCCPath
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installerScriptPath = Join-Path $projectRoot "installer\AnnualReportSpiderGUI.iss"
$distDir = Join-Path $projectRoot "dist"
$outputDir = Join-Path $distDir "installer"
$iconPath = Join-Path $projectRoot "assets\annual_report_spider.ico"
$appVersion = python -c "from app_metadata import APP_VERSION; print(APP_VERSION)"

Set-Location $projectRoot

function Resolve-InnoSetupCompiler {
    param([string]$PreferredPath)

    if ($PreferredPath -and (Test-Path $PreferredPath)) {
        return (Resolve-Path $PreferredPath).Path
    }

    $command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "ISCC.exe was not found. Install Inno Setup 6 or pass -ISCCPath explicitly."
}

Write-Host "Project root: $projectRoot"
Write-Host "Installer mode: $Mode"

if (-not $SkipGuiBuild) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "build_gui.ps1") -Mode $Mode
    if ($LASTEXITCODE -ne 0) {
        throw "GUI build failed."
    }
}

if (-not (Test-Path $installerScriptPath)) {
    throw "Installer script not found: $installerScriptPath"
}

if (-not (Test-Path $iconPath)) {
    throw "Installer icon not found: $iconPath"
}

$guiArtifactPath = if ($Mode -eq "onedir") {
    Join-Path $distDir "AnnualReportSpiderGUI\AnnualReportSpiderGUI.exe"
}
else {
    Join-Path $distDir "AnnualReportSpiderGUI.exe"
}

if (-not (Test-Path $guiArtifactPath)) {
    throw "GUI artifact not found: $guiArtifactPath"
}

$iscc = Resolve-InnoSetupCompiler -PreferredPath $ISCCPath
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

& $iscc `
    "/DProjectRoot=$projectRoot" `
    "/DDistDir=$distDir" `
    "/DOutputDir=$outputDir" `
    "/DIconPath=$iconPath" `
    "/DAppVersion=$appVersion" `
    "/DBuildMode=$Mode" `
    $installerScriptPath

if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed."
}

Write-Host ""
Write-Host "Installer completed."
Write-Host "Output: dist\\installer"
