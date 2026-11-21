@echo off
rem Claude Code with its system prompt replaced and all tools/MCP/Chrome removed.
rem --strict-mcp-config does NOT cover Claude in Chrome (built-in integration),
rem so --no-chrome is required too.
rem Extra args pass through, e.g.:  claude-stripped --model sonnet
setlocal
rem If "claude" isn't on PATH (common when double-clicked from Explorer with a very
rem long PATH), look in the standard install locations and add the first one found.
where claude >nul 2>nul
if errorlevel 1 (
  for %%D in ("%USERPROFILE%\.local\bin" "%APPDATA%\npm" "%LOCALAPPDATA%\Programs\claude" "%LOCALAPPDATA%\Microsoft\WinGet\Links") do (
    if exist "%%~D\claude.exe" set "PATH=%%~D;%PATH%" & goto :found
    if exist "%%~D\claude.cmd" set "PATH=%%~D;%PATH%" & goto :found
  )
)
:found
where claude >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: the "claude" command was not found.
  echo Install Claude Code first: https://docs.claude.com/en/docs/claude-code/setup
  echo Then open a NEW terminal window and run "claude" once to log in.
  echo.
  pause
  exit /b 1
)
call claude --system-prompt "You are a helpful assistant." --tools "" --strict-mcp-config --no-chrome %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Claude Code exited with error code %RC%. See the message above.
  echo If it says "unknown option", run:  claude update
  echo.
  pause
)
endlocal & exit /b %RC%
