# Changelog

Every Reidcc release. Newest first. Everything is beta.

## 0.2.6 beta · unreleased: OpenCode, and switching that carries the conversation

### OpenCode
- **OpenCode** is the third engine, beside Claude Code and Codex. Pick it on a profile's `name` row.
- It runs in session windows, in chat and in `reid --stream`, with resume, persona and memory.
- Model from `opencode models`; effort is the model's variant, set in **tune**.
- Sign-in is OpenCode's own setup, or an `opencode\*.json` file laid over it. Your `~/.config/opencode` isn't touched.
- Chat turns edit files without a shell; read-only turns only read and search.
- No proxy, tools or MCP rows on OpenCode yet.

### Switch
- Switching engines in a chat carries the whole conversation. The next engine gets it as a session of its
  own and answers from everything said so far, by any engine.
- Long chats keep the first turn and the newest that fit in 60% of the next engine's window.
- If an engine won't take the session, the conversation goes along as text, and the chat says so.
- Each chat's transcript is kept in Reidcc's `chats\` folder.

## 0.2.5 beta · 2026-11-27: one chat over Claude Code and Codex

### Chat
- **open chat**, beside resume: one composer over Claude Code and Codex, in the launcher's folder and
  profile. Each turn streams its text and tool lines; `stop` ends the turn.
- After a turn that edits files, a **changed** block lists them. Each file opens to its diff.
- Pick another profile and `send` becomes `switch → <engine>`. Reidcc writes `.reid/handoff.md`
  (changed files, diff stat) and passes it to the next engine.
- Turns read `edits` or `read-only`. The composer says what the next turn may do before you send:
  `edits · no shell` for Claude, `edits · shell` for Codex.
- 3 or more tool lines in a row fold into one: `ran N commands ›`, or `N tool calls ›` when they aren't all shell.
- Context and cost show only when the engine reports them. Codex reports neither, so they stay hidden;
  its real token counts show instead (the thread's total so far: `19.9k in · 5 out`, cached in the side panel).
- **open terminal** resumes the chat's session in a session window.
- In the terminal: `c` in the TUI, or `reid --chat [profile]`. `tab` picks the profile, `ctrl+r` read-only,
  `ctrl+t` open terminal, `ctrl+d` the diff, `ctrl+e` tune.

### Tune
- **tune**, beside the model: a profile's effort, and single MCP servers and plugins on or off.
  Saved in `reid.json` as `effort`, `mcp_off` and `plugins`.
- In a chat, **tune** changes model, effort, servers and plugins for that chat only. `reid.json` stays as it is.
  Or type it: `/model sonnet`, `/effort high`, `/effort default`.
- On a Codex profile the launcher's mcp row reads **set in tune ›**: Codex's servers, plugins and effort are set
  there. tools, chrome, connectors and safe mode stay greyed out (Claude only).

### One window
- Click **RC** on a session window's bar and the launcher opens beside the terminal. Again: full. Again: closed.
  `Alt+2` beside, `Alt+1` full. The terminal keeps its size.
- `/reid`, Codex's `/quit` and a session that ends turn the window you're in into Reidcc. Nothing jumps
  forward from behind. `/reid` and Codex's `/quit` turn it at once.
- The launcher docks into snapped frames too.

### Launcher
- Sizes are named **main** (`Alt+1`), **medium** (drag it narrow), **small** (`Alt+2`) and the **pod**
  (`Alt+3`, or drag it small). Keys `1`–`9` on small start that profile.
- **Rigs (beta):** save a snapped frame by name and open it again from the launcher.
- Settings: **terminal colours** (Reidcc's palette, or the engine's own) and a **change** button for each location.
- The launcher, session windows and settings share one set of colours. `--text3` is `#7F7A73`, 4.5:1 contrast.

### Engines
- Codex resumes both ways, like Claude Code. Each window finds its own Codex thread.
- Codex's `/quit` is its way back, like `/reid`: the thread is recorded, `resume` reopens it, and
  `reid <codex profile>` lands in the TUI with `Back from Codex. r resumes it.` A thread made just before
  a quick exit (Ctrl+C twice right after sending) is still found.
- Codex profiles take the proxy: `capture`, `slim` and `ultra` (`optimize` stays Claude-only). Measured on
  codex-cli 0.172.0: `slim` −12.0% and `ultra` −13.1% input tokens, but a fresh slimmed thread gets no
  server cache (numbers on the docs' proxy page).
- `reid --stream <profile> PROMPT`: one headless turn as JSON lines. `reid --resume <profile> --id ID`
  continues one session in this folder.

### Fixes
- A chat's write turn no longer freezes Reidcc while git takes its before and after snapshots. New files over
  2 MB stay out of them, so logs and build output don't pile up in `.git/objects`.
- Read-only Claude turns can't use MCP tools either, even ones the settings allow.
- A profile in `reid.json` that isn't an object gets an error that names it. Before, the TUI crashed.
- A failed save of `reid.json` (the file held open by OneDrive or an antivirus scan) shows an error. Before,
  the window kept the change and the file didn't, with no message. The leftover `reid.json.<pid>.tmp` is removed.
- The window's asset handler serves only files inside `assets\`, to Reidcc's own pages.
- Switches kept when going from medium to main.
- `reid -h`, `reid -l` and the install and MCP docs, from the user trial (13 fixes).
