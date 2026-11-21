#!/usr/bin/env sh
# Claude Code with its system prompt replaced and all tools/MCP/Chrome removed.
# --strict-mcp-config does NOT cover Claude in Chrome (built-in integration),
# so --no-chrome is required too.
# Extra args pass through, e.g.:  ./claude-stripped.sh --model sonnet
exec claude --system-prompt "You are a helpful assistant." --tools "" --strict-mcp-config --no-chrome "$@"
