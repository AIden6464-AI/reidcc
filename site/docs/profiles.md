<span class="tag">the launcher</span>

# Profiles

A profile is a named setup: engine, model, sign-in, persona, memory and switches. Make one per way you work.

## The fields

| Field | What it does |
|---|---|
| **name** | The profile's name, and its engine: `claude` or `codex` |
| **model** | The model to use. Empty means the engine's default |
| **sign-in** | `subscription` (your Claude login), or a settings file for API mode. See [engines](./engines) |
| **persona** | A Markdown file added to, or in place of, the engine's prompt. See [personas](./personas) |
| **memory** | Adds your memory file to the session. See [memory](./memory) |
| **args** | Extra arguments passed to the engine |
| **proxy** | Runs the session through Reidcc's local proxy, to trim what's sent. See [proxy](./proxy) |
| **tools** | `all`, or only the tools you tick (Claude Code) |
| **mcp** | `your servers`, `none`, or an MCP file that replaces your servers. See [MCP servers](./reid-json#mcp-servers) |
| **switches** | memory, Claude in Chrome, claude.ai connectors, and safe mode (no `CLAUDE.md`, none of your MCP servers) |

Fields an engine can't use stay visible and greyed out, so nothing is hidden.

## Making and changing profiles

- Under the list: **new profile**, **duplicate**, **delete** and **make default**. A new profile starts on the default engine from [settings](./settings).
- Rename a profile by typing in its `name` field. Changes save to `reid.json` as you make them.
- The default profile is the one `reid` uses when you don't name one.
- **open reid.json** opens the file itself, for the fields the screen doesn't show. See [reid.json](./reid-json).

## A one-line summary

Each profile in the list has a summary, for example `opus · subscription · persona plain · memory`, so you can tell them apart without opening them.
