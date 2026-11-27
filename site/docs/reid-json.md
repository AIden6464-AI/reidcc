<span class="tag">reference</span>

# reid.json

Your profiles, in your Reidcc folder. The launcher writes it as you make changes; you can also edit it by hand (`reid --edit`). Relative paths resolve against the Reidcc folder, so moving the folder doesn't break anything.

```json
{
  "default": "main",
  "profiles": {
    "main": { "model": "opus", "memory": true },
    "review": { "model": "sonnet", "persona": "personas/plain.md", "mode": "replace" },
    "local": { "engine": "codex", "settings": "codex/lmstudio.toml" }
  }
}
```

## Top level

| Field | What it does |
|---|---|
| `profiles` | The profiles, by name |
| `default` | The profile `reid` uses when you don't name one |
| `default_engine` | The engine a new profile starts on (`codex`; leave it out for `claude`) |
| `open_in` | `terminal` starts sessions in Windows Terminal; leave it out for a Reidcc window |
| `memory_file` | A different memory file for every profile |

## Profile fields

| Field | What it does |
|---|---|
| `engine` | `claude` (the default) or `codex` |
| `model` | The model. Empty means the engine's default |
| `effort` | Reasoning effort: Claude `low`…`max`, Codex `minimal`…`xhigh`. Set with **tune** |
| `mcp_off` | MCP server names this profile leaves out, as a list. Set with **tune** |
| `plugins` | Installed plugins turned on or off: `{"name@marketplace": false}`. Set with **tune** |
| `settings` | Sign-in file: `json/*.json` for Claude Code (API mode), `codex/*.toml` for Codex |
| `persona` | A persona file |
| `mode` | `replace` replaces the engine's prompt with the persona; otherwise it's added |
| `memory` | `true` adds the memory file |
| `memory_file`, `memory_limit` | This profile's memory file, and its size limit in characters (default 6000) |
| `args` | Extra engine arguments, as a list or one string |
| `env` | Environment variables for the session; `null` removes one |
| `statusline` | `false` turns off Reidcc's status line (Claude Code) |
| `tools` | The only tools Claude Code may use, as a list |
| `mcp` | An MCP config file, or `none`. Either way it **replaces** your own MCP servers for this profile (see [MCP servers](#mcp-servers)) |
| `no_chrome` | `true` turns off Claude in Chrome |
| `no_connectors` | `true` turns off claude.ai connectors |
| `safe` | `true` skips `CLAUDE.md` files and turns off your own MCP servers (only the profile's `mcp` file, if any) |
| `settings_json` | Claude Code settings merged onto the sign-in file for this profile |
| `proxy`, `proxy_drop` | See [proxy](./proxy) (from source only) |

## MCP servers

A profile's `mcp` is a file in Claude Code's MCP format. Put it anywhere; a relative path resolves against
the Reidcc folder, so `mcp/kiln.json` is a good home:

```json
{
  "mcpServers": {
    "kiln": { "command": "npx", "args": ["-y", "kiln-mcp"] }
  }
}
```

```json
"profiles": { "kiln": { "mcp": "mcp/kiln.json" } }
```

Setting `mcp` replaces the MCP servers you set up in Claude Code (Reidcc adds `--strict-mcp-config`), so
the session has only the servers in this file. `"mcp": "none"` gives a session with no MCP servers at all.
Leave `mcp` out to keep your own. Claude Code only: Codex profiles can't use `mcp`.
