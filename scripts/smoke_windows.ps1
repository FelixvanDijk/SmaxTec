param(
    [string]$ExecutablePath = ''
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskExecutable = if ($ExecutablePath) {
    [System.IO.Path]::GetFullPath($ExecutablePath)
} else {
    Join-Path $taskRoot 'dist\SmaxTec Workbench\SmaxTec Workbench.exe'
}
if (-not (Test-Path -LiteralPath $taskExecutable)) { throw 'Build the application first.' }
$taskOldPath = $env:PATH
$taskOldPythonPath = $env:PYTHONPATH
$taskOldBrowserPath = $env:PLAYWRIGHT_BROWSERS_PATH
$taskOldQtPlatform = $env:QT_QPA_PLATFORM
try {
    # Prove that developer Python and the user's browser cache are unnecessary.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONPATH = ''
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $taskRoot 'artifacts\deliberately-absent-browser'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $taskProcess = Start-Process -FilePath $taskExecutable -ArgumentList '--smoke-test' `
        -WorkingDirectory $env:TEMP -WindowStyle Hidden -PassThru
    if (-not $taskProcess.WaitForExit(45000)) {
        Stop-Process -Id $taskProcess.Id
        throw 'Packaged smoke test timed out.'
    }
    $taskProcess.Refresh()
    if ($taskProcess.ExitCode -ne 0) { throw "Packaged smoke test failed ($($taskProcess.ExitCode))." }
    Write-Output 'PASS: packaged Qt, Chromium, email parsers and private Outlook-helper IPC run offline without developer PATH/cache.'
} finally {
    $env:PATH = $taskOldPath
    $env:PYTHONPATH = $taskOldPythonPath
    $env:PLAYWRIGHT_BROWSERS_PATH = $taskOldBrowserPath
    $env:QT_QPA_PLATFORM = $taskOldQtPlatform
}
