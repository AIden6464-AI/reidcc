<span class="tag">the launcher</span>

# Personas

A persona is who the session is: a plain Markdown file in `personas\`. It's optional.

## Attaching one

Pick a file in the profile's **persona** field. Then choose how it's used (for a Codex profile the labels say Codex):

| Mode | What happens |
|---|---|
| **add to Claude Code's prompt** | The persona is added after the engine's own system prompt. The default |
| **replace Claude Code's prompt** | The persona replaces the engine's prompt. Reidcc adds the working folder and platform back, since the engine's prompt carried them. For Codex, add is the safe one |

In `reid.json` this is `"persona": "personas/plain.md"` and, for replace, `"mode": "replace"`.

## Writing one

A persona is ordinary Markdown. Keep it short: it's sent with every request.

```md
You are a careful senior engineer. Read the code before you change it.
Say what you skipped. Keep answers short.
```
