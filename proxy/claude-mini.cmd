@echo off
rem Stripped Claude Code + compact toolset (mcp__mini__read/write/edit/glob/grep/sh)
rem + ~150-token system prompt. Other MCP servers and Chrome are off.
rem MINI_BUILTINS = Claude Code built-ins to keep (web can't be done locally).
rem   WebSearch+WebFetch cost ~1.35k tokens/request; set to "" to drop them.
set "MINI_BUILTINS=WebSearch,WebFetch"
claude --system-prompt-file "%~dp0mini-system.md" --tools "%MINI_BUILTINS%" --strict-mcp-config --mcp-config "%~dp0mini-mcp.json" --no-chrome %*
