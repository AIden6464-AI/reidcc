<span class="tag">the launcher</span>

# Engines

A profile runs one of three engines: **Claude Code**, **Codex** or **OpenCode**. Choose it on the profile's `name` row. A profile without an `engine` field runs Claude Code.

## Claude Code

- **Sign-in:** `subscription` uses your Claude login. A settings file (`json\*.json`, in Claude Code's settings format) switches to API mode; the key stays in that file.
- **Persona and memory:** add to or replace Claude Code's prompt, and add your memory.
- **Status line:** every session shows `folder · PROFILE · persona   context 42% · limit 61%`. `limit` appears on a subscription after the first reply. Turn it off with `"statusline": false`.
- **Return and resume:** `/reid` returns to Reidcc with the conversation kept; **resume** picks it up again with any profile.

## Codex

- **Sign-in:** your terminal's `codex login` (shown as `ChatGPT`, `API key` or `not signed in`), or a `codex\*.toml` provider file for LM Studio, OpenRouter or another API.
- **Persona and memory:** the same persona files and memory, written per launch to `codex\prompts\<profile>.md`. Nothing is written to `~/.codex`.
- **Session:** the Codex status line shows `model · folder · context · 5h · weekly`, and `/quit` returns to Reidcc, as `/reid` does for Claude Code. See [CLI](./cli#inside-codex).
- **Resume:** works like Claude Code. Reidcc finds the Codex thread while the session runs, and **resume** reopens it. A chat's **open terminal** hands its Codex thread to a terminal; `/quit` there and the chat continues the same thread.
- **Usage:** chat shows Codex's real token counts, the thread's total so far (`19.9k in · 5 out`, cached in the side panel). Codex reports no context window or cost, so those stay hidden.
- **Proxy:** `capture`, `slim` and `ultra` work on Codex too (from source only; `optimize` is Claude Code only). See [proxy](./proxy).

## OpenCode

- **Sign-in:** OpenCode's own setup (its providers and keys), shown as `opencode setup`, or an `opencode\*.json` config file laid over it.
- **Model and effort:** `provider/model` from `opencode models`. Effort is the model's variant (`high`, `max`), set in **tune**.
- **Persona and memory:** written per launch to `opencode\prompts\<profile>.md`, added to OpenCode's prompt or replacing it. Your `~/.config/opencode` isn't touched.
- **Session:** OpenCode's own screen in a session window. Quitting it returns to Reidcc.
- **Resume:** Reidcc picks each session's id, so **resume** reopens it.
- **Chat:** turns edit files but have no shell; read-only turns only read and search. Tokens and cost show as OpenCode reports them.
- **Not on OpenCode:** the proxy, the tools and MCP rows, and Claude's switches (greyed out).

## All three

- **tune**, beside the model: effort for every engine; single MCP servers and plugins off or on for Claude Code and Codex. See [chat](./chat#tune).
- **open chat** talks to any engine from one composer, and switches between them mid-task with the whole conversation. See [chat](./chat).
