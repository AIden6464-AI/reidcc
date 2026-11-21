<span class="tag">start</span>

# Install

Reidcc runs on Windows 10 and 11. It's in beta.

## What you need

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), installed and signed in once, so `claude` works in a terminal.
- [Codex](https://github.com/openai/codex) is optional. Install it if you want Codex profiles.

## The installer

::: tip
The installer comes with the first release on the [releases page](https://github.com/AIden6464-AI/reidcc/releases). Until it's out, [build from source](./build-from-source).
:::

1. Download `Reidcc_<version>_x64-setup.exe` from the [latest release](https://github.com/AIden6464-AI/reidcc/releases/latest) and run it. It installs for your account only, so it needs no admin rights.
2. It isn't code-signed yet, so SmartScreen may say *Windows protected your PC*. Click *More info*, then *Run anyway*.
3. Open **Reidcc** from the Start menu or the desktop, or type `reid` in a new terminal.

## Where things go

| What | Where |
|---|---|
| The program (replaced on every update) | `%LOCALAPPDATA%\Reidcc` |
| Your profiles, memory, personas and keys (made on first launch) | `%USERPROFILE%\Reidcc` |

The installer also adds the program folder to your user PATH, adds Start menu and desktop shortcuts, and adds the `/reid` slash command to Claude Code if `~\.claude` exists and has none yet. Uninstalling undoes all of it except your own folder.

Next: [your first session](./first-session).
