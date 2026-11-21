@echo off
rem Mini without MCP: Claude Code's own built-in tools, cut down to a core set, plus a
rem ~150-token system prompt (native-system.md). Official flags only: no proxy, no MCP server.
rem Built-in permission rules work (e.g. allow Bash(git status) but not Bash(rm *)).
rem MINI_TOOLS = built-in tools to keep. Drop WebSearch,WebFetch to save ~1.35k tokens/request.
setlocal
if not defined MINI_TOOLS set "MINI_TOOLS=Read,Edit,Write,Glob,Grep,Bash,WebSearch,WebFetch"
claude --system-prompt-file "%~dp0native-system.md" --tools "%MINI_TOOLS%" --strict-mcp-config --no-chrome %*
endlocal
