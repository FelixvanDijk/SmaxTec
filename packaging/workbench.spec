# PyInstaller spec. Build on Windows for a Windows distribution.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    datas=[
        (str(root / "src" / "smaxtec" / "ui" / "theme.qss"), "smaxtec/ui"),
        (str(root / "packaging" / "START_HERE.txt"), "."),
    ] + sum(
        (
            copy_metadata(package)
            for package in (
                "olefile",
                "defusedxml",
                "pywin32",
                "msal",
                "requests",
                "PyJWT",
                "cryptography",
                "cffi",
                "charset-normalizer",
                "idna",
                "urllib3",
                "certifi",
            )
        ),
        [],
    ),
    hiddenimports=[],
    hookspath=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)

# The Playwright hook collects installed browsers. Ship only full Chromium,
# which also supports headless smoke tests via channel="chromium".
def keep_browser_file(entry):
    destination = entry[0].replace("\\", "/")
    marker = "/.local-browsers/"
    if marker not in destination:
        return True
    browser_folder = destination.split(marker, 1)[1].split("/", 1)[0]
    return browser_folder.startswith(("chromium-", "ffmpeg-", "winldd-"))

a.datas = [entry for entry in a.datas if keep_browser_file(entry)]
a.binaries = [entry for entry in a.binaries if keep_browser_file(entry)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SmaxTec Workbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SmaxTec Workbench",
)
