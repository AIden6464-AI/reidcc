@echo off
rem Mini + slim: Claude Code's built-in core tools only (no MCP), a ~150-token system prompt
rem (native-system.md), and tool descriptions shortened in flight by the slim proxy.
rem Reuses claude-slim.cmd for the proxy (starts it on 8080 if nothing is listening there).
rem MINI_TOOLS = built-in tools to keep. Drop WebSearch,WebFetch to save tokens.
setlocal
if not defined MINI_TOOLS set "MINI_TOOLS=Read,Edit,Write,Glob,Grep,Bash,WebSearch,WebFetch"
call "%~dp0claude-slim.cmd" --system-prompt-file "%~dp0native-system.md" --tools "%MINI_TOOLS%" --strict-mcp-config --no-chrome %*
endlocal
