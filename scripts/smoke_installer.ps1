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
$taskInstallLog = Join-Path $taskStage 'setup.log'
$taskUninstaller = Join-Path $taskInstallDir 'unins000.exe'
$taskInstalled = $false
$taskOutputSentinel = Join-Path $taskStage 'user-collection.txt'

function Invoke-TaskProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    # ProcessStartInfo.ArgumentList preserves each native argument exactly and
    # WaitForExit prevents a GUI executable from racing the filesystem checks.
    $taskStartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $taskStartInfo.FileName = $FilePath
    $taskStartInfo.UseShellExecute = $false
    foreach ($taskArgument in $ArgumentList) {
        [void]$taskStartInfo.ArgumentList.Add($taskArgument)
    }
    $taskProcess = [System.Diagnostics.Process]::Start($taskStartInfo)
    if ($null -eq $taskProcess) {
        throw "Could not start $([System.IO.Path]::GetFileName($FilePath))."
    }
    try {
        if (-not $taskProcess.WaitForExit(180000)) {
            $taskProcess.Kill($true)
            throw "$([System.IO.Path]::GetFileName($FilePath)) exceeded the three-minute limit."
        }
        return $taskProcess.ExitCode
    } finally {
        $taskProcess.Dispose()
    }
}

New-Item -ItemType Directory -Path $taskStage -Force | Out-Null
try {
    $taskInstallExitCode = Invoke-TaskProcess -FilePath $taskInstaller -ArgumentList @(
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART',
        '/SP-',
        '/NOICONS',
        '/CURRENTUSER',
        "/LOG=$taskInstallLog",
        "/DIR=$taskInstallDir"
    )
    if ($taskInstallExitCode -ne 0) {
        throw "Silent installation failed ($taskInstallExitCode)."
    }
    $taskInstalled = Test-Path -LiteralPath $taskUninstaller -PathType Leaf
    $taskExecutable = Join-Path $taskInstallDir 'SmaxTec Workbench.exe'
    if (-not (Test-Path -LiteralPath $taskExecutable -PathType Leaf)) {
        $taskInventory = @(
            Get-ChildItem -LiteralPath $taskStage -Recurse -File -ErrorAction SilentlyContinue |
                Select-Object -First 20 -ExpandProperty FullName |
                ForEach-Object { [System.IO.Path]::GetRelativePath($taskStage, $_) }
        )
        $taskLogTail = if (Test-Path -LiteralPath $taskInstallLog -PathType Leaf) {
            @(Get-Content -LiteralPath $taskInstallLog -Tail 25) -join [Environment]::NewLine
        } else {
            '(setup log was not created)'
        }
        throw (
            "The installer returned success but the application executable is missing from " +
            "$taskInstallDir.`nStaged files: $($taskInventory -join ', ')`nSetup log tail:`n$taskLogTail"
        )
    }
    & (Join-Path $PSScriptRoot 'smoke_windows.ps1') -ExecutablePath $taskExecutable
    foreach ($taskRequired in @('QUICK_START.html', 'THIRD_PARTY_NOTICES.txt', 'dependency-inventory.json', 'licenses')) {
        if (-not (Test-Path -LiteralPath (Join-Path $taskInstallDir $taskRequired))) {
            throw "Installed application is missing $taskRequired."
        }
    }
    if (-not (Test-Path -LiteralPath $taskUninstaller -PathType Leaf)) {
        throw 'The installed application did not register its uninstaller.'
    }
    # Exercise the stable-AppId replacement path and preserve data outside {app}.
    Set-Content -LiteralPath $taskOutputSentinel -Value 'synthetic user output: preserve me'
    $taskSentinelHash = (Get-FileHash -LiteralPath $taskOutputSentinel).Hash
    $taskUpgradeExitCode = Invoke-TaskProcess -FilePath $taskInstaller -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOICONS',
        '/CURRENTUSER', "/DIR=$taskInstallDir"
    )
    if ($taskUpgradeExitCode -ne 0) { throw "Same-version upgrade failed ($taskUpgradeExitCode)." }
    & (Join-Path $PSScriptRoot 'smoke_windows.ps1') -ExecutablePath $taskExecutable
    $taskUninstallExitCode = Invoke-TaskProcess -FilePath $taskUninstaller -ArgumentList @(
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART'
    )
    if ($taskUninstallExitCode -ne 0) {
        throw "Silent uninstall failed ($taskUninstallExitCode)."
    }
    $taskInstalled = $false
    if (Test-Path -LiteralPath $taskExecutable) {
        throw 'Uninstall left the application executable behind.'
    }
    if ((Get-FileHash -LiteralPath $taskOutputSentinel).Hash -ne $taskSentinelHash) {
        throw 'Upgrade or uninstall modified user output outside the application directory.'
    }
    Write-Output 'PASS: install, installed-app smoke, same-version upgrade, uninstall and output preservation.'
} finally {
    if ($taskInstalled -and (Test-Path -LiteralPath $taskUninstaller -PathType Leaf)) {
        Invoke-TaskProcess -FilePath $taskUninstaller -ArgumentList @(
            '/VERYSILENT',
            '/SUPPRESSMSGBOXES',
            '/NORESTART'
        ) | Out-Null
    }
    if (
        (Test-Path -LiteralPath $taskStage) -and
        $taskStage.StartsWith($taskTempRoot, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $taskStage -Recurse -Force
    }
}
