@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed. Run this in PowerShell, then reopen this file:
    echo winget install --id astral-sh.uv -e
    pause
    exit /b 1
)
uv run --no-project --cache-dir "%~dp0.uv-cache" "%~dp0terminal_menu.py" %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
