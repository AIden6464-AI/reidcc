# claude-proxy

Transparent MITM proxy that optimizes Anthropic `/v1/messages` payloads for prompt-cache efficiency. Claude Code keeps thinking it's talking to `api.anthropic.com` directly — no `ANTHROPIC_BASE_URL` rewrite, no MCP/auth side effects.

## What it does

`optimize_payload()` (in [claude_optimizer_addon.py](claude_optimizer_addon.py)):

- Strips `cache_control` from static blocks so the static prefix stays stable across turns.
- Hoists dynamic saboteurs (`<system-reminder>`, billing-header, "Today's date is…") out of `system` and out of mid-conversation messages, then re-inserts them in the final user message **after** any leading `tool_result` blocks (Anthropic API correctness invariant).
- Optionally prunes bloated tool definitions when `enable_pruning=True` (default `False`).

---

## Setup

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install --only-binary :all: mitmproxy
.\.venv\Scripts\pip.exe install pytest fastapi httpx uvicorn
```

> The `--only-binary :all:` flag is required on Windows — `zstandard` (a mitmproxy dep) doesn't build cleanly with MSVC.

### macOS / Linux (bash/zsh)

```bash
python3 -m venv .venv
./.venv/bin/pip install mitmproxy pytest fastapi httpx uvicorn
```

---

## Seed the local CA (one-time, all platforms)

Run mitmdump once so it generates `~/.mitmproxy/` (Windows: `%USERPROFILE%\.mitmproxy\`):

**Windows:**
```powershell
.\.venv\Scripts\mitmdump.exe --listen-port 8080
```

**macOS / Linux:**
```bash
./.venv/bin/mitmdump --listen-port 8080
```

Ctrl+C after a few seconds. The CA cert lands at:
- Windows: `%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem`
- macOS / Linux: `~/.mitmproxy/mitmproxy-ca-cert.pem`

---

## Run

### Window 1 — start the proxy

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\mitmdump.exe -s claude_optimizer_addon.py --listen-port 8080 -q
```

**macOS / Linux:**
```bash
./.venv/bin/mitmdump -s claude_optimizer_addon.py --listen-port 8080 -q
```

### Window 2 — launch Claude Code through the proxy

**Windows (PowerShell):**
```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:8080"
$env:NODE_EXTRA_CA_CERTS = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
$env:NO_PROXY = "localhost,127.0.0.1,::1"
claude
```

**Windows (cmd.exe):**
```cmd
set HTTPS_PROXY=http://127.0.0.1:8080
set NODE_EXTRA_CA_CERTS=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem
set NO_PROXY=localhost,127.0.0.1,::1
claude
```

**macOS / Linux (bash/zsh):**
```bash
export HTTPS_PROXY=http://127.0.0.1:8080
export NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem
export NO_PROXY="localhost,127.0.0.1,::1"
claude
```

Audit logs land in `./claude_audit/YYYY-MM-DD.jsonl` with original/optimized byte sizes and Anthropic `usage` tokens (`cache_creation_input_tokens` vs `cache_read_input_tokens`).

---

## Routing Claude Desktop through the proxy

Claude Desktop is Electron, so two things differ from Claude Code:

1. **Env vars must be set at the OS level** before launch — Electron caches env at process start, and shortcuts don't inherit your shell's `set`/`export`.
2. **The mitmproxy CA must be installed in the OS root trust store** — Chromium (used by Electron renderers) ignores `NODE_EXTRA_CA_CERTS` and only trusts certs the OS trusts.

> Heads up: once the mitmproxy CA is in your OS root store, **anything** running as your user trusts mitmproxy-signed certs while it's installed. Remove it (commands below) when you're done if that bothers you.

After both steps, **fully quit Claude Desktop** (check tray / Task Manager / Activity Monitor — Electron tray processes outlive the window) and relaunch. Watch `mitmdump` for incoming requests to confirm.

### Windows

Install the CA into your user's Trusted Root store:

```cmd
certutil -addstore -user "Root" "%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem"
```

Set proxy env vars permanently for your user:

```cmd
setx HTTPS_PROXY http://127.0.0.1:8080
setx NO_PROXY "localhost,127.0.0.1,::1"
```

To uninstall the CA later:

```cmd
certutil -delstore -user "Root" mitmproxy
```

### macOS

Install the CA into your login keychain and mark it trusted for SSL:

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

(Use `~/Library/Keychains/login.keychain-db` and drop `sudo` if you only want it trusted for your user.)

Set proxy env vars so GUI-launched apps inherit them — `~/.zshenv` is read by login shells AND `launchd`-spawned apps when you log in:

```bash
echo 'export HTTPS_PROXY=http://127.0.0.1:8080'   >> ~/.zshenv
echo 'export NO_PROXY="localhost,127.0.0.1,::1"' >> ~/.zshenv
```

Log out and back in (or `launchctl setenv HTTPS_PROXY http://127.0.0.1:8080` for the current login session) before relaunching Claude Desktop.

To uninstall the CA later:

```bash
sudo security delete-certificate -c mitmproxy /Library/Keychains/System.keychain
```

### Linux

Install the CA into the system trust store (commands vary by distro):

**Debian / Ubuntu:**
```bash
sudo cp ~/.mitmproxy/mitmproxy-ca-cert.pem /usr/local/share/ca-certificates/mitmproxy.crt
sudo update-ca-certificates
```

**Fedora / RHEL:**
```bash
sudo cp ~/.mitmproxy/mitmproxy-ca-cert.pem /etc/pki/ca-trust/source/anchors/mitmproxy.pem
sudo update-ca-trust
```

**Arch:**
```bash
sudo trust anchor --store ~/.mitmproxy/mitmproxy-ca-cert.pem
```

Set proxy env vars in `~/.profile` so they're picked up by your desktop session at login:

```bash
echo 'export HTTPS_PROXY=http://127.0.0.1:8080'   >> ~/.profile
echo 'export NO_PROXY="localhost,127.0.0.1,::1"' >> ~/.profile
```

Log out and back in before relaunching Claude Desktop.

To uninstall the CA later, delete the file you copied and re-run the corresponding `update-ca-*` command (or `sudo trust anchor --remove ...` on Arch).

---

## A/B: Claude Code prompt overhead

[ab_prompt.py](ab_prompt.py) runs one prompt through `claude -p` under four configs and compares output + token usage. It uses only supported CLI flags (`--system-prompt`, `--tools ""`, `--strict-mcp-config`), so it works with a subscription login — no request tampering.

| config | what's removed |
|---|---|
| `baseline` | nothing |
| `no_system` | Claude Code system prompt → `"You are a helpful assistant."` |
| `no_tools` | all built-in + MCP tool definitions |
| `stripped` | both |

```powershell
.\.venv\Scripts\python.exe ab_prompt.py "your prompt" --runs 2
```

Use `--runs 2+`: the first run of a config pays the cache write, later runs show steady-state cache reads. Full outputs land in `./ab_results/<timestamp>.json`.

---

## Lean launchers

| launcher | system prompt | tools | ~tokens/request |
|---|---|---|---|
| `claude` | Claude Code default | all built-ins + MCP + Chrome | ~25,000 |
| `claude-mini.cmd` | [mini-system.md](mini-system.md) (~150 tokens) | [mini_tools_mcp.py](mini_tools_mcp.py): read, write, edit, glob, grep, sh + built-in WebSearch/WebFetch | ~2,800 (measured) |
| `claude-stripped.cmd` | one line | none | ~570 |
| `claude-slim.cmd` | Claude Code default | all built-ins, but Read/Edit/Write/Glob/Grep/Bash/PowerShell descriptions shortened in flight by [slim_tools_addon.py](slim_tools_addon.py) | ~19,200 (`-p`, measured) |
| `claude-ultra-slim.cmd` | [slim-system.md](slim-system.md) + cwd/platform line | all built-ins, `SLIM_LEVEL=ultra` docs (core tools terser, plus Agent/ScheduleWakeup/Skill/ToolSearch/ListAgents/ReportFindings/AskUserQuestion/SendFeedback); no Chrome, no claude.ai connectors; skill listing capped at 300 chars per skill | ~9,400 (`-p`, measured) |
| `claude-mini-native.cmd` | [native-system.md](native-system.md) (~150 tokens) | built-in Read/Edit/Write/Glob/Grep/Bash + WebSearch/WebFetch only (`--tools`); no MCP, no proxy, official flags only | ~6,700 (`-p`, measured; re-caches every session) |
| `claude-mini-slim.cmd` | [native-system.md](native-system.md) | same tools as mini-native, descriptions shortened by the slim proxy (via `claude-slim.cmd`); no MCP | ~4,300 (`-p`, measured; cached across sessions) |

`MINI_TOOLS` (set before launching) changes the built-in tool list for both mini-native and mini-slim. Because they use built-in tools, Claude Code's fine-grained permission rules (e.g. `Bash(git *)`) work, unlike `claude-mini.cmd`'s single `sh` tool.

`claude-slim.cmd` keeps every Claude Code feature (subagents, plan mode, permission rules): only tool *descriptions* change; names, parameters and types are passed through exactly, and unknown tools (Agent, Skill, MCP, future built-ins) are untouched. It starts the proxy in a minimized window if nothing is on port 8080. `SLIM_DROP=ScheduleWakeup,ReportFindings` (set before launching) removes whole tools. This modifies Claude Code's requests, which is unsupported: it may break on a Claude Code update.

`claude-ultra-slim.cmd` keeps the same features as slim, with the same unsupported-rewrite caveat, and runs its own proxy on port 8081 (`ULTRA_PORT`) so it never picks up a slim or capture proxy on 8080. The `-p` measurement breaks down as: system ~630, tools ~4,500, reminders ~400, environment + agent/skill listings ~3,850. What it changes: the addon runs with `SLIM_LEVEL=ultra`; `--system-prompt-file slim-system.md` replaces the default prompt (set `ULTRA_KEEP_SYSTEM=1` to keep it); `--no-chrome`; `ENABLE_CLAUDEAI_MCP_SERVERS=false` (claude.ai connectors such as Claude Docs; local MCP servers still load); and `--settings ultra-settings.json` (`skillListingMaxDescChars: 300`, a supported setting with a default of 1536). Truncated skill descriptions can make skills trigger less reliably; raise the cap if that happens. Artifact and MCP tool descriptions are not touched; `SLIM_DROP` still works.

Note: after the first turn, Claude Code sends only new messages plus `cc_prev_req` in the billing header, and the server reuses the earlier request's system prompt, tools and history. Tool definitions are therefore sent once per conversation.

`mini_tools_mcp.py` is a dependency-free stdio MCP server whose tool descriptions are one or two lines; the guidance lives in the results instead (fuzzy "closest match" hints on failed edits, edited-region echo, head+tail truncation, write-before-read guard). It contains an absolute path in [mini-mcp.json](mini-mcp.json), so update that if you move the folder. Edit `MINI_BUILTINS` in the launcher to drop the web tools (~1.35k tokens). Don't run these through the proxy; they rely on Claude Code's own cache placement.

---

## Tests

**Windows:**
```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -v
```

**macOS / Linux:**
```bash
./.venv/bin/python -m pytest tests/ -v
```

The shared behavior contract in [tests/test_optimize_payload.py](tests/test_optimize_payload.py) runs against both `proxy.optimize_payload` and `claude_optimizer_addon.optimize_payload`, plus module-specific tests where they intentionally diverge (`cache_control` handling, pruning default). One case is a strict `xfail` documenting a known bug (a reminder-only final message gets spliced into the preceding assistant turn). Flow tests for the mitmproxy hooks are in [tests/test_addon_flow.py](tests/test_addon_flow.py). Also covered: the mini MCP tools, the capture addon and the slim addon. Current result: 83 passed, 2 xfailed.
