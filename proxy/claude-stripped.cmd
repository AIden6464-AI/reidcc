@echo off
rem Claude Code with its system prompt replaced and all tools/MCP/Chrome removed.
rem --strict-mcp-config does NOT cover Claude in Chrome (built-in integration),
rem so --no-chrome is required too.
rem Extra args pass through, e.g.:  claude-stripped --model sonnet
claude --system-prompt "You are a helpful assistant." --tools "" --strict-mcp-config --no-chrome %*
