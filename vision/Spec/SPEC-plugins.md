# SPEC: Reidcc plugins and the `reidcc` marketplace (ACA is the first plugin)

Reid, 2026-11-21: *"Let's make ACA its own repo, make it a plugin, make a spec for plugins and a
marketplace of some standard."*

## The idea in one line
A Reidcc plugin **is a Claude Code plugin**: the format, install, update and uninstall are Claude
Code's own. The `reidcc` marketplace is a small repo of Claude Code marketplace entries. Reidcc
adds one thing: a profile turns plugins on **for its own sessions only**.

---

## Part 0: decisions

| | Decision | Why |
|---|---|---|
| Format | Claude Code's plugin format (`.claude-plugin/plugin.json`, `hooks/`, `.mcp.json`, `skills/`…) | It's the standard that already exists. `claude plugin validate`, `/plugin`, updates and the keychain for secrets come free. We invent nothing. |
| Marketplace | A Claude Code marketplace repo, `AIden6464-AI/reidcc-plugins`, named **`reidcc`** | Install ids read `aca@reidcc`. One `marketplace.json`; each plugin lives in its own repo |
| Where plugins are on | **Off by default** (`defaultEnabled: false`). A Reidcc profile turns them on per session | The goal Part 5d of the repo spec set for ACA: nothing runs in Claude sessions that didn't come through Reidcc |
| ACA | Its own repo, `AIden6464-AI/aca`, history kept (`git subtree split`). The `aca\` folder leaves Reidcc's git | ACA is useful without Reidcc, and Reidcc without ACA |
| Visibility | Both new repos **private** until the 5f fixes (Part 5) land; then public | A memory plugin that pins stale build errors as "rules" shouldn't be offered to anyone yet |
| Codex | Not yet. Codex has its own plugin format; Reidcc's Codex profiles get plugins later | Claude Code first; one format done right |
| License | PolyForm Noncommercial 1.0.0 for `aca`, like Reidcc. The marketplace lists third-party plugins under their own licenses | Same terms as the rest of Reid's work |

---

## Part 1: three repos

```text
AIden6464-AI/reidcc            the app (dev = everything, main = user subset)
AIden6464-AI/aca               the ACA memory plugin: server + hooks + MCP + skills, one repo
AIden6464-AI/reidcc-plugins    the marketplace: .claude-plugin/marketplace.json + README, nothing else
```

`marketplace.json` names each plugin's source repo and pins nothing itself. Each plugin repo pins its
own `version` in `plugin.json` and tags releases with `claude plugin tag` (`aca--v2.1.0`).

### Installing, for a user
```text
/plugin marketplace add AIden6464-AI/reidcc-plugins
/plugin install aca@reidcc
```
Or from a terminal: `claude plugin marketplace add …` / `claude plugin install aca@reidcc`.
Updates come through Claude Code's own `/plugin` update. Uninstall: `claude plugin uninstall aca@reidcc`.

---

## Part 2: the standard (what a plugin needs to be listed in `reidcc`)

Every plugin in the marketplace meets all of these. A PR adding a plugin to `reidcc-plugins` shows them.

1. **Valid:** `claude plugin validate --strict` passes on the plugin, and on the marketplace with it listed.
2. **Off until asked:** `"defaultEnabled": false` in `plugin.json`. Reidcc profiles turn it on (Part 3); a
   Claude Code user can turn it on globally with `/plugin` if they want.
3. **Fails open:** a hook that errors, times out or can't reach its server exits 0 with no output.
   No plugin may block a prompt or a tool call because *it* broke.
4. **Says where it writes:**
   - caches, virtual environments, downloaded tools: `${CLAUDE_PLUGIN_DATA}` (Claude Code deletes it on uninstall)
   - **user data that must survive an uninstall** (memory, notes): a named folder outside the plugin,
     printed in the README and overridable in `userConfig`
   - never `${CLAUDE_PLUGIN_ROOT}` (replaced on every update)
5. **Says where it connects:** `"network": { "hosts": [...] }` lists every host. A local server binds
   `127.0.0.1` only.
6. **Secrets in the keychain:** any key or token is a `userConfig` option with `"sensitive": true`. Never in
   a file in the repo, never in `settings.json`.
7. **Works on Windows:** hooks use exec form (`command` + `args`) or quote `${CLAUDE_PLUGIN_ROOT}`; tested
   from PowerShell and Git Bash. (Reidcc is Windows-first.)
8. **Pinned and tagged:** a `version` in `plugin.json`, a git tag per release, a CHANGELOG line per release.
9. **States its runtime:** "needs Python 3.10+ on PATH", "needs Node 22", or "nothing" in the README's first lines.
10. **Licensed:** a LICENSE file. Reidcc's own plugins: PolyForm NC.

---

## Part 3: Reidcc's side

### 3a. Profiles turn plugins on, per session
```json
"main":  { "model": "opus", "memory": true, "plugins": ["aca@reidcc"] },
"lean":  { "tools": ["Read","Edit","Bash"] }
```
At launch, reid already writes a per-session `--settings` file (for the statusline). A profile's
`plugins` go into it:
```json
{ "enabledPlugins": { "aca@reidcc": true } }
```
So `aca` runs in `main`'s sessions and nowhere else, without touching `~\.claude\settings.json`.
A plugin that isn't installed is skipped, and the launcher's status line says `aca not installed`.
**To verify first (step 3):** that `enabledPlugins` in a `--settings` file turns on an installed plugin
whose `defaultEnabled` is false, for that session only. If it doesn't, the fallback is `--plugin-dir` on
the installed copy's folder (`claude plugin list --json` gives the path).

### 3b. The launcher
- The profile editor gets a **plugins** row: the installed plugins (from `claude plugin list --json`) as
  checkboxes. Codex profiles show it greyed out, like the other Claude-only fields.
- `reid -l` and `reid --dry` show a profile's plugins.
- The Codex engine ignores `plugins` (Part 0).

### 3c. The installer
`reid --install` adds the marketplace if Claude Code is found and it isn't added yet
(`claude plugin marketplace add AIden6464-AI/reidcc-plugins`). It installs no plugin.
`reid --uninstall` leaves the marketplace and plugins alone: they belong to Claude Code.

---

## Part 4: ACA as a plugin (replaces Parts 5c–5e of SPEC-github-repo.md)

### 4a. Layout (`AIden6464-AI/aca`)
```text
aca\
├─ .claude-plugin\plugin.json   name "aca", defaultEnabled false, userConfig (port, data_dir), network
├─ hooks\hooks.json             SessionStart → scripts\ensure.py (starts the server; never waits)
│                               UserPromptSubmit, PostToolUse(Bash), PostToolUseFailure(Bash) → aca_hook.py
├─ .mcp.json                    aca → scripts\mcp.py (aca_remember / aca_recall / aca_forget / aca_status)
├─ scripts\ensure.py            venv + key + server, all idempotent
├─ scripts\mcp.py               runs aca_mcp.py with the venv's Python
├─ integrations\claude_code\    aca_hook.py, aca_client.py (stdlib only), aca_mcp.py
├─ src\                         the server (unchanged)
├─ run.py, start.bat            standalone start, as today
├─ tests\, docs\, README.md, LICENSE.md, pyproject.toml
```

### 4b. What runs where
| Piece | Runs with | Needs |
|---|---|---|
| hooks (`aca_hook.py`, `aca_client.py`) | the Python on PATH | stdlib only, so the first prompt works before any setup |
| server (`run.py`) and MCP (`aca_mcp.py`) | `${CLAUDE_PLUGIN_DATA}\venv` | fastapi, uvicorn, pydantic, httpx, mcp (`pip install .[mcp]`) |

**Requirement:** Python 3.10+ on PATH. The README says so first.

### 4c. A session's start (`scripts\ensure.py`, from SessionStart)
1. `GET 127.0.0.1:<port>/health` answers as ACA: done (the usual case, ~20 ms).
2. Port answers but isn't ACA: print one line (`port 8420 is taken by something else; set aca's port`) and stop.
3. No venv in `${CLAUDE_PLUGIN_DATA}\venv` (or its `pyproject.toml` hash changed after an update): create it
   and `pip install` **in a detached background process**, and return at once. That session runs without
   recall; the next one has it. (First install: ~30–60 s in the background.)
4. No key at `~\.aca\claude_code.key`: create a `write` key with `python -m src.api.auth create` against the
   data folder, and write it there (the hook and MCP server already read that path).
5. Start `run.py --no-exit-with-parent` detached and hidden, with `ACA_DATA_DIR` set. It outlives sessions,
   so every session shares one server.

### 4d. Settings (`userConfig`)
| Key | Default | Used as |
|---|---|---|
| `port` | 8420 | `ACA_URL=http://127.0.0.1:<port>` for hooks (`CLAUDE_PLUGIN_OPTION_PORT`) and MCP (`${user_config.port}`) |
| `data_dir` | empty → `~\.aca\data` | `ACA_DATA_DIR`. Outside the plugin on purpose: uninstalling never deletes your memory |

### 4e. Reid's move from the global wiring
1. Install: `claude plugin marketplace add AIden6464-AI/reidcc-plugins`, `claude plugin install aca@reidcc`.
2. Set `data_dir` to `E:\Reidcc\aca\data`. Keep `~\.aca\claude_code.key`. Nothing is migrated.
3. Remove the three ACA hooks from `~\.claude\settings.json` and the `aca` server from `~\.claude.json`.
   Otherwise every prompt is ingested twice.
4. Add `"plugins": ["aca@reidcc"]` to the profiles that should remember (after Part 3 is built). Until
   then, `/plugin` → enable `aca` globally, which is today's behaviour.

---

## Part 5: before either repo goes public
The three bugs in SPEC-github-repo.md 5f, fixed in the `aca` server, each with a regression test:
1. **Outcomes never become pinned rules.** Only a user's own stated rule is pinned.
2. **Pinned items are scoped to the project** (`scope_for(cwd)`), not recalled in every folder.
3. **Outcome memories decay; rules expire or ask for a confirm.**

Seen live: every prompt in the session that wrote this spec carried ~3 KB of stale `cargo` errors as
"Pinned rules".

---

## Part 6: build order
| # | Work | Size |
|---|---|---|
| 1 | `aca` repo: subtree split, plugin layout, `ensure.py`, `mcp.py`, validate, test against a scratch port and data dir. `reidcc-plugins` repo with `marketplace.json`, validated. Both private on GitHub. `aca\` untracked in Reidcc (files stay on disk: Reid's live setup runs from there) | medium |
| 2 | 5f fixes in the `aca` server, with tests | medium |
| 3 | Reidcc: `plugins` profile field → `enabledPlugins` in the per-session settings (verify 3a), `reid -l`/`--dry`, the launcher row; `reid --install` adds the marketplace | medium |
| 4 | Reid moves over (4e). Both repos public; the Reidcc README and the site link the marketplace | small |

## Open questions
1. Third-party plugins in `reidcc`: open to PRs that meet Part 2, or Reid's own plugins only?
2. Submit `aca` to Anthropic's directory too once it's public?
3. A Rust port of the hook (Part 5d's `reid.exe --aca-hook`) to drop the Python requirement for recall? It
   would only work inside Reidcc, so the plugin keeps the Python hook either way.

## As built (2026-11-21): step 1
- `E:\aca` (repo `AIden6464-AI/aca`, v2.1.0): `.claude-plugin/plugin.json`, `hooks/hooks.json` (exec form; SessionStart
  runs `scripts/ensure.py` async), `.mcp.json` → `scripts/mcp.py`, `scripts/requirements.txt`, LICENSE, CHANGELOG.
  `aca_client.py` follows `CLAUDE_PLUGIN_OPTION_PORT`. README paths made relative (no personal paths).
- `E:\reidcc-plugins` (repo `AIden6464-AI/reidcc-plugins`): `marketplace.json` (name `reidcc`), README with the Part 2 standard.
- `claude plugin validate --strict` passes on both (only warning: no icon, optional).
- Tested against scratch dirs and port 8431: first run builds the venv (~45 s), creates the key, starts the
  server; a second run is a no-op (0.25 s); a port held by a non-ACA service is logged and left alone; the
  hook pins a rule and recalls it; the MCP server lists all 5 tools and `aca_status` answers.
- Found while testing: `mcp` 2.x renamed FastMCP, so requirements pin `mcp<2`.
- Not done: loading it through `/plugin install` in a real session (it would hit the live 8420 server); that's step 4.
