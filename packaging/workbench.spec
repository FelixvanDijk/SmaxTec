# PyInstaller spec. Build on Windows for a Windows distribution.
import json
import os
from pathlib import Path
from uuid import UUID

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
generated = root / "build" / "generated"
generated.mkdir(parents=True, exist_ok=True)
client_id = os.environ.get("SMAXTEC_MICROSOFT_CLIENT_ID", "").strip()
if client_id:
    try:
        client_id = str(UUID(client_id))
    except ValueError as error:
        raise SystemExit(
            "SMAXTEC_MICROSOFT_CLIENT_ID must be an approved Entra application UUID."
        ) from error
config_path = generated / "microsoft365.json"
config_path.write_text(
    json.dumps({"microsoft_client_id": client_id}, separators=(",", ":")),
    encoding="utf-8",
)

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    datas=[
        (str(root / "src" / "smaxtec" / "ui" / "theme.qss"), "smaxtec/ui"),
        (str(root / "packaging" / "START_HERE.txt"), "."),
        (str(config_path), "smaxtec"),
    ] + collect_data_files("tzdata") + sum(
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
                "XlsxWriter",
                "tzdata",
            )
        ),
        [],
    ),
    hiddenimports=collect_submodules("tzdata"),
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
