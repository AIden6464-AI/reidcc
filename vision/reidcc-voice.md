# Reidcc — Voice Guide

How Reidcc talks: every label, message, warning and empty state in the app.
Use this when writing any text a user will see. Colors come from `reidcc-palette.md`.

---

## 1. What Reidcc is (say it this way)

**One line:**
> Open a folder. Start coding.

**One sentence:**
> Reidcc is a simple launcher for Claude Code: pick a folder and a profile, and your
> persona, memory and settings are already there.

**Short pitch (README / about screen):**
> Reidcc is a launcher built on Claude Code for people who want things simple. Pick a
> folder and a profile and you're coding in seconds, with your persona, long-term memory
> and settings already set up. Every session shows where it is, which profile is running,
> and how much context and limit you've used. It keeps the essentials and leaves the rest out.

Keep the pitch true: add "which files changed" and "paste screenshots straight in" only
once Reidcc itself shows them.

**Product principle:** *Only the essentials, all in sight.*

> "if it's supposed to be simple to use, why are we hiding in settings?" (Reid, 2026-11-17)

Simple means nothing to hunt for, not fewer things on screen. See "Direction from Reid" in
`reidcc_design_motion_system.md`. The one settings page (not built; "In a settings page", Reid,
2026-11-20) holds only app-wide choices, like where sessions open. A profile's fields never go there.

---

## 2. The feeling

**Calm control.** You sit down, you're coding in seconds, and you always know where you stand.

Every piece of text should leave the user with one of these:

1. **Relief.** Nothing to set up. It's already ready.
2. **Awareness.** You can see what's happening: context, limits, changed files.
3. **Ownership.** It's yours: your persona, your memory, your way of working.

It should never feel like a power tool with 200 switches, a chatty assistant, or a toy.

---

## 3. Voice rules

| Rule | Do | Don't |
|---|---|---|
| Short | `memory on` | `Your memory has been successfully loaded!` |
| Declarative | `2 files changed.` | `It looks like a couple of files may have changed.` |
| Numbers over adjectives | `context 82%` | `context is getting pretty full` |
| Plain words | `pick folder` | `Initialize workspace directory` |
| Calm, slightly dry | `Limit reached. Resets in 2h 14m.` | `Oh no! You've hit your limit 😢` |
| Say what to do next | `Context 90%. Start a new session to keep speed up.` | `Warning: context high.` |
| No hype | `Ready.` | `Let's build something amazing!` |

Never use: emoji, exclamation marks, "magic", "awesome", "oops", "simply", "just", "please wait".

---

## 4. Formatting

- **Case:** UI labels and buttons are lowercase (`pick folder`, `open gate`, `open recent ▾`).
  Sentences in messages use normal sentence case. Small system tags may be UPPERCASE
  (`PROFILE · MAIN`, `PERSONA · KURE`, `MEMORY · ON`).
- **Numbers:** always digits. `3 files`, `42%`, `2h 14m`, `84k / 200k`.
- **Time:** relative and short. `2m ago`, `yesterday`, `resets in 3h 12m`.
- **Separators:** middle dot ` · ` between related facts. Arrow ` → ` for flow or cause.
- **Glyphs allowed:** `● → ↳ ▾ … ↵ + −`. Nothing else decorative.
- **Paths:** shown as written, shortened with `~` (`~/projects/kiln`).
- **Periods:** none on labels and buttons. Yes on full sentences.

### Text color
| Text | Token |
|---|---|
| Titles, labels in use, file names, button text | `#D6D0C8` (bone, primary) |
| Subtitles, explanations, system tags | `#9F978E` (bone, secondary) |
| Separators, timestamps, hints (`folder → profile → open gate`) | `#746F69` (bone, muted) |
| The `●` ready dot, `+12` | `#00C463` (emerald) |
| Context 75–89%, loading | `#C99A45` (bronze) |
| Context 90%+, limit reached, `−4`, errors | `#C0584B` (oxide) |

---

## 5. Words we use

| Use | Not |
|---|---|
| folder | workspace, directory, repo (in UI) |
| profile | config, preset, environment |
| persona | character, personality, agent |
| memory | knowledge base, brain |
| session | conversation, thread, chat |
| context | tokens (in labels; fine in detail text) |
| limit | quota, cap, rate limit |
| changed | modified, diffed, touched |
| paste | upload, attach |
| open gate | go, launch, start session, initialize |

**Profile, persona and memory are three different things. Never mix their tags:**
- `profile`: a named setup in `reid.json` (model, sign-in, persona, memory, switches). Tag `PROFILE · MAIN`.
- `persona`: the prompt file a profile uses, if any. Tag `PERSONA · KURE`. No persona, no tag.
- `memory`: `reidcc_memory.md`, added to the session when the profile has memory on. Tag `MEMORY · ON`.
- `ACA` is the separate memory server. Reidcc doesn't read it yet, so no UI text may claim
  ACA counts or saves (`ACA · 214`, `Remembered: …`) until it does.

**The start button is `open gate`.** Reid, 2026-11-17: "Go ---> Open gate". The session is
what's behind the gate; the launcher opens it. Plain `go` is retired as a label.

### Proposed multi-engine words (not built)

> "in vision(E:\reidcc\vision) let's make a spec on makeing this tool work for codex and opencode" (Reid, 2026-11-17)

Codex's strings are built and listed in the catalog below (2026-11-19). Still proposed: OpenCode
(`opencode` engine, `/reid` as its return shortcut; see `vision\Spec\SPEC-codex-opencode.md`).

> "can we spec [...] for codex the signin and persona's" (Reid, 2026-11-19)

Sign-in, persona and memory for Codex are built (2026-11-19, `vision\Spec\SPEC-codex-signin-persona.md`);
their strings are in the profile panel catalog below.

> "ok spec doc proxys for codex that fit the idea of the claude" (Reid, 2026-11-19)

Proposed for the Codex proxy (`vision\Spec\SPEC-codex-proxy.md`; not current UI claims):

| Situation | Proposed |
|---|---|
| Proxy list on Codex | `off` `slim` `ultra` `capture` `slim+capture` `ultra+capture` |
| optimize on Codex | `optimize is Claude's. Pick slim, ultra or capture for Codex.` |
| Engine switched with optimize on | `Engine is now codex. Model and sign-in reset to its defaults; optimize is Claude's, so the proxy is off.` |
| Launch banner | `proxy capture on 127.0.0.1:<port> · log proxy/logs/<profile>.log` (same as Claude) |

> "well i want the rust part one spec and the ideas in one spec and apart of the vision" (Reid, 2026-11-19)

Proposed words for vision version 1 (`vision\SPEC-vision-v1.md`; not current UI claims):

| Situation | Proposed |
|---|---|
| Window sizes | `full` · `medium` · `mini pod` (all three built in the Rust app, 2026-11-20). Each pod slot reads `CL  main  ●  01:42 · ctx 42% · lim 61%` (mark `CL` / `CX` / `OC`, profile, dot, elapsed, then Claude's own usage; a failed one adds `code <n>`); an empty pod says `No sessions running.` (Reid: "For the mini pod I can have more on it", 2026-11-21) |
| One key opens a profile | `combo`. Built in the Rust app: the medium size's list labels are `sessions` and `combos`, and an empty list says `No sessions running.` |
| The window the gate opens into | a `session window` by default; Windows Terminal is the other choice (`Session open in Windows Terminal.`) |
| Joining windows | `snap` / `unsnap` |
| Shrunk session | `headless`; its line is the `run strip` |
| Run strip states | `running` · `waiting for you` (oxide) · `finished` · `failed · exit <n>` |
| Saved layout | `rig` |

---

## 6. String catalog

### Launcher
| Spot | Text |
|---|---|
| Title | `Open a folder. Start coding.` |
| Subtitle | `Pick a project and a profile. Your persona, memory and settings are already there.` |
| Status tag | `● ready · persona + memory` (shows only what the selected profile has: `● ready · persona`, `● ready · memory`, `● ready`) |
| Primary button | `pick folder` |
| Secondary button | `open recent ▾` |
| Flow hint | `folder → profile → open gate` (full size only; semi-mini medium drops it and the `folder` label, Reid: "The medium is to medium can we make it simi-mini", 2026-11-21) |
| Profile picker | `profile` label + `kure ▾` |
| Profile tags | `PERSONA · KURE · MEMORY · ON` |
| Start button | `open gate` |
| Resume | `resume` |
| Recent header | `recent` |
| Recent item meta | `2h ago · 4 files changed` / `3d ago · clean` (not shown yet: needs per-folder session history) |
| No recent projects | `No projects yet. Pick a folder to start.` |
| Nothing to resume | `Nothing to resume yet.` |
| Gate opening (corner tag) | `REIDCC · OPENING` → `REIDCC · READY` (READY only once the session window exists) |
| Gate's opening line (on its dark last frame, only while the window isn't up yet) | `<engine> · <profile> · opening…` (`claude · main · opening…`, `codex · main · opening…`) over the folder path |
| Session window late (8 s) | `The session window didn't appear. It may still be starting.` |
| Session opened | `Session open in Windows Terminal.` |
| Session didn't open | `Couldn't open the session (reason). Check that Windows Terminal or Claude Code still runs.` |

### Profile panel (on the launcher, always visible)
| Spot | Text |
|---|---|
| List header | `profiles` |
| Default marker | `●` after the default profile's name |
| Fields | `name` `engine` `model` `sign-in` `persona` `persona mode` `memory` `proxy` `tools` `mcp` `chrome` `connectors` `safe mode` `extra args` |
| Engine | `claude` / `codex`; model shows `engine default` for Codex with no model |
| Codex profile tag | `CODEX · GREYED FIELDS ARE CLAUDE'S` |
| Engine switched | `Engine is now codex. Model and sign-in reset to its defaults.` |
| Claude-only field on | `Codex can't use the proxy. Turn it off for <profile>, or pick a Claude profile.` (also `a tools limit`, `an MCP choice`, `safe mode`, `chrome off`, `connectors off`, `settings_json`) |
| Claude-only field in the TUI editor | `proxy is Claude's. Switch engine to change it.` |
| Sign-in default on Codex | `codex login · ChatGPT` / `· API key` / `· signed in` / `· not signed in` (oxide) / `· checking…` |
| Codex not signed in | `Codex isn't signed in. Run codex login in a terminal, then try again.` |
| Persona mode on Codex | `add to Codex's prompt` / `replace Codex's prompt` |
| Replace mode on Codex | `replace drops Codex's own instructions; add is the safe one.` (TUI help line; GUI message when picked) |
| Codex help line (TUI) | `codex: /quit comes back here · resume is Claude's` |
| Codex session banner | `REIDCC · <profile> · codex · /quit comes back here` |
| Codex tab title | `REIDCC · codex · <profile>` while Codex runs, then `Reidcc` |
| Back from Codex (TUI) | `Back from Codex.` / `Codex ended with code <n>. See the output above.` |
| Claude sign-in file on Codex | `json\qwen.json is a Claude sign-in file. Pick a Codex one, or use codex login.` |
| Codex sign-in file on Claude | `codex\lms.toml is a Codex sign-in file. Pick a Claude one, or use subscription.` |
| Bad provider file | `codex\x.toml isn't valid TOML (reason). Fix it, then try again.` |
| Codex's prompt unreadable | `Couldn't read Codex's own prompt to add the persona to. Use replace mode, or update Reidcc.` |
| Persona override in extra args | `Leave model_instructions_file out of the extra args: it would replace the persona.` (or `developer_instructions`) |
| Provider override in extra args | `Leave model_provider out of the extra args: the sign-in file sets it.` |
| resume / fork in extra args | `Leave resume out of the extra args: a Codex profile starts a new session.` |
| Claude model on Codex | `opus is a Claude model. Clear the model to use Codex's default, or type a Codex model.` |
| -C in extra args | `Leave -C / --cd out of the extra args: Codex opens in the folder you picked.` |
| Codex missing | `Can't find Codex. Install it (npm install -g @openai/codex), then try again.` |
| Resume on Codex | `Resume is for Claude profiles for now. open gate starts a new Codex session.` (TUI: `↵ opens a new Codex session.`) |
| Unknown engine | `Profile <name>: there's no engine called <x>. Use claude or codex.` |
| Persona mode | `add to Claude Code's prompt` / `replace Claude Code's prompt` |
| Profile actions | `new profile` `duplicate` `delete` `make default` |
| Files | `open memory` `open reid.json` `open persona` `browse` |
| Delete confirm (inline) | `Delete profile red?` + `delete` / `keep` |
| Name taken | `A profile named red already exists.` |
| Last profile | `Can't delete the last profile.` |
| Saved | `Saved.` |
| Command preview header | `command` |

### Starting a session
| Spot | Text |
|---|---|
| Loading | `loading persona…` → `loading memory…` → `ready` (only the steps the profile has) |
| Ready | `Ready. Persona and memory loaded.` |
| Ready (detail) | `ready in 2.1s · context 0%` |
| Folder not found | `Can't find that folder. It may have moved.` + `pick again` |
| Profile missing | `That profile is gone. Using default.` |

### Terminal (statusline in every reid session)
| Spot | Text |
|---|---|
| Line | `~/kiln · PROFILE · MAIN · PERSONA · KURE   context 42% · limit 61%` |
| No limit data | the `limit` part is left out |
| Banner when a session starts | `REIDCC · main · /reid comes back here` |

### Terminal (reid TUI)
| Spot | Text |
|---|---|
| Title | `Open a folder. Start coding.` / `Pick a project and a profile. Your persona, memory and settings are already there.` (same as the GUI) |
| Folder row | `folder  ~/folder` … `w pick folder` |
| Profile panel | `profiles` list; the selected profile's name + `PERSONA · NYXIE · MEMORY · ON`, then the GUI's field rows, `command` |
| Keys | `↵ open gate · r resume · e edit · n new · x delete · d default · m memory · q quit` / `in a session: /reid comes back here` |
| Footer | `folder → profile → open gate` … `● ready · persona + memory` (`● not ready` in oxide, with the reason where the command goes) |
| Gate (corner tag) | `REIDCC · OPENING` (bronze) |
| Back from a session | `Back from the session. r resumes it.` |
| Session ended with an error | `Session ended with code 1. See the output above.` |
| `/reid` | `Back to Reidcc.` |
| `/reid` outside reid | `This session wasn't started by Reidcc, so there's nothing to go back to. Run reid to open it.` |
| Default set | `Default is now red.` |

### Session — chat
| Spot | Text |
|---|---|
| Input placeholder | `> type, or paste a screenshot` |
| Pasted image tag | `pasted · screenshot.png` |
| Paste failed | `Couldn't read that image. Try pasting again.` |
| Send | `↵` (aria-label: `send`) |
| Overflow menu | `…` (aria-label: `more`) |
| Stop | `stop` |
| Stopped | `Stopped.` |
| Close session | `close session` |

### Meters (always visible)
| Spot | Text |
|---|---|
| Context label | `context 42%` |
| Context detail | `84k / 200k` |
| Context 75% | `Context 75%. Fine for now.` |
| Context 90% | `Context 90%. Start a new session to keep speed up.` + `new session` |
| Context full | `Context full. Older messages are being compacted.` |
| Limit label | `limit 61%` |
| Limit detail | `resets in 3h 12m` |
| Limit 90% | `Limit 90%. About 20 messages left until reset.` |
| Limit reached | `Limit reached. Resets in 2h 14m.` |

### Changed files
| Spot | Text |
|---|---|
| Header | `changed · 4` |
| Row | `Nav.tsx  +12 −4` |
| None | `No changes yet.` |
| After a task | `Done. 2 files changed.` |
| Open diff | `view diff` |
| Undo | `undo changes` → confirm: `Undo changes to 2 files?` + `undo` / `keep` |

### Profile, persona & memory
| Spot | Text |
|---|---|
| Profile tag | `PROFILE · MAIN` |
| Persona tag | `PERSONA · KURE` |
| Memory tag | `MEMORY · ON` |
| Memory off | `Memory off for this session.` |
| Saved to memory | `Remembered: prefers Tailwind.` (only once Reidcc reads ACA; not today) |

### Errors (general shape)
Say **what happened**, then **what to do**. No blame, no apology spiral. Errors and
confirmations appear inline in the window, never as a system popup.

| Situation | Text |
|---|---|
| Claude Code not found | `Can't find Claude Code. If it's updating, this clears in a moment; otherwise install it.` + `try again`. The window re-checks every 3s and clears the error once Claude Code is back. Reidcc also rebuilds PATH from the registry at start, because Explorer can hand apps a stale PATH without npm (seen 2026-11-17). |
| Not signed in | `Not signed in to Claude. Sign in to start.` + `sign in` |
| Network down | `No connection. Your session is saved.` |
| Profile file broken | `reid.json has an error. Fix it, then try again.` + `open reid.json` |
| Unknown error | `Something broke. Your files are safe.` + `copy details` |

### Settings / about
| Spot | Text |
|---|---|
| Settings title | `settings` |
| About footer | `Reidcc · built on Claude Code · only the essentials` |
| Reset | `reset settings` → confirm: `Reset all settings? Profiles and memory stay.` |

---

## 7. Tests for new text

Before shipping any new line, check:

1. **Feeling:** does it give relief, awareness, or ownership?
2. **Length:** can it lose a word?
3. **Truth:** does it promise only what the app actually does?
4. **Next step:** if something went wrong, does it say what to do?
5. **Essentials:** if the text exists to explain an extra feature, should the feature exist?
