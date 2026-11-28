<p align="center">
  <img src="docs/emblem.png" alt="Reidcc" width="320" />
</p>

<h1 align="center">Reidcc</h1>

<p align="center">
  <strong>Folder. Profile. Gate.</strong><br />
  Only the essentials, all in sight.
</p>

---

Reidcc is a launcher for Claude Code and Codex, for people who want things simple. Pick a folder and
a profile and you're coding in seconds, with your persona, long-term memory and settings already set
up. Every session shows where it is, which profile is running, and how much context and limit you've used.

**Status:** Windows 10 and 11 · **beta** (everything is) ·
[download the latest release](https://github.com/AIden6464-AI/reidcc/releases/latest) ·
[website and docs](https://aiden6464-ai.github.io/reidcc/)

<p align="center">
  <img src="docs/launcher.png" alt="Reidcc launcher" width="900" />
</p>

---

## Install

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and sign in once (`claude` on
   your PATH). Codex is optional.
2. Download `Reidcc_<version>_x64-setup.exe` from the
   [latest release](https://github.com/AIden6464-AI/reidcc/releases/latest) and run it. No admin needed.
   It isn't code-signed yet, so SmartScreen may say *Windows protected your PC*: *More info* → *Run anyway*.
3. Open **Reidcc** from the Start Menu or desktop, or type `reid` in a new terminal.

| | Where |
|---|---|
| The program (replaced on every update) | `%LOCALAPPDATA%\Reidcc` |
| Your profiles, memory, personas, keys (made on first launch) | `%USERPROFILE%\Reidcc` |

- **Updates:** when a newer release is out, the footer shows `update <version> · install`. Click it
  once your sessions have finished. In a terminal: `reid --update`. Nothing installs unless you ask.
- **Offline:** Reidcc itself needs no internet. It goes online only to download the installer and for
  updates (a check at start and every 6 hours; offline, it just skips it). Your profiles, memory and
  personas stay on your PC. The sessions it opens (Claude Code, Codex) still need their own connection.
- **Uninstall:** Settings → Apps → Reidcc. Your folder is kept.
- **Also set up for you:** `reid` on your PATH, and the `/reid` command inside Claude Code (back to
  Reidcc with your conversation kept).

---

## Using it

<p align="center">
  <img src="docs/flow.png" alt="folder → profile → open gate" width="760" />
</p>

Pick a folder, pick a profile, **open gate**. The profile list and every field of the selected profile
stay on one screen, and changes save as you make them.

- **Window:** `Enter` on the list opens the gate · `Ctrl+Enter` from anywhere · `Ctrl+O` picks a folder ·
  `Ctrl+R` resumes · `Alt+1` main · `Alt+2` small · `Alt+3` the pod. Drag the window narrow for medium.
- **Terminal (TUI):** `↵ open gate · r resume · c chat · e edit · n new · x delete · d default · w pick folder · m memory · q quit`
- **Inside a session:** click **RC** on the bar and Reidcc opens beside the terminal; again for full, again
  to close (`Alt+2` beside, `Alt+1` full). `/reid` turns the window into Reidcc with the conversation kept
  (`r` resumes it with any profile) · `/exit` leaves as usual.
- **Inside a Codex session:** Codex has no `/reid`, so `/quit` (or any clean exit) is the way back. The
  window turns into Reidcc at once, with the Codex thread recorded: **resume** (`r` in the TUI) reopens
  that exact thread. A chat's **open terminal** works the same way: `/quit` and the chat carries on.

### Chat

**open chat**, beside resume, is one composer over Claude Code, Codex and OpenCode in the launcher's folder.
Each turn streams its text and tool lines, and `stop` ends it. After a turn that edits files, a
**changed** block opens to each file's diff. Pick another profile and `send` becomes `switch → <engine>`:
the next engine carries the whole conversation into a session of its own and answers from everything
said so far, with tool calls and the end of their output. **open terminal** continues the same session in a
session window. In a terminal: `reid --chat [profile]`.

**tune**, beside the model, sets a profile's effort and turns single MCP servers and plugins off or on.
In a chat, tune changes them for that chat only.

```text
reid                      the TUI in a terminal, the window when started as an app
reid <profile> [args]     start that profile in the current folder
reid --resume [profile]   resume the last session (Claude Code, Codex or OpenCode)
reid --resume <profile> --id ID   resume that session, in this folder
reid --chat [profile]     chat with Claude Code, Codex or OpenCode, in the terminal
reid --dry <profile>      show the exact command without running it
reid -l                   list profiles
reid --edit / --mem       open reid.json / your memory file
reid --version            show the version
reid --update             install the latest release
reid -h                   full help
```

See [CHANGELOG.md](CHANGELOG.md) for what each release changed.

### Profiles

A profile picks its engine (`claude`, `codex` or `opencode`), model, sign-in, persona and switches. They live in
`%USERPROFILE%\Reidcc\reid.json`; the window edits them, or open it with `reid --edit`.

- **Sign-in:** your Claude subscription, or a settings file in `json\` for an API key (the key stays in
  that file). Codex uses your `codex login`, or a provider `.toml` in `codex\` (LM Studio, OpenRouter...).
  OpenCode uses its own providers, or an `opencode\*.json` config file.
- **Persona:** any Markdown file in `personas\`, added to the engine's prompt or replacing it.
- **Memory:** `reidcc_memory.md`, given to sessions that have memory on.
- **Statusline:** `~/folder · PROFILE · PERSONA   context 42% · limit 61%` in every Claude session.

---

## Build from source

You need [Rust](https://rustup.rs) (stable) and [Node.js](https://nodejs.org) 22.

```powershell
git clone https://github.com/AIden6464-AI/reidcc
cd reidcc\rs\ui; npm ci; npm run build        # the window's UI
cd ..; cargo build --release                  # reid.exe (terminal) + Reidcc.exe (window)
```

Run `rs\target\release\Reidcc.exe` or `reid.exe`. They use the same `%USERPROFILE%\Reidcc` folder
as an installed copy (set `REIDCC_HOME` to use another). Tests: `cargo test --workspace` in `rs\`.

This branch has what you need to use and build Reidcc. Specs, design docs, the Python original and
the dev tools are on the [`dev`](https://github.com/AIden6464-AI/reidcc/tree/dev) branch, which is
also where pull requests go.

---

## License

Reidcc is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md).

- **Free for people:** use it, change it, fork it and share your changes, for personal use, hobby
  projects, study, research, and noncommercial organizations (charities, schools, public bodies).
- **Credit:** every copy and fork keeps the `Required Notice:` line from [LICENSE.md](LICENSE.md).
- **Companies and paid work** (including client work) need a commercial license. Open an issue
  titled `commercial license` to talk terms.
- **Name and art:** the Reidcc name, the RC logo and the art in `docs/` and `assets/` are not under
  the license. Copies of Reidcc may include them unchanged; a fork under another name uses its own.
- **Contributing:** by sending a pull request, you agree that your contribution is licensed under
  these terms, and that Reid may also include it in Reidcc's commercial licenses.
