param(
    [switch]$SkipChecks,
    [switch]$SkipArchive
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create the developer environment first; see docs/DEVELOPMENT.md.'
}
$taskPreviousBrowserPath = $env:PLAYWRIGHT_BROWSERS_PATH
Push-Location -LiteralPath $taskRoot
try {
    $env:PLAYWRIGHT_BROWSERS_PATH = '0'
    & $taskPython -m playwright install --no-shell chromium
    if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed.' }
    if (-not $SkipChecks) {
        & $taskPython -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
        & $taskPython -m ruff check src tests scripts
        if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
        & $taskPython -m ruff format --check src tests scripts
        if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }
        & $taskPython -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    }
    & $taskPython -m PyInstaller --noconfirm packaging/workbench.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    $taskBundle = Join-Path $taskRoot 'dist\SmaxTec Workbench'
    Copy-Item -LiteralPath (Join-Path $taskRoot 'packaging\START_HERE.txt') -Destination $taskBundle
    & (Join-Path $PSScriptRoot 'smoke_windows.ps1')
    if (-not $SkipArchive) {
        $taskArchive = Join-Path $taskRoot 'dist\SmaxTec-Workbench-0.2.0-windows-x64.zip'
        Compress-Archive -LiteralPath $taskBundle -DestinationPath $taskArchive -Force
        Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256
    }
    Write-Output 'Windows preview built and offline smoke test passed.'
} finally {
    $env:PLAYWRIGHT_BROWSERS_PATH = $taskPreviousBrowserPath
    Pop-Location
}
