# Add Codex and OpenCode to Reidcc profiles

Milestone 1 (Codex) **BUILT 2026-11-19** · milestone 2 (OpenCode) proposed · revised 2026-11-18

Since then (2026-11-23): Codex got its proxy (`SPEC-codex-proxy.md`), so only tools, mcp and the switches
stay Claude's. OpenCode is still not started; Reid's Discord poll spelled OPENCODE and the CLI research
(`research/agent-clis-2026-11-23.md`) found people pick it for any model, LSP feedback and server mode,
which makes it the next engine ahead of agy (`SPEC-agent-cli.md`).

A profile chooses which coding tool Reidcc starts. The launcher flow stays **folder → profile → open gate**. The first milestone is a Codex session running in the folder the user picked. OpenCode follows through the same launch path.

> "in vision(E:\reidcc\vision) let's make a spec on makeing this tool work for codex and opencode" (Reid, 2026-11-17)

> "i wanted to add a engine right not remakeing the hole app" (Reid, 2026-11-18, to Codex, which then cut this spec down)

## Read this first: the vision this must keep

Reid, 2026-11-18: "other models are not seeing the vision like you are". This section is here so
whoever builds from this spec (Claude, Codex or anyone else) builds Reidcc, not just a launcher.
Every rule comes from `vision\`; read those docs before changing a screen.

- **What Reidcc is: "You sit down. It already knows you. You build."** (design doc §0). The
  persona and long-term memory are the product, not a feature. A Codex session without them is a
  plain Codex session in a nice frame. That's acceptable for the first milestone only; see finding 5.
- **One screen, nothing hidden.** Reid: "if it's supposed to be simple to use, why are we hiding in
  settings?" The engine is one more row on the existing screen, directly above `model`. No engine
  page, no settings view, no wizard. Fields an engine can't use yet stay **visible**, shown disabled
  with the reason beside them (design doc, "Multi-engine direction"), never removed from the form.
- **Add an engine, don't remake the app.** Reid: "i wanted to add a engine right not remakeing the
  hole app". One `engine` check where the command is built; everything else (folder, profiles,
  gate, terminal launch) is reused as is.
- **The gate is the same for every engine** (`SPEC-gate.md`): hover ghost, doors, pull-out card.
  Only the card's title changes to name the engine (`codex · main`).
- **GUI and TUI move together.** Everything here lands in both. Reid wants the TUI to end up the
  nicer of the two (`SPEC-tui.md`).
- **Words and colours come from the docs:** labels and errors from `reidcc-voice.md` (an error says
  what happened and what to do), colours from `reidcc-palette.md` (one emerald signal: ready).
- **Docs only claim what's built.** When a milestone ships, move its line in palette §5 from
  "To do" to "Done <date>", with Reid's words.

## Profile selection

Add one optional field to a profile in `reid.json`. The supported values are `claude`, `codex`, and, once its launcher is ready, `opencode`. A missing field means `claude`. An unknown value produces an inline error naming the engine.

For example, these entries belong inside the existing `profiles` object:

```json
{
  "my-codex": { "engine": "codex" },
  "my-opencode": { "engine": "opencode" }
}
```

Profile names remain user-defined. Existing profiles and the selected default need no migration. A new Codex or OpenCode profile uses the engine's default model and native sign-in.

## First milestone — open Codex

1. Put an `engine` selector directly above `model` in the GUI and TUI profile editors. Offer each engine once its launch path works. Keep the existing folder picker, profile list, command preview and gate.
2. At the existing command-building step in `reid.py`, read the profile's engine. For Claude, call the existing builder. For Codex, use a small function that resolves the native executable and returns its argument list. The minimal Codex command is the executable itself, with the selected folder passed as the child's working directory.
3. Use that same command builder for readiness, preview, dry run and launch. Show the engine name in the preview and gate card. If the executable is missing, show the existing inline error treatment and identify which tool to install or put on PATH.
4. Reuse the current terminal launch, process wait and console restoration. Apply Claude's session flags, status line, settings files and proxy setup only on the Claude path. A clean Codex profile should open directly into Codex's interactive session.
5. Keep the profile editor honest about supported fields. Start with the engine default model, and pass an explicit model through the engine's supported model option. Switching engines should clear an incompatible model selection. Preserve saved persona, memory and other profile settings when editing. If a requested feature has no mapping for that engine yet, identify it before launch so the user can clear it or choose another profile.

## Second milestone — open OpenCode

Add a second small command builder for the native OpenCode executable. Start its standard interactive interface with the selected folder as the working directory. Use the same profile field, selector, preview and missing-tool handling as Codex. Verify the installed executable accepts the chosen model option before enabling it in the editor.

## Session behavior

Opening a Claude profile keeps the existing Claude resume and return behavior. Opening Codex or OpenCode starts a new native session. For those profiles, keep Reidcc's `resume` control disabled with a short explanation and omit the Claude `/reid` hint. Exiting the native tool follows the existing launcher's normal exit path. A Codex or OpenCode launch must preserve the saved Claude resume record.

Engine-specific resume, persona and memory mappings, OpenCode mini, and custom return shortcuts are possible follow-ups. The engine addition uses the existing launcher and state file. It requires neither a new database nor a session-manager rewrite.

## Acceptance checks

- An existing profile without `engine` builds the same Claude command and retains its resume behavior.
- Pick a folder with spaces, select a Codex profile, and press `open gate`. Exactly one interactive Codex session opens in that folder. Its preview names Codex and its arguments contain only the options intended for Codex.
- `reid my-codex` opens Codex from the terminal's current folder. `reid --dry my-codex` shows the corresponding command without starting a session.
- Remove the executable from a test PATH and confirm the launcher names the missing engine. Try an unsupported profile setting and confirm the user sees which field needs attention.
- Start and exit a new-engine session, then select a Claude profile and verify the previous Claude session can still be resumed.
- The gate card reads `codex · <profile>` for a Codex profile (finding 1).
- After a Codex launch, `reid_state.json`'s `last` still names the previous Claude session, and the folder is at the top of the recent list (finding 3).
- A folder whose name contains `&`, `%` or `^` opens Codex in that folder (finding 4).
- The gate card reads `codex · <profile>` for a Codex profile (finding 1).
- After a Codex launch, `reid_state.json`'s `last` still names the previous Claude session, and the folder is at the top of the recent list (finding 3).
- A folder whose name contains `&`, `%` or `^` opens Codex in that folder (finding 4).
- Repeat the launch checks with OpenCode for the second milestone. Check the packaged GUI and terminal launcher as well as the Python source entry points before marking each engine built.

## Found in review (Claude, 2026-11-18)

Checked against `reid.py` and `reid_gui.py` as they are today. Each one is something the steps above
imply but don't say, and would be easy to miss.

1. **The gate card says "claude" no matter what.** `reid_gui.py` builds the card title as
   `"claude · " + name` (in `go`, the `self.gate.open(...)` call). *Why it matters:* a Codex session
   pulled out of the gate under a "claude" label is the first thing Reid would see, and it's wrong.
   *Do:* take the engine from the profile: `engine + " · " + name`.
2. **New profiles start as Claude Opus.** The GUI's `new profile` writes `{"model": "opus"}`.
   *Why:* switch that profile to Codex and Codex is launched with `opus`, a model it doesn't know.
   *Do:* when the engine changes, clear `model` (back to "engine default") unless it belongs to the
   new engine. Step 5 says this in general; this is the concrete case that hits it first.
3. **Every launch overwrites the resume record.** `remember_session` (called from `run_session`)
   sets `state["last"]` and also moves the folder to the top of `recent_dirs`. *Why:* if a Codex
   launch writes `last`, `r resume` / the `resume` button later tries to resume a Codex session id
   with Claude, and the Claude session you meant is lost. *Do:* for Codex and OpenCode, still update
   `recent_dirs` (the folder history is engine-neutral) but leave `last` alone. The TUI's
   `last main2 · 23:09 r resumes it` row then keeps pointing at the Claude session.
4. **Launch the real exe, not the npm shim.** On Reid's machine `codex` and `opencode` are npm
   shims (`codex.cmd` / `codex.ps1`; there is also an `opencode2`). The real Codex binary is
   `npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe`.
   *Why:* `find_claude()` already prefers the real `claude.exe` "so args never pass through cmd.exe
   quoting". A `.cmd` shim runs through cmd.exe, which mangles quotes, `%`, `^` and `&` in
   arguments (folder names, model names, later the persona). *Do:* write `find_codex()` the same way:
   the vendored exe next to the shim first, then the shim, then the same "Can't find Codex" error
   pattern. Check OpenCode's install the same way before milestone 2 (and ask Reid which of
   `opencode` / `opencode2` he means).
5. **Persona and memory are listed as follow-ups, but they're the point.** A Codex profile with a
   persona set gets an error before launch. That's honest, and fine for milestone 1. *Why it can't
   stay that way:* "It already knows you" is what Reidcc is (see "Read this first"); without persona
   and memory, a Codex profile has no reason to go through Reidcc. *Do:* make it the next milestone
   after Codex opens. Known trap from the earlier version of this spec (and Codex's own review):
   passing the whole persona + memory on the command line can pass Windows' 32,767-character
   command-line limit. Prefer a file the engine reads, and test with Reid's real persona and memory.
6. **"Unsupported" fields: visible and disabled, not only an error at launch.** Step 5 says to
   "identify it before launch". The design doc's rule is stronger: the control stays on screen,
   disabled, with the reason next to it (for example `proxy · Claude only`). *Why:* hiding or
   silently ignoring a field is the "hiding in settings" problem again, and an error that only shows
   at launch means you find out after pressing `open gate`. *Do:* both: disabled with the reason in
   the form, and the launch-time error if a saved profile still has it set.
7. **The `/reid` hint and the resume control.** The TUI help line (`in a session: /reid comes back
   here`) and the line printed when a session starts are Claude-only (`/reid` is a Claude slash
   command). The Session behavior section already says to omit them; listing where they live:
   `run_session` (the `REIDCC · name · /reid comes back here` banner), `TUI.draw_main` (help line),
   and the GUI `resume` button.

## As built: milestone 1, Codex (2026-11-19)

Reid: "talk with codex in some way and build the spec" (2026-11-19). Claude asked Codex first (a fork of Reid's Codex session, read-only,
so his open window was untouched) about launching `codex.exe` directly, `cwd` vs `-C`, the terminal,
and persona options. Its answers are folded in below, marked *(Codex)*.

- **The field.** `"engine": "codex"` in a profile; missing means `claude`; anything else is an error
  naming it (`Profile x: there's no engine called gemini. Use claude or codex.`).
- **GUI.** The engine box is on the `name` row, at its right, above the persona buttons. That's still
  directly above `model`, and the form keeps its height: as a row of its own it pushed the bottom
  buttons off an 880 px window. **TUI:** an `engine` row under `name` on the main screen and first in
  the editor.
- **Launch.** `find_codex()` returns the native `codex.exe` from npm's platform package
  (`@openai/codex-win32-x64`), and sets the two variables npm's `codex.js` sets
  (`CODEX_MANAGED_PACKAGE_ROOT`, `CODEX_MANAGED_BY_NPM=1`). No `.cmd` fallback *(Codex)*: batch files
  re-parse arguments through cmd.exe. A standalone `codex.exe` on PATH is the last resort. The command
  is `codex [-m model] [extra args]`, run with the picked folder as its working directory.
  `-C` / `--cd` in extra args is refused *(Codex)*: the folder picker owns the workspace.
- **Claude-only fields** (sign-in file, persona, memory, proxy, tools, mcp, safe mode, chrome off,
  connectors off, settings_json): stay on screen, greyed out while off, with the tag
  `CODEX · CLAUDE-ONLY FIELDS GREYED OUT`. One that's still on stays live so you can turn it off, and
  the command line shows `Codex can't use a persona and memory yet. Turn them off for <profile>, or pick
  a Claude profile.` in oxide; the gate won't open. Off values don't block *(Codex)*.
  **Superseded 2026-11-19** by `SPEC-codex-signin-persona.md`: sign-in, persona and memory now work on
  Codex, the tag is `CODEX · GREYED FIELDS ARE CLAUDE'S`, and the message names the field
  (`Codex can't use the proxy. Turn it off for <profile>, or pick a Claude profile.`).
  **Superseded 2026-11-23** by `SPEC-codex-proxy.md`: the proxy works on Codex; the message now names
  the fields left (`Codex can't use a tools limit. ...`).
- **Model.** Switching engine resets the model to the new engine's default (finding 2). Each engine's
  model list is its own: Claude's names, or models other Codex profiles use. A Claude name on a Codex
  profile is refused: `opus is a Claude model. Clear the model to use Codex's default, or type a Codex model.`
- **Resume.** Refused for Codex before anything starts, in the GUI, the TUI and `reid --resume`:
  `Resume is for Claude profiles for now.` (+ how to start a new one). The GUI's `resume` button is dimmed
  for a Codex profile. A Codex launch keeps `last` and still puts the folder on top of the recent list
  (finding 3).
- **Labels.** The gate card reads `codex · <profile>` (finding 1). The start line reads
  `REIDCC · <profile> · codex` (no `/reid`), and the TUI help line becomes
  `codex: a new session each time · resume and /reid are Claude's`. `reid -l` / summaries start with `codex`.
- **Verified:** 15 backend checks (exe found, wrapper env, commands, every refusal, previews, resume,
  state file); the Claude commands for Reid's first six profiles are byte-identical to the previous
  build's `--dry`; the GUI on a temp copy of reid.json (engine box, greyed fields, tag, switching
  clears `opus`, resume refused); the TUI screen; and a real launch through `run_session` in a
  Windows Terminal window, in a folder named `reid codex & 100% test`: Codex 0.170.0 opened there.
  `reid.json` and `reid_state.json` were byte-identical after every test.
- **Not verified yet:** quitting Codex normally (the test window was closed instead) and Ctrl+C inside
  it; Reid opening it from his own Reidcc. The build is staged in `build\dist\app`; it installs when
  Reidcc is closed and `build\build.ps1` runs.
- **Next:** finding 5, persona and memory for Codex. *(Codex)*: `model_instructions_file` takes a file
  but **replaces** Codex's built-in instructions; `developer_instructions` is inline text (the
  command-line limit again); `AGENTS.md` would change every launch in that folder. There's no documented
  key in 0.170.0 to add a file for one launch. **Decided 2026-11-19** in `vision\Spec\SPEC-codex-signin-persona.md`:
  add mode = Codex's own prompt (captured with `codex debug prompt-input`) + persona + memory, in a
  `model_instructions_file` kept in the Reidcc folder. Verified to give Codex's prompt unchanged plus
  the persona. Not built yet.

## Milestone 2, researched: OpenCode 2.3.0 (2026-11-19)

Reid: "Opencode?" (2026-11-19). These facts were checked on this machine. Every test ran with
`--standalone` (a private server), so Reid's running OpenCode (its background service) was never
touched. Not built.

**Install.** `opencode` and `opencode2` are the **same program**: both npm shims run
`%APPDATA%\npm\node_modules\@opencode\cli\bin\opencode.exe` (`@opencode/cli` 2.3.0, a native exe with
no Node wrapper). So the old question "which one" is answered: either. `find_opencode()` returns that
exe, falling back to `opencode.exe` on PATH. It needs no extra environment, unlike Codex.

**Launch.** `opencode.exe --standalone`, run with the picked folder as its working directory.
- **`--standalone` is required.** By default OpenCode attaches to a shared background service that is
  already running with its own config. A profile's model, persona and sign-in are passed through
  environment variables, and only a private server reads them. Whether the shared service would pick
  them up is not verified, so it isn't relied on.
- The full screen (`opencode`) has **no `-m`**: the model goes in config (see below). `opencode mini`
  does take `-m provider/model`. That's the "OpenCode mini" follow-up.
- A trailing `[directory]` argument exists, but the folder picker owns the folder. As with Codex's
  `-C`, a directory in extra args is refused.

**Per-launch config (verified with `opencode debug config --standalone`).** Two environment
variables each add a config layer **over** Reid's `~/.config/opencode/opencode.json`, without
changing it:
- `OPENCODE_CONFIG=<path>` takes a JSON file.
- `OPENCODE_CONFIG_CONTENT=<json>` takes JSON inline.

Both are used:

| Profile field | How it reaches OpenCode |
|---|---|
| model | `"model": "provider/model"` in `OPENCODE_CONFIG_CONTENT` (verified to load) |
| sign-in | The default is **OpenCode's own setup** ( Reid's `opencode.json` providers and `opencode auth`). Or a provider file `opencode\<name>.json` (an OpenCode config fragment: `provider` / `model`), passed as `OPENCODE_CONFIG`. Reidcc never copies it, so keys stay in that one file, the same way Claude's `json\*.json` works. |
| persona, add mode | `"instructions": ["<Reidcc>/opencode/prompts/<profile>.md"]` (verified to load). That file is persona + memory block, rewritten every launch, kept in the Reidcc folder. |
| persona, replace mode | `"agent": {"reidcc": {"mode": "primary", "prompt": "{file:<that file>}"}}` + `"default_agent": "reidcc"`. Verified: the agent loads with the persona as its `system`. Still **to verify at build**: that `default_agent` makes it the starting agent, and that its `system` replaces OpenCode's own prompt rather than adding to it. The key is `agent` (singular); `agents` is ignored. |
| memory | Same file and text as Claude and Codex, in that prompt file. No extra folder access, like the Claude side. |

This follows Reid's three answers for Codex ("1. In the Reidcc application folder 2.just like the
Claude side 3.um like Claude engine with the idea"):
- generated files live in `E:\reidcc\opencode\prompts\`
- memory and sign-in work like the Claude side
- one OpenCode setup, other accounts through provider files

**Resume (later).** OpenCode has `--continue` and `--session <id>`, so engine-specific resume is
possible. It isn't in milestone 2.

**Screens.**
- Engine box: `claude` / `codex` / `opencode`.
- Gate card: `opencode · <profile>`.
- Model list for OpenCode: the `provider/model` names from `opencode models`, or models other OpenCode
  profiles use, plus `engine default`.
- Claude-only fields stay greyed out with the tag `OPENCODE · PROXY, TOOLS, MCP AND SWITCHES ARE CLAUDE'S`.

**Acceptance (in addition to the list above).**
1. `opencode debug config --standalone` under the generated environment lists the profile layer with
   the model and the prompt file.
2. Reid's background service (and its pids) is untouched by a Reidcc launch.
3. `~/.config/opencode/opencode.json` is byte-identical before and after.
4. A provider file's keys appear in neither the argv, the preview nor `opencode\prompts\`.
5. Claude and Codex `--dry` are unchanged.
