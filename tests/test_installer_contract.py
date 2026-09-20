from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_installer_has_stable_upgrade_identity_and_non_admin_default():
    script = _text("packaging/installer.iss")

    assert "AppId={{7D62376C-0D57-46A9-A799-FD7E7EAB7E85}" in script
    assert "PrivilegesRequired=lowest" in script
    assert "PrivilegesRequiredOverridesAllowed=dialog" in script
    assert "UsePreviousAppDir=yes" in script
    assert "UninstallDisplayIcon=" in script


def test_installer_packages_only_the_prebuilt_bundle_and_registers_shortcuts():
    script = _text("packaging/installer.iss")

    assert 'Source: "{#SourceDir}\\*"' in script
    assert "recursesubdirs" in script
    assert "{group}\\{#MyAppName}" in script
    assert "{autodesktop}\\{#MyAppName}" in script
    assert "src\\" not in script


def test_installer_build_requires_smoke_unless_explicitly_skipped():
    bundle = _text("scripts/build_windows.ps1")
    build = _text("scripts/build_installer.ps1")
    smoke = _text("scripts/smoke_installer.ps1")
    workflow = _text(".github/workflows/ci.yml")

    assert "[switch]$SkipSmoke" in bundle
    assert "if (-not $SkipSmoke)" in bundle
    assert "[switch]$SkipInstallerSmoke" in build
    assert "if (-not $SkipInstallerSmoke)" in build
    assert "smoke_installer.ps1" in build
    assert "smoke_windows.ps1" in smoke
    assert "unins000.exe" in smoke
    assert "-SkipSmoke" not in workflow
    assert "-SkipInstallerSmoke" not in workflow
    assert "choco install innosetup" not in workflow.lower()
