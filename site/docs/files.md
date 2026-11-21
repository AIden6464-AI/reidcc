<span class="tag">reference</span>

# Folders and files

Everything that's yours lives in one folder, `%USERPROFILE%\Reidcc` for an installed copy.

```text
Reidcc\
├─ reid.json          your profiles and settings
├─ reid_state.json    the last session and recent folders (written by Reidcc)
├─ reidcc_memory.md   your memory
├─ personas\          persona files
├─ json\              Claude Code settings files for API mode (they hold API keys)
└─ codex\             Codex sign-in files (*.toml) and prompts\ (persona + memory per launch)
```

::: warning
`json\` and `codex\` can hold API keys. Don't share or commit them.
:::

## Which folder Reidcc uses

In order:

1. The folder in the `REIDCC_HOME` environment variable.
2. The first folder above the program that holds a `reid.json`.
3. `%USERPROFILE%\Reidcc`.

**settings → locations** shows the folder in use, with **open**.

## Temp files

Each session's prompt and merged settings are written as temp files (`reid_prompt_*`, `reid_settings_*`) in your temp folder, and removed when the session ends.
