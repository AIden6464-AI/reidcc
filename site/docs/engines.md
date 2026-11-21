<span class="tag">the launcher</span>

# Engines

A profile runs one of two engines: **Claude Code** or **Codex**. Choose it on the profile's `name` row. A profile without an `engine` field runs Claude Code.

## Claude Code

- **Sign-in:** `subscription` uses your Claude login. A settings file (`json\*.json`, in Claude Code's settings format) switches to API mode; the key stays in that file.
- **Persona and memory:** add to or replace Claude Code's prompt, and add your memory.
- **Status line:** every session shows `folder · PROFILE · persona   context 42% · limit 61%`. `limit` appears on a subscription after the first reply. Turn it off with `"statusline": false`.
- **Return and resume:** `/reid` returns to Reidcc with the conversation kept; **resume** picks it up again with any profile.

## Codex

- **Sign-in:** your terminal's `codex login` (shown as `ChatGPT`, `API key` or `not signed in`), or a `codex\*.toml` provider file for LM Studio, OpenRouter or another API.
- **Persona and memory:** the same persona files and memory, written per launch to `codex\prompts\<profile>.md`. Nothing is written to `~/.codex`.
- **Session:** the Codex status line shows `model · folder · context · 5h · weekly`, and `/quit` returns to Reidcc.

::: tip
**resume** is Claude Code only for now.
:::
