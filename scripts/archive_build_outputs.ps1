param(
    [string]$Label,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$archiveBaseDir = Join-Path $projectRoot "_archive\build_artifacts"
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$suffix = if ($Label) { "_" + (($Label -replace '[^0-9A-Za-z_-]+', '_').Trim('_')) } else { "" }
$archiveDir = Join-Path $archiveBaseDir ($timestamp + $suffix)

Set-Location $projectRoot

$targets = @(
    @{ Name = "build"; Path = Join-Path $projectRoot "build" },
    @{ Name = "dist"; Path = Join-Path $projectRoot "dist" }
) | Where-Object { Test-Path $_.Path }

if (-not $targets) {
    Write-Host "No build outputs found."
    exit 0
}

$appVersion = python -c "from app_metadata import APP_VERSION; print(APP_VERSION)"

Write-Host "Project root: $projectRoot"
Write-Host "Archive target: $archiveDir"
Write-Host "App version: $appVersion"

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run only. The following directories would be archived:"
    foreach ($target in $targets) {
        Write-Host "- $($target.Name)"
    }
    exit 0
}

New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null

foreach ($target in $targets) {
    $destination = Join-Path $archiveDir $target.Name
    if (Test-Path $destination) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    }
    Move-Item -LiteralPath $target.Path -Destination $destination
    Write-Host "Archived: $($target.Name) -> $destination"
}

$summaryLines = @(
    "# Build Artifact Archive",
    "",
    "- Archived at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "- App version: $appVersion",
    "- Source project: $projectRoot",
    "- Archived folders: $($targets.Name -join ', ')",
    "",
    "## Restore",
    "",
    '- Move the archived `build` and `dist` directories back to the project root if needed.',
    "- Or rebuild them with:",
    '  - `powershell -ExecutionPolicy Bypass -File .\scripts\build_gui.ps1 -Mode onedir`',
    '  - `powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Mode onedir`'
)

Set-Content -LiteralPath (Join-Path $archiveDir "README.md") -Value ($summaryLines -join "`n") -Encoding UTF8

Write-Host ""
Write-Host "Archive completed."
Write-Host "Archived folders stored in: $archiveDir"
