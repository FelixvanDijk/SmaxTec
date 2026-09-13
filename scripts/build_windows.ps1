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
$taskTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskStage = Join-Path $taskTempRoot ('smaxtec-build-' + [guid]::NewGuid().ToString('N'))
$taskStage = [System.IO.Path]::GetFullPath($taskStage)
if (-not $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to create build staging outside the system temporary directory.'
}
$taskStageDist = Join-Path $taskStage 'dist'
$taskStageWork = Join-Path $taskStage 'work'
New-Item -ItemType Directory -Path $taskStageDist -Force | Out-Null
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
    & $taskPython -m PyInstaller --noconfirm --distpath $taskStageDist `
        --workpath $taskStageWork packaging/workbench.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    $taskBundle = Join-Path $taskStageDist 'SmaxTec Workbench'
    Copy-Item -LiteralPath (Join-Path $taskRoot 'packaging\START_HERE.txt') -Destination $taskBundle
    & (Join-Path $PSScriptRoot 'smoke_windows.ps1') `
        -ExecutablePath (Join-Path $taskBundle 'SmaxTec Workbench.exe')
    if (-not $SkipArchive) {
        $taskPublishedDist = Join-Path $taskRoot 'dist'
        New-Item -ItemType Directory -Path $taskPublishedDist -Force | Out-Null
        $taskArchive = Join-Path $taskRoot 'dist\SmaxTec-Workbench-0.8.0-windows-x64.zip'
        Compress-Archive -LiteralPath $taskBundle -DestinationPath $taskArchive -Force
        Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256
    }
    Write-Output 'Windows preview built and offline smoke test passed.'
} finally {
    $env:PLAYWRIGHT_BROWSERS_PATH = $taskPreviousBrowserPath
    Pop-Location
    if (
        (Test-Path -LiteralPath $taskStage) -and
        $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $taskStage -Recurse -Force
    }
}
