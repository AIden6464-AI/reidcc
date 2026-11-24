# Spec: sign-in, persona and memory for Codex profiles

Status: **BUILT 2026-11-19.** Follows milestone 1 in `vision\Spec\SPEC-codex-opencode.md`. Differences from
the text below are listed in "As built" at the end.

> "can we spec [the profile form: engine codex, sign-in / persona / persona mode greyed out] for codex
> the signin and persona's" (Reid, 2026-11-19)

> "1. In the Reidcc application folder 2.just like the Claude side 3.um like Claude engine with the idea"
> (Reid, 2026-11-19, answering the three open questions: where the generated files live, how memory
> gets written, separate accounts)

## Why

Today a Codex profile greys out `sign-in`, `persona`, `persona mode` and `memory`. That breaks the
product's main promise ("Your persona, memory and settings are already there") for half the engines.
Reid's own `claude` profile is already set to `engine: codex` with memory on, so it is blocked from
launching until this is built.

Goal: these four fields work on a Codex profile the same way they work on a Claude profile. Same
files, same picker, same feel. Codex reads the persona and memory fresh every launch. Everything
Reidcc generates stays in the Reidcc folder.

## What Codex 0.170.0 can do (verified 2026-11-19)

Every claim here was checked with `codex debug prompt-input`, which prints what the model would see
and makes no model call. Probe scripts: `cx_probe.py`, `cx_probe2.py` and `cx_probe3.py` (scratchpad).

| Mechanism | Result |
|---|---|
| `-c model_instructions_file="<path>"` | **Replaces** Codex's own prompt (the "You are Codex…" message) with the file. Any path works. The six other parts of the prompt (tools, skills, agent mode, `<environment_context>` with folder and shell, the user turn) are unchanged. |
| `-c developer_instructions="…"` | **Adds** a message after Codex's own prompt. But it's inline text on the command line, and Windows caps that at 32,767 characters. |
| `codex debug prompt-input` | Prints Codex's own prompt for the given `-m` / `-c` settings in about 1.1 s. Codex's prompt is 27.7k characters for Reid's setup. |
| prompt captured + persona → `model_instructions_file` | Gives **exactly** Codex's prompt followed by the persona, with nothing else changed. The file must be written with `\n` line endings (`newline=""`): Python's default `\r\n` changes the text. |
| `-p <name>` | Only reads `~/.codex\<name>.config.toml`. Paths are refused ("pass a plain name such as `work`"), so it can't serve files from the Reidcc folder. **Not used.** |
| custom provider | `model_provider` + `[model_providers.<id>]` (`name`, `base_url`, `wire_api`, `env_key`) is accepted as `-c` keys. |
| login | `codex login status` → `Logged in using ChatGPT`. `OPENAI_API_KEY` / `CODEX_API_KEY` are read from the environment. |

Real sizes: Nyxie is 21k characters, the memory block 6k and `sheher.md` 25k. Personas don't fit on
the command line, so they go in a file.

## The design: one prompt file per profile, in the Reidcc folder

Persona and memory are both carried by `model_instructions_file`, pointing at:

```
E:\reidcc\codex\prompts\<profile>.md
```

The folder is next to `json\` and `mds\`, not inside `app\`, because `build.ps1` replaces `app\` on
every install.
- It's rewritten at every launch, so edits to the persona or memory land in the next session, the
  same as with Claude.
- It's kept after the session rather than deleted, in case Codex reads it again later in a session.
- `<profile>` is lowercased and reduced to `a-z 0-9 -`. If two profiles reduce to the same name, a
  short hash is added.
- Nothing is written when the profile has no persona and no memory. A plain Codex profile stays
  byte-for-byte what milestone 1 launches today.
- Nothing is written to `~/.codex`.

| Mode | Codex label | What goes in the file |
|---|---|---|
| append | add to Codex's prompt | **Codex's own prompt** (captured, see below) + persona + memory |
| replace | replace Codex's prompt | persona + memory only |

Replace mode drops Codex's own prompt, which includes how it uses its tools. The help line says so:
`replace drops Codex's own instructions; add is the safe one.` Codex still sends the folder and
shell itself, so Reidcc doesn't append them the way Claude's replace mode does.

### Capturing Codex's own prompt (add mode)

1. Run `codex.exe [-m model] [provider -c keys] debug prompt-input` in the picked folder.
2. Take the first `developer` message whose text starts with `You are Codex`.
3. **Cache** it as `codex\prompts\.base-<key>.md`. The key is a hash of the codex.exe size and
   mtime, the model, the provider keys, and the mtime of `~/.codex\config.toml`. An unchanged setup
   then costs nothing; after a Codex update or config change, the first launch pays about 1.1 s.
   While that runs, the gate is already playing.
4. If capture fails (Codex changed its output, it timed out after 10 s, or no message matched), fall
   back to `-c developer_instructions` when persona + memory is under 24k characters. Otherwise
   refuse before launch:
   `Couldn't read Codex's own prompt to add the persona to. Use replace mode, or update Reidcc.`

### Sign-in: like the Claude side

One login for every profile, plus API provider files for anything else. This mirrors Claude's
`subscription` + `json\*.json` settings files.

| Option in the picker | What it does |
|---|---|
| `codex login` (default) | Uses whatever `codex login` set up (Reid's is ChatGPT). Reidcc removes `OPENAI_API_KEY` and `CODEX_API_KEY` from the session's environment, so a stray key can't quietly switch billing. This mirrors how `subscription` strips `ANTHROPIC_*`. |
| `codex\<name>.toml` | A provider file. Its top-level keys become `-c` keys (`model_provider`, `model`, `model_providers.<id>.base_url`, …). Its `[env]` table goes into the session's **environment only**, never onto the command line or into the preview. That's where API keys live, the same way Claude's settings files carry `env`. |
| `browse…` | Pick a `.toml` from anywhere. Stored relative, like the Claude files. |

Example `codex\lmstudio.toml`, Reid's local stack:

```toml
model_provider = "lmstudio"
model = "qwen3-coder"
[model_providers.lmstudio]
name = "LM Studio"
base_url = "http://localhost:1234/v1"
wire_api = "responses"
```

Example `codex\openrouter.toml`:

```toml
model_provider = "openrouter"
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
env_key = "OPENROUTER_API_KEY"
[env]
OPENROUTER_API_KEY = "sk-or-…"
```

- The field stays `settings` in reid.json. `.json` means a Claude settings file and `.toml` means a
  Codex provider file. The wrong kind for the engine is an error before launch:
  `json\qwen.json is a Claude sign-in file. Pick a Codex one, or use codex login.`
- The picker lists only the files for the profile's engine.
- Switching engine resets sign-in to that engine's default (`subscription` / `codex login`), just as
  it resets the model.
- The provider file's `model` is used unless the profile sets its own model.
- Not valid TOML → `codex\x.toml isn't valid TOML (line 4). Fix it, then try again.`

#### The row shows Codex's login status

> "show me the "codex sign-in tho because i am signed in my terminal in codex cli?" → "sure" (Reid, 2026-11-19)

`codex login` uses the same `codex.exe` and the same `~/.codex\auth.json` as Reid's terminal, so a
terminal login is all the setup there is. To make that visible, the default option shows what Codex
reports:

```
sign-in   [ codex login · ChatGPT ▾ ]      (codex login · API key / codex login · not signed in)
```

- **How:** run `codex.exe login status` with the same environment the launch uses. Verified: through
  `find_codex()` it prints `Logged in using ChatGPT`, the same as the terminal. Mapping:
  - contains `ChatGPT` → `ChatGPT`
  - contains `API key` → `API key` (the key itself is never shown)
  - non-zero exit or `Not logged in` → `not signed in`, in oxide
  - anything else → `signed in`
- **When:** it takes about 1.1 s, so it runs off the UI thread when a Codex profile is selected, and
  the answer is kept for the GUI or TUI session.
  - While it runs, the row reads `codex login · checking…`.
  - It runs again when `open gate` is pressed, but only if the last answer was `not signed in`, so
    signing in from a terminal is noticed without restarting Reidcc.
  - It doesn't run for a provider-file sign-in.
- **Not signed in** blocks like any other `not ready`:
  `Codex isn't signed in. Run codex login in a terminal, then try again.`
- **TUI:** the same text in the `sign-in` row on the main screen and in the editor.

### Memory: like the Claude side

- It's the same memory file and the same `memory_block()` text (trimmed to `memory_limit`), after
  the persona.
- Reidcc gives Codex no extra folder access, the same as the Claude side, which adds no `--add-dir`
  either. When Codex appends to the memory file outside the project, it follows Reid's own Codex
  approval setting (`on-request` today means it asks).
- `m open memory` and `open memory` work the same as for Claude.

### What stays Claude-only

These stay greyed out for Codex, and the tag becomes
`CODEX · GREYED FIELDS ARE CLAUDE'S`:
- proxy, tools, mcp
- chrome, connectors, safe mode
- settings_json
- `/reid` and resume

### Guards (refused in extra args before launch)

- When a persona or memory is on, `-c model_instructions_file=…` / `-c developer_instructions=…`.
  Otherwise they would silently replace the persona:
  `Leave model_instructions_file out of the extra args: it would replace the persona.`
- When a sign-in file is set, `-c model_provider=…`.
- `-p` is allowed. Reidcc doesn't use it, so Reid's own Codex config profiles still work.

## Screens

**GUI** (Reid's screenshot, after this is built):
- `sign-in` is live: `codex login` ▾, or the file name.
- `persona` is live with `browse` and `open persona`.
- `persona mode` is live: `◉ add to Codex's prompt  ○ replace Codex's prompt`.
- The `memory` switch is live.
- proxy / tools / mcp / chrome / connectors / safe mode stay greyed out.
- The command line shows the real argv:
  `codex -c model_instructions_file="codex/prompts/new.md"`.

**TUI:**
- Main screen: the same rows go back to normal brightness, and the help line drops to
  `codex: /reid and resume are Claude's`.
- Editor: Enter on sign-in or persona opens the engine's own list.
- Enter on a Claude-only field does nothing and says
  `proxy is Claude's. Switch engine to change it.`
  That also covers Astra's review item 7.

**Summary / `reid -l`:** the same shape as a Claude profile:
`codex · engine default · codex login · ChatGPT · persona Nyxie · memory` (a sign-in file shows its name).

## Not in this spec

- Separate ChatGPT accounts per profile. Answered "like Claude": one login, other accounts through
  provider files.
- Resume for Codex (`codex resume <id>`). That's a separate follow-up in the main spec.
- OpenCode (milestone 2).

## Acceptance checks

1. `--dry` for a Codex profile with no sign-in file, persona or memory is identical to today
   (`codex`), and `codex\prompts\` isn't written.
2. Add mode with Nyxie + memory: prompt-input under the generated argv shows Codex's own prompt
   **unchanged** (the same text as with no persona), then the persona, then the memory block. The
   other six items are identical to a plain launch.
3. In replace mode, prompt-input shows the persona where "You are Codex…" was, and
   `<environment_context>` is still there.
4. `sheher.md` + memory (over 32k) launches fine, and the command line stays under 1k characters.
5. A persona containing quotes, backslashes, `\r\n`, emoji and a DEL character comes back exactly
   (written with `newline=""`).
6. The second launch with the same setup uses the cached Codex prompt (no prompt-input run). A
   changed model or Codex version re-captures it.
7. If capture fails, the inline fallback is used under 24k characters, and the refusal message is
   shown above that.
8. The `[env]` key from a provider file is in the child environment, and appears in neither the argv
   nor the preview.
9. With `codex login`, an `OPENAI_API_KEY` set in Reid's shell isn't in the child environment.
9b. The row shows `codex login · ChatGPT` for Reid's login without freezing the window. With a temp
    `CODEX_HOME` that has no `auth.json`, it shows `not signed in` and the gate refuses with the
    message above.
10. Wrong-engine sign-in file, bad TOML, and `model_instructions_file` / `developer_instructions` in
    extra args are each refused before launch, with the voice-guide message.
11. Switching a profile Claude → Codex resets the model and sign-in, and keeps the persona, mode and
    memory.
12. Claude profiles: `--dry` is byte-identical to the build before this change for all of Reid's
    profiles.
13. Nothing is written under `~/.codex`, and `reid.json` and `reid_state.json` are unchanged by tests.

## As built (2026-11-19)

All 13 acceptance checks pass (46 scripted checks on temp configs, Codex 0.170.0). Check 12: all 19 of
Reid's Claude profiles give byte-identical `--dry` output to the installed build. Check 13: `reid.json`,
`reid_state.json`, `~/.codex/config.toml` and `auth.json` are unchanged by the tests.

Differences from the design above:
- The tag is `CODEX · GREYED FIELDS ARE CLAUDE'S`: shorter, and it fits the header.
- `reid -l` uses the Claude profile's shape (see Screens).
- Replace mode's hint `replace drops Codex's own instructions; add is the safe one.` shows on the TUI
  help line while the profile is in replace mode. The GUI says it in place of `Saved.` when you pick
  replace.
- More guards in extra args, from Astra's review: `-C` in any form (`-CD:\x`, `--cd=x`), and `resume` /
  `fork` as the first argument (`Leave resume out of the extra args: a Codex profile starts a new
  session.`).
- A Claude profile with a `.toml` sign-in file is refused:
  `codex\x.toml is a Codex sign-in file. Pick a Claude one, or use subscription.`
- Switching engine resets the model **and** the sign-in: `Engine is now codex. Model and sign-in reset
  to its defaults.`
- A Claude-only field that's still on stays live in the GUI and the TUI editor so it can be turned off.
  Reid's own `claude` profile still has `proxy: capture` from its Claude days, so it shows
  `Codex can't use the proxy. Turn it off for claude, or pick a Claude profile.` until the proxy is set
  to off. **Superseded 2026-11-23:** the proxy works on Codex (`SPEC-codex-proxy.md`), so that profile
  launches with `capture` as it is.

### Reidcc inside the Codex session (2026-11-19)

> "reidcc codex launch doesn't have reidcc" (Reid, 2026-11-19)

Asked which parts, Reid picked all four: persona + memory, a way back to the TUI, the Reidcc statusline,
the Reidcc tab title.
- **Way back:** Codex has no `/reid` (custom slash commands would need files in `~/.codex`). Quitting Codex
  (`/quit`, Ctrl+C) drops you back into the Reidcc TUI with `Back from Codex.`, or
  `Codex ended with code <n>. See the output above.` This works from the TUI and from `reid <profile>`
  (what the GUI's `open gate` runs), but not when extra args are given on the command line or there's no
  terminal. The banner reads `REIDCC · <profile> · codex · /quit comes back here`, and the TUI help line
  reads `codex: /quit comes back here · resume is Claude's`.
- **Statusline:** Codex's status line only takes its own items. Reidcc passes
  `-c tui.status_line=["model-with-reasoning","current-dir","context-used","five-hour-limit","weekly-limit"]`,
  which shows `GPT-6.2-Sol high · ~ · Context 0% used · 5h 100% left · weekly 90% left`. It can't show
  PROFILE / PERSONA. `"statusline": false` drops it. A `-c tui.status_line=…` of your own in extra args
  comes later on the command line and wins. Like Claude's statusline, it's left out of the command preview.
- **Tab title:** `REIDCC · codex · <profile>` while Codex runs (`-c tui.terminal_title=[]` turns Codex's own
  title off), then `Reidcc` again.
- **Persona + memory:** already built. Reid's `claude` profile is still blocked by its leftover
  `proxy: capture` until the proxy is set to off.
- **Cost, measured:** with any `-c` on its command line, Codex 0.170.0 runs "without the shared background
  server" (embedded mode) and lists that as a startup warning (`2 warnings` instead of `1`; the other is
  the PowerShell shell-snapshot warning that bare Codex shows too). Persona, memory and provider files
  already needed `-c`; the status line and title now make every Reidcc Codex launch embedded.
