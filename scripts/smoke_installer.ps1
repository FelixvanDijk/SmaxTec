param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskInstaller = [System.IO.Path]::GetFullPath($InstallerPath)
if (-not (Test-Path -LiteralPath $taskInstaller -PathType Leaf)) {
    throw 'Build the installer first.'
}
$taskTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskStage = [System.IO.Path]::GetFullPath(
    (Join-Path $taskTempRoot ('smaxtec-install-smoke-' + [guid]::NewGuid().ToString('N')))
)
if (-not $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to smoke-test outside the system temporary directory.'
}
$taskInstallDir = Join-Path $taskStage 'application'
$taskUninstaller = Join-Path $taskInstallDir 'unins000.exe'
$taskInstalled = $false
New-Item -ItemType Directory -Path $taskStage -Force | Out-Null
try {
    & $taskInstaller '/VERYSILENT' '/SUPPRESSMSGBOXES' '/NORESTART' '/SP-' '/NOICONS' "/DIR=$taskInstallDir"
    if ($LASTEXITCODE -ne 0) { throw "Silent installation failed ($LASTEXITCODE)." }
    $taskInstalled = $true
    $taskExecutable = Join-Path $taskInstallDir 'SmaxTec Workbench.exe'
    if (-not (Test-Path -LiteralPath $taskExecutable -PathType Leaf)) {
        throw 'The installed application executable is missing.'
    }
    & (Join-Path $PSScriptRoot 'smoke_windows.ps1') -ExecutablePath $taskExecutable
    if (-not (Test-Path -LiteralPath $taskUninstaller -PathType Leaf)) {
        throw 'The installed application did not register its uninstaller.'
    }
    & $taskUninstaller '/VERYSILENT' '/SUPPRESSMSGBOXES' '/NORESTART'
    if ($LASTEXITCODE -ne 0) { throw "Silent uninstall failed ($LASTEXITCODE)." }
    $taskInstalled = $false
    if (Test-Path -LiteralPath $taskExecutable) {
        throw 'Uninstall left the application executable behind.'
    }
    Write-Output 'PASS: installer, installed application smoke test and uninstall completed.'
} finally {
    if ($taskInstalled -and (Test-Path -LiteralPath $taskUninstaller -PathType Leaf)) {
        & $taskUninstaller '/VERYSILENT' '/SUPPRESSMSGBOXES' '/NORESTART' | Out-Null
    }
    if (
        (Test-Path -LiteralPath $taskStage) -and
        $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $taskStage -Recurse -Force
    }
}
