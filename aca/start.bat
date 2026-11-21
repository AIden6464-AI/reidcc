@echo off
setlocal

rem Always start from the repo root: src/api/server.py imports "src.*" absolutely,
rem so running uvicorn from src\ fails with "No module named 'src'".
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8420"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install it or add it to PATH, then run this again.
    pause
    exit /b 1
)

echo Starting ACA API (aca-firing-api) ...
echo   API:        http://%HOST%:%PORT%/
echo   Health:     http://%HOST%:%PORT%/health
echo   Inspector:  http://%HOST%:%PORT%/inspector
echo.
echo Closing this window stops the server. Press Ctrl+C to stop it and keep the window.
echo.

rem run.py holds the server in this process and exits as soon as this window goes away,
rem so closing it cannot leave a stray python.exe on port %PORT%.
python "%~dp0run.py" --host %HOST% --port %PORT%
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo Server exited with code %EXITCODE%.
    pause
)

endlocal & exit /b %EXITCODE%
