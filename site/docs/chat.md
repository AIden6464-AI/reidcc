<span class="tag">the launcher</span>

# Chat

**open chat**, beside resume, opens a chat window on the launcher's folder and profile: one composer over
Claude Code and Codex. Each turn runs the real engine headless (`reid --stream`) and streams its text and
tool lines as they come.

## A turn

- **send** runs the turn; **stop** ends it.
- Turns read `edits` or `read-only`. Before you send, the composer says what the next turn may do:
  `edits · no shell` for Claude Code, `edits · shell` for Codex. Read-only uses each engine's own flags.
- 3 or more tool lines in a row fold into one: `ran N commands ›`.
- Context and cost show only when the engine reports them: Claude Code reports both. Codex reports token counts instead: the thread's total so far, `19.9k in · 5 out` after each turn and in · cached · out in the side panel; its context and cost stay hidden, never 0.
- After a turn that edits files, a **changed** block lists them (from git). Each file opens to its diff.

## Switch engines

Pick another profile and **send** becomes `switch → <engine>`. Reidcc writes `.reid/handoff.md` in the
folder (changed files, diff stat) and passes it to the next engine, so it picks up where the last one stopped.

## Open terminal

**open terminal** continues the chat's session in a session window, with the full engine.

## One at a time

A session window and a chat can share a folder. A turn that may edit files needs the folder to itself:
when something else holds it, the composer says so and offers `focus window` or `send read-only`.

## Tune

**tune** sets effort, and turns single MCP servers and plugins off or on.

- **Beside the model in the launcher:** for the profile. Saved in `reid.json` as `effort`, `mcp_off` and `plugins`.
- **In a chat:** for that chat's turns only. `reid.json` stays as it is. The model can change here too.

## In a terminal

`c` in the TUI, or `reid --chat [profile]`, opens the same chat in text.

| Key | Does |
|---|---|
| `tab` | pick the profile |
| `ctrl+r` | read-only |
| `ctrl+t` | open terminal |
| `ctrl+d` | the diff |
| `ctrl+e` | tune |
