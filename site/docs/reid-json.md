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
| `settings` | Sign-in file: `json/*.json` for Claude Code (API mode), `codex/*.toml` for Codex |
| `persona` | A persona file |
| `mode` | `replace` replaces the engine's prompt with the persona; otherwise it's added |
| `memory` | `true` adds the memory file |
| `memory_file`, `memory_limit` | This profile's memory file, and its size limit in characters (default 6000) |
| `args` | Extra engine arguments, as a list or one string |
| `env` | Environment variables for the session; `null` removes one |
| `statusline` | `false` turns off Reidcc's status line (Claude Code) |
| `tools` | The only tools Claude Code may use, as a list |
| `mcp` | An MCP config file, or `none` for no MCP servers |
| `no_chrome` | `true` turns off Claude in Chrome |
| `no_connectors` | `true` turns off claude.ai connectors |
| `safe` | `true` skips `CLAUDE.md` files and uses only the profile's MCP config |
| `settings_json` | Claude Code settings merged onto the sign-in file for this profile |
| `proxy`, `proxy_drop` | See [proxy](./proxy) (from source only) |
