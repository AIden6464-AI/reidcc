# Spec: proxy + lean setups as reid profiles

Status: built 2026-11-17. Replaces the `proxy\claude-*.cmd` launchers with profiles. Codex profiles have
their own add-ons since 2026-11-23: `SPEC-codex-proxy.md`.

## Goal
Every lean setup in `proxy\` (slim, ultra-slim, mini, mini-native, mini-slim, stripped,
capture, optimizer) is a reid profile: pick it in the TUI, Enter, done. No second window,
no port juggling, `/reid` and resume work the same as any other profile.

## New profile fields (all optional)

| field | values | effect |
|---|---|---|
| `proxy` | `"slim"`, `"ultra"`, `"optimize"`, `"capture"`, or a list such as `["slim","capture"]` | Runs Claude through a mitmproxy with those add-ons (see Proxy lifecycle). |
| `proxy_drop` | list of tool names | Removes whole tools in flight (`SLIM_DROP`). Only with `slim`/`ultra`. |
| `tools` | list of built-in tool names; `[]` = no tools | `--tools "A,B"`. Missing = all tools. |
| `mcp` | `"none"` or a path to an MCP config | `"none"`: `--strict-mcp-config` (no MCP servers). Path: `--strict-mcp-config --mcp-config <path>` (only those servers). Missing = your normal MCP servers. |
| `no_chrome` | bool | `--no-chrome` (Claude in Chrome tools off; `--strict-mcp-config` doesn't cover them). |
| `no_connectors` | bool | `ENABLE_CLAUDEAI_MCP_SERVERS=false` (claude.ai connectors such as Claude Docs off; local MCP still loads). |
| `settings_json` | object | Extra Claude Code settings for this profile, e.g. `{"skillListingMaxDescChars": 300}`. Merged on top of the `settings` file (if any) into one temp `--settings` file, since Claude takes one `--settings`. |

Existing fields are unchanged (`model`, `settings`, `persona`, `mode`, `memory`, `safe`, `args`, `env`).

Replace-mode personas get one line appended, the way `claude-ultra-slim.cmd` did:
`Working directory: <cwd>. Platform: Windows; shells: PowerShell and Git Bash.`
Replacing Claude Code's prompt otherwise drops that context.

## Proxy lifecycle
- **One proxy per session, owned by reid.** At launch reid starts
  `proxy\.venv\Scripts\mitmdump.exe -s <addon>... --listen-port <free port> -q` with cwd = `proxy\`
  (so captures land in `proxy\claude_prompts\`, optimizer audit in `proxy\claude_audit\`).
  It's stopped when the session ends, including via `/reid`.
- **Free port** chosen by the OS each time, so it never collides with the old `.cmd` launchers
  on 8080/8081 or with another reid window.
- **Hidden**, no console window. Output goes to `proxy\logs\<profile>.log` (overwritten per session).
- **No orphans:** on Windows mitmdump runs inside a Job Object set to kill-on-close, so if the
  terminal is closed or reid is killed, the proxy dies with it.
- **Add-on edits apply on the next launch** (fresh process every session). The rewrites are
  deterministic, so the prompt cache still hits across sessions.
- Claude gets `HTTPS_PROXY=http://127.0.0.1:<port>`, `NODE_EXTRA_CA_CERTS=~\.mitmproxy\mitmproxy-ca-cert.pem`,
  `NO_PROXY=localhost,127.0.0.1,::1` (ACA on 8420 and local relays bypass it).
- Startup waits up to 15 s for the port. If mitmdump exits or never listens, the launch is aborted
  with the last log lines; Claude is never started half-configured.
- `slim` and `ultra` are the same add-on at different levels, so they can't be combined.
- Only `api.anthropic.com/v1/messages` is modified. Relay profiles (`settings` → other base URL)
  pass through unmodified.

## Starter profiles (added to reid.json)

| profile | was | definition |
|---|---|---|
| `slim` | claude-slim.cmd | `proxy: slim` |
| `ultra` | claude-ultra-slim.cmd | `proxy: ultra`, persona `proxy/slim-system.md` (replace), `no_chrome`, `no_connectors`, `settings_json.skillListingMaxDescChars: 300` |
| `mini` | claude-mini-native.cmd | persona `proxy/native-system.md` (replace), `tools` core + web, `mcp: none`, `no_chrome` |
| `mini-slim` | claude-mini-slim.cmd | `mini` + `proxy: slim` |
| `mini-mcp` | claude-mini.cmd | persona `proxy/mini-system.md` (replace), `tools` web only, `mcp: proxy/mini-mcp.json`, `no_chrome` |
| `plain` | claude-stripped.cmd | persona `personas/plain.md` (replace), `tools: []`, `mcp: none`, `no_chrome` |
| `capture` | capture_addon | `main` + `proxy: capture`: normal session, every distinct prompt setup saved to `proxy\claude_prompts\` |

All use your Pro login and have memory off (memory costs ~1.5k tokens/request; turn it on per profile).

## TUI
- Edit screen gains: `proxy`, `tools`, `mcp`, `chrome`, `connectors` (pickers/toggles).
  `settings_json` and `proxy_drop` are edited in reid.json (`reid --edit`).
- The profile summary shows `proxy:<addons>`, `tools:<n>`, `mcp:none|<file>`, `lean` flags.
- The launch banner shows the proxy port; `reid --dry` shows the proxy plan without starting it.

## Not in scope
- Long-lived shared proxies (per-session is simpler and has no stale-code problem).
- Claude Desktop routing (needs OS-level CA trust; see `proxy\README.md`).

## Caveat
`slim`/`ultra` rewrite Claude Code's requests, which is unsupported and may break on a
Claude Code update. `mini`, `mini-mcp` and `plain` use official flags only.
