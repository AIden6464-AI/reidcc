@echo off
rem claude-slim, squeezed harder. Keeps subagents, skills, plan mode and permissions.
rem   - slim_tools_addon.py with SLIM_LEVEL=ultra: terser docs for core + meta tools
rem   - slim-system.md replaces the default system prompt (cwd/platform appended)
rem     set ULTRA_KEEP_SYSTEM=1 to keep Claude Code's default system prompt
rem   - Claude in Chrome off (--no-chrome), claude.ai connectors off
rem     (ENABLE_CLAUDEAI_MCP_SERVERS=false). Local MCP servers still load.
rem   - ultra-settings.json: skill descriptions in the skill listing capped at 300 chars
rem Uses its own proxy port (default 8081) so it never reuses a slim/capture proxy on 8080.
rem Starts the proxy minimized if nothing listens there yet. SLIM_DROP works here too.
setlocal
if not defined ULTRA_PORT set "ULTRA_PORT=8081"
set "SLIM_LEVEL=ultra"
netstat -ano | findstr /R /C:":%ULTRA_PORT% .*LISTENING" >nul
if errorlevel 1 (
  start "claude-ultra-slim proxy" /min "%~dp0.venv\Scripts\mitmdump.exe" -s "%~dp0slim_tools_addon.py" --listen-port %ULTRA_PORT% -q
  ping -n 4 127.0.0.1 >nul
)
set "HTTPS_PROXY=http://127.0.0.1:%ULTRA_PORT%"
set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem"
set "NO_PROXY=localhost,127.0.0.1,::1"
set "ENABLE_CLAUDEAI_MCP_SERVERS=false"
if defined ULTRA_KEEP_SYSTEM (
  claude --no-chrome --settings "%~dp0ultra-settings.json" %*
) else (
  claude --no-chrome --settings "%~dp0ultra-settings.json" --system-prompt-file "%~dp0slim-system.md" --append-system-prompt "Working directory: %CD%. Platform: Windows; shells: PowerShell 5.1 and Git Bash." %*
)
endlocal
