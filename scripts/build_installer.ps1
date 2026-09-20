param(
    [string]$ApplicationArchive = '',
    [string]$IsccPath = '',
    [string]$SignToolCommand = '',
    [switch]$SkipInstallerSmoke
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create the developer environment first; see docs/DEVELOPMENT.md.'
}
$taskProjectFile = Join-Path $taskRoot 'pyproject.toml'
$taskVersion = (& $taskPython -c "import sys, tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['project']['version'])" $taskProjectFile).Trim()
if ($taskVersion -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') {
    throw 'The installer requires a numeric application version such as 1.2.3.'
}

$taskArchive = if ($ApplicationArchive) {
    [System.IO.Path]::GetFullPath($ApplicationArchive)
} else {
    Join-Path $taskRoot "dist\SmaxTec-Workbench-$taskVersion-windows-x64.zip"
}
if (-not (Test-Path -LiteralPath $taskArchive -PathType Leaf)) {
    throw 'Build the versioned Windows application archive first.'
}

$taskCompilerCandidates = @(
    $IsccPath,
    $env:SMAXTEC_ISCC_PATH,
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
) | Where-Object { $_ }
$taskCompiler = $taskCompilerCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $taskCompiler) {
    $taskCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($taskCommand) { $taskCompiler = $taskCommand.Source }
}
if (-not $taskCompiler) {
    throw 'Inno Setup 6 was not found. Install it for developers or set SMAXTEC_ISCC_PATH.'
}
$taskCompiler = (Resolve-Path -LiteralPath $taskCompiler).Path

$taskTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskStage = [System.IO.Path]::GetFullPath(
    (Join-Path $taskTempRoot ('smaxtec-installer-' + [guid]::NewGuid().ToString('N')))
)
if (-not $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to create installer staging outside the system temporary directory.'
}
$taskBundle = Join-Path $taskStage 'SmaxTec Workbench'
$taskOutput = Join-Path $taskRoot 'dist'
$taskScript = Join-Path $taskRoot 'packaging\installer.iss'

New-Item -ItemType Directory -Path $taskStage -Force | Out-Null
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
try {
    Expand-Archive -LiteralPath $taskArchive -DestinationPath $taskStage -Force
    foreach ($required in @('SmaxTec Workbench.exe', '_internal', 'START_HERE.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $taskBundle $required))) {
            throw "The application archive is incomplete: missing $required."
        }
    }

    $taskArguments = @(
        '/Qp',
        "/DMyAppVersion=$taskVersion",
        "/DSourceDir=$taskBundle",
        "/DOutputDir=$taskOutput"
    )
    if ($SignToolCommand) {
        $taskArguments += '/DSignInstaller=1'
        $taskArguments += "/Ssigntool=$SignToolCommand"
    }
    $taskArguments += $taskScript
    & $taskCompiler @taskArguments
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }

    $taskInstaller = Join-Path $taskOutput "SmaxTec-Workbench-Setup-$taskVersion-windows-x64.exe"
    if (-not (Test-Path -LiteralPath $taskInstaller -PathType Leaf)) {
        throw 'Installer compiler did not create the expected versioned executable.'
    }
    if (-not $SkipInstallerSmoke) {
        & (Join-Path $PSScriptRoot 'smoke_installer.ps1') -InstallerPath $taskInstaller
    }
    $taskHash = Get-FileHash -LiteralPath $taskInstaller -Algorithm SHA256
    $taskHashPath = "$taskInstaller.sha256"
    Set-Content -LiteralPath $taskHashPath -Encoding ascii `
        -Value "$($taskHash.Hash.ToLowerInvariant())  $([System.IO.Path]::GetFileName($taskInstaller))"
    Write-Output "Windows installer built: $taskInstaller"
    Write-Output "SHA-256: $($taskHash.Hash)"
} finally {
    if (
        (Test-Path -LiteralPath $taskStage) -and
        $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $taskStage -Recurse -Force
    }
}
