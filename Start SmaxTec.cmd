@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\pythonw.exe" (
    echo The local preview environment has not been set up in this folder.
    echo Ask the project developer to prepare it, or use the packaged Windows preview.
    pause
    popd
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m smaxtec
popd
endlocal
